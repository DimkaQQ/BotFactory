"""Standing access, a period at a time.

The claim being pinned is the honest one: **one** of the twenty providers can
charge again by itself. Telegram Stars does, and these tests check the
argument that makes it happen actually goes out. Every other provider is a
reminder-and-re-invoice cycle, and the code is required to call it that
rather than quietly present it as automatic billing.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from app.models.bot_block import BlockType
from app.models.payment import Payment, PaymentKind, PaymentStatus
from app.models.scheduled_step import ScheduledStep, StepStatus
from app.models.subscription import BillingMode, Subscription, SubscriptionStatus
from app.services import bot_dispatcher, subscription_service
from app.services.payments.base import CheckoutRequest

CHAT_ID = 991
USER_ID = 5150


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
    )
    return bot, blocks


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


def test_only_stars_is_sold_as_automatic():
    """Every other adapter is invoice-based: nothing in it can initiate a
    second charge, so calling it automatic would be the lie this whole change
    exists to remove."""
    from app.services.payments import PROVIDERS

    assert subscription_service.billing_mode("stars") == BillingMode.auto
    for slug in PROVIDERS:
        if slug == "stars":
            continue
        assert subscription_service.billing_mode(slug) == BillingMode.renewal, slug


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
