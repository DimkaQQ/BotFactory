"""ioka — Казахстан, обычный REST.

The friendliest gateway on this list: `POST /v2/orders` with one header and
the answer already contains `checkout_url`. Amounts are minor units, which
is what everything here is stored in, so nothing is converted.

**The callback is never believed on its own.** ioka signs its webhooks with
an HMAC over a *canonical* JSON — the body re-serialised with its keys
sorted, which is a JavaScript-shaped rule that is easy to reproduce almost
right and impossible to notice when you have. The one published client that
attempts it has the check commented out with "TODO: signature generation
algo". Rather than ship a signature check that might silently accept
anything, this adapter treats the webhook the way it treats ЮKassa's — as a
nudge — and asks `GET /v2/orders/{id}` what actually happened. The API
answer is stronger than any signature we could verify, and it also means a
shop that never configures a webhook still works: the buyer's «Я оплатил»
runs the same read.

Orders are created with `capture_method: AUTO`, so a paid order goes
straight to `PAID` rather than sitting at `ON_HOLD` — a hold is money
blocked on the card, not money taken, and goods must never go out for one.

Written against the published clients github.com/RiON69/ioka_api (typed
models: statuses, currencies, the order fields and the `amount >= 100`
floor), github.com/aruaycodes/myiokalib and github.com/boomfly/meteor-ioka
(hosts, header, endpoints) rather than from memory.
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

_PROD = "https://api.ioka.kz/v2"
_TEST = "https://stage-api.ioka.kz/v2"

#: OrderStatusEnum, as the published client types it.
_PAID = "PAID"
_FAILED = {"EXPIRED"}
_REFUNDED = {"REFUNDED", "PARTIALLY_REFUNDED", "REVERSED"}
#: UNPAID — nobody has paid yet. ON_HOLD — money blocked but not taken; we
#: ask for AUTO capture so it should never appear, and if it does it is
#: still not a sale.
_PENDING = {"UNPAID", "ON_HOLD"}

#: The gateway refuses anything smaller: 100 tiyn = 1 ₸.
_MIN_AMOUNT = 100


class IokaProvider(ProviderDefaults):
    slug = "ioka"
    title = "ioka"
    hint = (
        "API-ключ — в кабинете ioka, «Настройки → API». Уведомления мы перепроверяем запросом в ioka, "
        "поэтому подписывать их не нужно; вебхук в кабинете можно и не настраивать — бот всё равно "
        "спросит статус сам. Принимает тенге, рубли и доллары."
    )
    currencies = ("KZT", "RUB", "USD")
    supports_status_check = True
    credential_fields = (CredentialField("api_key", "API-ключ", "секретный ключ магазина"),)

    @staticmethod
    def _key(credentials: dict[str, str]) -> str:
        api_key = (credentials.get("api_key") or "").strip()
        if not api_key:
            raise ProviderError("ioka: не заполнен API-ключ")
        return api_key

    @staticmethod
    def _base(is_test: bool) -> str:
        return _TEST if is_test else _PROD

    async def _call(self, method: str, url: str, api_key: str, body: dict | None = None):
        """Returns whatever ioka answered — a list for a search, an object
        everywhere else. Kept as-is rather than coerced to a dict, because a
        search flattened to `{}` would read as "no such order"."""
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.request(
                method, url, json=body, headers={"API-KEY": api_key, "Content-Type": "application/json"}
            )
        if response.status_code >= 400:
            raise ProviderError(f"ioka: {_error(response)}")
        try:
            return response.json()
        except ValueError as exc:
            raise ProviderError("ioka: непонятный ответ") from exc

    async def create_checkout(self, request: CheckoutRequest) -> Checkout:
        api_key = self._key(request.credentials)
        if request.amount_minor < _MIN_AMOUNT:
            raise ProviderError("ioka: минимальная сумма заказа — 1 единица валюты")

        payload = await self._call(
            "POST",
            f"{self._base(request.is_test)}/orders",
            api_key,
            {
                # Minor units — tiyn for the tenge, exactly as stored.
                "amount": request.amount_minor,
                "currency": request.currency.upper(),
                # One-stage: a paid order becomes PAID, not ON_HOLD.
                "capture_method": "AUTO",
                "external_id": str(request.payment_id),
                "description": (request.description or "Оплата")[:255],
                "back_url": request.return_url,
                "success_url": request.return_url,
                "failure_url": request.return_url,
            },
        )

        # `POST /orders` wraps the order; `GET /orders/{id}` returns it bare.
        order = _unwrap(payload)
        if order is None:
            raise ProviderError("ioka: ответ без заказа")
        url = order.get("checkout_url")
        order_id = order.get("id")
        if not url or not order_id:
            raise ProviderError("ioka: ответ без ссылки на оплату")

        return Checkout(url=str(url), provider_payment_id=str(order_id), meta={"is_test": request.is_test})

    def locate_payment(self, *, headers: dict[str, str], raw_body: bytes, form: dict[str, str]) -> PaymentRef:
        try:
            event = json.loads(raw_body or b"{}")
        except json.JSONDecodeError:
            return PaymentRef()
        if not isinstance(event, dict):
            return PaymentRef()

        # The event nests the order under one of a couple of names depending
        # on which of them fired, so look in the envelope and one level in.
        places = [event]
        for key in ("order", "payment", "object", "data"):
            nested = event.get(key)
            if isinstance(nested, dict):
                places.append(nested)

        for place in places:
            raw = place.get("external_id")
            if raw:
                try:
                    return PaymentRef(payment_id=uuid.UUID(str(raw)))
                except ValueError:
                    continue
        for place in places:
            order_id = place.get("order_id") or place.get("id")
            if order_id:
                return PaymentRef(provider_payment_id=str(order_id))
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
        # Nothing in the request body is trusted — not the status, not the
        # amount. The order is re-read and only that answer counts.
        return await self._read(
            credentials, payment_id, provider_payment_id, amount_minor, (meta or {}).get("is_test"), currency
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
        return await self._read(
            credentials, payment_id, provider_payment_id, amount_minor, meta.get("is_test"), currency
        )

    async def _read(
        self,
        credentials: dict[str, str],
        payment_id: uuid.UUID,
        order_id: str | None,
        amount_minor: int,
        is_test,
        currency: str = "",
    ) -> WebhookResult:
        api_key = self._key(credentials)
        # Which ledger the order lives on is decided when it is created, so it
        # is read back from the payment rather than from the shop's current
        # setting — the switch can be flipped while a buyer is paying.
        base = self._base(bool(is_test))

        if order_id:
            order = _unwrap(await self._call("GET", f"{base}/orders/{order_id}", api_key))
        else:
            # No id kept: find it by the id we gave ioka ourselves.
            order = _unwrap(await self._call("GET", f"{base}/orders?external_id={payment_id}", api_key))
        if order is None:
            # Nothing to read yet — an order the buyer never opened.
            return WebhookResult(status=PaymentStatus.pending)

        status = str(order.get("status") or "").upper()
        remote_id = str(order["id"]) if order.get("id") else (str(order_id) if order_id else None)

        if status == _PAID:
            amount = order.get("amount")
            if not isinstance(amount, int) or amount != amount_minor:
                raise ProviderError(f"ioka: сумма не совпадает (в заказе {amount})")
            same_currency(self.title, order.get("currency"), currency)
            return WebhookResult(status=PaymentStatus.paid, provider_payment_id=remote_id)

        if status in _REFUNDED:
            return WebhookResult(status=PaymentStatus.refunded, provider_payment_id=remote_id)
        if status in _FAILED:
            return WebhookResult(status=PaymentStatus.failed, provider_payment_id=remote_id)
        if status in _PENDING:
            return WebhookResult(status=PaymentStatus.pending, provider_payment_id=remote_id)
        # An unfamiliar status is not a sale. Said out loud rather than
        # guessed at, so a new one shows up in the log instead of silently
        # counting as "not paid forever".
        raise ProviderError(f"ioka: неизвестный статус заказа {status!r}")


def _unwrap(payload) -> dict | None:
    """The order itself, whichever shape it arrived in.

    `POST /orders` wraps it under "order", `GET /orders/{id}` returns it
    bare, and a search by external_id returns a page — as a bare list on its
    own or under one of the usual names.
    """
    if isinstance(payload, list):
        payload = payload[0] if payload else None
    if not isinstance(payload, dict):
        return None
    if isinstance(payload.get("order"), dict):
        return payload["order"]
    for key in ("orders", "items", "data"):
        candidate = payload.get(key)
        if isinstance(candidate, list) and candidate and isinstance(candidate[0], dict):
            return candidate[0]
    return payload if payload.get("id") or payload.get("status") else None


def _error(response: httpx.Response) -> str:
    try:
        payload = response.json()
    except ValueError:
        return response.text[:200] or f"HTTP {response.status_code}"
    if isinstance(payload, dict):
        return str(payload.get("message") or payload.get("code") or payload)[:200]
    return f"HTTP {response.status_code}"
