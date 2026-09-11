"""ЮKassa — direct REST API v3.

Notifications from ЮKassa carry no signature at all, so the callback is
treated as nothing more than a nudge: the adapter re-reads the payment
through `GET /v3/payments/{id}` with the shop's own credentials and
believes that, which is both simpler and stronger than an IP allowlist.
"""

from __future__ import annotations

import json
import uuid

import httpx

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
    same_currency,
)

_BASE = "https://api.yookassa.ru/v3"


class YooKassaProvider(ProviderDefaults):
    slug = "yookassa"
    title = "ЮKassa"
    hint = (
        "shopId и секретный ключ — в личном кабинете ЮKassa, «Интеграция → Ключи API». Уведомления мы "
        "проверяем обратным запросом в API, поэтому подписывать их не нужно; адрес для уведомлений всё же "
        "укажи в кабинете («Интеграция → HTTP-уведомления», событие payment.succeeded)."
    )
    currencies = ("RUB",)
    supports_status_check = True
    credential_fields = (
        CredentialField("shop_id", "shopId", "идентификатор магазина", secret=False),
        CredentialField("secret_key", "Секретный ключ", "live_… или test_…"),
    )

    @staticmethod
    def _auth(credentials: dict[str, str]) -> tuple[str, str]:
        shop_id = (credentials.get("shop_id") or "").strip()
        secret = (credentials.get("secret_key") or "").strip()
        if not shop_id or not secret:
            raise ProviderError("ЮKassa: не заполнены shopId или секретный ключ")
        return shop_id, secret

    async def create_checkout(self, request: CheckoutRequest) -> Checkout:
        auth = self._auth(request.credentials)
        body = {
            "amount": {"value": minor_to_major(request.amount_minor), "currency": request.currency.upper()},
            "capture": True,
            "confirmation": {"type": "redirect", "return_url": request.return_url},
            "description": request.description[:128] or "Оплата",
            "metadata": {"order_id": str(request.payment_id)},
        }

        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(
                f"{_BASE}/payments",
                json=body,
                auth=auth,
                # Any unique value; ours is the payment id, so a retried
                # create can never charge twice.
                headers={"Idempotence-Key": str(request.payment_id)},
            )
        if response.status_code >= 400:
            raise ProviderError(f"ЮKassa: {_error(response)}")

        payload = response.json()
        url = (payload.get("confirmation") or {}).get("confirmation_url")
        if not url:
            raise ProviderError("ЮKassa: ответ без ссылки на оплату")
        return Checkout(url=url, provider_payment_id=payload.get("id"))

    def locate_payment(self, *, headers: dict[str, str], raw_body: bytes, form: dict[str, str]) -> PaymentRef:
        try:
            event = json.loads(raw_body or b"{}")
        except json.JSONDecodeError:
            return PaymentRef()
        obj = event.get("object") or {}
        raw_id = (obj.get("metadata") or {}).get("order_id", "")
        try:
            return PaymentRef(payment_id=uuid.UUID(str(raw_id)))
        except (ValueError, AttributeError):
            return PaymentRef(provider_payment_id=str(obj.get("id")) if obj.get("id") else None)

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
        try:
            event = json.loads(raw_body or b"{}")
        except json.JSONDecodeError:
            event = {}
        remote_id = provider_payment_id or (event.get("object") or {}).get("id")
        if not remote_id:
            raise ProviderError("ЮKassa: не удалось определить платёж")
        return await self._read(credentials, str(remote_id), amount_minor, currency)

    async def check_status(
        self,
        *,
        credentials: dict[str, str],
        amount_minor: int,
        invoice_no: int,
        payment_id: uuid.UUID,
        provider_payment_id: str | None,
        meta: dict,
        currency: str = "",
    ) -> WebhookResult:
        if not provider_payment_id:
            raise ProviderError("ЮKassa: платёж ещё не создан")
        return await self._read(credentials, provider_payment_id, amount_minor, currency)

    async def _read(
        self, credentials: dict[str, str], remote_id: str, amount_minor: int, currency: str = ""
    ) -> WebhookResult:
        """The single source of truth for this provider: what the shop's own
        API says about the payment. Both the callback and the buyer's "Я
        оплатил" tap end up here."""
        auth = self._auth(credentials)
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.get(f"{_BASE}/payments/{remote_id}", auth=auth)
        if response.status_code >= 400:
            raise ProviderError(f"ЮKassa: {_error(response)}")

        payment = response.json()
        status = payment.get("status")
        # A refund does not change `status` — ЮKassa keeps it "succeeded" and
        # adds `refunded_amount`. Checked first, or a refunded sale would go
        # on counting as revenue for good.
        refunded = (payment.get("refunded_amount") or {}).get("value")
        if status == "succeeded" and refunded not in (None, "", "0.00"):
            return WebhookResult(status=PaymentStatus.refunded, provider_payment_id=str(remote_id))
        if status == "succeeded" and payment.get("paid"):
            value = (payment.get("amount") or {}).get("value", "")
            if value and abs(float(value) - amount_minor / 100) > 0.009:
                raise ProviderError(f"ЮKassa: сумма не совпадает (в кассе {value})")
            same_currency(self.title, (payment.get("amount") or {}).get("currency"), currency)
            return WebhookResult(status=PaymentStatus.paid, provider_payment_id=str(remote_id))

        if status == "canceled":
            return WebhookResult(status=PaymentStatus.failed, provider_payment_id=str(remote_id))
        return WebhookResult(status=PaymentStatus.pending, provider_payment_id=str(remote_id))


def _error(response: httpx.Response) -> str:
    try:
        payload = response.json()
        return payload.get("description") or payload.get("error", {}).get("message") or response.text[:200]
    except ValueError:
        return response.text[:200]
