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
    RecurringMode,
    RecurringSetup,
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
    region = "ru"
    supports_status_check = True
    # Автоплатежи: первый платёж просит сохранить способ оплаты, ответ
    # приносит payment_method.id, и последующие списания идут с этим id
    # без участия покупателя. Поля сверены с официальным SDK
    # (yookassa 3.12.1: PaymentRequest.save_payment_method /
    # .payment_method_id, ResponsePaymentData.id / .saved).
    recurring = RecurringMode.token
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
        if request.extra.get("subscription"):
            # Turns this into the *first* payment of an autopayment series:
            # the buyer confirms once, and the response carries a handle we
            # can charge later. ЮKassa requires the shop to have autopayments
            # enabled by their manager — an account without it refuses the
            # field outright rather than silently ignoring it, which is the
            # behaviour we want.
            body["save_payment_method"] = True

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
            method = payment.get("payment_method") or {}
            notes = {}
            if method.get("saved") and method.get("id"):
                notes["yookassa_payment_method_id"] = str(method["id"])
            return WebhookResult(status=PaymentStatus.paid, provider_payment_id=str(remote_id), meta=notes)

        if status == "canceled":
            return WebhookResult(status=PaymentStatus.failed, provider_payment_id=str(remote_id))
        return WebhookResult(status=PaymentStatus.pending, provider_payment_id=str(remote_id))


    def recurring_setup(self, settled: dict) -> RecurringSetup | None:
        token = (settled or {}).get("yookassa_payment_method_id")
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
    ) -> WebhookResult:
        """The next period, with nobody present.

        Same POST /payments as a normal sale, minus the confirmation block
        and plus `payment_method_id` — ЮKassa then charges the saved method
        outright. The idempotence key is our own payment id, so a retried
        charge cannot take the money twice.
        """
        auth = self._auth(credentials)
        body = {
            "amount": {"value": minor_to_major(amount_minor), "currency": currency.upper()},
            "capture": True,
            "payment_method_id": setup.token,
            "description": description[:128] or "Продление подписки",
            "metadata": {"order_id": str(payment_id)},
        }
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(
                f"{_BASE}/payments", json=body, auth=auth, headers={"Idempotence-Key": str(payment_id)}
            )
        if response.status_code >= 400:
            raise ProviderError(f"ЮKassa: {_error(response)}")

        payload = response.json()
        remote_id = str(payload.get("id") or "")
        status = payload.get("status")
        if status == "succeeded" and payload.get("paid"):
            return WebhookResult(status=PaymentStatus.paid, provider_payment_id=remote_id)
        if status == "canceled":
            # A declined card is not an error to retry into oblivion — it is
            # this period's answer, and the subscription layer treats it as
            # "not paid" rather than "try again in a minute".
            return WebhookResult(status=PaymentStatus.failed, provider_payment_id=remote_id)
        # "pending" here means 3-D Secure was demanded for a payment nobody
        # is watching, which for an autopayment is a decline in slow motion.
        return WebhookResult(status=PaymentStatus.pending, provider_payment_id=remote_id)


def _error(response: httpx.Response) -> str:
    try:
        payload = response.json()
        return payload.get("description") or payload.get("error", {}).get("message") or response.text[:200]
    except ValueError:
        return response.text[:200]
