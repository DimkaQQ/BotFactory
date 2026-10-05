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

Сверено с официальной OpenAPI-схемой ioka v2.12.0 (docs/ioka-api.json): единственная валюта — тенге,
`API-KEY` выдаётся по Client ID и Client Secret и ИСТЕКАЕТ (`POST /v2/auth/token` → `api_key`,
`expiry_date`), вебхук регистрируется методом `POST /v2/webhooks`, у заказа нет статуса «возврат» —
возврат виден только в платежах (`refunded_amount`).

Written against the published clients github.com/RiON69/ioka_api (typed
models: statuses, currencies, the order fields and the `amount >= 100`
floor), github.com/aruaycodes/myiokalib and github.com/boomfly/meteor-ioka
(hosts, header, endpoints) rather than from memory.
"""

from __future__ import annotations

import json
import logging
import time
import uuid
from datetime import datetime

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
    same_currency,
)

_PROD = "https://api.ioka.kz/v2"
_TEST = "https://stage-api.ioka.kz/v2"

#: OrderStatusEnum, as the published client types it.
logger = logging.getLogger(__name__)

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
        "Client ID и Client Secret — в кабинете ioka, «Настройки → API»: по ним мы сами получаем рабочий "
        "ключ и обновляем его, когда он истекает. Уведомления мы перепроверяем запросом в ioka, поэтому "
        "подписывать их не нужно; при первой оплате мы сами добавляем в ioka вебхук на наш адрес, если "
        "его там ещё нет. Принимает только тенге. Тестовая среда (stage) выдаётся менеджером ioka."
    )
    currencies = ("KZT",)
    region = "ca"
    # Рекуррент по сохранённой карте. Карта сохраняется на стороне ioka —
    # PAN к нам не попадает: покупатель либо ставит галочку на странице
    # оплаты, либо проходит отдельную форму привязки (POST /v2/customers →
    # checkout_url). card_id и customer_id приходят в payer оплаченного
    # заказа; списание — POST /v2/orders/{id}/payments/card.
    recurring = RecurringMode.token
    supports_status_check = True
    credential_fields = (
        CredentialField("client_id", "Client ID", "идентификатор клиента из кабинета ioka", secret=False),
        CredentialField("client_secret", "Client Secret", "секрет клиента из кабинета ioka"),
        CredentialField(
            "api_key", "API-ключ (устаревший способ)", "нужен, только если Client ID/Secret не заданы; ключ истекает",
            required=False,
        ),
    )

    #: Рабочий ключ по Client ID/Secret живёт ограниченное время; держим его в памяти процесса.
    _tokens: dict[tuple[str, str], tuple[str, float]] = {}

    async def _api_key(self, credentials: dict[str, str], is_test: bool, *, fresh: bool = False) -> str:
        client_id = (credentials.get("client_id") or "").strip()
        secret = (credentials.get("client_secret") or "").strip()
        if client_id and secret:
            slot = (self._base(is_test), client_id)
            cached = self._tokens.get(slot)
            if cached and not fresh and cached[1] - time.time() > 60:
                return cached[0]
            async with httpx.AsyncClient(timeout=30) as client:
                response = await client.post(
                    f"{self._base(is_test)}/auth/token", json={"client_id": client_id, "client_secret": secret}
                )
            if response.status_code >= 400:
                raise ProviderError(f"ioka: не удалось получить ключ по Client ID/Secret ({_error(response)})")
            data = response.json()
            key = str(data.get("api_key") or "")
            if not key:
                raise ProviderError("ioka: в ответе нет api_key")
            try:
                expires = datetime.fromisoformat(str(data["expiry_date"]).replace("Z", "+00:00")).timestamp()
            except (KeyError, ValueError):
                expires = time.time() + 600  # срок неизвестен — обновим скоро
            if len(self._tokens) > 500:
                self._tokens.clear()
            self._tokens[slot] = (key, expires)
            return key
        legacy = (credentials.get("api_key") or "").strip()
        if not legacy:
            raise ProviderError("ioka: не заполнены Client ID и Client Secret")
        return legacy

    @staticmethod
    def _base(is_test: bool) -> str:
        return _TEST if is_test else _PROD

    async def _call(self, method: str, path: str, credentials: dict[str, str], is_test: bool, body: dict | None = None):
        """Returns whatever ioka answered — a list for a search, an object
        everywhere else. Kept as-is rather than coerced to a dict, because a
        search flattened to `{}` would read as "no such order".

        401 с ключом, полученным по Client ID/Secret, — ключ мог истечь раньше срока: берём новый и
        повторяем запрос один раз."""
        for attempt in (0, 1):
            api_key = await self._api_key(credentials, is_test, fresh=bool(attempt))
            async with httpx.AsyncClient(timeout=30) as client:
                response = await client.request(
                    method,
                    f"{self._base(is_test)}{path}",
                    json=body,
                    headers={"API-KEY": api_key, "Content-Type": "application/json"},
                )
            if response.status_code == 401 and attempt == 0 and credentials.get("client_id"):
                continue
            break
        if response.status_code >= 400:
            raise ProviderError(f"ioka: {_error(response)}")
        try:
            return response.json()
        except ValueError as exc:
            raise ProviderError("ioka: непонятный ответ") from exc

    #: События, о которых мы хотим знать (остальные — расщепление, рассрочки, выплаты — нам не нужны).
    _WEBHOOK_EVENTS = [
        "PAYMENT_CAPTURED", "PAYMENT_DECLINED", "PAYMENT_CANCELLED", "CAPTURE_DECLINED", "ORDER_EXPIRED",
        "REFUND_APPROVED",
    ]  # fmt: skip
    _webhooks_ready: set[tuple[str, str]] = set()

    async def _ensure_webhook(self, credentials: dict[str, str], is_test: bool) -> None:
        """Вебхук ioka заводится запросом (`POST /v2/webhooks`), а не только в кабинете: если на наш адрес
        его ещё нет — добавляем, чтобы оплата доходила без «Я оплатил». Чужие вебхуки магазина не
        трогаем. Не получилось — не страшно: статус по кнопке «Я оплатил» читается всё равно."""
        who = (credentials.get("client_id") or credentials.get("api_key") or "").strip()
        slot = (self._base(is_test), who)
        if slot in self._webhooks_ready:
            return
        url = f"{get_settings().public_base_url.rstrip('/')}/webhook/pay/ioka"
        try:
            existing = await self._call("GET", "/webhooks", credentials, is_test)
            hooks = existing if isinstance(existing, list) else (existing or {}).get("items") or []
            if not any(isinstance(h, dict) and h.get("url") == url for h in hooks):
                await self._call("POST", "/webhooks", credentials, is_test, {"url": url, "events": self._WEBHOOK_EVENTS})
                logger.info("ioka: вебхук %s зарегистрирован", url)
            if len(self._webhooks_ready) > 1000:
                self._webhooks_ready.clear()
            self._webhooks_ready.add(slot)
        except ProviderError as exc:
            logger.warning("ioka: не удалось проверить/добавить вебхук: %s", exc)

    async def create_checkout(self, request: CheckoutRequest) -> Checkout:
        if request.currency.upper() != "KZT":
            raise ProviderError("ioka принимает только тенге (KZT)")
        if request.amount_minor < _MIN_AMOUNT:
            raise ProviderError("ioka: минимальная сумма заказа — 1 единица валюты")
        await self._api_key(request.credentials, request.is_test)  # ошибка ключей — сразу и понятно
        await self._ensure_webhook(request.credentials, request.is_test)

        customer_id = ""
        if request.extra.get("subscription"):
            customer_id = await self._customer(
                request.credentials, request.is_test, request.telegram_user_id, request.payment_id
            )

        payload = await self._call(
            "POST",
            "/orders",
            request.credentials,
            request.is_test,
            {
                # Minor units — tiyn for the tenge, exactly as stored.
                "amount": request.amount_minor,
                "currency": request.currency.upper(),
                # One-stage: a paid order becomes PAID, not ON_HOLD.
                "capture_method": "AUTO",
                "external_id": str(request.payment_id),
                "description": (request.description or "Оплата")[:255],
                # A saved card belongs to a customer, so a subscription needs
                # one to exist before the first payment — otherwise there is
                # nothing for the card to attach to and the renewal has no
                # handle to charge.
                **(
                    {"customer_id": customer_id}
                    if customer_id
                    else {}
                ),
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
        # amount. The order is re-read and only that answer counts. Из тела берём лишь название события:
        # оно говорит, ЧТО перепроверить (возврат виден не в заказе, а в платежах).
        try:
            event = str((json.loads(raw_body or b"{}") or {}).get("event") or "")
        except (json.JSONDecodeError, AttributeError):
            event = ""
        return await self._read(
            credentials, payment_id, provider_payment_id, amount_minor, (meta or {}).get("is_test"), currency,
            refund_event=event == "REFUND_APPROVED",
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

    async def _customer(self, credentials: dict[str, str], is_test: bool, telegram_user_id: int | None, payment_id) -> str:
        """The ioka customer this buyer's saved card will belong to.

        Keyed on the Telegram user id, so the same person coming back gets
        the same customer rather than a new one per order — which is what
        makes a card saved last month usable this month. A failure here is
        not fatal: the order is created without a customer and the
        subscription falls back to re-invoicing.
        """
        external_id = str(telegram_user_id or payment_id)
        try:
            found = await self._call("POST", "/customers", credentials, is_test, {"external_id": external_id})
        except ProviderError as exc:
            # Already exists is the common case on a second subscription.
            logger.info("ioka: could not create customer %s (%s)", external_id, exc)
            return ""
        customer = _unwrap(found) or (found if isinstance(found, dict) else {})
        return str(customer.get("id") or "")

    def recurring_setup(self, settled: dict) -> RecurringSetup | None:
        card = (settled or {}).get("ioka_card_id")
        if not card:
            return None
        return RecurringSetup(token=str(card), customer=str((settled or {}).get("ioka_customer_id") or ""))

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
        """Two calls: an order for this period, then pay it with the saved card.

        `capture_method: AUTO` on purpose — under MANUAL an APPROVED response
        is only an authorisation (`captured_amount: 0`) and the money has not
        moved, which for a renewal nobody is watching would mean handing over
        a month for a hold.
        """
        if not setup.token:
            raise ProviderError("ioka: нет сохранённой карты")
        is_test = bool(is_test)

        created = _unwrap(
            await self._call(
                "POST",
                "/orders",
                credentials,
                is_test,
                {
                    "amount": amount_minor,
                    "currency": currency.upper(),
                    "capture_method": "AUTO",
                    "external_id": str(payment_id),
                    "description": (description or "Продление подписки")[:255],
                    **({"customer_id": setup.customer} if setup.customer else {}),
                },
            )
        )
        order_id = (created or {}).get("id")
        if not order_id:
            raise ProviderError("ioka: не удалось создать заказ на продление")

        paid = await self._call(
            "POST", f"/orders/{order_id}/payments/card", credentials, is_test, {"card_id": setup.token}
        )
        payment = _unwrap(paid) or (paid if isinstance(paid, dict) else {})
        status = str(payment.get("status") or "").upper()

        if status == "CAPTURED":
            # Списано — это и есть оплата (при AUTO платёж сразу попадает сюда).
            return WebhookResult(status=PaymentStatus.paid, provider_payment_id=str(order_id))

        if status == "APPROVED":
            # APPROVED — холд: деньги заблокированы, но не списаны (ioka сама спишет
            # через 48 часов, если не подтвердить). Товар за холд не выдаём, пока не
            # видно списанной суммы.
            captured = payment.get("captured_amount")
            if isinstance(captured, int) and captured > 0:
                return WebhookResult(status=PaymentStatus.paid, provider_payment_id=str(order_id))
            return WebhookResult(
                status=PaymentStatus.pending,
                provider_payment_id=str(order_id),
                meta={"decline": "деньги только заблокированы, а не списаны"},
            )

        if status == "DECLINED":
            error = payment.get("error") or {}
            reason = error.get("message") or error.get("code") or "банк отклонил списание"
            return WebhookResult(
                status=PaymentStatus.failed, provider_payment_id=str(order_id), meta={"decline": str(reason)}
            )
        return WebhookResult(status=PaymentStatus.pending, provider_payment_id=str(order_id))

    async def _fully_refunded(self, credentials: dict[str, str], is_test: bool, order_id: str, amount_minor: int) -> bool:
        """У заказа нет статуса «возврат»: возвращённая сумма лежит в его платежах (`refunded_amount`).
        Частичный возврат заказ не закрывает — вернули всё, тогда да."""
        payments = await self._call("GET", f"/orders/{order_id}/payments", credentials, is_test)
        if isinstance(payments, dict):
            payments = payments.get("items") or payments.get("payments") or [payments]
        refunded = sum(
            int(p.get("refunded_amount") or 0) for p in payments if isinstance(p, dict)
        )
        return refunded >= amount_minor

    def error_body(self, *, form: dict[str, str], raw_body: bytes, found: bool) -> tuple[str, str] | None:
        """Уведомление про чужой заказ магазина (его создали не мы) подтверждаем кодом 200: вебхук ioka
        приходит на ВСЕ заказы магазина, а ответ 4xx заставил бы ioka повторять его без конца."""
        if found:
            return None
        return "{}", "application/json"

    async def _read(
        self,
        credentials: dict[str, str],
        payment_id: uuid.UUID,
        order_id: str | None,
        amount_minor: int,
        is_test,
        currency: str = "",
        *,
        refund_event: bool = False,
    ) -> WebhookResult:
        # Which ledger the order lives on is decided when it is created, so it
        # is read back from the payment rather than from the shop's current
        # setting — the switch can be flipped while a buyer is paying.
        is_test = bool(is_test)

        if order_id:
            order = _unwrap(await self._call("GET", f"/orders/{order_id}", credentials, is_test))
        else:
            # No id kept: find it by the id we gave ioka ourselves.
            order = _unwrap(await self._call("GET", f"/orders?external_id={payment_id}", credentials, is_test))
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
            if refund_event and remote_id and await self._fully_refunded(credentials, is_test, remote_id, amount_minor):
                return WebhookResult(status=PaymentStatus.refunded, provider_payment_id=remote_id)
            payer = order.get("payer") or {}
            notes = {}
            if payer.get("card_id"):
                notes["ioka_card_id"] = str(payer["card_id"])
                notes["ioka_customer_id"] = str(payer.get("customer_id") or "")
                notes["ioka_is_test"] = bool(is_test)
            return WebhookResult(status=PaymentStatus.paid, provider_payment_id=remote_id, meta=notes)

        if status in _REFUNDED:
            return WebhookResult(status=PaymentStatus.refunded, provider_payment_id=remote_id)
        if status in _FAILED:
            return WebhookResult(status=PaymentStatus.failed, provider_payment_id=remote_id)
        if status in _PENDING:
            return WebhookResult(status=PaymentStatus.pending, provider_payment_id=remote_id)
        # An unfamiliar status is not a sale; it is logged so a new one is noticed.
        # Не теряем оплату из-за незнакомого статуса: ошибка (400) заставила бы ioka
        # повторять уведомление, а продавец остался бы без заказа.
        logger.warning("ioka: неизвестный статус заказа %r — считаю платёж ещё не завершённым", status)
        return WebhookResult(status=PaymentStatus.pending, provider_payment_id=remote_id)


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
