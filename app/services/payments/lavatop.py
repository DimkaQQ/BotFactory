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
import logging
import re
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
    WebhookResult,
    same_currency,
)

_BASE = "https://gate.lava.top"
_PAID = {"COMPLETED", "SUBSCRIPTION_ACTIVE"}
_FAILED = {"FAILED", "CANCELLED"}
_REFUNDED = {"REFUNDED", "PARTIALLY_REFUNDED", "REVERSED", "CHARGEBACK"}


#: lava.top bills on named periods, not on a number of days. Values taken
#: from the published SDK (lava-top-sdk 1.1.1, `types_custom.Periodicity`);
#: `create_subscription` there is the same POST /api/v3/invoice as a one-off
#: sale with a non-ONE_TIME value, which is why there is no second code path.
_PERIODICITY = (
    (365, "PERIOD_YEAR"),
    (180, "PERIOD_180_DAYS"),
    (90, "PERIOD_90_DAYS"),
    (0, "MONTHLY"),
)


def _periodicity(extra: dict) -> str:
    """Which lava.top cycle this block is selling, if any."""
    if not extra.get("subscription"):
        return "ONE_TIME"
    chosen = str(extra.get("periodicity") or "").strip().upper()
    if chosen and chosen != "ONE_TIME":
        # Выбранный в конструкторе период из цен оффера — вернее вычисленного по дням.
        return chosen
    days = int(extra.get("period_days") or 30)
    for threshold, value in _PERIODICITY:
        if days >= threshold:
            return value
    return "MONTHLY"


logger = logging.getLogger(__name__)

#: Сколько страниц каталога читаем за один платёж: лента постраничная, а счёт ждёт покупатель.
_MAX_CATALOGUE_PAGES = 10


async def offer_prices(api_key: str) -> list[dict]:
    """Все цены офферов аккаунта — для выбора тарифа в конструкторе:
    [{offer_id, product, currency, amount, periodicity}]. `periodicity` берём как есть,
    а не вычисляем по числу дней: у оффера может быть только то, что завёл владелец."""
    # По умолчанию lava.top отдаёт только ВИДИМЫЕ товары (`feedVisibility=ONLY_VISIBLE`), а товар,
    # который продаётся только по ссылке или через API, обычно скрыт, поэтому просим все. Лента
    # постраничная: идём по `nextPage`, но не бесконечно.
    items: list[dict] = []
    async with httpx.AsyncClient(base_url=_BASE, headers={"X-Api-Key": api_key}, timeout=30) as client:
        response = await client.get(
            "/api/v2/products", params={"showAllSubscriptionPeriods": "true", "feedVisibility": "ALL"}
        )
        response.raise_for_status()
        payload = response.json()
        items += payload.get("items", [])
        for _ in range(_MAX_CATALOGUE_PAGES - 1):
            next_page = payload.get("nextPage")
            if not next_page:
                break
            response = await client.get(next_page)
            response.raise_for_status()
            payload = response.json()
            items += payload.get("items", [])
    out = []
    for item in items:
        # В схеме товар лежит под `data`, а настоящий ответ lava.top отдаёт его прямо в элементе списка
        # (`items[].id/title/offers`) — разбираем оба вида.
        data = item.get("data") or item
        for offer in data.get("offers") or []:
            for price in offer.get("prices") or []:
                out.append(
                    {
                        "product_id": data.get("id"),
                        "dynamic": bool(data.get("isDynamicPrice")),
                        "offer_id": offer["id"],
                        "product": data.get("title"),
                        "currency": price["currency"],
                        "amount": price.get("amount"),
                        "periodicity": price.get("periodicity") or "ONE_TIME",
                    }
                )
    return out


_UUID = re.compile(r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}")


def resolve_offer_id(raw: str, prices: list[dict], currency: str, periodicity: str) -> str:
    """То, что вставили в поле, — offerId, id товара или ссылка на страницу товара в кабинете
    (`app.lava.top/products/<id>/content`). Находим сам оффер.

    id товара не годится для счёта, а владельцу его проще всего найти: он виден в адресе страницы.
    Если у товара один оффер с нужной валютой и периодом — берём его; если несколько — просим
    указать offerId. Каталог недоступен (`prices` пуст) — оставляем как есть: вставленное пойдёт
    дальше и lava.top сама скажет, что не так."""
    found = _UUID.search(raw or "")
    value = found.group(0).lower() if found else (raw or "").strip()
    if not prices:
        return value
    if any(str(p["offer_id"]).lower() == value for p in prices):
        return next(str(p["offer_id"]) for p in prices if str(p["offer_id"]).lower() == value)
    own = [p for p in prices if str(p.get("product_id") or "").lower() == value]
    if not own:
        return value
    fitting = sorted({str(p["offer_id"]) for p in own if p["currency"] == currency and p["periodicity"] == periodicity})
    if len(fitting) == 1:
        return fitting[0]
    if not fitting:
        have = ", ".join(sorted({f"{p['currency']}/{p['periodicity']}" for p in own}))
        raise ProviderError(f"lava.top: у товара нет оффера с ценой {currency}/{periodicity}. Есть: {have}")
    raise ProviderError(
        "lava.top: у товара несколько офферов с такой ценой, укажи offerId вручную: " + ", ".join(fitting)
    )


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
    # Подписку ведёт сам lava.top: тот же POST /api/v3/invoice, только с
    # periodicity, отличной от ONE_TIME.
    recurring = RecurringMode.gateway
    supports_status_check = True
    credential_fields = (
        CredentialField("api_key", "API-ключ", "заголовок X-Api-Key из настроек аккаунта"),
        CredentialField("buyer_email", "Почта для чеков", "на неё Lava пришлёт чек — обычно твоя", secret=False),
    )
    block_fields = (
        CredentialField(
            "offer_id",
            "offerId товара в Lava",
            "UUID оффера или ссылка на страницу товара в lava.top (app.lava.top/products/…): оффер найдём сами",
            secret=False,
        ),
        CredentialField(
            "periodicity",
            "Период оффера (для подписки)",
            "ONE_TIME, MONTHLY, PERIOD_90_DAYS, PERIOD_180_DAYS или PERIOD_YEAR — как в оффере; пусто — по числу дней",
            secret=False,
            required=False,
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

        periodicity = _periodicity(request.extra)
        try:
            prices = await offer_prices((request.credentials.get("api_key") or "").strip())
        except (httpx.HTTPError, ValueError, KeyError):
            logger.warning("lava.top: каталог офферов недоступен, проверка периода пропущена")
            prices = None
        offer_id = resolve_offer_id(offer_id, prices or [], request.currency.upper(), periodicity)
        # У товара с динамической ценой сумма задаётся в самом счёте (`amount`), и тогда цена блока
        # и есть цена продажи; у обычного — цена берётся из оффера и обязана совпасть с блоком.
        dynamic = any(p["offer_id"] == offer_id and p.get("dynamic") for p in prices or [])
        if prices is not None and not dynamic:
            await self._check_offer_price(
                request.credentials, offer_id, request.currency.upper(), periodicity, request.amount_minor, prices=prices
            )
        body = {
            "email": email,
            "offerId": offer_id,
            "currency": request.currency.upper(),
            "periodicity": periodicity,
            **({"amount": round(request.amount_minor / 100, 2)} if dynamic else {}),
            "buyerLanguage": "RU",
            # Lava has no order id field; utm_content is the one value that
            # makes the round trip into the webhook untouched.
            "clientUtm": {"utm_source": "telegram_bot", "utm_content": str(request.payment_id)},
            # lava.top принимает только абсолютные https-адреса до 512 знаков и при любом другом ответит 400 на весь
            # счёт — тогда адреса просто не передаём.
            **(
                {
                    "successful_return_url": request.return_url,
                    "failure_return_url": request.return_url,
                    "cancel_return_url": request.return_url,
                }
                if request.return_url.startswith("https://") and len(request.return_url) <= 512
                else {}
            ),
        }

        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(f"{_BASE}/api/v3/invoice", json=body, headers=headers)
        if response.status_code >= 400:
            detail = _error(response)
            if "not found" in detail.lower():
                detail += (
                    ". Проверь, что API-ключ из того же аккаунта, где лежит товар, что у товара есть оффер "
                    "с ценой и что в поле указан offerId (или ссылка на страницу товара)"
                )
            raise ProviderError(f"lava.top: {detail}")

        payload = response.json()
        url = payload.get("paymentUrl")
        if not url:
            raise ProviderError("lava.top: ответ без ссылки на оплату")

        # The offer decides the price, so this is the moment to find out that
        # the block and the catalogue disagree — before a buyer is charged
        # the wrong amount for something the bot then hands over anyway.
        total = (payload.get("amountTotal") or {}).get("amount")
        # В схеме `amountTotal.amount` — целое число, так что копейки в нём могут быть округлены: точную
        # сверку цены делает `_check_offer_price` по каталогу, здесь ловим только явное расхождение.
        if total is not None and abs(float(total) - request.amount_minor / 100) >= 1.0:
            raise ProviderError(
                f"lava.top: оффер стоит {total} {request.currency.upper()}, а в блоке указано "
                f"{request.amount_minor / 100:.2f} — поправь цену, чтобы совпадали"
            )

        return Checkout(url=url, provider_payment_id=str(payload.get("id") or "") or None)

    @staticmethod
    async def _check_offer_price(
        credentials: dict[str, str],
        offer_id: str,
        currency: str,
        periodicity: str,
        amount_minor: int | None = None,
        prices: list[dict] | None = None,
    ) -> None:
        """У оффера должна быть цена именно в этой валюте и с этим периодом, и равная цене в блоке —
        иначе Lava вернёт невнятную ошибку (или возьмёт другую сумму) уже у покупателя. Цену берём из
        каталога (`amount` — число с копейками), а не из ответа на создание счёта, где сумма целая.
        Если каталог недоступен, проверку пропускаем: оплата из-за проверки ломаться не должна."""
        if prices is None:
            try:
                prices = await offer_prices((credentials.get("api_key") or "").strip())
            except (httpx.HTTPError, ValueError, KeyError):
                logger.warning("lava.top: каталог офферов недоступен, проверка периода пропущена")
                return
        mine = [p for p in prices if p["offer_id"] == offer_id]
        if not mine:
            return
        match = [p for p in mine if p["currency"] == currency and p["periodicity"] == periodicity]
        if not match:
            have = ", ".join(sorted({f"{p['currency']}/{p['periodicity']}" for p in mine}))
            raise ProviderError(f"lava.top: у оффера нет цены {currency}/{periodicity}. Есть: {have}")
        price = match[0].get("amount")
        if amount_minor is not None and price is not None and abs(float(price) - amount_minor / 100) > 0.009:
            raise ProviderError(
                f"lava.top: оффер стоит {price} {currency}, а в блоке указано {amount_minor / 100:.2f} — "
                "поправь цену, чтобы совпадали"
            )

    async def cancel_subscription(self, *, credentials: dict[str, str], contract_id: str) -> bool:
        """DELETE /api/v1/subscriptions — contractId ПЕРВОГО платежа подписки. 404 — её уже нет."""
        email = (credentials.get("buyer_email") or "").strip()
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.delete(
                f"{_BASE}/api/v1/subscriptions",
                params={"contractId": contract_id, "email": email},
                headers=self._headers(credentials),
            )
        if response.status_code in (200, 204, 404):
            return True
        raise ProviderError(f"lava.top: {_error(response)}")

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
        # Продление несёт НОВЫЙ contractId и контракт первой покупки в parentContractId; а у нас
        # сохранён именно первый. Поэтому родитель — первым, иначе продления не находят платёж.
        contract = event.get("parentContractId") or event.get("contractId")
        return PaymentRef(provider_payment_id=str(contract) if contract else None)

    def error_body(self, *, form: dict[str, str], raw_body: bytes, found: bool) -> tuple[str, str] | None:
        """Событие без нашего платежа подтверждаем кодом 200.

        Возвраты (`refund.success`) и чарджбэки приходят в другой структуре и без
        `contractId`, и привязать их к платежу нечем. На 4xx/5xx lava.top повторяет
        доставку 19 раз; такие события разбираются вручную (deploy/runbook.md).
        """
        if found:
            return None
        try:
            event = json.loads(raw_body or b"{}")
            kind = str(event.get("eventType") or event.get("event_type") or "")
        except (json.JSONDecodeError, AttributeError):
            return None
        logger.warning("lava.top event %r has no payment of ours attached", kind)
        return "{}", "application/json"

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
        kind = str(event.get("eventType") or "")
        parent = str(event.get("parentContractId") or "")

        if kind == "subscription.cancelled":
            # Подписчик отменил подписку на стороне lava.top: оплаченный период он дослушивает, дальше
            # списаний не будет. Телу уведомления не верим — спрашиваем у lava.top, отменена ли она.
            first = parent or provider_payment_id or contract
            if await self._subscription_cancelled(credentials, first):
                return WebhookResult(
                    status=PaymentStatus.pending,
                    provider_payment_id=provider_payment_id,
                    meta={"gateway_unsubscribed": True},
                )
            return WebhookResult(status=PaymentStatus.pending, provider_payment_id=provider_payment_id)

        if parent and kind.startswith("subscription.recurring.payment"):
            # Продление: новый контракт (contractId) под родительским. Читаем ЕГО, а платёж у нас
            # остаётся первым — `provider_payment_id` не трогаем, иначе потеряем контракт для отмены.
            renewal = await self._read(credentials, contract, amount_minor, currency)
            if renewal.status is PaymentStatus.paid:
                return WebhookResult(
                    status=PaymentStatus.paid,
                    provider_payment_id=provider_payment_id or parent,
                    meta={"gateway_renewal": contract},
                )
            # Неудачное продление — повод для лога, а не для отмены уже оплаченного заказа.
            logger.warning("lava.top: продление %s подписки %s не прошло (%s)", contract, parent, renewal.status.value)
            return WebhookResult(status=PaymentStatus.pending, provider_payment_id=provider_payment_id or parent)

        # Webhook authentication on lava.top is whatever the shop configured
        # in their dashboard, which we cannot see — so the notification only
        # tells us *which* invoice to look at, and the answer comes from
        # reading that invoice back with our own API key.
        return await self._read(credentials, contract, amount_minor, currency)

    async def _subscription_cancelled(self, credentials: dict[str, str], contract_id: str) -> bool:
        """GET /api/v1/subscriptions/{id}: `subscriptionStatus == CANCELLED`."""
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.get(
                f"{_BASE}/api/v1/subscriptions/{contract_id}", headers=self._headers(credentials)
            )
        if response.status_code == 404:
            return False
        if response.status_code >= 400:
            raise ProviderError(f"lava.top: {_error(response)}")
        return str((response.json() or {}).get("subscriptionStatus") or "").upper() == "CANCELLED"

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
            response = await client.get(f"{_BASE}/api/v2/invoices/{contract_id}", headers=headers)
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
