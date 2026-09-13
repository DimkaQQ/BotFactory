"""CloudPayments — Россия и Казахстан, счёт по ссылке.

CloudPayments is normally a JavaScript widget on the merchant's own page,
which is no use to a bot. `/orders/create` is the other half of it: an
invoice with a hosted payment page, and a link we can put in a button.

Two independent checks, both cheap: the notification carries a
`Content-HMAC` header — base64(HMAC-SHA256(raw body, API secret)) — and the
adapter then re-reads the payment through `/v2/payments/find`, so a replayed
body cannot settle an order on its own.

Written against the published SDK github.com/MrConsoleka/cloudpayments_sdk
(endpoints, Basic auth, the HMAC header and its encoding) rather than from
memory.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
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
    same_currency,
)

_BASE = "https://api.cloudpayments.ru"

#: Where the hosted invoice lives in the `/orders/create` answer. The SDK
#: models the order loosely (`extra="allow"`), so the key is looked for
#: rather than assumed, and a miss is reported instead of guessed around.
_URL_KEYS = ("Url", "PaymentUrl", "PayUrl", "url")

#: "Authorized" is a hold on a two-stage scheme, not money taken — the goods
#: only go out on "Completed".
_PAID = {"completed"}
_REFUNDED = {"refunded", "partiallyrefunded"}
_FAILED = {"declined", "cancelled"}


class CloudPaymentsProvider(ProviderDefaults):
    slug = "cloudpayments"
    title = "CloudPayments"
    hint = (
        "Public ID и API-пароль — в кабинете CloudPayments, «Сайты → Настройки». В том же разделе, "
        "«Уведомления», включи Pay-уведомление на адрес, который мы покажем ниже, и метод POST. "
        "Работает с рублями и тенге."
    )
    currencies = ("RUB", "KZT", "USD", "EUR", "UAH")
    region = "ru"
    supports_status_check = True
    # Рекуррент по токену карты: успешный платёж возвращает Token, и
    # последующие списания идут через payments/tokens/charge с этим
    # токеном и AccountId. Поля сверены с официальной библиотекой
    # (cloudpayments 1.6.3: Client.charge_token → payments/tokens/charge,
    # параметры Token / AccountId / Amount / Currency / InvoiceId).
    recurring = RecurringMode.token
    credential_fields = (
        CredentialField("public_id", "Public ID", "pk_… из кабинета", secret=False),
        CredentialField("api_secret", "API-пароль", "он же API Secret"),
    )

    @staticmethod
    def _auth(credentials: dict[str, str]) -> tuple[str, str]:
        public_id = (credentials.get("public_id") or "").strip()
        secret = (credentials.get("api_secret") or "").strip()
        if not public_id or not secret:
            raise ProviderError("CloudPayments: не заполнены Public ID или API-пароль")
        return public_id, secret

    async def _call(self, path: str, body: dict, credentials: dict[str, str]) -> dict:
        """The raw call, without treating a business refusal as an error.

        `_post` below turns `Success: false` into a ProviderError, which is
        right for "find this payment" and wrong for "charge this card": a
        declined card is this period's answer, not a broken integration, and
        the shop owner needs the bank's own wording rather than a stringified
        response body.
        """
        auth = self._auth(credentials)
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(f"{_BASE}{path}", json=body, auth=auth)
        if response.status_code >= 400:
            raise ProviderError(f"CloudPayments: HTTP {response.status_code}")
        try:
            return response.json()
        except ValueError as exc:
            raise ProviderError("CloudPayments: непонятный ответ") from exc

    async def _post(self, path: str, body: dict, credentials: dict[str, str]) -> dict:
        auth = self._auth(credentials)
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(f"{_BASE}{path}", json=body, auth=auth)
        if response.status_code >= 400:
            raise ProviderError(f"CloudPayments: HTTP {response.status_code}")
        try:
            parsed = response.json()
        except ValueError as exc:
            raise ProviderError("CloudPayments: непонятный ответ") from exc
        if not parsed.get("Success"):
            detail = parsed.get("Message") or parsed.get("Model") or "отказ"
            raise ProviderError(f"CloudPayments: {detail}")
        return parsed

    async def create_checkout(self, request: CheckoutRequest) -> Checkout:
        parsed = await self._post(
            "/orders/create",
            {
                "Amount": float(request.amount_minor) / 100,
                "Currency": request.currency.upper(),
                "Description": (request.description or "Оплата")[:250],
                # Our payment id is the invoice id, so both the notification
                # and the status re-read find the order by it.
                "InvoiceId": str(request.payment_id),
            },
            request.credentials,
        )
        model = parsed.get("Model") or {}
        url = next((model[key] for key in _URL_KEYS if model.get(key)), None)
        if not url:
            raise ProviderError("CloudPayments: ответ без ссылки на оплату")
        order_id = model.get("Id") or model.get("Number")
        return Checkout(url=str(url), provider_payment_id=str(order_id) if order_id else None)

    def locate_payment(self, *, headers: dict[str, str], raw_body: bytes, form: dict[str, str]) -> PaymentRef:
        raw = (form.get("InvoiceId") or "").strip()
        try:
            return PaymentRef(payment_id=uuid.UUID(raw))
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
        _public_id, secret = self._auth(credentials)

        received = (
            headers.get("content-hmac") or headers.get("x-content-hmac") or ""
        ).strip()
        expected = base64.b64encode(hmac.new(secret.encode(), raw_body, hashlib.sha256).digest()).decode()
        if not received or not hmac.compare_digest(received, expected):
            raise ProviderError("CloudPayments: подпись уведомления не совпала")

        # The header proves who sent it; this proves what it says. Both,
        # because a Pay-notification is fire-and-forget and we would rather
        # ask than assume.
        result = await self._find(credentials, payment_id, amount_minor, currency)
        # Anything but {"code":0} is read as "resend this later".
        return WebhookResult(
            status=result.status,
            provider_payment_id=result.provider_payment_id,
            response_body='{"code":0}',
            response_content_type="application/json",
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
        return await self._find(credentials, payment_id, amount_minor, currency)

    def recurring_setup(self, settled: dict) -> RecurringSetup | None:
        token = (settled or {}).get("cloudpayments_token")
        if not token:
            return None
        return RecurringSetup(token=str(token), customer=str((settled or {}).get("cloudpayments_account") or ""))

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
        """Charge the saved card for the next period.

        `payments/tokens/charge`, not `.../auth`: the auth variant holds the
        money for a later confirm, and a subscription renewal nobody is
        watching has no one to do the confirming.
        """
        if not setup.token:
            raise ProviderError("CloudPayments: нет сохранённого токена карты")
        body = {
            "Amount": round(amount_minor / 100, 2),
            "Currency": currency.upper(),
            "AccountId": setup.customer or str(payment_id),
            "Token": setup.token,
            "InvoiceId": str(payment_id),
            "Description": description[:250] or "Продление подписки",
        }
        parsed = await self._call("/payments/tokens/charge", body, credentials)
        model = parsed.get("Model") or {}
        transaction_id = model.get("TransactionId")
        remote_id = str(transaction_id) if transaction_id is not None else None

        if not parsed.get("Success"):
            # A refusal here is the bank declining, not the integration
            # breaking — `Message`/`CardHolderMessage` is what the shop owner
            # needs to see in their subscription list.
            reason = model.get("CardHolderMessage") or parsed.get("Message") or "отказ банка"
            return WebhookResult(status=PaymentStatus.failed, provider_payment_id=remote_id, meta={"decline": reason})

        status = str(model.get("Status") or "").lower()
        if status in _PAID:
            return WebhookResult(status=PaymentStatus.paid, provider_payment_id=remote_id)
        if status in _FAILED:
            return WebhookResult(status=PaymentStatus.failed, provider_payment_id=remote_id)
        return WebhookResult(status=PaymentStatus.pending, provider_payment_id=remote_id)

    async def _find(
        self, credentials: dict[str, str], payment_id: uuid.UUID, amount_minor: int, currency: str = ""
    ) -> WebhookResult:
        # Checked here, outside the try: a shop that has not filled in its
        # keys must hear about it, not be told nobody has paid.
        self._auth(credentials)
        try:
            parsed = await self._post("/v2/payments/find", {"InvoiceId": str(payment_id)}, credentials)
        except ProviderError:
            # CloudPayments answers "not found" as a business refusal rather
            # than an empty result, and for an invoice nobody has paid yet
            # that is the normal answer.
            return WebhookResult(status=PaymentStatus.pending)

        model = parsed.get("Model") or {}
        if isinstance(model, list):
            model = model[0] if model else {}
        status = str(model.get("Status") or "").lower()
        transaction_id = model.get("TransactionId")
        remote_id = str(transaction_id) if transaction_id is not None else None

        if status in _PAID:
            amount = model.get("Amount")
            try:
                mismatch = amount is None or abs(float(amount) - amount_minor / 100) > 0.009
            except (TypeError, ValueError):
                mismatch = True
            if mismatch:
                raise ProviderError(f"CloudPayments: сумма не совпадает (пришло {amount})")
            same_currency(self.title, model.get("Currency"), currency)
            notes = {}
            # Present only when the payment was made with card-token saving
            # enabled; a one-off sale simply has no Token and this stays empty.
            if model.get("Token"):
                notes["cloudpayments_token"] = str(model["Token"])
                notes["cloudpayments_account"] = str(model.get("AccountId") or "")
            return WebhookResult(status=PaymentStatus.paid, provider_payment_id=remote_id, meta=notes)

        if status in _REFUNDED:
            return WebhookResult(status=PaymentStatus.refunded, provider_payment_id=remote_id)
        if status in _FAILED:
            return WebhookResult(status=PaymentStatus.failed, provider_payment_id=remote_id)
        return WebhookResult(status=PaymentStatus.pending, provider_payment_id=remote_id)
