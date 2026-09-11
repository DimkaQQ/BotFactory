"""Click — Узбекистан.

The odd one on this list: Click confirms a payment in *two* calls to the
same address. First `action=0` (Prepare) asks "do you know this order, and
is the amount right?" and expects an id back; then `action=1` (Complete)
says the money is in and repeats that id. Only the second call settles
anything.

Both are signed with md5 over

    click_trans_id + service_id + secret_key + merchant_trans_id
    + merchant_prepare_id + amount + action + sign_time

where `merchant_prepare_id` is empty on Prepare and, on Complete, whatever
we answered with. We answer with the order's own invoice number, so nothing
extra has to be stored between the two calls.

Click also does not use HTTP status codes: every answer is 200 with an
`error` field, so a refusal here is a body, not an exception — see
`error_body`.

Written against the official integration github.com/click-llc/click-
integration-django and the published github.com/Muhammadali-Akbarov/click-
pkg (pay-link shape, signature order, error codes) rather than from memory.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from urllib.parse import urlencode

from app.models.payment import PaymentStatus
from app.services.payments.base import (
    Checkout,
    CheckoutRequest,
    CredentialField,
    PaymentRef,
    ProviderDefaults,
    ProviderError,
    WebhookResult,
    minor_to_major,
)

_CHECKOUT = "https://my.click.uz/services/pay"

_PREPARE = "0"
_COMPLETE = "1"

# Click's own vocabulary for what went wrong. Values are theirs, not ours.
_ERR_OK = 0
_ERR_SIGN = -1
_ERR_ORDER_NOT_FOUND = -5


def _sign(form: dict[str, str], secret: str) -> str:
    parts = [
        form.get("click_trans_id", ""),
        form.get("service_id", ""),
        secret,
        form.get("merchant_trans_id", ""),
        form.get("merchant_prepare_id", "") or "",
        form.get("amount", ""),
        form.get("action", ""),
        form.get("sign_time", ""),
    ]
    return hashlib.md5("".join(str(part) for part in parts).encode()).hexdigest()


def _reply(form: dict[str, str], *, error: int, note: str, prepare_id: str | int | None = None) -> str:
    body: dict[str, object] = {
        "click_trans_id": form.get("click_trans_id", ""),
        "merchant_trans_id": form.get("merchant_trans_id", ""),
        "error": error,
        "error_note": note,
    }
    if prepare_id is not None:
        # Click reads whichever of the two it asked for; sending both keeps
        # one code path for Prepare and Complete.
        body["merchant_prepare_id"] = prepare_id
        body["merchant_confirm_id"] = prepare_id
    return json.dumps(body, ensure_ascii=False)


class ClickProvider(ProviderDefaults):
    slug = "click"
    title = "Click"
    hint = (
        "Service ID, Merchant ID и секретный ключ — в кабинете Click Merchant. Там же в настройках "
        "сервиса укажи один и тот же адрес (мы покажем его ниже) в полях Prepare URL и Complete URL: "
        "Click вызывает его дважды и оба раза мы отвечаем сами."
    )
    currencies = ("UZS",)
    credential_fields = (
        CredentialField("service_id", "Service ID", "номер сервиса из кабинета", secret=False),
        CredentialField("merchant_id", "Merchant ID", "номер мерчанта", secret=False),
        CredentialField("secret_key", "Секретный ключ", "SECRET KEY сервиса"),
    )

    @staticmethod
    def _keys(credentials: dict[str, str]) -> tuple[str, str, str]:
        service_id = (credentials.get("service_id") or "").strip()
        merchant_id = (credentials.get("merchant_id") or "").strip()
        secret = (credentials.get("secret_key") or "").strip()
        if not service_id or not merchant_id or not secret:
            raise ProviderError("Click: не заполнены Service ID, Merchant ID или секретный ключ")
        return service_id, merchant_id, secret

    async def create_checkout(self, request: CheckoutRequest) -> Checkout:
        service_id, merchant_id, _secret = self._keys(request.credentials)
        params = {
            "service_id": service_id,
            "merchant_id": merchant_id,
            "amount": minor_to_major(request.amount_minor),
            # Click echoes this back as merchant_trans_id in both callbacks.
            "transaction_param": str(request.invoice_no),
            "return_url": request.return_url,
        }
        return Checkout(url=f"{_CHECKOUT}?{urlencode(params)}", provider_payment_id=str(request.invoice_no))

    def locate_payment(self, *, headers: dict[str, str], raw_body: bytes, form: dict[str, str]) -> PaymentRef:
        try:
            return PaymentRef(invoice_no=int((form.get("merchant_trans_id") or "").strip()))
        except ValueError:
            return PaymentRef()

    async def verify_webhook(
        self,
        *,
        headers: dict[str, str],
        raw_body: bytes,
        form: dict[str, str],
        credentials: dict[str, str],
        amount_minor: int,
        invoice_no: int,
        payment_id: uuid.UUID,
        provider_payment_id: str | None,
        meta: dict | None = None,
        currency: str = "",
    ) -> WebhookResult:
        service_id, _merchant_id, secret = self._keys(credentials)

        received = (form.get("sign_string") or "").strip().lower()
        if not received or received != _sign(form, secret):
            raise ProviderError("Click: подпись уведомления не совпала")
        if (form.get("service_id") or "").strip() != service_id:
            raise ProviderError("Click: уведомление адресовано другому сервису")

        amount = (form.get("amount") or "").strip()
        try:
            mismatch = abs(float(amount.replace(",", ".")) - amount_minor / 100) > 0.009
        except ValueError:
            mismatch = True
        if mismatch:
            raise ProviderError(f"Click: сумма не совпадает (пришло {amount})")

        action = (form.get("action") or "").strip()
        click_trans_id = (form.get("click_trans_id") or "").strip() or None
        reply = _reply(form, error=_ERR_OK, note="Success", prepare_id=invoice_no)

        if action == _PREPARE:
            # "Yes, this order exists and the amount matches." No money yet.
            return WebhookResult(
                status=PaymentStatus.pending,
                provider_payment_id=click_trans_id,
                response_body=reply,
                response_content_type="application/json",
            )

        if action == _COMPLETE:
            # Click sends `error` < 0 here when the payment was cancelled on
            # its side; that is a failure, not a sale.
            try:
                remote_error = int(form.get("error") or 0)
            except ValueError:
                remote_error = 0
            status = PaymentStatus.paid if remote_error >= 0 else PaymentStatus.failed
            return WebhookResult(
                status=status,
                provider_payment_id=click_trans_id,
                response_body=reply,
                response_content_type="application/json",
            )

        raise ProviderError(f"Click: неизвестное действие {action!r}")

    def error_body(self, *, form: dict[str, str], raw_body: bytes, found: bool) -> tuple[str, str]:
        """What to answer when the request never reached `verify_webhook`.

        Click treats an HTTP error as a delivery problem and retries forever;
        a refusal has to come back as 200 with an `error` code, so the router
        asks the adapter instead of raising.
        """
        if not found:
            return _reply(form, error=_ERR_ORDER_NOT_FOUND, note="Order not found"), "application/json"
        return _reply(form, error=_ERR_SIGN, note="Request rejected"), "application/json"
