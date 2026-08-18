"""Executes a client bot's blocks as a simple linear dialogue.

Phase 1 scope: on `/start` from an end user, read `bot_blocks` for this bot
ordered by `order_index` and send them one after another — text, photo,
video, buttons, poll, a file/link "delivery", or a bare pause. No
branching logic.
"""

from __future__ import annotations

import asyncio
import logging
import re
import uuid

from aiogram import Bot
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.bot_block import BlockType, BotBlock

logger = logging.getLogger(__name__)

# Blocks are sent with a short "typing…" pause in between instead of all at
# once, so a multi-block reply reads like a conversation rather than a wall
# of text dumped in a single instant.
_TYPING_DELAY_MIN = 0.5
_TYPING_DELAY_MAX = 1.8
_CHARS_PER_SECOND = 45


def _typing_delay(text: str) -> float:
    seconds = len(text) / _CHARS_PER_SECOND
    return max(_TYPING_DELAY_MIN, min(seconds, _TYPING_DELAY_MAX))


_URL_SCHEME_RE = re.compile(r"^[a-zA-Z][a-zA-Z0-9+.-]*://")


def _build_keyboard(content: dict) -> InlineKeyboardMarkup | None:
    buttons = content.get("buttons") or []
    rows = []
    for button in buttons:
        label = (button.get("label") or "").strip()
        action_type = button.get("action_type", "text")
        action_value = (button.get("action_value") or "").strip()

        # A fully blank row (added via "+ Добавить кнопку" and never filled
        # in) used to still build a "..." button whose callback_data could
        # end up empty — Telegram then rejects the whole sendMessage call,
        # which our per-block try/except swallows, so the *entire* block
        # (caption text included) would silently vanish. Skip blank rows
        # instead of ever building an invalid button from them.
        if not label and not action_value:
            continue
        label = label or "…"

        if action_type == "url" and action_value:
            url = action_value
            # The single most common way a URL button breaks a block: the
            # user typed "example.com" instead of "https://example.com".
            # Telegram rejects a schemeless URL outright — assume https
            # rather than let one typo take the whole message down.
            if not _URL_SCHEME_RE.match(url):
                url = f"https://{url}"
            rows.append([InlineKeyboardButton(text=label, url=url)])
        else:
            # Phase 1 has no branching, so "text" buttons carry the value as
            # callback_data purely for display — nothing handles the click
            # yet beyond acknowledging it (see process_update).
            callback_data = (action_value or label)[:64] or "noop"
            rows.append([InlineKeyboardButton(text=label, callback_data=callback_data)])

    return InlineKeyboardMarkup(inline_keyboard=rows) if rows else None


async def _send_block(bot: Bot, chat_id: int, block: BotBlock) -> None:
    content = block.content or {}

    if block.block_type == BlockType.poll:
        question = (content.get("question") or "").strip()
        options = [opt.strip() for opt in content.get("options") or [] if opt and opt.strip()]
        if not question or len(options) < 2:
            return
        await bot.send_poll(chat_id, question=question, options=options, is_anonymous=content.get("anonymous", True))
        return

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
    callback_query = update.get("callback_query")
    if callback_query:
        # Phase 1 has no branching (see module docstring), so a tapped
        # "text" button has nowhere to go yet — but Telegram still shows a
        # spinning loading state on the button until answerCallbackQuery is
        # called, and leaves it spinning indefinitely (eventually erroring)
        # if it never is. Acknowledging it is the minimum for the button to
        # not feel broken, independent of whether it does anything yet.
        try:
            await bot.answer_callback_query(callback_query["id"])
        except Exception:
            logger.exception("Failed to answer callback query for bot %s", bot_id)
        return

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

    for index, block in enumerate(blocks):
        try:
            if block.block_type == BlockType.delay:
                # A bare pause — no message of its own, just stretches the
                # gap before the next block. Clamped defensively: the
                # webhook request stays open for this long, and both
                # Telegram and a reverse proxy in front of us have their
                # own patience limits.
                seconds = (block.content or {}).get("seconds", 2)
                await asyncio.sleep(max(0.0, min(float(seconds), 15.0)))
                continue

            if index > 0:
                text = (block.content or {}).get("text") or ""
                await bot.send_chat_action(chat_id, "typing")
                await asyncio.sleep(_typing_delay(text))
            await _send_block(bot, chat_id, block)
        except Exception:
            logger.exception("Failed to send block %s for bot %s", block.id, bot_id)
