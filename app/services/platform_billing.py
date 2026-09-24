"""What the bot's owner pays *us*, and what happens when they stop.

Two charges, one clock:

* the **launch** — paid once, at the end of building, and it opens the first
  period along with the publish button;
* the **renewal** — paid every period after that, to keep the bot on the air.

Both are ordinary one-off checkouts. Nothing here ever charges a saved card,
and that is a decision rather than an omission: the two methods this is
actually sold through are Stripe and Crypto Bot, and Crypto Bot has no way
to take money again at all — there is no stored instrument, no mandate, no
API for it. A billing model where half the customers are auto-charged and
the other half are invoiced is two products to support and two ways to get
it wrong, so everyone is invoiced. The owner gets a message in the
constructor's bot before the period ends and a «Продлить» button that opens
the same checkout the launch used.

The other decision worth stating: running out of money does not delete
anything. A bot whose period has ended keeps working through a grace period
while its owner is reminded, and only then goes off the air — its scenario,
its blocks, its buyers and its order history all still there, waiting for a
payment to switch it back on. The people this hurts if we get it wrong are
not our customers; they are our customers' customers, who paid someone else
for a guide and would just see a dead bot.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models.bot import Bot as BotModel
from app.models.bot import BotStatus

logger = logging.getLogger(__name__)

#: Nothing has been said about the current period yet.
NOTICE_NONE = 0
#: "Период заканчивается" — sent once, `REMINDER_LEAD_DAYS` before the end.
NOTICE_SOON = 1
#: "Период закончился, бот работает ещё N дней" — sent once, at expiry.
NOTICE_GRACE = 2
#: "Бот снят с эфира" — sent once, when the grace period runs out too.
NOTICE_SUSPENDED = 3

#: How long before the period ends to ask for the next one. Five days,
#: because paying us may mean topping up a crypto wallet or waiting for a
#: card to clear, and both take longer than the two days a *customer* of a
#: client's bot needs.
REMINDER_LEAD_DAYS = 5

#: How often the sweep looks. Hourly: the numbers it acts on are in days, so
#: anything finer is only extra queries, and anything coarser makes "бот
#: выключится через сутки" a lie by up to that much.
SWEEP_SECONDS = 3600.0


@dataclass(frozen=True)
class BillingState:
    """Where a bot stands with us, in the terms the UI shows.

    `state` is the one field worth reading first:

    * ``off``       — this deployment charges nothing per period.
    * ``active``    — paid, and the period has not ended.
    * ``grace``     — the period ended, the bot still works, the clock is on.
    * ``suspended`` — the grace period ran out too; the bot is off the air.
    """

    state: str
    paid_until: datetime | None
    grace_until: datetime | None
    days_left: int | None
    price_minor: int
    currency: str

    @property
    def required(self) -> bool:
        return self.state != "off"


def period_days() -> int:
    return max(1, get_settings().renewal_period_days)


def grace_days() -> int:
    return max(0, get_settings().renewal_grace_days)


def renewal_price() -> tuple[int, str]:
    """What one period costs, and in what. Taken from the first configured
    method, the same one whose price the paywall leads with."""
    from app.services import payment_service

    methods = payment_service.platform_methods()
    for method in methods:
        if method.renewal_price_minor > 0:
            return method.renewal_price_minor, method.currency
    return 0, methods[0].currency if methods else ""


def charges_per_period() -> bool:
    return renewal_price()[0] > 0


def state_of(bot: BotModel) -> BillingState:
    """Read-only: what this bot's clock says right now.

    A bot with no `paid_until` is never "overdue" — it predates the monthly,
    or the deployment charges nothing — so it reads as ``off`` regardless of
    what is configured today. Turning a price on must not retroactively put
    every existing bot into arrears.
    """
    price_minor, currency = renewal_price()
    if bot.paid_until is None or price_minor <= 0:
        return BillingState(
            state="off", paid_until=bot.paid_until, grace_until=None,
            days_left=None, price_minor=price_minor, currency=currency,
        )

    now = datetime.now(timezone.utc)
    paid_until = _aware(bot.paid_until)
    grace_until = paid_until + timedelta(days=grace_days())
    # Rounded up, so "осталось 0 дней" means the period is actually over
    # rather than ending this evening.
    days_left = -(-(paid_until - now) // timedelta(days=1)) if paid_until > now else 0

    if now < paid_until:
        state = "active"
    elif now < grace_until:
        state = "grace"
    else:
        state = "suspended"
    return BillingState(
        state=state, paid_until=paid_until, grace_until=grace_until,
        days_left=int(days_left), price_minor=price_minor, currency=currency,
    )


def _aware(value: datetime) -> datetime:
    """Postgres hands these back with a tzinfo; a freshly built object in a
    test may not have one, and comparing the two raises."""
    return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)


def open_first_period(bot: BotModel, at: datetime) -> None:
    """The launch is paid — the first period starts now.

    The launch price includes it: someone who has just paid us for a launch
    and is immediately asked for a renewal has been charged twice for the
    same week, whatever the invoices say.
    """
    if not charges_per_period():
        return
    bot.paid_until = at + timedelta(days=period_days())
    bot.billing_notice_stage = NOTICE_NONE


def extend_period(bot: BotModel, at: datetime) -> None:
    """A renewal is paid — one more period.

    Counted from whichever is later, the end of the paid period or now: an
    owner who renews early keeps the days they already paid for, and one who
    renews three weeks late does not get those three weeks backdated into
    the period they just bought.
    """
    base = max(_aware(bot.paid_until), at) if bot.paid_until is not None else at
    bot.paid_until = base + timedelta(days=period_days())
    bot.billing_notice_stage = NOTICE_NONE


async def sweep(db: AsyncSession) -> None:
    """One pass over every bot on a clock: remind, then suspend.

    Only bots that are actually on the air are touched. A draft has nothing
    to switch off, and one already suspended is waiting on a payment, not on
    another message.
    """
    if not charges_per_period():
        return

    now = datetime.now(timezone.utc)
    result = await db.execute(
        select(BotModel)
        .where(
            BotModel.paid_until.is_not(None),
            BotModel.status.in_((BotStatus.active, BotStatus.disabled)),
            # Everything still comfortably inside its period is nobody's
            # business yet, and this is the whole point of the index.
            BotModel.paid_until < now + timedelta(days=REMINDER_LEAD_DAYS),
        )
        .order_by(BotModel.paid_until)
    )
    for bot in result.scalars().all():
        try:
            await _act_on(db, bot)
        except Exception:
            # One owner whose Telegram blocks our bot must not stop the
            # sweep from suspending anyone else.
            logger.exception("Billing sweep failed for bot %s", bot.id)


async def _act_on(db: AsyncSession, bot: BotModel) -> None:
    status = state_of(bot)
    if status.state == "off":
        return

    if status.state == "active":
        if bot.billing_notice_stage < NOTICE_SOON:
            await _tell_owner(
                db, bot,
                f"⏳ Оплаченный период бота {_name(bot)} заканчивается через {status.days_left} дн. "
                f"Продли в конструкторе — бот продолжит работать без перерыва.",
            )
            bot.billing_notice_stage = NOTICE_SOON
            await db.commit()
        return

    if status.state == "grace":
        if bot.billing_notice_stage < NOTICE_GRACE:
            left = max(0, (status.grace_until - datetime.now(timezone.utc)).days)
            await _tell_owner(
                db, bot,
                f"⚠️ Период бота {_name(bot)} закончился. Бот пока работает — "
                f"ещё {left} дн., потом уйдёт с эфира. Продли в конструкторе, "
                f"сценарий и заказы никуда не денутся.",
            )
            bot.billing_notice_stage = NOTICE_GRACE
            await db.commit()
        return

    # Suspended. The message goes out before the webhook is pulled, so the
    # owner is told by us rather than by a customer asking why the bot is
    # silent.
    if bot.billing_notice_stage < NOTICE_SUSPENDED:
        await _tell_owner(
            db, bot,
            f"⛔️ Бот {_name(bot)} снят с эфира — период не продлён. "
            f"Всё сохранено: сценарий, настройки, заказы. Оплати продление в конструкторе, "
            f"и бот вернётся в строй сразу же.",
        )
        bot.billing_notice_stage = NOTICE_SUSPENDED
        await db.commit()
    if bot.status == BotStatus.active:
        await suspend(db, bot)


async def suspend(db: AsyncSession, bot: BotModel) -> None:
    """Take the bot off the air without taking anything away.

    The webhook goes first: while it is set, Telegram keeps delivering
    updates, and a dispatcher that answers them would keep selling.
    """
    from app.services import bot_registry
    from app.services.security import decrypt_token

    token = decrypt_token(bot.bot_token_encrypted) if bot.bot_token_encrypted else None
    await bot_registry.remove(bot.id, token)
    bot.status = BotStatus.disabled
    await db.commit()
    logger.info("Bot %s suspended: period not renewed", bot.id)


async def resume(db: AsyncSession, bot: BotModel) -> None:
    """Back on the air after a renewal. A bot that was never suspended is
    left exactly as it is — including a draft, which must not be published
    by a payment."""
    from app.services import bot_registry
    from app.services.security import decrypt_token

    if bot.status != BotStatus.disabled or not bot.bot_token_encrypted:
        return
    bot.status = BotStatus.active
    await db.commit()
    await bot_registry.register_webhook(bot.id, decrypt_token(bot.bot_token_encrypted))
    logger.info("Bot %s back on the air after a renewal", bot.id)


def _name(bot: BotModel) -> str:
    if bot.telegram_bot_username:
        return f"@{bot.telegram_bot_username}"
    return f"«{bot.name or 'Новый бот'}»"


async def _tell_owner(db: AsyncSession, bot: BotModel, text: str) -> None:
    """Through the constructor's own bot, not the client's.

    The client's bot is the wrong messenger twice over: it is the thing
    being switched off, so the last notice would have to travel through a
    webhook we are about to remove — and «ваш бот выключен» arriving *from
    that bot* reads like a message to its customers.
    """
    from aiogram import Bot as AiogramBot

    from app.models.client import Client
    from app.services.telegram_session import build_bot_session

    settings = get_settings()
    if not settings.meta_bot_token:
        logger.warning("No meta bot token — bot %s owner cannot be told about billing", bot.id)
        return

    owner = (await db.execute(select(Client).where(Client.id == bot.client_id))).scalar_one_or_none()
    if owner is None or not owner.telegram_user_id:
        return

    bot_api = AiogramBot(token=settings.meta_bot_token, session=build_bot_session())
    try:
        await bot_api.send_message(owner.telegram_user_id, text)
    finally:
        await bot_api.session.close()


async def sweep_forever(every_seconds: float = SWEEP_SECONDS) -> None:
    import asyncio

    from app.database import AsyncSessionLocal

    while True:
        await asyncio.sleep(every_seconds)
        try:
            async with AsyncSessionLocal() as db:
                await sweep(db)
        except asyncio.CancelledError:
            raise
        except Exception:
            # A sweep that dies takes every later sweep with it, and the
            # failure mode is bots running unpaid forever.
            logger.exception("Billing sweep failed; will try again")


async def sweep_once() -> None:
    """One pass at boot: everything that came due while the process was down
    is due now."""
    from app.database import AsyncSessionLocal

    async with AsyncSessionLocal() as db:
        await sweep(db)
