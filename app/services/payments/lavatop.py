"""lava.top — invoices against a product offer.

Two different things ship under the name Lava: lava.top (gate.lava.top,
`X-Api-Key`, a catalogue of digital products) and the legacy Lava Business
(api.lava.ru, HMAC-signed bodies). This is lava.top, the one built for
selling digital products from a bot.

Its shape differs from every other provider here in one way that drives the
whole adapter: **an invoice has no free-form amount**. You bill against an
`offerId` from your Lava catalogue, and the offer carries the price. So the
price in the payment block is not what gets charged — it is checked against
what Lava says the offer costs, and a disagreement is refused rather than
quietly charging the buyer something else.

There is likewise no free `order_id` field. Lava hands back a `contractId`
at creation, and `clientUtm.utm_content` comes back in the webhook; the
adapter sends both, as their own docs recommend, so a callback can always be
tied to a row even if one of the two goes missing.
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

_BASE = "https://gate.lava.top"
_PAID = {"COMPLETED", "SUBSCRIPTION_ACTIVE"}
_FAILED = {"FAILED", "CANCELLED"}
_REFUNDED = {"REFUNDED", "PARTIALLY_REFUNDED", "REVERSED", "CHARGEBACK"}


class LavaTopProvider(ProviderDefaults):
    slug = "lavatop"
    title = "lava.top"
    hint = (
        "API-ключ — в настройках аккаунта lava.top. Товар заводится у них в каталоге, а в блок оплаты "
        "вставляется offerId нужного тарифа (ЛК → товар → оффер). Цена берётся из оффера в Lava, поэтому "
        "она должна совпадать с ценой в блоке. Почта нужна самой Lava для чека — укажи свою: покупателю "
        "товар выдаёт бот, а не Lava. Адрес для вебхуков задаётся в ЛК, там же включи авторизацию."
    )
    currencies = ("RUB", "USD", "EUR")
    region = "ru"
    supports_status_check = True
    credential_fields = (
        CredentialField("api_key", "API-ключ", "заголовок X-Api-Key из настроек аккаунта"),
        CredentialField("buyer_email", "Почта для чеков", "на неё Lava пришлёт чек — обычно твоя", secret=False),
    )
    block_fields = (
        CredentialField(
            "offer_id",
            "offerId товара в Lava",
            "UUID оффера: ЛК lava.top → товар → нужный тариф",
            secret=False,
        ),
    )

    @staticmethod
    def _headers(credentials: dict[str, str]) -> dict[str, str]:
        api_key = (credentials.get("api_key") or "").strip()
        if not api_key:
            raise ProviderError("lava.top: не заполнен API-ключ")
        return {"X-Api-Key": api_key, "Content-Type": "application/json"}

    async def create_checkout(self, request: CheckoutRequest) -> Checkout:
        headers = self._headers(request.credentials)
        offer_id = (request.extra.get("offer_id") or "").strip()
        if not offer_id:
            raise ProviderError("lava.top: в блоке оплаты не указан offerId товара")
        email = (request.credentials.get("buyer_email") or "").strip()
        if not email:
            raise ProviderError("lava.top: не заполнена почта для чеков")

        body = {
            "email": email,
            "offerId": offer_id,
            "currency": request.currency.upper(),
            "periodicity": "ONE_TIME",
            "buyerLanguage": "RU",
            # Lava has no order id field; utm_content is the one value that
            # makes the round trip into the webhook untouched.
            "clientUtm": {"utm_source": "telegram_bot", "utm_content": str(request.payment_id)},
            "successful_return_url": request.return_url,
            "failure_return_url": request.return_url,
            "cancel_return_url": request.return_url,
        }

        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(f"{_BASE}/api/v3/invoice", json=body, headers=headers)
        if response.status_code >= 400:
            raise ProviderError(f"lava.top: {_error(response)}")

        payload = response.json()
        url = payload.get("paymentUrl")
        if not url:
            raise ProviderError("lava.top: ответ без ссылки на оплату")

        # The offer decides the price, so this is the moment to find out that
        # the block and the catalogue disagree — before a buyer is charged
        # the wrong amount for something the bot then hands over anyway.
        total = (payload.get("amountTotal") or {}).get("amount")
        if total is not None and abs(float(total) - request.amount_minor / 100) > 0.009:
            raise ProviderError(
                f"lava.top: оффер стоит {total} {request.currency.upper()}, а в блоке указано "
                f"{request.amount_minor / 100:.2f} — поправь цену, чтобы совпадали"
            )

        return Checkout(url=url, provider_payment_id=str(payload.get("id") or "") or None)

    def locate_payment(self, *, headers: dict[str, str], raw_body: bytes, form: dict[str, str]) -> PaymentRef:
        try:
            event = json.loads(raw_body or b"{}")
        except json.JSONDecodeError:
            return PaymentRef()

        tagged = ((event.get("clientUtm") or {}).get("utm_content") or "").strip()
        try:
            return PaymentRef(payment_id=uuid.UUID(tagged))
        except (ValueError, AttributeError):
            pass
        # A renewal carries the original contract in parentContractId; the
        # one-off case is contractId itself.
        contract = event.get("contractId") or event.get("parentContractId")
        return PaymentRef(provider_payment_id=str(contract) if contract else None)

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

        # A refund used to be believed straight from `eventType`, before any
        # check at all — so an anonymous POST naming a payment id could mark
        # someone's sale refunded, and that is a one-way door: a refunded
        # payment is refused by `mark_paid` and skipped by «Я оплатил», so
        # the buyer pays at Lava and can never be delivered to. Refunds now
        # go through the same re-read as everything else.
        contract = str(event.get("contractId") or "") or provider_payment_id
        if not contract:
            raise ProviderError("lava.top: в уведомлении нет contractId")

        # Webhook authentication on lava.top is whatever the shop configured
        # in their dashboard, which we cannot see — so the notification only
        # tells us *which* invoice to look at, and the answer comes from
        # reading that invoice back with our own API key.
        return await self._read(credentials, contract, amount_minor, currency)

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
            raise ProviderError("lava.top: счёт ещё не создан")
        return await self._read(credentials, provider_payment_id, amount_minor, currency)

    async def _read(
        self, credentials: dict[str, str], contract_id: str, amount_minor: int, currency: str = ""
    ) -> WebhookResult:
        headers = self._headers(credentials)
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.get(f"{_BASE}/api/v1/invoices/{contract_id}", headers=headers)
        if response.status_code >= 400:
            raise ProviderError(f"lava.top: {_error(response)}")

        invoice = response.json()
        status = str(invoice.get("status") or "").upper()

        if status in _PAID:
            paid = (invoice.get("receipt") or {}).get("amount")
            if paid is not None and abs(float(paid) - amount_minor / 100) > 0.009:
                raise ProviderError(f"lava.top: сумма не совпадает (оплачено {paid})")
            same_currency(self.title, (invoice.get("receipt") or {}).get("currency"), currency)
            return WebhookResult(status=PaymentStatus.paid, provider_payment_id=str(contract_id))
        if status in _REFUNDED:
            return WebhookResult(status=PaymentStatus.refunded, provider_payment_id=str(contract_id))
        if status in _FAILED:
            return WebhookResult(status=PaymentStatus.failed, provider_payment_id=str(contract_id))
        return WebhookResult(status=PaymentStatus.pending, provider_payment_id=str(contract_id))


def _error(response: httpx.Response) -> str:
    try:
        payload = response.json()
    except ValueError:
        return response.text[:200]
    if isinstance(payload, dict):
        return str(payload.get("error") or payload.get("message") or payload.get("detail") or payload)[:200]
    return str(payload)[:200]
