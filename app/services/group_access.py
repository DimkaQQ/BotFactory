"""Letting a buyer into a private group, and taking them back out.

The product's answer to "продаю доступ в закрытый канал" used to be: paste
one `https://t.me/+…` link into a delivery block. That link is the same for
every buyer, works forever, and can be forwarded — so the shop was selling
something it had already given away, and a subscriber who stopped paying
stayed in the group for good.

What this does instead:

* on delivery, mint a **single-use** invite link for that one buyer
  (`member_limit=1`), so a forwarded link is worthless;
* on expiry, remove them — ban then immediately unban, which is Telegram's
  way of saying "kick": a plain ban would stop them ever coming back, and
  coming back is exactly what we want them to do next month.

Everything here needs the bot to be an administrator of the chat with the
"invite users" and "ban users" rights. It is not, by default, and that is
the single most common way this feature fails — so every failure is turned
into a sentence the shop owner can act on rather than a log line.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.subscription import Subscription

logger = logging.getLogger(__name__)


class GroupAccessError(Exception):
    """Something the shop owner has to fix, phrased for the shop owner."""


def chat_ref(content: dict | None) -> str:
    """The chat a block grants access to, as the owner typed it.

    Accepts either a numeric id (`-1001234567890`, what @userinfobot and
    friends show) or an @username. Both are what Telegram's API takes, so
    neither is converted.
    """
    return str((content or {}).get("group_chat_id") or "").strip()


def _as_chat_id(raw: str) -> int | str:
    try:
        return int(raw)
    except ValueError:
        return raw if raw.startswith("@") else f"@{raw}"


def _explain(exc: Exception, chat: str) -> str:
    text = str(exc).lower()
    if "not enough rights" in text or "administrator" in text or "can_invite_users" in text:
        return (
            f"Бот не может выдавать приглашения в {chat}. Добавь бота в группу администратором "
            f"и включи право «Приглашать пользователей»."
        )
    if "chat not found" in text:
        return (
            f"Telegram не нашёл чат {chat}. Проверь id — для групп и каналов он начинается с -100, "
            f"узнать его можно, переслав любое сообщение из группы боту @userinfobot."
        )
    return f"Не удалось выдать доступ в {chat}: {exc}"


async def grant(
    db: AsyncSession,
    *,
    bot_id: uuid.UUID,
    chat_ref_raw: str,
    subscription: Subscription | None = None,
    valid_days: int | None = None,
) -> str:
    """Mint a one-person invite link, and remember where it leads.

    Raises `GroupAccessError` with something the owner can act on — the
    caller turns that into a message to the owner rather than swallowing it,
    because a buyer who paid and got nothing is the worst outcome here.
    """
    from app.services import bot_registry

    if not chat_ref_raw:
        raise GroupAccessError("В блоке не указан чат, в который нужно пустить покупателя.")

    bot_instance = await bot_registry.get_or_create(bot_id, db)
    if bot_instance is None:
        raise GroupAccessError("У бота нет токена — сначала опубликуй бота.")

    chat = _as_chat_id(chat_ref_raw)
    # Slightly longer than the paid period: the link has to outlive the
    # moment of delivery (someone pays at night and joins in the morning),
    # but not outlive the access it grants.
    expire_at = None
    if valid_days:
        expire_at = datetime.now(timezone.utc) + timedelta(days=valid_days + 1)

    try:
        link = await bot_instance.create_chat_invite_link(
            chat_id=chat,
            name=f"BotFactory {datetime.now(timezone.utc):%Y-%m-%d}"[:32],
            member_limit=1,
            expire_date=expire_at,
        )
    except Exception as exc:
        raise GroupAccessError(_explain(exc, chat_ref_raw)) from exc

    if subscription is not None:
        # Which chat to remove them from when the period runs out. Stored on
        # the subscription rather than re-read from the block, because the
        # owner may point the block at a different chat later and that must
        # not orphan everyone already inside the old one.
        subscription.granted_chat_id = link.chat.id if getattr(link, "chat", None) else None
        if subscription.granted_chat_id is None:
            subscription.meta = {**(subscription.meta or {}), "granted_chat_ref": chat_ref_raw}
        await db.commit()

    return link.invite_link


async def revoke(db: AsyncSession, subscription: Subscription) -> bool:
    """Remove a lapsed subscriber from the chat they were let into.

    Ban-then-unban, not ban: a ban is permanent and this person is a
    customer we want back next month. Returns whether anyone was actually
    removed.

    Never raises. Expiry must not stall because one group lost its admin
    rights — the sweep behind it has hundreds of other subscriptions to get
    through, and the owner finds out from the log and their own member list.
    """
    from app.services import bot_registry

    chat = subscription.granted_chat_id or (subscription.meta or {}).get("granted_chat_ref")
    if not chat:
        return False

    try:
        bot_instance = await bot_registry.get_or_create(subscription.bot_id, db)
        if bot_instance is None:
            return False
        await bot_instance.ban_chat_member(chat_id=chat, user_id=subscription.telegram_user_id)
        # Immediately lifted, so "доступ закончился" does not quietly mean
        # "забанен навсегда" — they can rejoin the moment they pay again.
        await bot_instance.unban_chat_member(
            chat_id=chat, user_id=subscription.telegram_user_id, only_if_banned=True
        )
        logger.info(
            "Removed user %s from chat %s (subscription %s lapsed)",
            subscription.telegram_user_id,
            chat,
            subscription.id,
        )
        return True
    except Exception:
        logger.exception(
            "Could not remove user %s from chat %s for lapsed subscription %s",
            subscription.telegram_user_id,
            chat,
            subscription.id,
        )
        return False
