"""In-memory cache of live `aiogram.Bot` instances for published client bots.

Bots are created lazily: the token is decrypted once, on first use (or right
after publishing), and the resulting `Bot` instance is cached in this
process's memory. Nothing here ever hands the decrypted token back out —
only an already-constructed `Bot` instance.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import uuid

from aiogram import Bot
from aiogram.types import BotCommand
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models.bot import Bot as BotModel
from app.models.bot import BotStatus
from app.database import AsyncSessionLocal
from app.services.security import decrypt_token, webhook_secret
from app.services.telegram_session import build_bot_session

logger = logging.getLogger(__name__)

_registry: dict[uuid.UUID, Bot] = {}


async def get_or_create(bot_id: uuid.UUID, db: AsyncSession) -> Bot | None:
    """Return a cached (or freshly created) aiogram Bot instance for an active bot."""

    cached = _registry.get(bot_id)
    if cached is not None:
        return cached

    result = await db.execute(select(BotModel).where(BotModel.id == bot_id))
    bot_row = result.scalar_one_or_none()
    if bot_row is None or bot_row.status != BotStatus.active or not bot_row.bot_token_encrypted:
        return None

    token = decrypt_token(bot_row.bot_token_encrypted)
    instance = Bot(token=token, session=build_bot_session())
    _registry[bot_id] = instance
    return instance


def put(bot_id: uuid.UUID, instance: Bot) -> None:
    previous = _registry.get(bot_id)
    _registry[bot_id] = instance
    if previous is not None and previous is not instance:
        # Replacing a cached bot without closing it leaked an aiohttp session
        # on every webhook refresh — and refresh now runs for every live bot
        # at startup.
        # Through `background.spawn`, which keeps a reference: a bare
        # create_task is only weakly held by the loop and the close could be
        # collected halfway through.
        from app.services import background

        background.spawn(_close_quietly(previous), name=f"close-session:{bot_id}")


async def _close_quietly(instance: Bot) -> None:
    try:
        await instance.session.close()
    except Exception:
        logger.debug("Could not close a replaced bot session", exc_info=True)


async def register_webhook(bot_id: uuid.UUID, token: str) -> None:
    """Set the Telegram webhook for a just-published bot and warm the cache."""

    settings = get_settings()
    instance = Bot(token=token, session=build_bot_session())
    try:
        await instance.set_webhook(
            settings.webhook_url(str(bot_id)),
            # Named rather than left to Telegram's default: pre_checkout_query
            # is what makes Stars work, and spelling the list out means a bot
            # stops being delivered update types nothing here reads.
            # poll_answer included because the «Опрос» block is sold as a way
            # to find out what subscribers want — without it Telegram never
            # delivers the answers and the block collects nothing.
            allowed_updates=["message", "callback_query", "pre_checkout_query", "poll_answer"],
            # Echoed back on every update, which is what lets the webhook
            # route tell Telegram apart from anyone who guessed the URL.
            secret_token=webhook_secret(bot_id),
        )
    except Exception:
        logger.exception("Failed to set webhook for bot %s", bot_id)
        await instance.session.close()
        raise

    # Меню команд. /stop существовал и отвечал как надо, но узнать о нём было
    # неоткуда: в меню Telegram его не было, в рассылке не подписывалось, в
    # кабинете не упоминалось. Человеку оставалось заблокировать бота — а
    # вместе с ботом он терял и купленный доступ. Отдельной попыткой, а не
    # внутри try выше: меню — приятная мелочь, а вебхук — работа бота, и
    # падать из-за первого второму незачем.
    with contextlib.suppress(Exception):
        await instance.set_my_commands(
            [
                BotCommand(command="start", description="Начать сначала"),
                BotCommand(command="stop", description="Не присылать рассылку"),
            ]
        )

    put(bot_id, instance)


async def refresh_all_webhooks() -> None:
    """Re-register every live bot's webhook, once, at startup.

    This is what lets the webhook route refuse an update that carries no
    secret token: bots published before secret tokens existed were registered
    without one, and rather than leaving a permanent unauthenticated path
    open for their sake, they are brought up to date here. Doing it on every
    boot is cheap and idempotent — Telegram simply stores the same URL again.
    """
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(BotModel.id).where(BotModel.status == BotStatus.active))
        bot_ids = list(result.scalars().all())

    for bot_id in bot_ids:
        await refresh_webhook(bot_id)
    if bot_ids:
        logger.info("Refreshed webhooks for %d live bots", len(bot_ids))


async def refresh_webhook(bot_id: uuid.UUID) -> None:
    """Re-register a live bot's webhook, so it starts sending the secret.

    Best-effort: an unreachable Telegram must not turn a startup into a
    crash, or one bot's revoked token into every other bot staying stale.
    """
    try:
        async with AsyncSessionLocal() as db:
            result = await db.execute(select(BotModel).where(BotModel.id == bot_id))
            bot_row = result.scalar_one_or_none()
            if bot_row is None or bot_row.status != BotStatus.active or not bot_row.bot_token_encrypted:
                return
            # Inside the try on purpose: an unreadable token blob — a rotated
            # FERNET_KEY, a corrupted row — raises here, and left uncaught it
            # aborted the loop over every other bot. Since the webhook route
            # now refuses updates without a secret, and the secret is handed
            # out by exactly this call, that took the whole fleet off the air.
            token = decrypt_token(bot_row.bot_token_encrypted)
        await register_webhook(bot_id, token)
    except Exception:
        logger.warning("Could not refresh the webhook for bot %s", bot_id, exc_info=True)


async def remove(bot_id: uuid.UUID, token: str | None = None) -> None:
    """Tear down a deleted bot: best-effort unset its Telegram webhook and
    drop it (or a fresh throwaway instance, if it was never cached) from
    the in-memory registry. Never raises — deletion should succeed even if
    Telegram itself is unreachable."""

    instance = _registry.pop(bot_id, None)

    if instance is None and token:
        instance = Bot(token=token, session=build_bot_session())

    if instance is None:
        return

    try:
        await instance.delete_webhook(drop_pending_updates=True)
    except Exception:
        logger.exception("Failed to delete webhook for bot %s (continuing)", bot_id)
    finally:
        await instance.session.close()


async def close_all() -> None:
    for instance in _registry.values():
        await instance.session.close()
    _registry.clear()
