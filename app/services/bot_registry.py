"""In-memory cache of live `aiogram.Bot` instances for published client bots.

Bots are created lazily: the token is decrypted once, on first use (or right
after publishing), and the resulting `Bot` instance is cached in this
process's memory. Nothing here ever hands the decrypted token back out —
only an already-constructed `Bot` instance.
"""

from __future__ import annotations

import logging
import uuid

from aiogram import Bot
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models.bot import Bot as BotModel
from app.models.bot import BotStatus
from app.services.security import decrypt_token
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
    _registry[bot_id] = instance


async def register_webhook(bot_id: uuid.UUID, token: str) -> None:
    """Set the Telegram webhook for a just-published bot and warm the cache."""

    settings = get_settings()
    instance = Bot(token=token, session=build_bot_session())
    try:
        await instance.set_webhook(settings.webhook_url(str(bot_id)))
    except Exception:
        logger.exception("Failed to set webhook for bot %s", bot_id)
        await instance.session.close()
        raise
    put(bot_id, instance)


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
