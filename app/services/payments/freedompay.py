"""Freedom Pay (бывший PayBox) — Казахстан, Узбекистан, Кыргызстан, Россия.

The one gateway on this list that takes tenge, sum, som and roubles from the
same merchant account, which is why it is here: for a seller in Kazakhstan
it is usually the shortest path to accepting local cards.

Protocol, all of it: form-encoded POST to `init_payment.php`, XML back with
`pg_redirect_url`. Every request and every callback carries `pg_sig` —

    md5( script_name ; values of all other params sorted by key ; secret )

joined by semicolons. `script_name` is the last path segment of the URL
being signed, which for the callback is *our* address, not theirs — so the
callback signs against "freedompay", the tail of `/webhook/pay/freedompay`.

Written against the published PayBox signature implementation
(github.com/boomfly/meteor-paybox, src/signature.coffee) rather than from
memory.
"""

from __future__ import annotations

import hashlib
import secrets
import uuid
import xml.etree.ElementTree as ET

import httpx

from app.config import get_settings
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

_BASE = "https://api.freedompay.money"
#: The tail of our own callback address — what Freedom Pay signs its
#: notification with. Must match the route in `payments.py`.
_CALLBACK_SCRIPT = "freedompay"


def _sign(script: str, params: dict[str, str], secret: str) -> str:
    """md5 over script name, every value sorted by key, and the secret."""
    parts = [script]
    parts += [str(params[key]) for key in sorted(params) if key != "pg_sig"]
    parts.append(secret)
    return hashlib.md5(";".join(parts).encode()).hexdigest()


class FreedomPayProvider(ProviderDefaults):
    slug = "freedompay"
    title = "Freedom Pay"
    hint = (
        "Merchant ID и секретный ключ — в кабинете Freedom Pay, раздел «Настройки магазина». "
        "Там же в поле «Post-запрос при результате платежа» укажи адрес, который мы покажем ниже. "
        "Принимает карты Казахстана, Узбекистана, Кыргызстана и России."
    )
    currencies = ("KZT", "UZS", "KGS", "RUB", "USD", "EUR")
    credential_fields = (
        CredentialField("merchant_id", "Merchant ID", "номер магазина из кабинета", secret=False),
        CredentialField("secret_key", "Секретный ключ", "секретный ключ мерчанта"),
    )

    @staticmethod
    def _keys(credentials: dict[str, str]) -> tuple[str, str]:
        merchant = (credentials.get("merchant_id") or "").strip()
        secret = (credentials.get("secret_key") or "").strip()
        if not merchant or not secret:
            raise ProviderError("Freedom Pay: не заполнены Merchant ID или секретный ключ")
        return merchant, secret

    async def create_checkout(self, request: CheckoutRequest) -> Checkout:
        merchant, secret = self._keys(request.credentials)
        base = get_settings().public_base_url.rstrip("/")

        params = {
            "pg_merchant_id": merchant,
            "pg_order_id": str(request.payment_id),
            "pg_amount": minor_to_major(request.amount_minor),
            "pg_currency": request.currency.upper(),
            "pg_description": (request.description or "Оплата")[:255],
            "pg_result_url": f"{base}/webhook/pay/{_CALLBACK_SCRIPT}",
            # Freedom Pay only POSTs the result when told to; without this it
            # would wait for the buyer's browser to come back, and a buyer
            # who closes the tab would never be delivered to.
            "pg_request_method": "POST",
            "pg_success_url": request.return_url,
            "pg_failure_url": request.return_url,
            "pg_language": "ru",
            # Any unique value; it only exists to make the signature differ
            # between two otherwise identical requests.
            "pg_salt": secrets.token_hex(8),
        }
        if request.is_test:
            params["pg_testing_mode"] = "1"
        params["pg_sig"] = _sign("init_payment.php", params, secret)

        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(f"{_BASE}/init_payment.php", data=params)
        if response.status_code >= 400:
            raise ProviderError(f"Freedom Pay: HTTP {response.status_code}")

        payload = _parse_xml(response.text)
        if (payload.get("pg_status") or "").lower() == "error":
            detail = payload.get("pg_error_description") or payload.get("pg_error_code") or "отказ"
            raise ProviderError(f"Freedom Pay: {detail}")
        url = payload.get("pg_redirect_url")
        if not url:
            raise ProviderError("Freedom Pay: ответ без ссылки на оплату")

        return Checkout(url=url, provider_payment_id=payload.get("pg_payment_id"))

    def locate_payment(self, *, headers: dict[str, str], raw_body: bytes, form: dict[str, str]) -> PaymentRef:
        try:
            return PaymentRef(payment_id=uuid.UUID((form.get("pg_order_id") or "").strip()))
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
    ) -> WebhookResult:
        _merchant, secret = self._keys(credentials)

        received = (form.get("pg_sig") or "").strip().lower()
        if not received or received != _sign(_CALLBACK_SCRIPT, form, secret):
            raise ProviderError("Freedom Pay: подпись уведомления не совпала")

        remote_id = (form.get("pg_payment_id") or "").strip() or None
        result = (form.get("pg_result") or "").strip()
        if result != "1":
            # 0 means the payment failed; anything else is not a settlement.
            return WebhookResult(
                status=PaymentStatus.failed if result == "0" else PaymentStatus.pending,
                provider_payment_id=remote_id,
                response_body=_ack(secret, "ok"),
                response_content_type="application/xml",
            )

        amount = (form.get("pg_amount") or "").strip()
        try:
            mismatch = abs(float(amount.replace(",", ".")) - amount_minor / 100) > 0.009
        except ValueError:
            mismatch = True
        if mismatch:
            raise ProviderError(f"Freedom Pay: сумма не совпадает (пришло {amount})")

        return WebhookResult(
            status=PaymentStatus.paid,
            provider_payment_id=remote_id,
            # Freedom Pay retries until it gets a signed "ok" back.
            response_body=_ack(secret, "ok"),
            response_content_type="application/xml",
        )


def _ack(secret: str, status: str) -> str:
    """The acknowledgement Freedom Pay wants: an XML response signed the same
    way, with our own script name."""
    params = {"pg_status": status, "pg_salt": secrets.token_hex(8)}
    params["pg_sig"] = _sign(_CALLBACK_SCRIPT, params, secret)
    body = "".join(f"<{key}>{value}</{key}>" for key, value in params.items())
    return f"<?xml version='1.0' encoding='utf-8'?><response>{body}</response>"


def _parse_xml(text: str) -> dict[str, str]:
    try:
        root = ET.fromstring(text)
    except ET.ParseError as exc:
        raise ProviderError("Freedom Pay: непонятный ответ") from exc
    return {child.tag: (child.text or "") for child in root}
