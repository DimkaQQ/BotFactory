"""The shape every payment provider adapter has to fit.

Adding a provider is one module implementing `PaymentProvider` plus a line
in `registry.py` — deliberately, because the list of providers people ask
for is long (Robokassa, ЮKassa, Prodamus, Lava, LifePay, CKassa, PayMaster,
Stripe…) and they all do the same three things: build a checkout link,
call us back, and be verifiable.

`credential_fields` doubles as the UI contract: the constructor renders the
provider's settings form straight from it, so a new provider needs no
frontend work at all.
"""

from __future__ import annotations

import enum
import re
import uuid
from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal
from typing import Protocol

from app.models.payment import PaymentStatus


@dataclass(frozen=True)
class CredentialField:
    key: str
    label: str
    hint: str = ""
    #  Secret values are write-only in the API: never sent back to the
    #  browser, only replaced.
    secret: bool = True
    #  Необязательные поля (чеки, тестовые пароли) не мешают кассе считаться настроенной.
    required: bool = True


@dataclass(frozen=True)
class CheckoutRequest:
    payment_id: uuid.UUID
    invoice_no: int
    amount_minor: int
    currency: str
    description: str
    # Where the payer lands after paying (a page of ours, not the provider's).
    return_url: str
    is_test: bool
    credentials: dict[str, str]
    # Per-block settings, straight from the payment block's content: what
    # varies per product rather than per shop (Lava's offer id, the link a
    # "pay by link" block points at). Credentials are the shop; this is the
    # thing being sold.
    extra: dict = field(default_factory=dict)
    # Only Telegram Stars needs this: its "checkout" is an invoice minted by
    # the selling bot itself, so the adapter has to speak as that bot.
    bot_token: str | None = None
    telegram_user_id: int | None = None
    # Контакт покупателя для чека 54-ФЗ — если он известен (см. `receipt_contact`). Сейчас ни один
    # шаг диалога его не собирает, поэтому обычно пусто и чек уходит на почту продавца.
    buyer_email: str | None = None
    buyer_phone: str | None = None


@dataclass(frozen=True)
class PaymentRef:
    """Which payment a webhook is about, before anything is trusted."""

    payment_id: uuid.UUID | None = None
    invoice_no: int | None = None
    # For providers that carry no order id of their own (LIFE PAY), the only
    # handle is the id they gave us when the invoice was created.
    provider_payment_id: str | None = None


@dataclass(frozen=True)
class Checkout:
    """Where to send the payer, plus whatever the provider called this
    payment — several of them mint an id at creation time and then use it,
    not our order id, as the only reference in the callback."""

    url: str
    provider_payment_id: str | None = None
    meta: dict = field(default_factory=dict)


class RecurringMode(str, enum.Enum):
    """How — and whether — this gateway can take money a second time.

    Three genuinely different mechanisms, and the difference decides what the
    shop owner is actually selling, so it is carried explicitly rather than
    inferred:

    * `gateway` — the gateway runs the subscription itself. We create it once
      and it charges on its own schedule, retries its own declines, and lets
      the buyer cancel on its own surface. Nothing about the card ever
      reaches us. Telegram Stars and Stripe work this way.
    * `token` — the first payment saves a payment method and hands back a
      handle; *we* initiate every later charge with it, on our own schedule.
      ЮKassa, CloudPayments and Т-Банк work this way. More power and more
      responsibility: the retry policy, the dunning and the "period ended"
      decision are ours.
    * `none` — the integration cannot charge again by any means, so a
      subscription here is a reminder plus a fresh invoice each period.
    """

    none = "none"
    gateway = "gateway"
    token = "token"


@dataclass(frozen=True)
class RecurringSetup:
    """What a first payment has to carry so a later one can be charged.

    Returned by the adapter from its own reading of a settled payment, and
    stored against the subscription. `token` is a handle to a payment method
    held by the gateway — it is useless without the shop's own API keys, but
    it moves money when combined with them, so it is stored encrypted.
    """

    token: str
    #: Some gateways need the customer handle they minted alongside the
    #: token (CloudPayments' AccountId, Т-Банк's CustomerKey).
    customer: str = ""


@dataclass(frozen=True)
class WebhookResult:
    status: PaymentStatus
    provider_payment_id: str | None = None
    # Some providers demand an exact acknowledgement body (Robokassa wants
    # "OK{InvId}"), and treat anything else as a failed delivery worth
    # retrying — so the adapter, not the router, decides what we answer.
    response_body: str = "OK"
    response_content_type: str = "text/plain"
    meta: dict = field(default_factory=dict)


class ProviderError(Exception):
    """The provider refused us — bad credentials, malformed request, or a
    signature that doesn't check out."""


class PaymentProvider(Protocol):
    slug: str
    title: str
    #: Human note shown under the provider's settings form.
    hint: str
    #: Currencies the adapter is known to handle, uppercase ISO codes.
    currencies: tuple[str, ...]
    #: Which of `REGIONS` this gateway belongs to. Purely a catalogue
    #: concern — nothing in the payment flow reads it — but a flat list of
    #: nineteen providers is a wall, and "which of these works for a shop in
    #: Almaty" is the first question anyone actually has.
    region: str
    credential_fields: tuple[CredentialField, ...]
    #: True when `check_status` can ask the provider outright whether a
    #: payment went through. Drives the "Я оплатил" button in the bot: with a
    #: status check it re-reads the payment; without one there is nothing to
    #: read, and the buyer's claim goes to the shop owner to confirm.
    supports_status_check: bool
    #: Per-block fields the constructor asks for on the payment block itself
    #: (as opposed to once per shop in the settings form).
    block_fields: tuple[CredentialField, ...]
    #: Whether this provider notifies us over `/webhook/pay/{slug}` at all.
    uses_callback: bool
    #: Отправляем ли мы адрес уведомления сами, в каждом счёте. Отдельно от
    #: `uses_callback`: тот отвечает «шлюз нам звонит», а этот — «нужно ли
    #: владельцу что-то вписывать у себя в кабинете». Настройки показывали
    #: обе подсказки сразу — «подставляем сами» и тут же «укажи в кабинете»,
    #: — и человек шёл вписывать адрес туда, где он уже есть.
    sends_own_callback_url: bool
    #: Whether "тестовый режим" means anything for this provider.
    has_test_mode: bool
    #: Whether this gateway can be charged a second time, and by whom.
    recurring: RecurringMode

    async def create_checkout(self, request: CheckoutRequest) -> Checkout:
        """Create the payment on the provider's side and return where to
        send the payer."""
        ...

    def locate_payment(self, *, headers: dict[str, str], raw_body: bytes, form: dict[str, str]) -> PaymentRef:
        """Identify which payment a callback refers to — parsing only, no
        trust: the payment is loaded by this reference and only then are its
        credentials used to verify the callback really came from the
        provider."""
        ...

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
        """Check the callback's authenticity and say what it means.

        Where the provider signs its callbacks (Prodamus), that signature is
        the proof. Where it doesn't (ЮKassa, PayMaster, LIFE PAY), the
        callback is only a hint: the adapter calls the provider's API back
        and believes the answer, not the request body.

        `meta` is the payment's stored notes, for the one protocol that is a
        conversation rather than a single message: Payme asks about the same
        transaction repeatedly and expects the same timestamps back every
        time. Anything an adapter returns in `WebhookResult.meta` is written
        there, so the next call can read it."""
        ...

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
        """Ask the provider where this payment stands, with no callback
        involved — what the buyer's "Я оплатил" tap runs.

        Only meaningful when `supports_status_check` is True; a webhook can
        be lost or delayed, and a buyer who has already paid should not have
        to wait for a retry schedule to get what they bought."""
        ...

    def error_body(self, *, form: dict[str, str], raw_body: bytes, found: bool) -> tuple[str, str] | None:
        """The body to answer a refused callback with, or None for an HTTP
        error. See `ProviderDefaults.error_body`."""
        ...

    def recurring_setup(self, settled: dict) -> RecurringSetup | None:
        """Pull the saved-payment-method handle out of a settled payment.

        Only meaningful when `recurring is RecurringMode.token`. `settled` is
        whatever the adapter itself put in `WebhookResult.meta`, so no
        provider-shaped JSON escapes its own module."""
        ...

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
        """Take the next period's money with nobody present.

        Only for `RecurringMode.token`. Returns the same verdict shape as a
        webhook, so a successful charge settles through exactly the same path
        as a payment the buyer made by hand — one place where an order
        becomes paid, whatever prompted it."""
        ...

    async def cancel_subscription(self, *, credentials: dict[str, str], contract_id: str) -> bool:
        """Остановить подписку на стороне шлюза (только `RecurringMode.gateway`).

        True — остановлена или её там уже нет; False — шлюз так не умеет. Ошибка
        связи — исключение: вызывающий не должен считать подписку снятой."""
        ...


class ProviderDefaults:
    """What most providers don't have to think about.

    Adapters inherit this and override only where they differ, so the two
    optional halves of the protocol — an on-demand status check and per-block
    fields — cost nothing to the providers that have neither.
    """

    supports_status_check = False
    #: False for the providers that never call `/webhook/pay/...` — Stars
    #: (Telegram delivers on the bot's own webhook), pay-by-link and the test
    #: provider. Drives whether the settings form shows a callback address to
    #: paste into a merchant dashboard.
    uses_callback = True
    sends_own_callback_url = False
    #: Whether "тестовый режим" means anything here, and so whether the
    #: settings form offers the switch. Kept separate from `uses_callback`:
    #: tying the two together left Processing.kz — which has no callback but
    #: does have its own test gateway — with no way to be switched to the
    #: live one, since `payment_is_test` defaults to True.
    has_test_mode = True
    #: Most providers are country-specific and say so; "works everywhere" is
    #: the safe default for the handful that genuinely do.
    region = "global"
    #: Assume no. An adapter claiming recurring it does not have would sell a
    #: shop a subscription business and charge their customers once.
    recurring = RecurringMode.none
    block_fields: tuple[CredentialField, ...] = ()

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
        raise ProviderError(f"{getattr(self, 'title', 'Провайдер')}: статус платежа так не проверяется")

    def error_body(self, *, form: dict[str, str], raw_body: bytes, found: bool) -> tuple[str, str] | None:
        """What to answer a callback we are refusing.

        `None` — the default — means the router answers with an HTTP error,
        which is what almost every provider reads as "try again later".
        Click and Payme are the exceptions: they answer *everything* with
        200 and put the refusal in the body, and an HTTP error to them means
        a broken integration, not a rejected payment. Those two override it.

        `found` is False when no payment matched the callback at all.
        """
        return None

    def recurring_setup(self, settled: dict) -> RecurringSetup | None:
        return None

    async def cancel_subscription(self, *, credentials: dict[str, str], contract_id: str) -> bool:
        return False

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
        raise ProviderError(f"{getattr(self, 'title', 'Провайдер')}: автосписание так не работает")


# --- Общая модель чека 54-ФЗ -------------------------------------------------
#
# Одна модель на всех: адаптер переводит её в формат своей кассы, а не строит
# чек с нуля. Чек отправляется только если продавец указал почту для чеков
# (`fiscal_email`) — это и есть переключатель «передавать чек»: без неё платёж
# уходит как раньше, ничего не ломая магазинам без онлайн-кассы.


class Vat(str, enum.Enum):
    NONE = "none"
    VAT0 = "vat0"
    VAT5 = "vat5"
    VAT7 = "vat7"
    VAT10 = "vat10"
    VAT22 = "vat22"
    VAT105 = "vat105"
    VAT107 = "vat107"
    VAT110 = "vat110"
    VAT122 = "vat122"


class PayMethod(str, enum.Enum):
    """Признак способа расчёта (тег 1214)."""

    FULL_PREPAYMENT = "full_prepayment"
    PREPAYMENT = "prepayment"
    ADVANCE = "advance"
    FULL_PAYMENT = "full_payment"


class PayObject(str, enum.Enum):
    """Признак предмета расчёта (тег 1212)."""

    SERVICE = "service"
    COMMODITY = "commodity"
    PAYMENT = "payment"


class TaxSystem(str, enum.Enum):
    OSN = "osn"
    USN_INCOME = "usn_income"
    USN_INCOME_OUTCOME = "usn_income_outcome"
    ESN = "esn"
    PATENT = "patent"


@dataclass(frozen=True)
class ReceiptItem:
    name: str
    qty: Decimal
    price: Decimal  # рубли за единицу
    vat: Vat
    method: PayMethod = PayMethod.FULL_PREPAYMENT
    obj: PayObject = PayObject.SERVICE

    @property
    def total(self) -> Decimal:
        return (self.price * self.qty).quantize(Decimal("0.01"), ROUND_HALF_UP)


@dataclass(frozen=True)
class Receipt:
    items: list[ReceiptItem]
    tax_system: TaxSystem
    email: str | None = None
    phone: str | None = None  # +7XXXXXXXXXX

    def total(self) -> Decimal:
        return sum((i.total for i in self.items), Decimal("0"))

    def check(self, payment_amount: Decimal) -> None:
        """Касса отклонит платёж с чеком, не сходящимся с суммой, — лучше
        сказать об этом заранее и по-русски."""
        if not (self.email or self.phone):
            raise ProviderError("Для чека нужен email или телефон покупателя")
        if self.total() != payment_amount:
            raise ProviderError(f"Сумма чека {self.total()} не совпадает с суммой платежа {payment_amount}")
        for i in self.items:
            if len(i.name) > 128:
                raise ProviderError(f"Название позиции длиннее 128 символов: {i.name[:30]}…")


def _enum_or_error(enum_cls, raw: str, default, what: str):
    value = (raw or "").strip().lower() or default
    try:
        return enum_cls(value)
    except ValueError:
        allowed = ", ".join(m.value for m in enum_cls)
        raise ProviderError(f"Чек: неизвестное значение «{raw}» для поля «{what}». Допустимо: {allowed}") from None


_TRUE = {"1", "true", "yes", "on", "да"}


def fiscalization_enabled(credentials: dict[str, str]) -> bool:
    """Передавать ли чек 54-ФЗ — только по явному переключателю `fiscalization_enabled`.

    Никаких догадок по заполненной почте: касса с подключённой онлайн-кассой отклоняет платёж
    без чека, а касса без неё — с чеком. Магазинам, у которых чеки работали до появления
    переключателя, флаг проставила миграция 0018."""
    return str(credentials.get("fiscalization_enabled") or "").strip().lower() in _TRUE


_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _clean_email(raw: str | None) -> str | None:
    value = (raw or "").strip()
    return value if _EMAIL.match(value) else None


def _clean_phone(raw: str | None) -> str | None:
    """+7XXXXXXXXXX: цифры и ведущий плюс, остальное (пробелы, скобки, дефисы) отбрасываем.
    Не телефон — None, чтобы мусор не ломал чек, а уступал запасному контакту."""
    digits = re.sub(r"[^\d+]", "", (raw or "").strip())
    if digits.startswith("8") and len(digits) == 11:
        digits = "+7" + digits[1:]
    elif digits and not digits.startswith("+"):
        digits = "+" + digits
    return digits if re.fullmatch(r"\+\d{10,15}", digits) else None


def receipt_contact(
    credentials: dict[str, str], buyer_email: str | None = None, buyer_phone: str | None = None
) -> tuple[str | None, str | None]:
    """Кому уходит чек: по 54-ФЗ — покупателю, на контакт, который он указал. Контакт
    покупателя (почта и/или телефон) берётся, если он есть и похож на настоящий; почта
    продавца из настроек — только когда контакта покупателя нет."""
    email, phone = _clean_email(buyer_email), _clean_phone(buyer_phone)
    if email or phone:
        return email, phone
    return _clean_email(credentials.get("fiscal_email")), None


def check_receipt_contact(
    credentials: dict[str, str], buyer_email: str | None = None, buyer_phone: str | None = None
) -> None:
    """Ошибка ДО создания платежа: чек включён, а слать его некуда."""
    if fiscalization_enabled(credentials) and not any(receipt_contact(credentials, buyer_email, buyer_phone)):
        raise ProviderError(
            "Чек включён, но чек некуда отправить: у покупателя нет контакта, а почта для чеков в "
            "настройках кассы не заполнена. Заполни её или выключи передачу чека"
        )


def receipt_from_credentials(
    credentials: dict[str, str],
    description: str,
    amount_minor: int,
    *,
    tax_key: str = "tax_system",
    vat_key: str = "default_vat",
    buyer_email: str | None = None,
    buyer_phone: str | None = None,
) -> Receipt | None:
    """Чек запуска/продления: одна позиция-услуга, полная предоплата. None — продавец чеки не
    включал. Контакт — покупателя, если известен, иначе почта продавца (`receipt_contact`)."""
    if not fiscalization_enabled(credentials):
        return None
    check_receipt_contact(credentials, buyer_email, buyer_phone)
    email, phone = receipt_contact(credentials, buyer_email, buyer_phone)
    amount = Decimal(int(amount_minor)) / 100
    receipt = Receipt(
        items=[
            ReceiptItem(
                name=((description or "Оплата").strip() or "Оплата")[:128],
                qty=Decimal("1"),
                price=amount,
                vat=_enum_or_error(Vat, credentials.get(vat_key, ""), "none", "ставка НДС"),
                # Бот выдаёт товар сразу после оплаты: полный расчёт. «Полная предоплата» требует от
                # продавца закрывающего чека при передаче товара, которого мы не пробиваем, — налоговая
                # недоработка (см. docs/tbank-docs.md, раздел 18).
                method=PayMethod.FULL_PAYMENT,
            )
        ],
        tax_system=_enum_or_error(TaxSystem, credentials.get(tax_key, ""), "usn_income", "система налогообложения"),
        email=email,
        phone=phone,
    )
    receipt.check(amount)
    return receipt


def kop(x: Decimal) -> int:
    return int((x * 100).quantize(Decimal("1"), ROUND_HALF_UP))


def same_currency(provider_title: str, charged, ordered: str) -> None:
    """Refuse a payment taken in a currency we did not ask for.

    Every adapter checks the amount; none of them checked the unit. "990"
    is a very different sale in roubles, tenge and dollars, and the number
    alone matches all three. Only checked when both sides say — a provider
    that reports no currency is left alone rather than guessed at.
    """
    if not charged or not ordered:
        return
    if str(charged).strip().upper() != ordered.strip().upper():
        raise ProviderError(f"{provider_title}: оплачено в {charged}, а заказ был в {ordered}")

def minor_to_major(amount_minor: int) -> str:
    """990_00 -> "990.00" — the string form providers expect in a signature,
    where a rounding difference of one kopek means a rejected payment.

    For anything a person reads, use `money()` instead: this one is
    deliberately exact and ugly, and showed a 250-star subscription to its
    own seller as "250.00 XTR".
    """
    return f"{amount_minor // 100}.{amount_minor % 100:02d}"


#: Валюты, у которых знак читается лучше кода. Список намеренно короткий:
#: это те, что стоят на ценниках в странах, откуда наши магазины.
_SYMBOLS = {"RUB": "₽", "USD": "$", "EUR": "€", "KZT": "₸", "UAH": "₴", "XTR": "⭐"}


def money(amount_minor: int, currency: str) -> str:
    """"990 RUB", "990.50 RUB", "250 ⭐" — an amount as a person reads it.

    Trailing kopeks are dropped when there are none, because "990.00 ₽" for
    a round price reads like a machine wrote it; Stars have no fractional
    part at all and get their own symbol.
    """
    whole, kopecks = divmod(int(amount_minor), 100)
    amount = str(whole) if kopecks == 0 else f"{whole}.{kopecks:02d}"
    code = (currency or "").upper()
    # Символ там, где он привычнее кода: «Оплатить 2500 ₽» — это цена, а
    # «Оплатить 2500 RUB» — выписка из банка. Для валют без общеизвестного
    # символа остаётся код: выдумывать знак хуже, чем показать буквы.
    return f"{amount} {_SYMBOLS[code]}" if code in _SYMBOLS else f"{amount} {code}"
