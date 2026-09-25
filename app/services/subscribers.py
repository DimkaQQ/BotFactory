"""Who is on the other side of a client's bot.

Kept apart from the dispatcher because three different things need it and
none of them should have to know how it is stored: the dialogue engine
(every /start and every tap), the payment layer (a buyer's name on an
order), and the scheduler (where to send next week's video).
"""

from __future__ import annotations

import contextlib
import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.bot_subscriber import BotSubscriber

logger = logging.getLogger(__name__)


def _trim(value, limit: int) -> str:
    """Telegram's limits are not ours, and a display name is not worth an
    integrity error in the middle of someone's first /start."""
    return (str(value or "").strip())[:limit]


async def remember(
    db: AsyncSession,
    *,
    bot_id: uuid.UUID,
    telegram_user_id: int | None,
    chat_id: int | None,
    user: dict | None = None,
) -> BotSubscriber | None:
    """Record (or refresh) the person this update came from.

    Upserted in one statement rather than select-then-insert: two updates
    from the same person can land at once — the dispatcher answers
    immediately and does the talking in a background task — and the losing
    insert would otherwise raise on the unique constraint in the middle of
    an unrelated conversation.

    Never raises. Losing a display name must not cost the bot a reply, so a
    failure here is logged and the dialogue carries on without it.
    """
    if telegram_user_id is None or chat_id is None:
        return None

    user = user or {}
    fields = {
        "first_name": _trim(user.get("first_name"), 128),
        "last_name": _trim(user.get("last_name"), 128),
        "username": _trim(user.get("username"), 64),
        "language_code": _trim(user.get("language_code"), 16),
    }
    # Only overwrite what we were actually told. An update that carries no
    # `from` (a channel post, say) must not blank out a name we already know.
    known = {key: value for key, value in fields.items() if value}

    try:
        statement = (
            pg_insert(BotSubscriber)
            .values(
                id=uuid.uuid4(),
                bot_id=bot_id,
                telegram_user_id=telegram_user_id,
                chat_id=chat_id,
                **fields,
            )
            .on_conflict_do_update(
                constraint="uq_bot_subscriber",
                set_={
                    "chat_id": chat_id,
                    "last_seen_at": datetime.now(timezone.utc),
                    # Someone who came back is not blocked any more.
                    "blocked_at": None,
                    **known,
                },
            )
            .returning(BotSubscriber)
        )
        subscriber = (await db.execute(statement)).scalar_one()
        await db.commit()
        return subscriber
    except Exception:
        logger.exception("Could not record subscriber %s of bot %s", telegram_user_id, bot_id)
        await db.rollback()
        return None


async def get(db: AsyncSession, bot_id: uuid.UUID, telegram_user_id: int | None) -> BotSubscriber | None:
    if telegram_user_id is None:
        return None
    result = await db.execute(
        select(BotSubscriber).where(
            BotSubscriber.bot_id == bot_id,
            BotSubscriber.telegram_user_id == telegram_user_id,
        )
    )
    return result.scalar_one_or_none()


async def set_unsubscribed(
    db: AsyncSession, bot_id: uuid.UUID, telegram_user_id: int | None, *, value: bool
) -> None:
    """Записать «больше не пишите» или снять его.

    Снимается только явным /start: человек, который вернулся и написал
    «спасибо», согласия на рассылку этим не давал.
    """
    if telegram_user_id is None:
        return
    with contextlib.suppress(Exception):
        await db.execute(
            update(BotSubscriber)
            .where(BotSubscriber.bot_id == bot_id, BotSubscriber.telegram_user_id == telegram_user_id)
            .values(unsubscribed_at=datetime.now(timezone.utc) if value else None)
        )
        await db.commit()


async def mark_blocked(db: AsyncSession, bot_id: uuid.UUID, telegram_user_id: int | None) -> None:
    """The bot can no longer write to this person.

    Without this, every scheduled send to someone who blocked the bot would
    fail, be retried, and fail again — on every sweep, forever, for as long
    as the row existed.
    """
    subscriber = await get(db, bot_id, telegram_user_id)
    if subscriber is None or subscriber.blocked_at is not None:
        return
    subscriber.blocked_at = datetime.now(timezone.utc)
    await db.commit()


def looks_blocked(error: Exception) -> bool:
    """Whether a failed send means "this person is gone" rather than "try again".

    Matched on the message because aiogram raises `TelegramForbiddenError`
    for several different situations and the distinction we need — bot
    blocked / chat deleted / user deactivated — is only in the text.
    """
    text = str(error).lower()
    return any(
        phrase in text
        for phrase in ("bot was blocked", "user is deactivated", "chat not found", "bot can't initiate conversation")
    )
