"""LiqPay — Украина (ПриватБанк), карты Visa/Mastercard стран СНГ.

Everything LiqPay does is the same two fields: `data`, a base64 of the JSON
request, and `signature`, base64(sha1(private_key + data + private_key)).
That one rule signs the checkout and verifies the callback, which is why
this adapter is short.

Written against the official SDK (github.com/liqpay/sdk-python): the
signature scheme, the parameter list and the `3/checkout/` form action all
come from there rather than from memory. The SDK builds an HTML form and
POSTs to the checkout — so do we, through `/api/pay/redirect/{id}`, instead
of inventing a GET form of the same URL.
"""

from __future__ import annotations

import base64
import hashlib
import json
import uuid

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

_HOST = "https://www.liqpay.ua/api"
_CHECKOUT = f"{_HOST}/3/checkout/"

#: What LiqPay calls a payment that went through. "sandbox" is a test-mode
#: success and only ever appears when we asked for sandbox.
_PAID = {"success", "sandbox"}
_FAILED = {"failure", "error"}


def _sign(private_key: str, data: str) -> str:
    """The whole of LiqPay's authentication, both directions."""
    joined = f"{private_key}{data}{private_key}".encode()
    return base64.b64encode(hashlib.sha1(joined).digest()).decode()


class LiqPayProvider(ProviderDefaults):
    slug = "liqpay"
    title = "LiqPay"
    hint = (
        "public_key и private_key — в кабинете LiqPay, «Настройки → API». Карты Украины и большинства "
        "стран, оплата в гривне, долларе или евро. Адрес для уведомлений (server_url) мы подставляем сами, "
        "в кабинете его указывать не нужно."
    )
    currencies = ("UAH", "USD", "EUR")
    supports_status_check = True
    credential_fields = (
        CredentialField("public_key", "public_key", "начинается с i… или sandbox_i…", secret=False),
        CredentialField("private_key", "private_key", "секретный ключ из того же раздела"),
    )

    @staticmethod
    def _keys(credentials: dict[str, str]) -> tuple[str, str]:
        public = (credentials.get("public_key") or "").strip()
        private = (credentials.get("private_key") or "").strip()
        if not public or not private:
            raise ProviderError("LiqPay: не заполнены public_key или private_key")
        return public, private

    async def create_checkout(self, request: CheckoutRequest) -> Checkout:
        public, private = self._keys(request.credentials)
        base = get_settings().public_base_url.rstrip("/")
        params = {
            "version": "3",
            "action": "pay",
            "public_key": public,
            "amount": minor_to_major(request.amount_minor),
            "currency": request.currency.upper(),
            "description": (request.description or "Оплата")[:250],
            # Our payment id is the order id, so the callback identifies the
            # order without us having to store anything of LiqPay's.
            "order_id": str(request.payment_id),
            "result_url": request.return_url,
            "server_url": f"{base}/webhook/pay/liqpay",
            "language": "ru",
            "sandbox": 1 if request.is_test else 0,
        }
        data = base64.b64encode(json.dumps(params).encode()).decode()
        return Checkout(
            # LiqPay's checkout is a POST, so the "link" we hand the buyer is
            # a page of ours that posts the form for them. Nothing in it is
            # secret — it is exactly what the browser would send anyway.
            url=f"{base}/api/pay/redirect/{request.payment_id}",
            meta={"form_action": _CHECKOUT, "form_fields": {"data": data, "signature": _sign(private, data)}},
        )

    def locate_payment(self, *, headers: dict[str, str], raw_body: bytes, form: dict[str, str]) -> PaymentRef:
        payload = _decode(form.get("data") or "")
        try:
            return PaymentRef(payment_id=uuid.UUID(str(payload.get("order_id"))))
        except (ValueError, AttributeError, TypeError):
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
        _public, private = self._keys(credentials)
        data = (form.get("data") or "").strip()
        received = (form.get("signature") or "").strip()
        if not data or not received:
            raise ProviderError("LiqPay: уведомление без data или signature")
        if received != _sign(private, data):
            raise ProviderError("LiqPay: подпись уведомления не совпала")

        return self._verdict(_decode(data), amount_minor)

    async def check_status(
        self,
        *,
        credentials: dict[str, str],
        amount_minor: int,
        invoice_no: int,
        payment_id: uuid.UUID,
        provider_payment_id: str | None,
        meta: dict,
    ) -> WebhookResult:
        public, private = self._keys(credentials)
        params = {"version": "3", "action": "status", "public_key": public, "order_id": str(payment_id)}
        data = base64.b64encode(json.dumps(params).encode()).decode()

        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(
                f"{_HOST}/request", data={"data": data, "signature": _sign(private, data)}
            )
        if response.status_code >= 400:
            raise ProviderError(f"LiqPay: {response.text[:200]}")
        try:
            payload = response.json()
        except ValueError as exc:
            raise ProviderError("LiqPay: непонятный ответ на запрос статуса") from exc

        # An error from the API is not "not paid" — say so rather than
        # telling the buyer their money is missing.
        if payload.get("result") == "error" or payload.get("status") == "error":
            raise ProviderError(f"LiqPay: {payload.get('err_description') or payload.get('err_code') or 'ошибка'}")
        return self._verdict(payload, amount_minor)

    def _verdict(self, payload: dict, amount_minor: int) -> WebhookResult:
        status = str(payload.get("status") or "").lower()
        remote_id = payload.get("payment_id")
        remote_id = str(remote_id) if remote_id is not None else None

        if status in _PAID:
            amount = payload.get("amount")
            try:
                mismatch = amount is None or abs(float(amount) - amount_minor / 100) > 0.009
            except (TypeError, ValueError):
                mismatch = True
            if mismatch:
                raise ProviderError(f"LiqPay: сумма не совпадает (пришло {amount})")
            return WebhookResult(status=PaymentStatus.paid, provider_payment_id=remote_id)

        if status in _FAILED:
            return WebhookResult(status=PaymentStatus.failed, provider_payment_id=remote_id)
        # Everything else — 3-D Secure in progress, "wait_accept", a hold —
        # is still open. Deliberately not guessed at.
        return WebhookResult(status=PaymentStatus.pending, provider_payment_id=remote_id)


def _decode(data: str) -> dict:
    try:
        return json.loads(base64.b64decode(data).decode("utf-8"))
    except (ValueError, TypeError, UnicodeDecodeError):
        return {}
