"""Standing access, a period at a time.

The honest shape of this feature, stated once so the rest of the code can be
read against it: **exactly one of the twenty payment providers can charge a
second time by itself.** Telegram Stars does, because Telegram holds the
payment instrument and bills against it on a 30-day cycle. ЮKassa, Т-Банк,
CloudPayments, Freedom Pay and the rest are invoice-based here — the adapter
mints a checkout, a person pays it, and nothing in the integration can
initiate a second charge later.

Pretending otherwise is what the product used to do: a template called
«Платная подписка» selling «Подписка стоит [цена] в месяц» on top of an
engine that took the money once and never came back. So there are two
billing modes and they are named differently everywhere the owner can see
them:

* `auto` (Stars) — Telegram charges monthly; we receive a fresh
  `successful_payment` on the same invoice payload and extend the period.
* `renewal` (everyone else) — when the period is nearly up the bot sends a
  fresh invoice and says so. Access continues if it is paid. This is a
  reminder-and-re-invoice cycle, and the constructor calls it that.

Either way `current_period_end` is the one fact everything else reads:
whether to send this month's video, whether the person is still in the
group, what the owner's list shows.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.bot_block import BotBlock
from app.models.payment import Payment, PaymentKind, PaymentStatus
from app.models.subscription import BillingMode, Subscription, SubscriptionStatus
from app.services import scheduler

logger = logging.getLogger(__name__)

#: Providers whose adapter can take money again without the buyer acting.
_SELF_CHARGING = {"stars"}

#: How long before a period ends to ask for the next one. Two days, so a
#: renewal that needs a bank app, a top-up or a working day still has room
#: before access stops.
RENEWAL_LEAD_DAYS = 2

DEFAULT_PERIOD_DAYS = 30


def billing_mode(provider: str | None) -> BillingMode:
    return BillingMode.auto if (provider or "") in _SELF_CHARGING else BillingMode.renewal


def is_subscription_block(content: dict | None) -> bool:
    return bool((content or {}).get("subscription"))


def period_days(content: dict | None) -> int:
    """How long one paid period lasts, from the block.

    Clamped rather than trusted: the field is a free number in the editor,
    and a zero would make every sweep treat the subscription as expired the
    instant it was created, while a huge one would sell lifetime access by
    typo. Stars has no choice at all — Telegram bills on 30 days and nothing
    else — which the constructor also says out loud.
    """
    raw = (content or {}).get("period_days", DEFAULT_PERIOD_DAYS)
    try:
        days = int(raw)
    except (TypeError, ValueError):
        return DEFAULT_PERIOD_DAYS
    return max(1, min(days, 365))


async def _block_content(db: AsyncSession, block_id: uuid.UUID | None) -> dict:
    if block_id is None:
        return {}
    block = (await db.execute(select(BotBlock).where(BotBlock.id == block_id))).scalar_one_or_none()
    return (block.content or {}) if block is not None else {}


async def find_for_payment(db: AsyncSession, payment: Payment) -> Subscription | None:
    """The subscription a payment belongs to, if any.

    Matched on the payload Telegram echoes back, because a Stars renewal
    arrives as a `successful_payment` for the *original* invoice — the same
    payment row, thirty days later. That is also why this is looked up by
    payment id rather than by (bot, user, block): the buyer may hold several
    subscriptions to the same bot.
    """
    if payment.bot_id is None or payment.telegram_user_id is None:
        return None
    result = await db.execute(
        select(Subscription).where(
            Subscription.bot_id == payment.bot_id,
            Subscription.provider_subscription_id == str(payment.id),
        )
    )
    return result.scalar_one_or_none()


async def start_or_extend(db: AsyncSession, payment: Payment) -> Subscription | None:
    """Called on every settled payment. Creates the subscription on the first
    one and pushes the period out on each later one.

    Returns the subscription, or None when this payment is not for one — the
    caller uses that to decide whether to say anything about renewals.
    """
    if payment.kind != PaymentKind.order or payment.bot_id is None or payment.telegram_user_id is None:
        return None

    content = await _block_content(db, payment.block_id)
    existing = await find_for_payment(db, payment)
    if existing is None and not is_subscription_block(content):
        return None

    now = datetime.now(timezone.utc)

    if existing is not None:
        days = existing.period_days
        # Extend from whichever is later: a renewal paid early must add to
        # what is left rather than throw it away, and one paid late starts
        # from today rather than back-dating a period the person did not have.
        base = max(existing.current_period_end, now)
        existing.current_period_end = base + timedelta(days=days)
        existing.periods_paid += 1
        existing.status = SubscriptionStatus.active
        existing.cancelled_at = None
        await db.commit()
        logger.info(
            "Subscription %s extended to %s (period %d)",
            existing.id,
            existing.current_period_end.isoformat(),
            existing.periods_paid,
        )
        await _schedule_renewal(db, existing)
        return existing

    days = period_days(content)
    subscription = Subscription(
        bot_id=payment.bot_id,
        block_id=payment.block_id,
        telegram_user_id=payment.telegram_user_id,
        chat_id=payment.chat_id or payment.telegram_user_id,
        provider=payment.provider,
        billing_mode=billing_mode(payment.provider),
        status=SubscriptionStatus.active,
        period_days=days,
        amount_minor=payment.amount_minor,
        currency=payment.currency,
        title=(content.get("title") or payment.description or "Подписка")[:255],
        current_period_end=now + timedelta(days=days),
        periods_paid=1,
        # The handle a Stars renewal will arrive under.
        provider_subscription_id=str(payment.id),
    )
    db.add(subscription)
    await db.commit()
    logger.info(
        "Subscription %s opened for user %s on bot %s (%s, %d days)",
        subscription.id,
        payment.telegram_user_id,
        payment.bot_id,
        subscription.billing_mode.value,
        days,
    )
    await _schedule_renewal(db, subscription)
    return subscription


async def _schedule_renewal(db: AsyncSession, subscription: Subscription) -> None:
    """Queue what happens as this period runs out.

    For `auto` there is nothing to ask for — Telegram will either charge or
    not — so only the expiry check is queued, and it is what withdraws access
    if the charge never came. For `renewal` a reminder goes out first, far
    enough ahead to be actionable.
    """
    # Anything queued for an earlier period is stale the moment the period
    # moves; leaving it would send a second reminder for a month already paid.
    await scheduler.cancel_for_subscription(db, subscription.id, why="период продлён")

    if subscription.billing_mode == BillingMode.renewal:
        lead = timedelta(days=min(RENEWAL_LEAD_DAYS, max(1, subscription.period_days - 1)))
        await scheduler.schedule(
            db,
            bot_id=subscription.bot_id,
            block_id=subscription.block_id,
            chat_id=subscription.chat_id,
            telegram_user_id=subscription.telegram_user_id,
            run_at=subscription.current_period_end - lead,
            reason="renewal",
            subscription_id=subscription.id,
        )


async def cancel(db: AsyncSession, subscription: Subscription, *, why: str = "") -> None:
    subscription.status = SubscriptionStatus.cancelled
    subscription.cancelled_at = datetime.now(timezone.utc)
    if why:
        subscription.meta = {**(subscription.meta or {}), "cancel_reason": why}
    await db.commit()
    await scheduler.cancel_for_subscription(db, subscription.id, why=why or "подписка отменена")


async def expire_due(limit: int = 500) -> int:
    """Close out every period that has run out without being paid for.

    Separate from the scheduler's own queue on purpose: a subscription can
    lapse without any step having been queued for it (the block was deleted,
    the queue was cleared, the process was down when the reminder was due),
    and "access ends when the period ends" must not depend on a row having
    survived. Returns how many were expired.
    """
    from app.database import AsyncSessionLocal
    from app.services import group_access

    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(Subscription)
            .where(
                Subscription.status == SubscriptionStatus.active,
                Subscription.current_period_end <= datetime.now(timezone.utc),
            )
            .limit(limit)
        )
        lapsed = list(result.scalars().all())

        for subscription in lapsed:
            subscription.status = SubscriptionStatus.expired
            logger.info("Subscription %s expired at %s", subscription.id, subscription.current_period_end)
        await db.commit()

        for subscription in lapsed:
            await scheduler.cancel_for_subscription(db, subscription.id, why="подписка закончилась")
            await group_access.revoke(db, subscription)
            await _tell_them_it_ended(db, subscription)

    return len(lapsed)


async def _tell_them_it_ended(db: AsyncSession, subscription: Subscription) -> None:
    """Say it out loud. A subscription that stops without a word is how a
    person finds out by noticing nothing arrived."""
    from app.services import bot_registry

    try:
        bot_instance = await bot_registry.get_or_create(subscription.bot_id, db)
        if bot_instance is None:
            return
        what = subscription.title or "подписка"
        if subscription.billing_mode == BillingMode.auto:
            note = "Оплата не прошла, поэтому доступ приостановлен. Можно оформить заново в любой момент."
        else:
            note = "Чтобы продолжить, оплати следующий период — нажми /start."
        await bot_instance.send_message(subscription.chat_id, f"⏳ «{what}» — срок доступа закончился.\n{note}")
    except Exception as exc:
        from app.services import subscribers

        if subscribers.looks_blocked(exc):
            await subscribers.mark_blocked(db, subscription.bot_id, subscription.telegram_user_id)
            return
        logger.exception("Could not tell user %s their subscription ended", subscription.telegram_user_id)


async def expire_forever(every_seconds: float = 300.0) -> None:
    import asyncio

    while True:
        await asyncio.sleep(every_seconds)
        try:
            await expire_due()
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Subscription expiry sweep failed; will try again")


async def active_for(db: AsyncSession, bot_id: uuid.UUID, telegram_user_id: int) -> list[Subscription]:
    result = await db.execute(
        select(Subscription)
        .where(
            Subscription.bot_id == bot_id,
            Subscription.telegram_user_id == telegram_user_id,
            Subscription.status == SubscriptionStatus.active,
        )
        .order_by(Subscription.created_at)
    )
    return list(result.scalars().all())


async def has_paid_for(db: AsyncSession, bot_id: uuid.UUID, telegram_user_id: int, block_id: uuid.UUID) -> bool:
    """Whether this person already bought this exact thing.

    Used to stop a returning buyer paying twice for the same volume of a
    guide, and to let a live subscriber back in without a second charge.
    """
    subscription = (
        await db.execute(
            select(Subscription.id).where(
                Subscription.bot_id == bot_id,
                Subscription.telegram_user_id == telegram_user_id,
                Subscription.block_id == block_id,
                Subscription.status == SubscriptionStatus.active,
                Subscription.current_period_end > datetime.now(timezone.utc),
            )
        )
    ).scalar_one_or_none()
    if subscription is not None:
        return True
    paid = (
        await db.execute(
            select(Payment.id).where(
                Payment.bot_id == bot_id,
                Payment.telegram_user_id == telegram_user_id,
                Payment.block_id == block_id,
                Payment.status == PaymentStatus.paid,
            )
        )
    ).first()
    return paid is not None
