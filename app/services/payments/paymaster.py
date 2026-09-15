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
    RecurringMode,
    RecurringSetup,
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
    region = "ru"
    supports_status_check = True
    # Хостируемая токенизация: объект tokenization в счёте, id токена
    # приходит и в ответе, и в колбэке, списание — POST /payments с
    # paymentData.token.id. Деньги только на Settled: Confirmation и
    # Pending — это ещё не оплата.
    recurring = RecurringMode.token
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
        if request.extra.get("subscription"):
            # PayMaster hosts the card form, so no PAN ever reaches us; what
            # comes back is a token id. `purpose` is the consent text the
            # payer is shown, so it has to name the actual arrangement.
            body["tokenization"] = {
                "type": "recurring",
                "purpose": (request.description or "Подписка")[:255],
                "callbackUrl": f"{base}/webhook/pay/paymaster",
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

    @staticmethod
    def _token_id(payment: dict) -> str:
        """The saved-card handle, wherever this response happens to put it."""
        for holder in (payment.get("paymentData") or {}, payment):
            token = holder.get("token")
            if isinstance(token, dict) and token.get("id"):
                return str(token["id"])
            if isinstance(token, str) and token:
                return token
        tokenization = payment.get("tokenization") or {}
        return str(tokenization.get("id") or "") if tokenization.get("id") else ""

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
            token = self._token_id(payment)
            return WebhookResult(
                status=PaymentStatus.paid,
                provider_payment_id=str(remote_id),
                meta={"paymaster_token_id": token} if token else {},
            )
        if status in _REFUNDED:
            return WebhookResult(status=PaymentStatus.refunded, provider_payment_id=str(remote_id))
        if status in _FAILED:
            return WebhookResult(status=PaymentStatus.failed, provider_payment_id=str(remote_id))
        return WebhookResult(status=PaymentStatus.pending, provider_payment_id=str(remote_id))


    def recurring_setup(self, settled: dict) -> RecurringSetup | None:
        token = (settled or {}).get("paymaster_token_id")
        return RecurringSetup(token=str(token)) if token else None

    async def charge_recurring(
        self,
        *,
        credentials: dict[str, str],
        setup: RecurringSetup,
        amount_minor: int,
        currency: str,
        description: str,
        payment_id: uuid.UUID,
        is_test: bool = False,
        invoice_no: int | None = None,
    ) -> WebhookResult:
        """Charge the saved token. Only `Settled` counts as money.

        The response comes back immediately but is not final: `Confirmation`
        means PayMaster still wants something from the payer, and `Pending`
        means it is still deciding. Both are reported as pending, and the
        ordinary callback settles the payment when it resolves — the same
        route a hand-made payment takes.
        """
        from app.config import get_settings

        headers = self._headers(credentials)
        merchant_id = (credentials.get("merchant_id") or "").strip()
        if not merchant_id:
            raise ProviderError("PayMaster: не заполнен merchantId")
        if not setup.token:
            raise ProviderError("PayMaster: нет сохранённого токена карты")

        base = get_settings().public_base_url.rstrip("/")
        body = {
            "merchantId": merchant_id,
            "invoice": {
                "description": (description or "Продление подписки")[:255],
                "orderNo": str(payment_id),
            },
            "amount": {"value": round(amount_minor / 100, 2), "currency": currency.upper()},
            "paymentData": {"token": {"id": setup.token}},
            "protocol": {"callbackUrl": f"{base}/webhook/pay/paymaster"},
            "testMode": bool(is_test),
        }

        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(
                f"{_BASE}/payments", json=body, headers={**headers, "Idempotency-Key": str(payment_id)}
            )
        if response.status_code >= 400:
            raise ProviderError(f"PayMaster: {_error(response)}")

        payload = response.json()
        remote_id = payload.get("paymentId") or payload.get("id")
        status = str(payload.get("status", "")).lower()
        if status in _SETTLED:
            return WebhookResult(status=PaymentStatus.paid, provider_payment_id=str(remote_id or ""))
        if status in _FAILED:
            return WebhookResult(status=PaymentStatus.failed, provider_payment_id=str(remote_id or ""))
        return WebhookResult(status=PaymentStatus.pending, provider_payment_id=str(remote_id or ""))


def _error(response: httpx.Response) -> str:
    try:
        payload = response.json()
        return payload.get("message") or payload.get("error") or response.text[:200]
    except ValueError:
        return response.text[:200]
