"""Т-Банк (бывший Тинькофф) — интернет-эквайринг, Россия.

`Init` creates the payment and returns `PaymentURL`; `GetState` says where
it stands. Every request is signed with a `Token`:

    sha256( values of all top-level scalar params, plus Password,
            concatenated in order of their key names )

Nested objects (Receipt, DATA, Shops) are excluded from the signature.

The notification is *not* trusted on its own: like ЮKassa and PayMaster,
this adapter treats it as a nudge and re-reads `GetState`, so the money
question is answered by the bank's API rather than by a request body.

Signature scheme taken from the official API description
(github.com/Tinkoff/api_asdk) plus the published acquiring client
github.com/saliy/tinkoff-acquiring-api — not from memory.
"""

from __future__ import annotations

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
)

_BASE = "https://securepay.tinkoff.ru/v2"

#: Fields that are objects, not values — excluded from the token.
_UNSIGNED = {"Token", "Receipt", "DATA", "Shops", "Items"}

#: Only CONFIRMED, deliberately. On a two-stage terminal AUTHORIZED means the
#: money is held, not taken — handing over goods for a hold would be giving
#: them away to anyone who can cancel the authorisation.
_PAID = {"CONFIRMED"}
_FAILED = {"REJECTED", "CANCELED", "DEADLINE_EXPIRED", "AUTH_FAIL"}
_REFUNDED = {"REFUNDED", "PARTIAL_REFUNDED", "REVERSED", "PARTIAL_REVERSED"}


def _token(payload: dict, password: str) -> str:
    values = {key: value for key, value in payload.items() if key not in _UNSIGNED}
    values = {key: value for key, value in values.items() if not isinstance(value, (dict, list))}
    values["Password"] = password
    joined = "".join(str(values[key]) for key in sorted(values))
    return hashlib.sha256(joined.encode()).hexdigest()


class TBankProvider(ProviderDefaults):
    slug = "tbank"
    title = "Т-Банк (Тинькофф)"
    hint = (
        "Terminal Key и пароль — в личном кабинете Т-Кассы, «Магазины → Терминалы». Уведомления мы "
        "перепроверяем запросом в банк, поэтому достаточно указать в терминале адрес нотификаций, "
        "который мы покажем ниже."
    )
    currencies = ("RUB",)
    supports_status_check = True
    credential_fields = (
        CredentialField("terminal_key", "Terminal Key", "идентификатор терминала", secret=False),
        CredentialField("password", "Пароль терминала", "он же Secret Key"),
    )

    @staticmethod
    def _keys(credentials: dict[str, str]) -> tuple[str, str]:
        terminal = (credentials.get("terminal_key") or "").strip()
        password = (credentials.get("password") or "").strip()
        if not terminal or not password:
            raise ProviderError("Т-Банк: не заполнены Terminal Key или пароль терминала")
        return terminal, password

    async def _call(self, method: str, payload: dict, credentials: dict[str, str]) -> dict:
        terminal, password = self._keys(credentials)
        body = {"TerminalKey": terminal, **payload}
        body["Token"] = _token(body, password)

        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(f"{_BASE}/{method}", json=body)
        if response.status_code >= 400:
            raise ProviderError(f"Т-Банк: HTTP {response.status_code}")
        try:
            parsed = response.json()
        except ValueError as exc:
            raise ProviderError("Т-Банк: непонятный ответ") from exc
        if not parsed.get("Success"):
            detail = parsed.get("Message") or parsed.get("Details") or parsed.get("ErrorCode") or "отказ"
            raise ProviderError(f"Т-Банк: {detail}")
        return parsed

    async def create_checkout(self, request: CheckoutRequest) -> Checkout:
        base = get_settings().public_base_url.rstrip("/")
        parsed = await self._call(
            "Init",
            {
                # Kopecks, which is what we store anyway.
                "Amount": request.amount_minor,
                "OrderId": str(request.payment_id),
                "Description": (request.description or "Оплата")[:250],
                "SuccessURL": request.return_url,
                "FailURL": request.return_url,
                "NotificationURL": f"{base}/webhook/pay/tbank",
            },
            request.credentials,
        )
        url = parsed.get("PaymentURL")
        if not url:
            raise ProviderError("Т-Банк: ответ без ссылки на оплату")
        payment_id = parsed.get("PaymentId")
        return Checkout(url=url, provider_payment_id=str(payment_id) if payment_id is not None else None)

    def locate_payment(self, *, headers: dict[str, str], raw_body: bytes, form: dict[str, str]) -> PaymentRef:
        try:
            event = json.loads(raw_body or b"{}")
        except json.JSONDecodeError:
            event = {}
        raw_order = str(event.get("OrderId") or form.get("OrderId") or "")
        try:
            return PaymentRef(payment_id=uuid.UUID(raw_order))
        except ValueError:
            remote = event.get("PaymentId") or form.get("PaymentId")
            return PaymentRef(provider_payment_id=str(remote) if remote else None)

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
        try:
            event = json.loads(raw_body or b"{}")
        except json.JSONDecodeError:
            event = {}
        remote_id = provider_payment_id or event.get("PaymentId") or form.get("PaymentId")
        if not remote_id:
            raise ProviderError("Т-Банк: уведомление без PaymentId")
        result = await self._read(credentials, str(remote_id), amount_minor)
        # The terminal keeps resending until it sees exactly "OK".
        return WebhookResult(
            status=result.status, provider_payment_id=result.provider_payment_id, response_body="OK"
        )

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
        if not provider_payment_id:
            raise ProviderError("Т-Банк: платёж ещё не создан")
        return await self._read(credentials, provider_payment_id, amount_minor)

    async def _read(self, credentials: dict[str, str], remote_id: str, amount_minor: int) -> WebhookResult:
        parsed = await self._call("GetState", {"PaymentId": remote_id}, credentials)
        status = str(parsed.get("Status") or "").upper()

        if status in _PAID:
            amount = parsed.get("Amount")
            # GetState reports kopecks, the same unit we asked to charge.
            if amount is not None and int(amount) != amount_minor:
                raise ProviderError(f"Т-Банк: сумма не совпадает (в банке {amount})")
            return WebhookResult(status=PaymentStatus.paid, provider_payment_id=str(remote_id))
        if status in _REFUNDED:
            return WebhookResult(status=PaymentStatus.refunded, provider_payment_id=str(remote_id))
        if status in _FAILED:
            return WebhookResult(status=PaymentStatus.failed, provider_payment_id=str(remote_id))
        return WebhookResult(status=PaymentStatus.pending, provider_payment_id=str(remote_id))
