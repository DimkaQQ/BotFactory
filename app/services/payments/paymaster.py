"""PayMaster — REST API v2 (invoice → payment link).

The public v2 docs describe no webhook signature, so the callback is
treated as a hint only and the truth comes from `GET /api/v2/payments/{id}`.
Goods ship on `Settled`.
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
    same_currency,
)

_BASE = "https://paymaster.ru/api/v2"
_SETTLED = {"settled"}
_REFUNDED = {"refunded", "partiallyrefunded", "partially_refunded"}
_FAILED = {"cancelled", "rejected"}


class PayMasterProvider(ProviderDefaults):
    slug = "paymaster"
    title = "PayMaster"
    hint = (
        "Токен — в кабинете мерчанта, «Настройки → Токены доступа». merchantId (UUID сайта) там же, в списке "
        "сайтов. Адрес уведомления мы передаём в самом счёте, отдельно настраивать не нужно."
    )
    currencies = ("RUB",)
    supports_status_check = True
    credential_fields = (
        CredentialField("merchant_id", "merchantId", "UUID сайта в PayMaster", secret=False),
        CredentialField("token", "Токен доступа", "из раздела «Токены доступа»"),
    )

    @staticmethod
    def _headers(credentials: dict[str, str]) -> dict[str, str]:
        token = (credentials.get("token") or "").strip()
        if not token:
            raise ProviderError("PayMaster: не заполнен токен доступа")
        return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

    async def create_checkout(self, request: CheckoutRequest) -> Checkout:
        headers = self._headers(request.credentials)
        merchant_id = (request.credentials.get("merchant_id") or "").strip()
        if not merchant_id:
            raise ProviderError("PayMaster: не заполнен merchantId")

        from app.config import get_settings

        base = get_settings().public_base_url.rstrip("/")
        body = {
            "merchantId": merchant_id,
            "invoice": {
                "description": request.description[:255] or "Оплата",
                # Our payment id rides back in the callback as orderNo.
                "orderNo": str(request.payment_id),
            },
            "amount": {"value": round(request.amount_minor / 100, 2), "currency": request.currency.upper()},
            "protocol": {
                "returnUrl": request.return_url,
                "callbackUrl": f"{base}/webhook/pay/paymaster",
            },
            "testMode": request.is_test,
        }

        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(
                f"{_BASE}/invoices", json=body, headers={**headers, "Idempotency-Key": str(request.payment_id)}
            )
        if response.status_code >= 400:
            raise ProviderError(f"PayMaster: {_error(response)}")

        payload = response.json()
        url = payload.get("url")
        if not url:
            raise ProviderError("PayMaster: ответ без ссылки на оплату")
        return Checkout(url=url, provider_payment_id=payload.get("paymentId"))

    def locate_payment(self, *, headers: dict[str, str], raw_body: bytes, form: dict[str, str]) -> PaymentRef:
        try:
            event = json.loads(raw_body or b"{}")
        except json.JSONDecodeError:
            return PaymentRef()
        order_no = (event.get("invoice") or {}).get("orderNo", "")
        try:
            return PaymentRef(payment_id=uuid.UUID(str(order_no)))
        except (ValueError, AttributeError):
            return PaymentRef(provider_payment_id=str(event.get("id")) if event.get("id") else None)

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
        remote_id = provider_payment_id or event.get("id")
        if not remote_id:
            raise ProviderError("PayMaster: не удалось определить платёж")
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
            raise ProviderError("PayMaster: платёж ещё не создан")
        return await self._read(credentials, provider_payment_id, amount_minor, currency)

    async def _read(
        self, credentials: dict[str, str], remote_id: str, amount_minor: int, currency: str = ""
    ) -> WebhookResult:
        """What PayMaster itself says about the payment — the only thing
        believed here, whether prompted by a callback or by the buyer."""
        api_headers = self._headers(credentials)
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.get(f"{_BASE}/payments/{remote_id}", headers=api_headers)
        if response.status_code >= 400:
            raise ProviderError(f"PayMaster: {_error(response)}")

        payment = response.json()
        status = str(payment.get("status", "")).lower()
        if status in _SETTLED:
            value = (payment.get("amount") or {}).get("value")
            if value is not None and abs(float(value) - amount_minor / 100) > 0.009:
                raise ProviderError(f"PayMaster: сумма не совпадает (у провайдера {value})")
            same_currency(self.title, (payment.get("amount") or {}).get("currency"), currency)
            return WebhookResult(status=PaymentStatus.paid, provider_payment_id=str(remote_id))
        if status in _REFUNDED:
            return WebhookResult(status=PaymentStatus.refunded, provider_payment_id=str(remote_id))
        if status in _FAILED:
            return WebhookResult(status=PaymentStatus.failed, provider_payment_id=str(remote_id))
        return WebhookResult(status=PaymentStatus.pending, provider_payment_id=str(remote_id))


def _error(response: httpx.Response) -> str:
    try:
        payload = response.json()
        return payload.get("message") or payload.get("error") or response.text[:200]
    except ValueError:
        return response.text[:200]
