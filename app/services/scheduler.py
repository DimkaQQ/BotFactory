"""Conversations that continue later.

The dialogue engine runs a chain to its end inside the update that started
it, which is why a "Пауза" block was clamped to fifteen seconds: the webhook
request is held open for it. That ceiling is what made the product's most
common subscription promise — "3-4 видео в течение месяца" — unbuildable
with any combination of blocks.

A `ScheduledStep` is a walk that has not started yet. The dispatcher, on
reaching a pause longer than it is willing to sit through, writes one for
`next_block_id` and returns; this sweep picks it up when it is due and
resumes the chain exactly as the webhook would have.

Two properties this has to hold, both learned from the payment path:

* **At most one send per step.** A step is claimed with a conditional
  UPDATE (pending → sent) before anything is sent, so two sweeps — or two
  processes — cannot both deliver it. The cost is that a hard crash between
  the claim and the send drops that step; the same window the payment
  delivery has, and the same trade (a silent duplicate is worse here than a
  missed one, because the duplicate charges nobody but does confuse).
* **Liveness is re-read, never trusted.** Work queued a month ago was
  queued while the subscription was healthy. Whether it still is gets
  checked at send time, so a cancellation takes effect immediately instead
  of playing out whatever was already in the queue.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.bot_block import BotBlock
from app.models.scheduled_step import ScheduledStep, StepStatus
from app.models.subscription import Subscription, SubscriptionStatus

logger = logging.getLogger(__name__)

#: How long a pause the dispatcher will simply sit through inside the
#: webhook request. Anything longer becomes a scheduled step. Kept here
#: rather than in the dispatcher because it is really a property of this
#: mechanism: below it, the scheduler is not worth a database round trip.
INLINE_PAUSE_SECONDS = 15.0

#: Give up after this many failed attempts. A step that has failed five
#: times is not going to start working, and retrying it forever is how a
#: sweep turns into a permanent error loop.
MAX_ATTEMPTS = 5

#: Retry backoff, indexed by attempt count.
_BACKOFF = (timedelta(minutes=1), timedelta(minutes=5), timedelta(minutes=30), timedelta(hours=2))


#: Сколько раз одна переписка может пройти через длинную «Паузу» за окно.
#: Настоящий сценарий — подписка с уроками — это единицы шагов в сутки;
#: сотня означает, что владелец замкнул стрелку на себя.
_MAX_PAUSED_HOPS = 100
_LOOP_WINDOW_HOURS = 24


async def _loop_is_sane(db: AsyncSession, bot_id: uuid.UUID, chat_id: int) -> bool:
    since = datetime.now(timezone.utc) - timedelta(hours=_LOOP_WINDOW_HOURS)
    hops = await db.execute(
        select(func.count(ScheduledStep.id)).where(
            ScheduledStep.bot_id == bot_id,
            ScheduledStep.chat_id == chat_id,
            ScheduledStep.reason == "delay",
            ScheduledStep.created_at > since,
        )
    )
    return hops.scalar_one() < _MAX_PAUSED_HOPS


async def schedule(
    db: AsyncSession,
    *,
    bot_id: uuid.UUID,
    block_id: uuid.UUID | None,
    chat_id: int,
    telegram_user_id: int | None,
    delay_seconds: float | None = None,
    run_at: datetime | None = None,
    reason: str = "delay",
    subscription_id: uuid.UUID | None = None,
) -> ScheduledStep | None:
    """Queue "resume from `block_id`" for later. Commits.

    Returns None when there is nothing to resume — a pause at the very end
    of a chain has no next block, and queueing a walk from nowhere would
    just be a row that wakes up and does nothing.
    """
    if reason == "delay" and not await _loop_is_sane(db, bot_id, chat_id):
        # A cycle that goes through a long «Пауза» has no brake of its own:
        # `_MAX_CHAIN_STEPS` and the `visited` set live inside one walk, and a
        # scheduled hop starts a fresh walk with both reset. So [сообщение] →
        # [Пауза] → назад ran forever, growing the queue, hammering Telegram's
        # rate limit and spamming from a published bot with nothing to stop it
        # short of editing the database.
        logger.error(
            "Bot %s chat %s: too many paused hops in %d h — refusing to queue another. "
            "Похоже на цикл в сценарии.", bot_id, chat_id, _LOOP_WINDOW_HOURS,
        )
        return None

    if block_id is None:
        return None

    when = run_at or datetime.now(timezone.utc) + timedelta(seconds=max(0.0, delay_seconds or 0.0))
    step = ScheduledStep(
        bot_id=bot_id,
        block_id=block_id,
        chat_id=chat_id,
        telegram_user_id=telegram_user_id,
        subscription_id=subscription_id,
        reason=reason,
        run_at=when,
    )
    db.add(step)
    await db.commit()
    logger.info("Scheduled %s step for bot %s at %s (block %s)", reason, bot_id, when.isoformat(), block_id)
    return step


async def cancel_for_subscription(db: AsyncSession, subscription_id: uuid.UUID, *, why: str = "") -> int:
    """Withdraw everything still queued for a subscription that has ended.

    Belt and braces alongside the liveness re-read in `_run_step`: that stops
    a cancelled subscription from *sending*, this stops it from occupying the
    queue at all.
    """
    result = await db.execute(
        update(ScheduledStep)
        .where(ScheduledStep.subscription_id == subscription_id, ScheduledStep.status == StepStatus.pending)
        .values(status=StepStatus.cancelled, last_error=why[:500], ran_at=datetime.now(timezone.utc))
    )
    await db.commit()
    return result.rowcount or 0


async def _claim(db: AsyncSession, step_id: uuid.UUID) -> bool:
    """Take ownership of a step, or discover somebody already has.

    One conditional UPDATE, exactly like `payment_service.mark_paid` — the
    row moves out of `pending` in the same statement that tests that it is
    still in it, so two sweeps racing on the same step produce one winner.
    """
    result = await db.execute(
        update(ScheduledStep)
        .where(ScheduledStep.id == step_id, ScheduledStep.status == StepStatus.pending)
        .values(status=StepStatus.sent, ran_at=datetime.now(timezone.utc), attempts=ScheduledStep.attempts + 1)
    )
    await db.commit()
    return (result.rowcount or 0) == 1


async def _give_up_or_retry(db: AsyncSession, step: ScheduledStep, error: str) -> None:
    step.last_error = error[:500]
    if step.attempts >= MAX_ATTEMPTS:
        step.status = StepStatus.failed
        logger.error("Scheduled step %s failed %d times, giving up: %s", step.id, step.attempts, error)
    else:
        step.status = StepStatus.pending
        step.run_at = datetime.now(timezone.utc) + _BACKOFF[min(step.attempts - 1, len(_BACKOFF) - 1)]
        logger.warning("Scheduled step %s failed (attempt %d), retrying at %s", step.id, step.attempts, step.run_at)
    await db.commit()


#: Сколько ждать возвращения снятого бота, прежде чем признать, что он не
#: вернётся. Заметно больше грейса (7 дней) и больше периода (30): владелец,
#: который оплатил через три недели, должен получить свою очередь целой.
_HOLD_LIMIT = timedelta(days=45)
#: Как часто проверять, не вернулся ли он. Не чаще: ожидание измеряется
#: днями, а каждая проверка — это строка, поднятая из очереди.
_HOLD_RECHECK = timedelta(hours=1)


async def _bot_is_merely_off_the_air(db: AsyncSession, bot_id: uuid.UUID) -> bool:
    """Бот выключен, но жив: токен на месте, вернуть его может одна оплата."""
    from app.models.bot import Bot as BotModel
    from app.models.bot import BotStatus

    row = (
        await db.execute(
            select(BotModel.status, BotModel.bot_token_encrypted).where(BotModel.id == bot_id)
        )
    ).first()
    return bool(row and row[0] == BotStatus.disabled and row[1])


async def _hold(db: AsyncSession, step: ScheduledStep, reason: str) -> None:
    """Отложить, не тратя попытку.

    Попытки считают отказы, а это не отказ: слать некуда не потому, что
    что-то сломалось, а потому что бот ждёт оплаты. Шаг остаётся pending и
    возвращается через час — и так до `_HOLD_LIMIT`, после чего сдаёмся
    честно, с причиной, которую видно в очереди.
    """
    now = datetime.now(timezone.utc)
    created = step.created_at if step.created_at.tzinfo else step.created_at.replace(tzinfo=timezone.utc)
    if now - created > _HOLD_LIMIT:
        step.status = StepStatus.cancelled
        step.last_error = f"{reason}: не дождались за {_HOLD_LIMIT.days} дн."
        step.ran_at = now
        await db.commit()
        logger.warning("Scheduled step %s cancelled: %s", step.id, step.last_error)
        return
    step.status = StepStatus.pending
    step.run_at = now + _HOLD_RECHECK
    step.last_error = reason
    # `_claim` увеличивает счётчик попыток на входе — а удержание попыткой не
    # является. Без отката ожидание само сожгло бы лимит за пять часов, и
    # смысл удержания пропал бы полностью: шаг дождался бы возвращения бота
    # уже помеченным failed.
    step.attempts = max(0, step.attempts - 1)
    await db.commit()


async def _still_entitled(db: AsyncSession, step: ScheduledStep) -> str | None:
    """Reason not to send, or None to go ahead."""
    if step.subscription_id is None:
        return None
    subscription = (
        await db.execute(select(Subscription).where(Subscription.id == step.subscription_id))
    ).scalar_one_or_none()
    if subscription is None:
        return "подписка удалена"
    if subscription.status != SubscriptionStatus.active:
        return f"подписка {subscription.status.value}"
    # Expiry is a moment, not an event: nothing has to have run for a period
    # to be over, so the date is what decides, not a status somebody had to
    # remember to update.
    if subscription.current_period_end <= datetime.now(timezone.utc):
        return "период оплачен до " + subscription.current_period_end.date().isoformat()
    return None


async def _run_step(step_id: uuid.UUID) -> None:
    from app.database import AsyncSessionLocal
    from app.services import bot_dispatcher, bot_registry, subscribers

    async with AsyncSessionLocal() as db:
        step = (await db.execute(select(ScheduledStep).where(ScheduledStep.id == step_id))).scalar_one_or_none()
        if step is None or step.status != StepStatus.pending:
            return

        if step.block_id is None:
            # ON DELETE SET NULL fired: the owner deleted the block this step
            # was going to send. Cancelled with a reason rather than left
            # pending forever or quietly dropped.
            step.status = StepStatus.cancelled
            step.last_error = "блок удалён"
            step.ran_at = datetime.now(timezone.utc)
            await db.commit()
            return

        skip = await _still_entitled(db, step)
        if skip is not None:
            step.status = StepStatus.cancelled
            step.last_error = skip[:500]
            step.ran_at = datetime.now(timezone.utc)
            await db.commit()
            return

        subscriber = await subscribers.get(db, step.bot_id, step.telegram_user_id)
        if subscriber is not None and subscriber.blocked_at is not None:
            step.status = StepStatus.cancelled
            step.last_error = "бот заблокирован пользователем"
            step.ran_at = datetime.now(timezone.utc)
            await db.commit()
            return

        # The block may have been deleted and the FK not yet reflected here,
        # or moved to another bot; either way there is nothing to send.
        block = (
            await db.execute(
                select(BotBlock.id).where(BotBlock.id == step.block_id, BotBlock.bot_id == step.bot_id)
            )
        ).scalar_one_or_none()
        if block is None:
            step.status = StepStatus.cancelled
            step.last_error = "блок больше не принадлежит этому боту"
            step.ran_at = datetime.now(timezone.utc)
            await db.commit()
            return

        if not await _claim(db, step.id):
            return  # another sweep got there first

        await db.refresh(step)

        if step.reason == "charge":
            # Not a message to send — money to take. The subscription layer
            # owns everything that follows (the new payment row, extending
            # the period, telling both sides), so this is the whole branch.
            from app.services import subscription_service

            subscription = (
                await db.execute(select(Subscription).where(Subscription.id == step.subscription_id))
            ).scalar_one_or_none()
            if subscription is None:
                step.status = StepStatus.cancelled
                step.last_error = "подписка удалена"
                await db.commit()
                return
            try:
                await subscription_service.charge_now(db, subscription)
            except Exception as exc:
                await _give_up_or_retry(db, step, repr(exc))
            return

        try:
            bot_instance = await bot_registry.get_or_create(step.bot_id, db)
            if bot_instance is None:
                # "Бот не отвечает" бывает двух совершенно разных сортов, и
                # раньше оба считались неудачей. Снятый за неоплату бот
                # сжигал пять попыток за пять часов, после чего ВСЁ, что
                # было запланировано его подписчикам, помечалось failed
                # навсегда. Владелец платил на следующий день, бот
                # возвращался — а уроки, за которые люди уже отдали деньги,
                # не приходили никогда. Грейс-период существует ровно
                # затем, чтобы такого не было, и обрывался на полпути.
                if await _bot_is_merely_off_the_air(db, step.bot_id):
                    await _hold(db, step, "бот снят с эфира — ждём продления")
                    return
                await _give_up_or_retry(db, step, "у бота нет токена")
                return
            await bot_dispatcher.walk_chain(
                bot_instance,
                step.chat_id,
                step.block_id,
                step.bot_id,
                db,
                telegram_user_id=step.telegram_user_id,
                # Рассылку человек не просил — значит, в ней обязано быть
                # сказано, как её прекратить.
                footer="Чтобы не получать рассылку — отправь /stop" if step.reason == "broadcast" else "",
            )
        except Exception as exc:
            if subscribers.looks_blocked(exc):
                await subscribers.mark_blocked(db, step.bot_id, step.telegram_user_id)
                step.status = StepStatus.cancelled
                step.last_error = "бот заблокирован пользователем"
                await db.commit()
                return
            await _give_up_or_retry(db, step, repr(exc))


async def run_due(limit: int = 200) -> int:
    """Run everything that has come due. Returns how many were attempted."""
    from app.database import AsyncSessionLocal

    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(ScheduledStep.id)
            .where(ScheduledStep.status == StepStatus.pending, ScheduledStep.run_at <= datetime.now(timezone.utc))
            .order_by(ScheduledStep.run_at)
            .limit(limit)
        )
        due = list(result.scalars().all())

    for step_id in due:
        try:
            await _run_step(step_id)
        except Exception:
            # One bad step must not end the sweep for everyone behind it.
            logger.exception("Scheduled step %s blew up outside its own error handling", step_id)
    return len(due)


async def run_forever(every_seconds: float = 30.0) -> None:
    """Keep the queue moving for as long as the process lives.

    Thirty seconds because the unit a person schedules in is minutes at the
    finest — the block editor's smallest non-inline step — so this is well
    inside "on time" while still being one cheap indexed query per tick.
    """
    while True:
        await asyncio.sleep(every_seconds)
        try:
            await run_due()
        except asyncio.CancelledError:
            raise
        except Exception:
            # A sweep that dies takes every later sweep with it, which is the
            # failure this loop exists to prevent.
            logger.exception("Scheduler sweep failed; will try again")
