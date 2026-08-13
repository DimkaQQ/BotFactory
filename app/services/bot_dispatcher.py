"""Executes a client bot's blocks as a simple linear dialogue.

Phase 1 scope: on `/start` from an end user, read `bot_blocks` for this bot
ordered by `order_index` and send them one after another
(welcome -> description -> buttons -> delivery). No branching logic.
"""

from __future__ import annotations

import logging
import uuid

from aiogram import Bot
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.bot_block import BlockType, BotBlock

logger = logging.getLogger(__name__)


def _build_keyboard(content: dict) -> InlineKeyboardMarkup | None:
    buttons = content.get("buttons") or []
    if not buttons:
        return None

    rows = []
    for button in buttons:
        label = button.get("label") or "..."
        action_type = button.get("action_type", "text")
        action_value = button.get("action_value") or ""
        if action_type == "url" and action_value:
            rows.append([InlineKeyboardButton(text=label, url=action_value)])
        else:
            # Phase 1 has no branching, so "text" buttons carry the value as
            # callback_data purely for display — nothing handles the click yet.
            rows.append([InlineKeyboardButton(text=label, callback_data=(action_value or label)[:64])])

    return InlineKeyboardMarkup(inline_keyboard=rows)


async def _send_block(bot: Bot, chat_id: int, block: BotBlock) -> None:
    content = block.content or {}
    text = content.get("text") or ""
    media_file_id = content.get("media_file_id")
    media_type = content.get("media_type")
    keyboard = _build_keyboard(content) if block.block_type == BlockType.buttons else None

    if not text and not media_file_id and not keyboard:
        return

    if media_file_id:
        caption = text or None
        if media_type == "photo":
            await bot.send_photo(chat_id, media_file_id, caption=caption, reply_markup=keyboard)
        elif media_type == "video":
            await bot.send_video(chat_id, media_file_id, caption=caption, reply_markup=keyboard)
        else:
            await bot.send_document(chat_id, media_file_id, caption=caption, reply_markup=keyboard)
    else:
        await bot.send_message(chat_id, text or "…", reply_markup=keyboard)


async def process_update(bot: Bot, update: dict, bot_id: uuid.UUID, db: AsyncSession) -> None:
    message = update.get("message")
    if not message:
        return

    chat_id = message.get("chat", {}).get("id")
    text = message.get("text", "") or ""
    if chat_id is None:
        return

    if not text.startswith("/start"):
        return

    result = await db.execute(
        select(BotBlock).where(BotBlock.bot_id == bot_id).order_by(BotBlock.order_index)
    )
    blocks = list(result.scalars().all())

    if not blocks:
        await bot.send_message(chat_id, "Этот бот пока пуст 🤷")
        return

    for block in blocks:
        try:
            await _send_block(bot, chat_id, block)
        except Exception:
            logger.exception("Failed to send block %s for bot %s", block.id, bot_id)
