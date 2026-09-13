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
    RecurringMode,
    RecurringSetup,
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
    region = "ru"
    supports_status_check = True
    # Автоплатёж: Init с Recurrent="Y" и CustomerKey, банк возвращает RebillId
    # в нотификации, дальше Init нового платежа + Charge(PaymentId, RebillId).
    # Поля сверены с типизированной реализацией github.com/nikita-vanyasin/tinkoff
    # (InitRequest.Recurrent "Y", InitRequest.CustomerKey, Notification.RebillId,
    # ChargeRequest.PaymentId/.RebillId) — не по памяти.
    recurring = RecurringMode.token
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
                **(
                    {
                        "Recurrent": "Y",
                        # The bank ties the RebillId to this key, so it has to
                        # be the buyer — not the order, which changes every
                        # period.
                        "CustomerKey": str(request.telegram_user_id or request.payment_id),
                    }
                    if request.extra.get("subscription")
                    else {}
                ),
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
        currency: str = "",
    ) -> WebhookResult:
        try:
            event = json.loads(raw_body or b"{}")
        except json.JSONDecodeError:
            event = {}
        remote_id = provider_payment_id or event.get("PaymentId") or form.get("PaymentId")
        if not remote_id:
            raise ProviderError("Т-Банк: уведомление без PaymentId")
        result = await self._read(credentials, str(remote_id), amount_minor)
        # RebillId is only ever in the notification — GetState does not carry
        # it — so it is picked up here or not at all.
        notes = dict(result.meta or {})
        rebill = event.get("RebillId") or form.get("RebillId")
        if rebill:
            notes["tbank_rebill_id"] = str(rebill)
        customer = event.get("CustomerKey") or form.get("CustomerKey")
        if customer:
            notes["tbank_customer_key"] = str(customer)
        # The terminal keeps resending until it sees exactly "OK".
        return WebhookResult(
            status=result.status,
            provider_payment_id=result.provider_payment_id,
            response_body="OK",
            meta=notes,
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
        currency: str = "",
    ) -> WebhookResult:
        if not provider_payment_id:
            raise ProviderError("Т-Банк: платёж ещё не создан")
        return await self._read(credentials, provider_payment_id, amount_minor)

    def recurring_setup(self, settled: dict) -> RecurringSetup | None:
        rebill = (settled or {}).get("tbank_rebill_id")
        if not rebill:
            return None
        return RecurringSetup(token=str(rebill), customer=str((settled or {}).get("tbank_customer_key") or ""))

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
        #: The short numeric invoice number of *this* charge. Robokassa signs
        #: the recurring call with it; the others never look at it.
        invoice_no: int | None = None,
    ) -> WebhookResult:
        """Two calls, because Charge needs a payment to charge.

        `Init` mints a fresh PaymentId for this period — deliberately without
        `Recurrent`, since the arrangement already exists and re-registering
        it would ask the bank for a second one — and `Charge` then takes the
        money against the stored RebillId with nobody present.
        """
        started = await self._call(
            "Init",
            {
                "Amount": amount_minor,
                "OrderId": str(payment_id),
                "Description": (description or "Продление подписки")[:250],
                **({"CustomerKey": setup.customer} if setup.customer else {}),
            },
            credentials,
        )
        remote_id = started.get("PaymentId")
        if remote_id is None:
            raise ProviderError("Т-Банк: Init не вернул PaymentId")

        charged = await self._call(
            "Charge", {"PaymentId": str(remote_id), "RebillId": setup.token}, credentials
        )
        status = str(charged.get("Status") or "").upper()
        if status in _PAID:
            amount = charged.get("Amount")
            if amount is not None and int(amount) != amount_minor:
                raise ProviderError(f"Т-Банк: списано {amount} вместо {amount_minor}")
            return WebhookResult(status=PaymentStatus.paid, provider_payment_id=str(remote_id))
        if status in _FAILED:
            return WebhookResult(status=PaymentStatus.failed, provider_payment_id=str(remote_id))
        # AUTHORIZED on a two-stage terminal means held, not taken — and a
        # renewal nobody is watching has no one to confirm it.
        return WebhookResult(status=PaymentStatus.pending, provider_payment_id=str(remote_id))

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
