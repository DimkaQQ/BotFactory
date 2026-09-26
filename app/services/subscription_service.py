"""Standing access, a period at a time.

Three different things are called "подписка" by the twenty gateways, and the
difference decides what the shop owner actually has, so it is carried
explicitly rather than averaged away (see `payments.base.RecurringMode`):

* **the gateway runs it** — Telegram Stars and Stripe. We create the
  subscription once; they charge on their own schedule, retry their own
  declines, and give the buyer somewhere to cancel. No card detail, not even
  a handle to one, is ours to hold.
* **we charge a saved method** — ЮKassa (`save_payment_method` →
  `payment_method_id`) and CloudPayments (`Token` → `payments/tokens/charge`).
  The first payment saves the method and hands back a handle; every later
  charge is initiated by our own scheduler. More control, and the dunning
  policy becomes our problem.
* **re-invoice** — everyone else. Nothing in the integration can take money
  again, so the bot sends a fresh invoice before the period ends and access
  continues only if it is paid. Honest recurring *billing*, not recurring
  *collection*, and the constructor says so in those words.

Either way `current_period_end` is the one fact everything else reads:
whether to send this month's video, whether the person is still in the
group, what the owner's list shows.
"""

from __future__ import annotations

import contextlib
import logging
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.bot import Bot as BotModel
from app.models.bot_block import BotBlock
from app.models.payment import Payment, PaymentKind, PaymentStatus
from app.models.subscription import BillingMode, Subscription, SubscriptionStatus
from app.services import dates
from app.services import scheduler
from app.services.payments import get_provider
from app.services.payments.base import ProviderError, RecurringMode, RecurringSetup

logger = logging.getLogger(__name__)


#: How long before a period ends to ask for the next one. Two days, so a
#: renewal that needs a bank app, a top-up or a working day still has room
#: before access stops.
RENEWAL_LEAD_DAYS = 2

DEFAULT_PERIOD_DAYS = 30


def billing_mode(provider: str | None) -> BillingMode:
    """Automatic where the integration can actually take money again.

    Read off the adapter rather than a list kept here, so a provider that
    gains (or loses) recurring changes this in one place — the module that
    knows how that gateway works.
    """
    try:
        mode = get_provider(provider or "").recurring
    except ProviderError:
        return BillingMode.renewal
    return BillingMode.auto if mode is not RecurringMode.none else BillingMode.renewal


def charges_itself(provider: str | None) -> bool:
    """True when *we* have to initiate each later charge (token recurring),
    as opposed to the gateway running the subscription on its own."""
    try:
        return get_provider(provider or "").recurring is RecurringMode.token
    except ProviderError:
        return False


def is_subscription_block(content: dict | None) -> bool:
    """Whether this payment block sells a period rather than a thing.

    Gated on the feature switch so that turning subscriptions off really
    turns them off: an existing block still carries `subscription: true` in
    its content, and without this check it would keep opening subscriptions
    and queueing charges while the constructor showed no sign of it.
    """
    from app.config import get_settings

    if not get_settings().subscriptions_enabled:
        return False
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
    # A payment we raised ourselves to renew carries the handle of the one
    # that opened the subscription; a payment the buyer made *is* that handle.
    handle = (payment.meta or {}).get("renews") or str(payment.id)
    result = await db.execute(
        select(Subscription).where(
            Subscription.bot_id == payment.bot_id,
            Subscription.provider_subscription_id == str(handle),
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
        _remember_method(existing, payment)
        # A method can arrive late — the buyer saved a card on their second
        # payment — and a subscription that starts as "по счёту" becomes
        # automatic from then on.
        existing.billing_mode = _actual_billing_mode(existing)
        await db.commit()
        await _schedule_renewal(db, existing)
        return existing

    days = period_days(content)
    subscription = Subscription(
        bot_id=payment.bot_id,
        block_id=payment.block_id,
        telegram_user_id=payment.telegram_user_id,
        chat_id=payment.chat_id or payment.telegram_user_id,
        provider=payment.provider,
        billing_mode=BillingMode.renewal,  # corrected below, once we know
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
    _remember_method(subscription, payment)
    # "Автосписание" only if there is actually something to charge with. For
    # a gateway-run subscription that is the gateway's promise; for a saved
    # method it is a handle we either got or did not — ЮKassa refuses to save
    # one for a shop without autopayments enabled, and ioka only saves a card
    # the buyer chose to save. Claiming `auto` in those cases would put
    # "спишется само" in front of an owner whose subscribers will be
    # re-invoiced.
    subscription.billing_mode = _actual_billing_mode(subscription)
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


def _actual_billing_mode(subscription: Subscription) -> BillingMode:
    """What this subscription can really do, not what the gateway can."""
    if not charges_itself(subscription.provider):
        # Gateway-run, or nothing at all — the provider's own capability is
        # the whole answer.
        return billing_mode(subscription.provider)
    return BillingMode.auto if (subscription.meta or {}).get("recurring_token") else BillingMode.renewal


def _remember_method(subscription: Subscription, payment: Payment) -> None:
    """Keep the handle the gateway gave us for charging this person again.

    Stored encrypted with the same Fernet key as the shop's API credentials.
    On its own the handle is inert — it only moves money together with those
    credentials — but it moves money, so it is not left lying in plaintext
    JSONB next to things that do not.

    Re-read on every settled payment rather than only the first: a gateway
    can rotate the handle (ЮKassa returns a fresh `payment_method.id` when a
    buyer re-confirms), and a stale one declines silently a month later.
    """
    from app.services.payment_service import encrypt_credentials

    try:
        provider = get_provider(subscription.provider)
    except ProviderError:
        return
    setup = provider.recurring_setup(payment.meta or {})
    if setup is None:
        return

    blob = encrypt_credentials({"token": setup.token, "customer": setup.customer}).decode("ascii")
    subscription.meta = {**(subscription.meta or {}), "recurring_token": blob}


def _saved_method(subscription: Subscription) -> RecurringSetup | None:
    from app.services.payment_service import decrypt_credentials

    blob = (subscription.meta or {}).get("recurring_token")
    if not blob:
        return None
    try:
        stored = decrypt_credentials(blob.encode("ascii"))
    except Exception:
        logger.exception("Subscription %s: stored payment method could not be read", subscription.id)
        return None
    token = stored.get("token")
    return RecurringSetup(token=token, customer=stored.get("customer") or "") if token else None


async def _schedule_renewal(db: AsyncSession, subscription: Subscription) -> None:
    """Queue what happens as this period runs out — one of three things.

    * gateway-run (Stars, Stripe): nothing to queue. They will charge or they
      will not, and the expiry sweep withdraws access if nothing arrived.
    * token (ЮKassa, CloudPayments): a charge, at the moment the period ends.
      Not earlier — the buyer paid for every day of it.
    * re-invoice: a reminder, far enough ahead to be actionable.
    """
    # Anything queued for an earlier period is stale the moment the period
    # moves; leaving it would charge or remind twice for a month already paid.
    await scheduler.cancel_for_subscription(db, subscription.id, why="период продлён")

    if charges_itself(subscription.provider):
        if not (subscription.meta or {}).get("recurring_token"):
            # Paid, but the gateway did not hand back a saved method — the
            # shop may not have autopayments enabled. Falls back to asking,
            # which at least keeps the subscriber, and says so in the log.
            logger.warning(
                "Subscription %s is on %s but has no saved payment method — falling back to re-invoicing",
                subscription.id,
                subscription.provider,
            )
        else:
            await scheduler.schedule(
                db,
                bot_id=subscription.bot_id,
                block_id=subscription.block_id,
                chat_id=subscription.chat_id,
                telegram_user_id=subscription.telegram_user_id,
                run_at=subscription.current_period_end,
                reason="charge",
                subscription_id=subscription.id,
            )
            return

    if subscription.billing_mode == BillingMode.renewal or charges_itself(subscription.provider):
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


async def charge_now(db: AsyncSession, subscription: Subscription) -> bool:
    """Take the next period's money from the saved method. Returns success.

    A fresh `Payment` row is created for it and settled through
    `apply_result` — the same single place an order becomes paid whether the
    money came from a webhook, a buyer's "Я оплатил", the owner's confirm or
    this. That is also what extends the period, notifies the owner and
    re-queues the next charge, so none of it is duplicated here.
    """
    from app.services import bot_registry, payment_service

    setup = _saved_method(subscription)
    if setup is None:
        return False

    bot_row = (
        await db.execute(select(BotModel).where(BotModel.id == subscription.bot_id))
    ).scalar_one_or_none()
    if bot_row is None:
        return False

    provider = get_provider(subscription.provider)
    credentials = payment_service.decrypt_credentials(bot_row.payment_credentials_encrypted)

    payment = Payment(
        kind=PaymentKind.order,
        status=PaymentStatus.pending,
        provider=subscription.provider,
        amount_minor=subscription.amount_minor,
        currency=subscription.currency,
        description=(subscription.title or "Продление подписки")[:255],
        bot_id=subscription.bot_id,
        block_id=subscription.block_id,
        telegram_user_id=subscription.telegram_user_id,
        chat_id=subscription.chat_id,
        meta={
            # Marks this as our own initiative, not something the buyer
            # started — the sales log and any support question need to know.
            "auto_charge": True,
            "subscription_id": str(subscription.id),
            # Written *before* the charge, not after: Robokassa settles a
            # recurring charge through the ordinary ResultURL callback, which
            # can arrive before this function returns. Without the link
            # already in place that callback would settle a payment belonging
            # to no subscription, and the period would never move.
            "renews": subscription.provider_subscription_id,
        },
    )
    db.add(payment)
    await db.commit()

    try:
        verdict = await provider.charge_recurring(
            credentials=credentials,
            setup=setup,
            amount_minor=subscription.amount_minor,
            currency=subscription.currency,
            description=payment.description,
            payment_id=payment.id,
            is_test=bool(bot_row.payment_is_test),
            invoice_no=payment.invoice_no,
        )
    except ProviderError as exc:
        logger.warning("Subscription %s: charge refused — %s", subscription.id, exc)
        payment.status = PaymentStatus.failed
        payment.meta = {**(payment.meta or {}), "decline": str(exc)[:300]}
        await db.commit()
        await _tell_them_the_charge_failed(db, subscription, str(exc))
        return False

    if verdict.status == PaymentStatus.pending:
        # Requested, not yet taken. Robokassa works this way by design: its
        # acknowledgement means the operation was created, and whether the
        # money moved arrives later on the ordinary callback — which settles
        # this very payment and extends the period through the same path as
        # everything else. Nothing to tell the subscriber yet; if nothing
        # comes, the expiry sweep closes the period on its date.
        logger.info("Subscription %s: charge requested, waiting for the provider", subscription.id)
        return False

    if verdict.status != PaymentStatus.paid:
        reason = (verdict.meta or {}).get("decline") or "банк отклонил списание"
        logger.info("Subscription %s: charge not paid (%s)", subscription.id, reason)
        payment.status = PaymentStatus.failed
        payment.meta = {**(payment.meta or {}), "decline": str(reason)[:300]}
        await db.commit()
        await _tell_them_the_charge_failed(db, subscription, str(reason))
        return False

    charged = await payment_service.apply_result(db, payment, verdict, deliver=False)
    if charged:
        await _tell_them_it_renewed(db, subscription)
    return charged


async def _tell_them_the_charge_failed(db: AsyncSession, subscription: Subscription, why: str) -> None:
    """A failed charge is the one moment a subscriber can still fix it.

    Silence here is how a customer discovers a month later that they lost
    access, and the shop discovers it as a refund request.
    """
    from app.services import bot_registry, subscribers

    try:
        instance = await bot_registry.get_or_create(subscription.bot_id, db)
        if instance is None:
            return
        ends = dates.day(subscription.current_period_end)
        await instance.send_message(
            subscription.chat_id,
            f"⚠️ Не получилось списать оплату за «{subscription.title}».\n"
            f"Доступ работает до {ends}. Проверь карту и оплати вручную — нажми /start.",
        )
    except Exception as exc:
        if subscribers.looks_blocked(exc):
            await subscribers.mark_blocked(db, subscription.bot_id, subscription.telegram_user_id)
            return
        logger.exception("Could not tell user %s their charge failed", subscription.telegram_user_id)


async def _tell_them_it_renewed(db: AsyncSession, subscription: Subscription) -> None:
    from app.services import bot_registry

    with contextlib.suppress(Exception):
        instance = await bot_registry.get_or_create(subscription.bot_id, db)
        if instance is not None:
            until = dates.day(subscription.current_period_end)
            await instance.send_message(
                subscription.chat_id,
                f"🔁 Подписка «{subscription.title}» продлена — доступ открыт до {until}.",
            )


async def cancel(
    db: AsyncSession, subscription: Subscription, *, why: str = "", keep_paid_period: bool = False
) -> None:
    """Прекратить подписку.

    `keep_paid_period` — отмена самим подписчиком: списаний больше не будет,
    но оплаченный период он дослушивает до конца, и всё, что в нём
    запланировано, придёт. Доступ закроется в конце периода: `expire_due`
    забирает и отменённые тоже — пока он смотрел только на активные,
    отменённая подписка не истекала никогда и человек оставался в закрытом
    чате навсегда, перестав платить.
    """
    subscription.status = SubscriptionStatus.cancelled
    subscription.cancelled_at = datetime.now(timezone.utc)
    if why:
        subscription.meta = {**(subscription.meta or {}), "cancel_reason": why}
    await db.commit()
    await scheduler.cancel_for_subscription(
        db,
        subscription.id,
        why=why or "подписка отменена",
        # Снимаем только деньги, не содержимое.
        only_reasons=("charge", "renewal") if keep_paid_period else None,
    )


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
                # И отменённые тоже. Отмена означает «больше не списывайте»,
                # а не «отключите сейчас» — оплаченный период человек
                # дослушивает до конца. Но закрывать доступ в конце всё равно
                # надо: пока здесь стоял только `active`, отменённая подписка
                # не истекала никогда, и человек оставался в закрытом чате
                # навсегда, перестав платить.
                Subscription.status.in_((SubscriptionStatus.active, SubscriptionStatus.cancelled)),
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
