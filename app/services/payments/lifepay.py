"""LIFE PAY — invoice (`POST /v1/bill`), paid by SBP or card.

Two quirks shape this adapter. There is no order id of our own in a LIFE PAY
bill, so the only handle is the `number` they mint at creation — stored as
provider_payment_id and used to match the callback. And the callback is
unsigned, so the truth is `GET /v1/bill/status`, not the request body.
"""

from __future__ import annotations

import json

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
)

_BASE = "https://api.life-pay.ru/v1"
# Statuses per LIFE PAY: 0 initiated, 10 success, 15 awaiting, 20 failed, 30 cancelled.
_SUCCESS = {10, "10", "success"}
_FAILED = {20, 30, "20", "30", "fail"}


class LifePayProvider(ProviderDefaults):
    slug = "lifepay"
    title = "LIFE PAY"
    hint = (
        "API-ключ — в кабинете LIFE PAY, «Настройки → Раздел для разработчиков». Логин — телефон "
        "администратора в формате 7XXXXXXXXXX. Там же пропиши адрес уведомлений, который мы покажем ниже. "
        "По умолчанию оплата идёт через СБП."
    )
    currencies = ("RUB",)
    region = "ru"
    supports_status_check = True
    credential_fields = (
        CredentialField("login", "Логин (телефон администратора)", "7XXXXXXXXXX", secret=False),
        CredentialField("apikey", "API-ключ", "из раздела для разработчиков"),
        CredentialField("method", "Способ оплаты", "sbp (по умолчанию), internetAcquiring", secret=False),
    )

    @staticmethod
    def _auth(credentials: dict[str, str]) -> dict[str, str]:
        apikey = (credentials.get("apikey") or "").strip()
        login = (credentials.get("login") or "").strip()
        if not apikey or not login:
            raise ProviderError("LIFE PAY: не заполнены API-ключ или логин")
        # Auth travels in the body for this API, not in headers.
        return {"apikey": apikey, "login": login}

    async def create_checkout(self, request: CheckoutRequest) -> Checkout:
        body = self._auth(request.credentials)

        from app.config import get_settings

        base = get_settings().public_base_url.rstrip("/")
        body.update(
            {
                "amount": minor_to_major(request.amount_minor),
                "description": request.description[:255] or "Оплата",
                "method": (request.credentials.get("method") or "sbp").strip() or "sbp",
                "callback_url": f"{base}/webhook/pay/lifepay",
            }
        )

        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(f"{_BASE}/bill", json=body)
        if response.status_code >= 400:
            raise ProviderError(f"LIFE PAY: {response.text[:200]}")

        payload = response.json()
        if payload.get("code") not in (0, "0", None):
            raise ProviderError(f"LIFE PAY: {payload.get('message') or 'счёт не создан'}")

        data = payload.get("data") or {}
        # paymentUrlWeb is the bank-picker page — the one that works in a
        # button; paymentUrl is the raw SBP link, better as a QR code.
        url = data.get("paymentUrlWeb") or data.get("paymentUrl")
        number = data.get("number")
        if not url or not number:
            raise ProviderError("LIFE PAY: ответ без ссылки на оплату")
        return Checkout(url=url, provider_payment_id=str(number), meta={"sbp_url": data.get("paymentUrl")})

    def locate_payment(self, *, headers: dict[str, str], raw_body: bytes, form: dict[str, str]) -> PaymentRef:
        try:
            event = json.loads(raw_body or b"{}")
        except json.JSONDecodeError:
            event = form or {}
        number = event.get("number") or (event.get("data") or {}).get("number")
        return PaymentRef(provider_payment_id=str(number)) if number else PaymentRef()

    async def verify_webhook(
        self,
        *,
        headers: dict[str, str],
        raw_body: bytes,
        form: dict[str, str],
        credentials: dict[str, str],
        amount_minor: int,
        invoice_no: int,
        payment_id,
        provider_payment_id: str | None,
        meta: dict | None = None,
        currency: str = "",
    ) -> WebhookResult:
        return await self._read(credentials, provider_payment_id, amount_minor)

    async def check_status(
        self,
        *,
        credentials: dict[str, str],
        amount_minor: int,
        invoice_no: int,
        payment_id,
        provider_payment_id: str | None,
        meta: dict,
        currency: str = "",
    ) -> WebhookResult:
        return await self._read(credentials, provider_payment_id, amount_minor)

    async def _read(self, credentials: dict[str, str], number: str | None, amount_minor: int) -> WebhookResult:
        """The bill as LIFE PAY has it — the callback only says which bill to
        look at, and the buyer's "Я оплатил" asks the same question."""
        # `GET /v1/bill/status` takes apikey and login as query parameters —
        # that is LIFE PAY's own design, not a choice here, and moving them
        # into a body would simply not authenticate. Worth knowing when
        # deciding what a reverse proxy in front of us logs.
        params = self._auth(credentials)
        if not number:
            raise ProviderError("LIFE PAY: у платежа нет номера счёта")
        params["number"] = number

        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.get(f"{_BASE}/bill/status", params=params)
        if response.status_code >= 400:
            raise ProviderError(f"LIFE PAY: {response.text[:200]}")

        payload = response.json()
        data = payload.get("data") or {}
        status = data.get("status")

        if status in _SUCCESS:
            amount = data.get("amount")
            if amount is not None and abs(float(str(amount).replace(",", ".")) - amount_minor / 100) > 0.009:
                raise ProviderError(f"LIFE PAY: сумма не совпадает (в кассе {amount})")
            return WebhookResult(status=PaymentStatus.paid, provider_payment_id=number)
        if status in _FAILED:
            return WebhookResult(status=PaymentStatus.failed, provider_payment_id=number)
        return WebhookResult(status=PaymentStatus.pending, provider_payment_id=number)
