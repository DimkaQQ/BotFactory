"""Standing access, a period at a time.

Eight of the twenty gateways can take money a second time, by two different
mechanisms, and these tests pin the difference — because getting it wrong
either charges a subscriber twice (our scheduler charging a subscription the
gateway is already running) or never (a subscription nobody charges at all):

* **the gateway runs it** — Telegram Stars, Stripe, LiqPay, lava.top. We ask
  once, at checkout; the tests check that the one parameter which turns a
  sale into a subscription actually goes out, and that an ordinary sale
  never carries it.
* **we charge a saved method** — ЮKassa, Т-Банк, CloudPayments, Robokassa.
  The tests check the first payment asks to save the method, that the handle
  is read back out, that the off-session charge sends what the gateway
  expects, and that a decline is treated as this period's answer rather than
  an error to retry into a surprise charge days later.

The claim these replaced — "only Telegram Stars can charge again" — was
true of our adapters and false of the gateways, which is the whole reason
this file grew.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta, timezone

import httpx
import pytest
from sqlalchemy import select

from app.models.bot_block import BlockType
from app.models.payment import Payment, PaymentKind, PaymentStatus
from app.models.scheduled_step import ScheduledStep, StepStatus
from app.models.subscription import BillingMode, Subscription, SubscriptionStatus
from app.services import bot_dispatcher, subscription_service
from app.services.payments import get_provider
from app.services.payments.base import CheckoutRequest, ProviderError

CHAT_ID = 991
USER_ID = 5150


@pytest.fixture(autouse=True)
def subscriptions_on(monkeypatch):
    """This whole file tests the subscription feature, which ships switched
    off while the one-off sale is being shaken out on real shops. Turning it
    on here keeps the tests honest about what the code does when it *is* on —
    the two tests about the switch itself override this explicitly."""
    from app.config import get_settings

    monkeypatch.setenv("SUBSCRIPTIONS_ENABLED", "true")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


async def paid_order(db, bot, block, *, provider="stars", amount=59000, currency="RUB") -> Payment:
    payment = Payment(
        kind=PaymentKind.order,
        status=PaymentStatus.paid,
        provider=provider,
        amount_minor=amount,
        currency=currency,
        description="Закрытый клуб — месяц",
        bot_id=bot.id,
        block_id=block.id,
        telegram_user_id=USER_ID,
        chat_id=CHAT_ID,
        paid_at=datetime.now(timezone.utc),
    )
    db.add(payment)
    await db.commit()
    return payment


async def club_bot(db, owner, make_bot, *, subscription=True, period_days=30, provider="stars"):
    bot, blocks = await make_bot(
        owner,
        [
            (BlockType.welcome, {"text": "Клуб"}),
            (
                BlockType.payment,
                {
                    "title": "Закрытый клуб",
                    "price": "590",
                    "currency": currency_of(provider),
                    "subscription": subscription,
                    "period_days": period_days,
                },
            ),
            (BlockType.delivery, {"text": "Добро пожаловать!"}),
        ],
        provider=provider,
        credentials=_CREDENTIALS.get(provider),
    )
    return bot, blocks


#: Enough for the adapter to get as far as an HTTP call, which is where the
#: mock takes over. A charge attempted without them fails early with a
#: perfectly good message — just not the one these tests are about.
_CREDENTIALS = {
    "yookassa": {"shop_id": "1", "secret_key": "test_x"},
    "cloudpayments": {"public_id": "pk_test", "api_secret": "secret"},
    "stripe": {"secret_key": "sk_test_1", "webhook_secret": "whsec_1"},
}


def currency_of(provider: str) -> str:
    return "XTR" if provider == "stars" else "RUB"


# ------------------------------------------------- the one argument that matters


async def test_a_stars_subscription_invoice_actually_asks_for_a_subscription(monkeypatch):
    """The engine's whole claim to recurring billing is one parameter. If it
    stops going out, nothing else here is true — a customer is sold «списание
    каждый месяц» and charged exactly once, forever."""
    from app.services.payments import telegram_stars

    seen: dict = {}

    class FakeBot:
        def __init__(self, *args, **kwargs):
            self.session = type("S", (), {"close": staticmethod(_noop)})()

        async def create_invoice_link(self, **kwargs):
            seen.update(kwargs)
            return "https://t.me/invoice/1"

    monkeypatch.setattr(telegram_stars, "Bot", FakeBot)

    provider = telegram_stars.TelegramStarsProvider()
    await provider.create_checkout(_request(extra={"subscription": True}))
    assert seen["subscription_period"] == telegram_stars.SUBSCRIPTION_PERIOD_SECONDS == 2592000

    seen.clear()
    await provider.create_checkout(_request(extra={}))
    assert seen["subscription_period"] is None, "разовая покупка не должна становиться подпиской"


async def _noop() -> None:
    return None


def _request(*, extra: dict) -> CheckoutRequest:
    return CheckoutRequest(
        payment_id=uuid.uuid4(),
        invoice_no=1001,
        amount_minor=25000,
        currency="XTR",
        description="Клуб",
        return_url="https://example.test/ok",
        is_test=False,
        credentials={},
        extra=extra,
        bot_token="111:AAA",
        telegram_user_id=USER_ID,
    )


def test_a_provider_claiming_recurring_can_actually_do_it():
    """The lie this guards against is an adapter *declaring* recurring it has
    not implemented: the shop is sold a subscription business and its
    customers are charged once.

    So the declaration has to be backed by code. `token` means we initiate
    each charge, which needs both halves — reading the saved method out of a
    settled payment, and using it — and inheriting either default (which
    returns None / raises) is exactly the failure being caught.
    """
    from app.services.payments import PROVIDERS
    from app.services.payments.base import ProviderDefaults, RecurringMode

    for slug, provider in PROVIDERS.items():
        if provider.recurring is not RecurringMode.token:
            continue
        assert type(provider).recurring_setup is not ProviderDefaults.recurring_setup, (
            f"{slug} объявил рекуррент по токену, но не умеет достать токен из платежа"
        )
        assert type(provider).charge_recurring is not ProviderDefaults.charge_recurring, (
            f"{slug} объявил рекуррент по токену, но не умеет списывать"
        )


def test_billing_mode_follows_the_adapter_not_a_list():
    """Anything that can charge again — however — is `auto`; everything else
    is honestly `renewal`."""
    from app.services.payments import PROVIDERS
    from app.services.payments.base import RecurringMode

    for slug, provider in PROVIDERS.items():
        expected = BillingMode.renewal if provider.recurring is RecurringMode.none else BillingMode.auto
        assert subscription_service.billing_mode(slug) == expected, slug

    # And "we do the charging" is only true for the token kind: a
    # gateway-run subscription must never have our scheduler charging it too.
    assert subscription_service.charges_itself("yookassa") is True
    assert subscription_service.charges_itself("stars") is False
    assert subscription_service.charges_itself("stripe") is False


def test_we_have_more_than_one_recurring_option():
    """The point of the exercise: a shop should not have to take Telegram
    Stars to sell a subscription."""
    from app.services.payments import PROVIDERS
    from app.services.payments.base import RecurringMode

    recurring = {slug for slug, p in PROVIDERS.items() if p.recurring is not RecurringMode.none}
    assert len(recurring) >= 3, recurring
    # At least one that takes ordinary cards in roubles, or the Russian
    # market has exactly one option and it is stars.
    cards = {slug for slug in recurring if "RUB" in PROVIDERS[slug].currencies}
    assert cards, "рекуррент есть только там, где не принимают рубли"


# ------------------------------------------------------------- the period


async def test_the_first_payment_opens_a_subscription(db, owner, make_bot, as_bot):
    bot, blocks = await club_bot(db, owner, make_bot, period_days=30)
    payment = await paid_order(db, bot, blocks[1])

    subscription = await subscription_service.start_or_extend(db, payment)

    assert subscription is not None
    assert subscription.status == SubscriptionStatus.active
    assert subscription.billing_mode == BillingMode.auto
    assert subscription.periods_paid == 1
    assert subscription.title == "Закрытый клуб"
    assert timedelta(days=29) < subscription.current_period_end - datetime.now(timezone.utc) < timedelta(days=31)


async def test_a_plain_purchase_opens_nothing(db, owner, make_bot, as_bot):
    """A guide sold by the volume must not quietly become a subscription."""
    bot, blocks = await club_bot(db, owner, make_bot, subscription=False)
    payment = await paid_order(db, bot, blocks[1])

    assert await subscription_service.start_or_extend(db, payment) is None


async def test_paying_early_adds_to_what_is_left_instead_of_throwing_it_away(db, owner, make_bot, as_bot):
    """Someone who renews with ten days still on the clock keeps those ten
    days. Resetting to now+30 would quietly take them."""
    bot, blocks = await club_bot(db, owner, make_bot, period_days=30)
    payment = await paid_order(db, bot, blocks[1])
    subscription = await subscription_service.start_or_extend(db, payment)
    first_end = subscription.current_period_end

    await subscription_service.start_or_extend(db, payment)

    assert subscription.periods_paid == 2
    assert subscription.current_period_end == first_end + timedelta(days=30)


async def test_paying_late_starts_from_today_not_from_the_lapsed_date(db, owner, make_bot, as_bot):
    """The mirror case: back-dating would sell a period that had already
    elapsed, so someone returning after two months away would get days they
    never had access for."""
    bot, blocks = await club_bot(db, owner, make_bot, period_days=30)
    payment = await paid_order(db, bot, blocks[1])
    subscription = await subscription_service.start_or_extend(db, payment)

    subscription.current_period_end = datetime.now(timezone.utc) - timedelta(days=40)
    subscription.status = SubscriptionStatus.expired
    await db.commit()

    await subscription_service.start_or_extend(db, payment)

    assert subscription.status == SubscriptionStatus.active
    assert subscription.current_period_end - datetime.now(timezone.utc) > timedelta(days=29)


@pytest.mark.parametrize("raw, expected", [(0, 1), (-5, 1), ("7", 7), ("вчера", 30), (10_000, 365), (None, 30)])
def test_the_period_is_clamped_not_trusted(raw, expected):
    """It is a free number in the editor. A zero would expire every
    subscriber the instant they paid; a typo'd 10000 sells lifetime access."""
    assert subscription_service.period_days({"period_days": raw}) == expected


# ------------------------------------------------------------- renewals


async def test_a_renewal_reminder_is_queued_for_invoice_providers(db, owner, make_bot, as_bot):
    """These providers cannot charge again, so something has to ask. The
    reminder lands before the period ends, not after."""
    bot, blocks = await club_bot(db, owner, make_bot, provider="yookassa", period_days=30)
    payment = await paid_order(db, bot, blocks[1], provider="yookassa")

    subscription = await subscription_service.start_or_extend(db, payment)

    queued = (
        await db.execute(select(ScheduledStep).where(ScheduledStep.subscription_id == subscription.id))
    ).scalars().all()
    assert len(queued) == 1
    assert queued[0].reason == "renewal"
    assert queued[0].run_at < subscription.current_period_end, "напоминать надо ДО конца периода"


async def test_stars_gets_no_reminder_because_telegram_does_the_asking(db, owner, make_bot, as_bot):
    bot, blocks = await club_bot(db, owner, make_bot, provider="stars")
    payment = await paid_order(db, bot, blocks[1])

    subscription = await subscription_service.start_or_extend(db, payment)

    queued = (
        await db.execute(select(ScheduledStep).where(ScheduledStep.subscription_id == subscription.id))
    ).scalars().all()
    assert queued == []


async def test_extending_clears_the_previous_periods_reminder(db, owner, make_bot, as_bot):
    """Otherwise a subscriber who renews early gets last month's reminder
    anyway, asking for money they have already paid."""
    bot, blocks = await club_bot(db, owner, make_bot, provider="yookassa")
    payment = await paid_order(db, bot, blocks[1], provider="yookassa")
    subscription = await subscription_service.start_or_extend(db, payment)

    await subscription_service.start_or_extend(db, payment)

    live = (
        await db.execute(
            select(ScheduledStep).where(
                ScheduledStep.subscription_id == subscription.id,
                ScheduledStep.status == StepStatus.pending,
            )
        )
    ).scalars().all()
    assert len(live) == 1, "на период должно быть ровно одно напоминание"


async def test_a_stars_renewal_extends_the_period_without_reselling(db, owner, make_bot, telegram, as_bot):
    """Telegram charges on its own and sends a `successful_payment` for the
    *original* invoice. `apply_result` would see a payment already marked
    paid and do nothing — including not extending the period, which is the
    one thing this update exists to do."""
    bot, blocks = await club_bot(db, owner, make_bot, provider="stars")
    payment = await paid_order(db, bot, blocks[1], amount=25000, currency="XTR")
    subscription = await subscription_service.start_or_extend(db, payment)
    first_end = subscription.current_period_end
    telegram.reset_mock()

    await bot_dispatcher.process_update(
        telegram,
        {
            "message": {
                "chat": {"id": CHAT_ID},
                "from": {"id": USER_ID},
                "successful_payment": {
                    "invoice_payload": str(payment.id),
                    "total_amount": 250,
                    "telegram_payment_charge_id": "ch_renewal_1",
                    "is_recurring": True,
                    "is_first_recurring": False,
                },
            }
        },
        bot.id,
        db,
    )

    await db.refresh(subscription)
    assert subscription.periods_paid == 2
    assert subscription.current_period_end == first_end + timedelta(days=30)
    # And the subscriber is told, because money left their account.
    assert any("продлена" in message for message in telegram.sent()), telegram.sent()
    # The goods are not re-sent: a renewal is not a new purchase.
    assert not any("Добро пожаловать" in message for message in telegram.sent())


# ------------------------------------------------------------- expiry


async def test_a_period_that_runs_out_ends_the_access_and_says_so(db, owner, make_bot, as_bot, telegram):
    bot, blocks = await club_bot(db, owner, make_bot)
    payment = await paid_order(db, bot, blocks[1])
    subscription = await subscription_service.start_or_extend(db, payment)
    subscription.current_period_end = datetime.now(timezone.utc) - timedelta(minutes=1)
    await db.commit()
    telegram.reset_mock()

    assert await subscription_service.expire_due() >= 1

    await db.refresh(subscription)
    assert subscription.status == SubscriptionStatus.expired
    assert any("закончил" in message for message in telegram.sent()), telegram.sent()


async def test_a_live_subscriber_is_left_alone_by_the_expiry_sweep(db, owner, make_bot, as_bot):
    bot, blocks = await club_bot(db, owner, make_bot)
    payment = await paid_order(db, bot, blocks[1])
    subscription = await subscription_service.start_or_extend(db, payment)

    await subscription_service.expire_due()

    await db.refresh(subscription)
    assert subscription.status == SubscriptionStatus.active


# ------------------------------------------- what is already bought stays bought


async def test_a_returning_buyer_is_not_sold_the_same_volume_twice(db, owner, make_bot, telegram, as_bot):
    """Том 1 of a guide, bought last month. Pressing /start again used to
    offer it for sale a second time, with nothing anywhere to stop the
    payment going through."""
    bot, blocks = await club_bot(db, owner, make_bot, subscription=False, provider="test")
    _welcome, payment_block, delivery = blocks
    await paid_order(db, bot, payment_block, provider="test")
    telegram.reset_mock()

    await bot_dispatcher.process_update(
        telegram,
        {"message": {"chat": {"id": CHAT_ID}, "from": {"id": USER_ID}, "text": "/start"}},
        bot.id,
        db,
    )

    sent = telegram.sent()
    assert any("уже" in message for message in sent), sent
    # And the chain continues into what they bought, rather than stopping at
    # a paywall they already paid.
    assert "Добро пожаловать!" in sent, sent
    assert not any("Оплатить" in str(k) for k in telegram.keyboards())


async def test_someone_who_has_not_paid_still_sees_the_paywall(db, owner, make_bot, telegram, as_bot):
    """The mirror: the check must be per person, not per block."""
    bot, blocks = await club_bot(db, owner, make_bot, subscription=False, provider="test")
    await paid_order(db, bot, blocks[1], provider="test")
    telegram.reset_mock()

    await bot_dispatcher.process_update(
        telegram,
        {"message": {"chat": {"id": CHAT_ID}, "from": {"id": USER_ID + 1}, "text": "/start"}},
        bot.id,
        db,
    )

    sent = telegram.sent()
    assert not any("уже" in message for message in sent), sent
    assert "Добро пожаловать!" not in sent, "чужая оплата не должна открывать товар"


# ------------------------------------------------- автосписание по сохранённой карте


def _yookassa_paid(method_id: str | None) -> dict:
    body = {
        "id": "2f0a-remote",
        "status": "succeeded",
        "paid": True,
        "amount": {"value": "590.00", "currency": "RUB"},
    }
    if method_id:
        body["payment_method"] = {"id": method_id, "saved": True, "type": "bank_card"}
    return body


async def test_yookassa_asks_to_save_the_card_only_for_a_subscription(mock_http):
    """`save_payment_method` is what makes the *next* charge possible at all —
    and putting it on an ordinary sale would ask a one-off buyer to authorise
    a standing arrangement they never agreed to."""
    seen: list[dict] = []

    def handler(request):
        seen.append(json.loads(request.content))
        return httpx.Response(200, json={"id": "p1", "confirmation": {"confirmation_url": "https://pay"}})

    provider = get_provider("yookassa")
    creds = {"shop_id": "1", "secret_key": "test_x"}

    with mock_http(handler):
        await provider.create_checkout(_yk_request(creds, extra={"subscription": True}))
        await provider.create_checkout(_yk_request(creds, extra={}))

    assert seen[0].get("save_payment_method") is True
    assert "save_payment_method" not in seen[1], "разовая покупка не должна сохранять карту"


async def test_yookassa_hands_back_the_saved_method_when_the_payment_settles(mock_http):
    provider = get_provider("yookassa")
    with mock_http(lambda request: httpx.Response(200, json=_yookassa_paid("pm_saved_1"))):
        verdict = await provider.check_status(
            credentials={"shop_id": "1", "secret_key": "test_x"},
            amount_minor=59000,
            invoice_no=1,
            payment_id=uuid.uuid4(),
            provider_payment_id="2f0a-remote",
            meta={},
            currency="RUB",
        )
    assert verdict.status == PaymentStatus.paid
    setup = provider.recurring_setup(verdict.meta)
    assert setup is not None and setup.token == "pm_saved_1"

    # And a payment made without saving leaves nothing to charge later.
    with mock_http(lambda request: httpx.Response(200, json=_yookassa_paid(None))):
        plain = await provider.check_status(
            credentials={"shop_id": "1", "secret_key": "test_x"},
            amount_minor=59000,
            invoice_no=1,
            payment_id=uuid.uuid4(),
            provider_payment_id="2f0a-remote",
            meta={},
            currency="RUB",
        )
    assert provider.recurring_setup(plain.meta) is None


async def test_yookassa_charges_the_saved_method_with_no_confirmation_step(mock_http):
    """The off-session charge: same endpoint as a sale, `payment_method_id`
    instead of a confirmation block — that difference is the whole feature."""
    from app.services.payments.base import RecurringSetup

    seen: list[dict] = []

    def handler(request):
        seen.append(json.loads(request.content))
        return httpx.Response(200, json={"id": "renew-1", "status": "succeeded", "paid": True})

    payment_id = uuid.uuid4()
    with mock_http(handler):
        verdict = await get_provider("yookassa").charge_recurring(
            credentials={"shop_id": "1", "secret_key": "test_x"},
            setup=RecurringSetup(token="pm_saved_1"),
            amount_minor=59000,
            currency="RUB",
            description="Клуб",
            payment_id=payment_id,
        )

    assert verdict.status == PaymentStatus.paid
    body = seen[0]
    assert body["payment_method_id"] == "pm_saved_1"
    assert "confirmation" not in body, "у автосписания нет никого, кто бы подтвердил"
    assert body["amount"] == {"value": "590.00", "currency": "RUB"}
    assert body["metadata"]["order_id"] == str(payment_id)


async def test_a_declined_card_is_this_periods_answer_not_an_error(mock_http):
    """A `canceled` payment means the bank said no. Raising here would put the
    step on a retry schedule and charge the moment the card works again —
    days later, unannounced."""
    from app.services.payments.base import RecurringSetup

    with mock_http(lambda request: httpx.Response(200, json={"id": "x", "status": "canceled"})):
        verdict = await get_provider("yookassa").charge_recurring(
            credentials={"shop_id": "1", "secret_key": "test_x"},
            setup=RecurringSetup(token="pm_1"),
            amount_minor=59000,
            currency="RUB",
            description="Клуб",
            payment_id=uuid.uuid4(),
        )
    assert verdict.status == PaymentStatus.failed


async def test_cloudpayments_charges_the_token_not_the_auth_endpoint(mock_http):
    """`tokens/auth` holds the money for a later confirm, and a renewal has
    nobody watching to confirm it."""
    from app.services.payments.base import RecurringSetup

    seen: list[httpx.Request] = []

    def handler(request):
        seen.append(request)
        return httpx.Response(
            200, json={"Success": True, "Model": {"TransactionId": 77, "Status": "Completed"}}
        )

    with mock_http(handler):
        verdict = await get_provider("cloudpayments").charge_recurring(
            credentials={"public_id": "pk", "api_secret": "s"},
            setup=RecurringSetup(token="card_token_1", customer="acc-9"),
            amount_minor=59000,
            currency="RUB",
            description="Клуб",
            payment_id=uuid.uuid4(),
        )

    assert verdict.status == PaymentStatus.paid
    assert str(seen[0].url).endswith("/payments/tokens/charge")
    body = json.loads(seen[0].content)
    assert body["Token"] == "card_token_1"
    assert body["AccountId"] == "acc-9"
    assert body["Amount"] == 590.0


async def test_cloudpayments_reports_the_banks_own_words_on_a_decline(mock_http):
    """The shop owner needs "недостаточно средств", not "ошибка"."""
    from app.services.payments.base import RecurringSetup

    refusal = {"Success": False, "Message": None, "Model": {"CardHolderMessage": "Недостаточно средств"}}
    with mock_http(lambda request: httpx.Response(200, json=refusal)):
        verdict = await get_provider("cloudpayments").charge_recurring(
            credentials={"public_id": "pk", "api_secret": "s"},
            setup=RecurringSetup(token="t", customer="a"),
            amount_minor=59000,
            currency="RUB",
            description="Клуб",
            payment_id=uuid.uuid4(),
        )
    assert verdict.status == PaymentStatus.failed
    assert verdict.meta["decline"] == "Недостаточно средств"


async def test_stripe_turns_the_same_checkout_into_a_real_subscription(mock_http):
    """Stripe runs the subscription itself, so the only thing we have to get
    right is the mode and the interval."""
    seen: list[str] = []

    def handler(request):
        seen.append(request.content.decode())
        return httpx.Response(200, json={"id": "cs_1", "url": "https://checkout.stripe.com/x"})

    provider = get_provider("stripe")
    with mock_http(handler):
        await provider.create_checkout(_stripe_request(extra={"subscription": True, "period_days": 30}))
        await provider.create_checkout(_stripe_request(extra={}))

    assert "mode=subscription" in seen[0]
    assert "%5Brecurring%5D%5Binterval%5D=month" in seen[0], seen[0]
    assert "%5Brecurring%5D%5Binterval_count%5D=1" in seen[0]
    assert "mode=payment" in seen[1] and "recurring" not in seen[1]


def _yk_request(creds: dict, *, extra: dict) -> CheckoutRequest:
    return CheckoutRequest(
        payment_id=uuid.uuid4(),
        invoice_no=1,
        amount_minor=59000,
        currency="RUB",
        description="Клуб",
        return_url="https://example.test/ok",
        is_test=True,
        credentials=creds,
        extra=extra,
    )


def _stripe_request(*, extra: dict) -> CheckoutRequest:
    return CheckoutRequest(
        payment_id=uuid.uuid4(),
        invoice_no=1,
        amount_minor=59000,
        currency="USD",
        description="Club",
        return_url="https://example.test/ok",
        is_test=True,
        credentials={"secret_key": "sk_test_1"},
        extra=extra,
    )


async def test_the_scheduler_charges_the_card_when_the_period_runs_out(db, owner, make_bot, as_bot, telegram, mock_http):
    """The whole chain, on a card: pay → period → the queue charges → the
    period moves. Nobody taps anything."""
    from app.models.scheduled_step import ScheduledStep
    from app.services import scheduler

    bot, blocks = await club_bot(db, owner, make_bot, provider="yookassa", period_days=30)
    payment = await paid_order(db, bot, blocks[1], provider="yookassa")
    # The saved-method handle arrives with the settled payment, exactly as the
    # adapter puts it there.
    payment.meta = {"yookassa_payment_method_id": "pm_saved_9"}
    await db.commit()

    subscription = await subscription_service.start_or_extend(db, payment)
    assert subscription.billing_mode == BillingMode.auto
    first_end = subscription.current_period_end
    assert (subscription.meta or {}).get("recurring_token"), "способ оплаты обязан сохраниться"
    # ...and not in the clear: it moves money together with the shop's keys.
    assert "pm_saved_9" not in str(subscription.meta)

    queued = (
        await db.execute(
            select(ScheduledStep)
            .where(ScheduledStep.subscription_id == subscription.id)
            .execution_options(populate_existing=True)
        )
    ).scalars().all()
    assert [s.reason for s in queued] == ["charge"], "на карте продлевают списанием, а не напоминанием"
    assert queued[0].run_at == first_end, "списывать в конце периода, не раньше — дни оплачены"

    queued[0].run_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    await db.commit()

    with mock_http(lambda request: httpx.Response(200, json={"id": "renew-9", "status": "succeeded", "paid": True})):
        await scheduler.run_due()

    await db.refresh(subscription)
    assert subscription.periods_paid == 2
    assert subscription.current_period_end == first_end + timedelta(days=30)
    assert any("продлена" in m for m in telegram.sent()), telegram.sent()


async def test_a_declined_renewal_leaves_the_period_alone_and_warns(db, owner, make_bot, as_bot, telegram, mock_http):
    """Access must not be extended by a charge that did not go through — and
    the subscriber gets the one message that can still save the subscription."""
    from app.models.scheduled_step import ScheduledStep
    from app.services import scheduler

    bot, blocks = await club_bot(db, owner, make_bot, provider="yookassa")
    payment = await paid_order(db, bot, blocks[1], provider="yookassa")
    payment.meta = {"yookassa_payment_method_id": "pm_saved_9"}
    await db.commit()
    subscription = await subscription_service.start_or_extend(db, payment)
    first_end = subscription.current_period_end
    telegram.reset_mock()

    step = (
        await db.execute(select(ScheduledStep).where(ScheduledStep.subscription_id == subscription.id))
    ).scalar_one()
    step.run_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    await db.commit()

    with mock_http(lambda request: httpx.Response(200, json={"id": "x", "status": "canceled"})):
        await scheduler.run_due()

    await db.refresh(subscription)
    assert subscription.periods_paid == 1
    assert subscription.current_period_end == first_end
    assert any("Не получилось списать" in m for m in telegram.sent()), telegram.sent()


async def test_a_gateway_run_subscription_is_never_charged_by_us(db, owner, make_bot, as_bot):
    """Stripe and Stars bill on their own. Queueing a charge for them would
    take the money twice."""
    from app.models.scheduled_step import ScheduledStep

    for provider in ("stars", "stripe"):
        bot, blocks = await club_bot(db, owner, make_bot, provider=provider)
        payment = await paid_order(db, bot, blocks[1], provider=provider)
        subscription = await subscription_service.start_or_extend(db, payment)
        queued = (
            await db.execute(select(ScheduledStep).where(ScheduledStep.subscription_id == subscription.id))
        ).scalars().all()
        assert [s.reason for s in queued] == [], f"{provider}: списывает сам шлюз"


async def test_a_card_subscription_without_a_saved_method_falls_back_to_asking(db, owner, make_bot, as_bot):
    """ЮKassa refuses `save_payment_method` for a shop that has not had
    autopayments switched on. Losing the subscriber over that would be worse
    than asking them each month."""
    from app.models.scheduled_step import ScheduledStep

    bot, blocks = await club_bot(db, owner, make_bot, provider="yookassa")
    payment = await paid_order(db, bot, blocks[1], provider="yookassa")  # no handle in meta
    subscription = await subscription_service.start_or_extend(db, payment)

    queued = (
        await db.execute(select(ScheduledStep).where(ScheduledStep.subscription_id == subscription.id))
    ).scalars().all()
    assert [s.reason for s in queued] == ["renewal"]


# ------------------------------------------- остальные шлюзы, по одному механизму


async def test_tbank_registers_the_autopayment_and_then_charges_the_rebill_id(mock_http):
    """Two calls, and the second is the whole feature: Init mints a PaymentId
    for this period, Charge takes the money against the stored RebillId."""
    from app.services.payments.base import RecurringSetup

    seen: list[dict] = []

    def handler(request):
        body = json.loads(request.content)
        seen.append({"url": str(request.url), **body})
        if request.url.path.endswith("/Init"):
            return httpx.Response(200, json={"Success": True, "PaymentId": 4242, "PaymentURL": "https://pay"})
        return httpx.Response(200, json={"Success": True, "Status": "CONFIRMED", "Amount": 59000})

    provider = get_provider("tbank")
    creds = {"terminal_key": "T1", "password": "p"}

    with mock_http(handler):
        await provider.create_checkout(_tbank_request(creds, extra={"subscription": True}))
        seen.clear()
        verdict = await provider.charge_recurring(
            credentials=creds,
            setup=RecurringSetup(token="rebill-77", customer="tg-5150"),
            amount_minor=59000,
            currency="RUB",
            description="Клуб",
            payment_id=uuid.uuid4(),
            invoice_no=1234,
        )

    assert verdict.status == PaymentStatus.paid
    init, charge = seen
    assert init["url"].endswith("/Init") and "Recurrent" not in init, "повторная регистрация автоплатежа не нужна"
    assert charge["url"].endswith("/Charge")
    assert charge["RebillId"] == "rebill-77"
    assert charge["PaymentId"] == "4242"


async def test_tbank_asks_for_the_autopayment_only_on_a_subscription(mock_http):
    seen: list[dict] = []

    def handler(request):
        seen.append(json.loads(request.content))
        return httpx.Response(200, json={"Success": True, "PaymentId": 1, "PaymentURL": "https://pay"})

    provider = get_provider("tbank")
    creds = {"terminal_key": "T1", "password": "p"}
    with mock_http(handler):
        await provider.create_checkout(_tbank_request(creds, extra={"subscription": True}))
        await provider.create_checkout(_tbank_request(creds, extra={}))

    assert seen[0]["Recurrent"] == "Y" and seen[0]["CustomerKey"]
    assert "Recurrent" not in seen[1]


async def test_tbank_a_held_but_uncaptured_charge_is_not_treated_as_paid(mock_http):
    """AUTHORIZED on a two-stage terminal means the money is held, not taken,
    and a renewal has nobody to confirm it."""
    from app.services.payments.base import RecurringSetup

    def handler(request):
        if request.url.path.endswith("/Init"):
            return httpx.Response(200, json={"Success": True, "PaymentId": 9})
        return httpx.Response(200, json={"Success": True, "Status": "AUTHORIZED", "Amount": 59000})

    with mock_http(handler):
        verdict = await get_provider("tbank").charge_recurring(
            credentials={"terminal_key": "T1", "password": "p"},
            setup=RecurringSetup(token="r"),
            amount_minor=59000,
            currency="RUB",
            description="Клуб",
            payment_id=uuid.uuid4(),
            invoice_no=1,
        )
    assert verdict.status == PaymentStatus.pending


async def test_robokassa_says_requested_not_paid(mock_http):
    """«OK<InvId>» means the operation was created. Reading it as a settlement
    would hand over a month for a charge that can still be declined — the real
    answer comes later on ResultURL."""
    from app.services.payments.base import RecurringSetup

    seen: list[httpx.Request] = []

    def handler(request):
        seen.append(request)
        return httpx.Response(200, text="OK1235")

    with mock_http(handler):
        verdict = await get_provider("robokassa").charge_recurring(
            credentials={"merchant_login": "shop", "password1": "p1", "password2": "p2"},
            setup=RecurringSetup(token="1000"),
            amount_minor=59000,
            currency="RUB",
            description="Клуб",
            payment_id=uuid.uuid4(),
            invoice_no=1235,
        )

    assert verdict.status == PaymentStatus.pending, "ответ Robokassa — не подтверждение списания"
    body = dict(x.split("=", 1) for x in seen[0].content.decode().split("&"))
    assert str(seen[0].url).endswith("/Merchant/Recurring")
    assert body["PreviousInvoiceID"] == "1000"
    assert body["InvoiceID"] == "1235"
    assert body["OutSum"] == "590.00"


async def test_robokassa_refuses_a_charge_it_cannot_sign(mock_http):
    from app.services.payments.base import RecurringSetup

    with mock_http(lambda request: httpx.Response(200, text="OK1")):
        with pytest.raises(ProviderError):
            await get_provider("robokassa").charge_recurring(
                credentials={"merchant_login": "shop", "password1": "p1"},
                setup=RecurringSetup(token="1000"),
                amount_minor=59000,
                currency="RUB",
                description="Клуб",
                payment_id=uuid.uuid4(),
                invoice_no=None,
            )


async def test_liqpay_creates_a_subscription_the_gateway_then_runs():
    """LiqPay bills it itself, so the only thing to get right is the action
    and the period."""
    import base64

    provider = get_provider("liqpay")
    creds = {"public_key": "pub", "private_key": "priv"}

    checkout = await provider.create_checkout(_generic_request(creds, extra={"subscription": True, "period_days": 30}))
    params = json.loads(base64.b64decode(checkout.meta["form_fields"]["data"]))
    assert params["action"] == "subscribe"
    assert params["subscribe"] == 1
    assert params["subscribe_periodicity"] == "month"
    assert params["subscribe_date_start"]

    plain = await provider.create_checkout(_generic_request(creds, extra={}))
    plain_params = json.loads(base64.b64decode(plain.meta["form_fields"]["data"]))
    assert plain_params["action"] == "pay"
    assert "subscribe" not in plain_params


async def test_lavatop_stops_hardcoding_one_time(mock_http):
    """The adapter used to send `"periodicity": "ONE_TIME"` unconditionally —
    lava.top sells subscriptions and we were refusing to ask for one."""
    seen: list[dict] = []

    def handler(request):
        seen.append(json.loads(request.content))
        return httpx.Response(200, json={"paymentUrl": "https://lava/pay", "id": "inv-1"})

    provider = get_provider("lavatop")
    creds = {"api_key": "k", "buyer_email": "a@b.c"}
    with mock_http(handler):
        await provider.create_checkout(
            _generic_request(creds, extra={"offer_id": "o1", "subscription": True, "period_days": 30})
        )
        await provider.create_checkout(_generic_request(creds, extra={"offer_id": "o1"}))

    assert seen[0]["periodicity"] == "MONTHLY"
    assert seen[1]["periodicity"] == "ONE_TIME"


def _tbank_request(creds: dict, *, extra: dict) -> CheckoutRequest:
    return CheckoutRequest(
        payment_id=uuid.uuid4(),
        invoice_no=1,
        amount_minor=59000,
        currency="RUB",
        description="Клуб",
        return_url="https://example.test/ok",
        is_test=True,
        credentials=creds,
        extra=extra,
        telegram_user_id=USER_ID,
    )


def _generic_request(creds: dict, *, extra: dict) -> CheckoutRequest:
    return CheckoutRequest(
        payment_id=uuid.uuid4(),
        invoice_no=1,
        amount_minor=59000,
        currency="RUB",
        description="Клуб",
        return_url="https://example.test/ok",
        is_test=True,
        credentials=creds,
        extra=extra,
        telegram_user_id=USER_ID,
    )


# ---------------------------------- шлюзы, добавленные по присланной документации


async def test_freedompay_opens_a_profile_and_charges_it_by_name(mock_http):
    """The script name is not cosmetic: Freedom Pay signs the request with the
    last segment of the URL exactly as called, so `make_recurring_payment` and
    `make_recurring_payment.php` are two different signatures. Getting it wrong
    fails as a signature error, not as a 404."""
    from app.services.payments.base import RecurringSetup

    seen: list[httpx.Request] = []

    def handler(request):
        seen.append(request)
        if request.url.path.endswith("init_payment.php"):
            return httpx.Response(200, text="<response><pg_status>ok</pg_status>"
                                            "<pg_redirect_url>https://pay</pg_redirect_url></response>")
        return httpx.Response(200, text="<response><pg_status>ok</pg_status>"
                                        "<pg_payment_id>987</pg_payment_id></response>")

    provider = get_provider("freedompay")
    creds = {"merchant_id": "m1", "secret_key": "s1"}

    with mock_http(handler):
        await provider.create_checkout(_generic_request(creds, extra={"subscription": True}))
        first = dict(x.split("=", 1) for x in seen[0].content.decode().split("&"))
        assert first["pg_recurring_start"] == "1"
        assert "pg_recurring_lifetime" in first

        seen.clear()
        verdict = await provider.charge_recurring(
            credentials=creds,
            setup=RecurringSetup(token="profile-55"),
            amount_minor=59000,
            currency="KZT",
            description="Клуб",
            payment_id=uuid.uuid4(),
            invoice_no=7,
        )

    assert str(seen[0].url).endswith("/make_recurring_payment"), "имя скрипта — без .php"
    body = {k: v for k, v in (x.split("=", 1) for x in seen[0].content.decode().split("&"))}
    assert body["pg_recurring_profile"] == "profile-55"
    # …and the signature was built over that same name.
    assert verdict.status == PaymentStatus.pending, "pg_status=ok — это «платёж создан», а не «деньги списаны»"


async def test_freedompay_does_not_ask_to_save_a_card_for_a_one_off_sale(mock_http):
    def handler(request):
        return httpx.Response(200, text="<response><pg_status>ok</pg_status>"
                                        "<pg_redirect_url>https://pay</pg_redirect_url></response>")

    with mock_http(handler) :
        checkout = await get_provider("freedompay").create_checkout(
            _generic_request({"merchant_id": "m1", "secret_key": "s1"}, extra={})
        )
    assert checkout.url == "https://pay"


async def test_freedompay_says_plainly_when_the_saved_card_is_gone(mock_http):
    """9011/11070 mean the profile is dead — retrying it forever would be a
    permanent error loop, and the subscription has to fall back to asking."""
    from app.services.payments.base import RecurringSetup

    refusal = ("<response><pg_status>error</pg_status><pg_error_code>9011</pg_error_code>"
               "<pg_error_description>Неверный рекуррентный профиль</pg_error_description></response>")
    with mock_http(lambda request: httpx.Response(200, text=refusal)):
        with pytest.raises(ProviderError, match="привязка карты"):
            await get_provider("freedompay").charge_recurring(
                credentials={"merchant_id": "m1", "secret_key": "s1"},
                setup=RecurringSetup(token="dead"),
                amount_minor=59000,
                currency="KZT",
                description="Клуб",
                payment_id=uuid.uuid4(),
                invoice_no=7,
            )


async def test_paymaster_asks_for_a_token_and_only_settled_is_money(mock_http):
    from app.services.payments.base import RecurringSetup

    seen: list[dict] = []

    def handler(request):
        seen.append({"url": str(request.url), **json.loads(request.content)})
        if request.url.path.endswith("/invoices"):
            return httpx.Response(200, json={"url": "https://pay", "paymentId": "p1"})
        return httpx.Response(200, json={"paymentId": "p2", "status": "Settled"})

    provider = get_provider("paymaster")
    creds = {"merchant_id": "m", "token": "t"}

    with mock_http(handler):
        await provider.create_checkout(_generic_request(creds, extra={"subscription": True}))
        assert seen[0]["tokenization"]["type"] == "recurring"
        seen.clear()
        verdict = await provider.charge_recurring(
            credentials=creds,
            setup=RecurringSetup(token="tok-1"),
            amount_minor=99000,
            currency="RUB",
            description="PRO",
            payment_id=uuid.uuid4(),
        )

    assert verdict.status == PaymentStatus.paid
    assert seen[0]["paymentData"]["token"]["id"] == "tok-1"
    assert seen[0]["amount"] == {"value": 990.0, "currency": "RUB"}


@pytest.mark.parametrize("status", ["Confirmation", "Pending", "Authorized"])
async def test_paymaster_holds_back_on_anything_short_of_settled(mock_http, status):
    """Authorized is a hold, Confirmation wants the payer back. Handing over a
    month for either would be giving the goods away."""
    from app.services.payments.base import RecurringSetup

    with mock_http(lambda request: httpx.Response(200, json={"paymentId": "p", "status": status})):
        verdict = await get_provider("paymaster").charge_recurring(
            credentials={"merchant_id": "m", "token": "t"},
            setup=RecurringSetup(token="tok"),
            amount_minor=99000,
            currency="RUB",
            description="PRO",
            payment_id=uuid.uuid4(),
        )
    assert verdict.status == PaymentStatus.pending


async def test_ioka_charges_a_saved_card_through_a_fresh_order(mock_http):
    seen: list[httpx.Request] = []

    def handler(request):
        seen.append(request)
        if request.url.path.endswith("/orders"):
            return httpx.Response(200, json={"order": {"id": "ord_9", "checkout_url": "https://pay"}})
        return httpx.Response(
            200, json={"id": "pay_9", "status": "APPROVED", "approved_amount": 59000, "captured_amount": 59000}
        )

    from app.services.payments.base import RecurringSetup

    with mock_http(handler):
        verdict = await get_provider("ioka").charge_recurring(
            credentials={"api_key": "sk"},
            setup=RecurringSetup(token="card_1", customer="cus_1"),
            amount_minor=59000,
            currency="KZT",
            description="Клуб",
            payment_id=uuid.uuid4(),
        )

    assert verdict.status == PaymentStatus.paid
    order_body = json.loads(seen[0].content)
    assert order_body["capture_method"] == "AUTO", "под MANUAL APPROVED — это только холд"
    assert order_body["customer_id"] == "cus_1"
    assert json.loads(seen[1].content) == {"card_id": "card_1"}
    assert str(seen[1].url).endswith("/orders/ord_9/payments/card")


async def test_ioka_an_approved_but_uncaptured_charge_is_not_money(mock_http):
    """The one trap the docs call out: APPROVED with captured_amount 0 is an
    authorisation, and the money has not moved."""
    from app.services.payments.base import RecurringSetup

    def handler(request):
        if request.url.path.endswith("/orders"):
            return httpx.Response(200, json={"order": {"id": "ord_9"}})
        return httpx.Response(200, json={"id": "p", "status": "APPROVED", "captured_amount": 0})

    with mock_http(handler):
        verdict = await get_provider("ioka").charge_recurring(
            credentials={"api_key": "sk"},
            setup=RecurringSetup(token="card_1", customer="cus_1"),
            amount_minor=59000,
            currency="KZT",
            description="Клуб",
            payment_id=uuid.uuid4(),
        )
    assert verdict.status == PaymentStatus.pending


async def test_ioka_reports_the_declines_own_words(mock_http):
    from app.services.payments.base import RecurringSetup

    def handler(request):
        if request.url.path.endswith("/orders"):
            return httpx.Response(200, json={"order": {"id": "ord_9"}})
        return httpx.Response(
            200,
            json={"status": "DECLINED", "error": {"code": "WRONG_CARD_DATA_INPUT", "message": "Операция отклонена"}},
        )

    with mock_http(handler):
        verdict = await get_provider("ioka").charge_recurring(
            credentials={"api_key": "sk"},
            setup=RecurringSetup(token="card_1", customer="cus_1"),
            amount_minor=59000,
            currency="KZT",
            description="Клуб",
            payment_id=uuid.uuid4(),
        )
    assert verdict.status == PaymentStatus.failed
    assert verdict.meta["decline"] == "Операция отклонена"


async def test_prodamus_sells_the_plan_not_our_price(mock_http):
    """Prodamus documents that with a subscription id present «сумма платежа
    не учитывается» — so sending `products` alongside would only look like the
    block's price mattered."""
    from urllib.parse import parse_qs, urlparse

    provider = get_provider("prodamus")
    creds = {"shop_domain": "demo.payform.ru", "secret_key": "s"}

    checkout = await provider.create_checkout(
        _generic_request(creds, extra={"subscription": True, "prodamus_subscription_id": "777"})
    )
    params = parse_qs(urlparse(checkout.url).query)
    assert params["subscription"] == ["777"]
    assert not any(key.startswith("products") for key in params), "план и товар одновременно — ложь про цену"

    plain = await provider.create_checkout(_generic_request(creds, extra={}))
    plain_params = parse_qs(urlparse(plain.url).query)
    assert "subscription" not in plain_params
    assert any(key.startswith("products") for key in plain_params)


async def test_prodamus_refuses_a_subscription_block_without_a_plan():
    """Silently selling it as a one-off would take the money once and never
    come back — the exact failure this whole feature exists to remove."""
    with pytest.raises(ProviderError, match="ID подписки"):
        await get_provider("prodamus").create_checkout(
            _generic_request({"shop_domain": "demo.payform.ru", "secret_key": "s"}, extra={"subscription": True})
        )


async def test_prodamus_records_what_the_plan_charged_instead_of_rejecting_it():
    """The block says 590; the plan charges 990, or 1 ₽ for a first month.
    Comparing them would reject every renewal forever. The notification's
    signature is what actually guards this, and the real amount is written
    down rather than argued with."""
    from app.services.payments.prodamus import sign

    secret = "s"
    data = {
        "order_id": str(uuid.uuid4()),
        "order_num": "A-1",
        "payment_status": "success",
        "sum": "990.00",
        "subscription[id]": "777",
    }
    body = "&".join(f"{k}={v}" for k, v in data.items())
    # Prodamus signs the *parsed* structure, PHP-style keys and all — which is
    # also the shape the adapter has to find the plan id in.
    from app.services.payments.prodamus import parse_form

    verdict = await get_provider("prodamus").verify_webhook(
        headers={"sign": sign(parse_form(body), secret)},
        raw_body=body.encode(),
        form=data,
        credentials={"shop_domain": "demo.payform.ru", "secret_key": secret},
        amount_minor=59000,  # ← our block's price, deliberately different
        invoice_no=1,
        payment_id=uuid.UUID(data["order_id"]),
        provider_payment_id=None,
        meta={},
        currency="RUB",
    )

    assert verdict.status == PaymentStatus.paid
    assert verdict.meta["charged_amount_minor"] == 99000
    assert verdict.meta["prodamus_subscription_id"] == "777"


async def test_a_plain_prodamus_sale_still_checks_the_amount():
    """The relaxation is scoped to subscriptions. A one-off sale that comes
    back for less must still be refused."""
    from app.services.payments.prodamus import sign

    secret = "s"
    from app.services.payments.prodamus import parse_form

    data = {
        "order_id": str(uuid.uuid4()),
        "order_num": "A-2",
        "payment_status": "success",
        "sum": "10.00",
    }
    body = "&".join(f"{k}={v}" for k, v in data.items())

    with pytest.raises(ProviderError, match="сумма не совпадает"):
        await get_provider("prodamus").verify_webhook(
            headers={"sign": sign(parse_form(body), secret)},
            raw_body=body.encode(),
            form=data,
            credentials={"shop_domain": "demo.payform.ru", "secret_key": secret},
            amount_minor=59000,
            invoice_no=1,
            payment_id=uuid.UUID(data["order_id"]),
            provider_payment_id=None,
            meta={},
            currency="RUB",
        )


async def test_the_row_records_what_was_actually_charged(db, owner, make_bot, as_bot):
    """A sales log showing the price we guessed, not the price taken, is how a
    shop that raised its plan in the dashboard keeps seeing the old number."""
    from app.services import payment_service

    bot, blocks = await club_bot(db, owner, make_bot, provider="test")
    payment = await paid_order(db, bot, blocks[1], provider="test", amount=59000)
    payment.status = PaymentStatus.pending
    await db.commit()

    verdict = type("R", (), {
        "status": PaymentStatus.paid,
        "provider_payment_id": "x",
        "meta": {"charged_amount_minor": 99000},
    })()
    await payment_service.apply_result(db, payment, verdict, deliver=False)

    await db.refresh(payment)
    assert payment.amount_minor == 99000
    assert payment.meta["block_amount_minor"] == 59000


# ------------------------------------------------- выключатель подписок


async def test_the_switch_really_switches_it_off(db, owner, make_bot, as_bot, monkeypatch):
    """Hiding the toggle is not enough. A block saved while subscriptions were
    on still carries `subscription: true`, and the danger is that it goes on
    opening subscriptions — and, on Stripe or Stars, asking the gateway to
    bill a card every month — with nothing in the constructor to show for it.
    """
    from app.config import get_settings
    from app.services.payment_service import _purchase_terms

    monkeypatch.setenv("SUBSCRIPTIONS_ENABLED", "false")
    get_settings.cache_clear()

    content = {"title": "Клуб", "price": "590", "subscription": True, "period_days": 30}

    # 1. The adapters never see the flag, so no recurring invoice is minted.
    assert "subscription" not in _purchase_terms(content)
    assert "period_days" not in _purchase_terms(content)

    # 2. And a settled payment on such a block opens nothing.
    bot, blocks = await club_bot(db, owner, make_bot, provider="stars")
    payment = await paid_order(db, bot, blocks[1])
    assert await subscription_service.start_or_extend(db, payment) is None


async def test_turning_it_back_on_needs_no_migration(db, owner, make_bot, as_bot, monkeypatch):
    """The point of a switch rather than a deletion: the same block starts
    selling subscriptions again the moment it is flipped."""
    from app.config import get_settings
    from app.services.payment_service import _purchase_terms

    monkeypatch.setenv("SUBSCRIPTIONS_ENABLED", "true")
    get_settings.cache_clear()

    content = {"title": "Клуб", "price": "590", "subscription": True, "period_days": 30}
    assert _purchase_terms(content)["subscription"] is True

    bot, blocks = await club_bot(db, owner, make_bot, provider="stars")
    payment = await paid_order(db, bot, blocks[1])
    assert await subscription_service.start_or_extend(db, payment) is not None


async def test_a_subscription_block_sells_as_a_one_off_while_the_switch_is_off(
    db, owner, make_bot, mock_http, monkeypatch
):
    """The whole point of stripping the flag at the choke point rather than
    only hiding the toggle.

    A block saved while subscriptions were on still carries them in its
    content — a template's does from the start. With the feature off, the
    money path must sell it as an ordinary purchase: no `save_payment_method`
    on the way out, and no subscription row on the way back. Anything less
    and a shop testing "просто разовая оплата" would quietly be asking its
    customers to authorise a standing arrangement.
    """
    from app.config import get_settings
    from app.services import payment_service

    monkeypatch.setenv("SUBSCRIPTIONS_ENABLED", "false")
    get_settings.cache_clear()

    seen: list[dict] = []

    def handler(request):
        seen.append(json.loads(request.content))
        return httpx.Response(200, json={"id": "p1", "confirmation": {"confirmation_url": "https://pay"}})

    bot, blocks = await club_bot(db, owner, make_bot, provider="yookassa", subscription=True)
    # Exactly the shape a template leaves behind.
    assert blocks[1].content["subscription"] is True

    with mock_http(handler):
        payment, url = await payment_service.create_order_payment(
            db, bot=bot, block=blocks[1], chat_id=CHAT_ID, telegram_user_id=USER_ID
        )

    assert url == "https://pay"
    assert "save_payment_method" not in seen[0], "выключенная подписка не должна просить сохранить карту"

    verdict = type("R", (), {"status": PaymentStatus.paid, "provider_payment_id": "x", "meta": {}})()
    await payment_service.apply_result(db, payment, verdict, deliver=False)
    opened = (
        await db.execute(select(Subscription).where(Subscription.bot_id == bot.id))
    ).scalars().all()
    assert opened == [], "подписка не должна открыться при выключенной фиче"
