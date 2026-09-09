"""Executes a client bot's dialogue graph.

Each bot has a `start_block_id` and every block has a `next_block_id` — the
default "what happens after this" edge, drawn as the plain arrow out of a
node in the visual flow editor. A "buttons" block can *additionally* carry
a `target_block_id` on individual buttons (content["buttons"][i]) — the
branch arrows dragged from a specific button to another node. On /start,
the dispatcher walks the chain from start_block_id, sending each block with
a short "typing…" pause in between, until it runs off the end (next_block_id
is null) *or* reaches a buttons block that actually has at least one branch
configured — at that point it stops and waits for the tap. A buttons block
with no branches configured behaves exactly like every other block (sent,
then straight through to next_block_id) — that's what makes this backward
compatible with every bot built before branching existed (see migration
0003, which backfills next_block_id from the old order_index sequence).

A "payment" block halts the walk the same way: it sends a checkout link
and stops, and the chain resumes from its next_block_id only once the
payment provider confirms the money (payment_service.resume_after_payment).
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

from app.models.bot import Bot as BotModel
from app.models.bot_block import BlockType, BotBlock

logger = logging.getLogger(__name__)

# Blocks are sent with a short "typing…" pause in between instead of all at
# once, so a multi-block reply reads like a conversation rather than a wall
# of text dumped in a single instant.
_TYPING_DELAY_MIN = 0.5
_TYPING_DELAY_MAX = 1.8
_CHARS_PER_SECOND = 45

# A visual graph lets someone wire a block's "next" straight back to an
# earlier block — a deliberate loop is a legitimate pattern (repeat a
# question, etc.) if a buttons block breaks it up, but a loop of *plain*
# blocks with no branch point would otherwise hang this webhook request
# forever. This is the circuit breaker.
_MAX_CHAIN_STEPS = 50

_CALLBACK_PREFIX = "b"


def _typing_delay(text: str) -> float:
    seconds = len(text) / _CHARS_PER_SECOND
    return max(_TYPING_DELAY_MIN, min(seconds, _TYPING_DELAY_MAX))


_URL_SCHEME_RE = re.compile(r"^[a-zA-Z][a-zA-Z0-9+.-]*://")


def _button_has_branches(content: dict) -> bool:
    return any((b.get("target_block_id") or "").strip() for b in content.get("buttons") or [])


def _build_keyboard(block_id: uuid.UUID, content: dict) -> InlineKeyboardMarkup | None:
    buttons = content.get("buttons") or []
    rows = []
    for index, button in enumerate(buttons):
        label = (button.get("label") or "").strip()
        action_type = button.get("action_type", "text")
        action_value = (button.get("action_value") or "").strip()

        # A fully blank row (added via "+ Добавить кнопку" and never filled
        # in) used to still build a "..." button whose callback_data could
        # end up empty — Telegram then rejects the whole sendMessage call,
        # which our per-block try/except swallows, so the *entire* block
        # (caption text included) would silently vanish. Skip blank rows
        # instead of ever building an invalid button from them.
        if not label and not action_value and not (button.get("target_block_id") or "").strip():
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
            # Every non-URL button's callback_data is just a pointer back to
            # "which button on which block" — process_update looks up the
            # actual target_block_id fresh from the DB when it's tapped,
            # rather than baking a target into the callback_data itself, so
            # editing a button's connection later doesn't require anything
            # already sent to the user to change.
            rows.append([InlineKeyboardButton(text=label, callback_data=f"{_CALLBACK_PREFIX}:{block_id.hex}:{index}")])

    return InlineKeyboardMarkup(inline_keyboard=rows) if rows else None


async def _send_payment_block(
    bot: Bot, chat_id: int, block: BotBlock, bot_id: uuid.UUID, db: AsyncSession, telegram_user_id: int | None
) -> bool:
    """Send the invoice message for a payment block.

    Returns True if the chain should halt here — which it does whenever a
    payment was actually offered, because what comes next is the delivery,
    and that is owed only once the money lands (payment_service resumes the
    walk from the provider's callback).
    """
    from app.services import payment_service  # local import: avoids a cycle

    content = block.content or {}
    result = await db.execute(select(BotModel).where(BotModel.id == bot_id))
    bot_row = result.scalar_one_or_none()
    if bot_row is None:
        return False

    text = (content.get("text") or content.get("title") or "").strip()
    try:
        payment, url = await payment_service.create_order_payment(
            db, bot=bot_row, block=block, chat_id=chat_id, telegram_user_id=telegram_user_id
        )
    except Exception:
        # A misconfigured payment block must not swallow the rest of the
        # dialogue: say the message it carries and walk on, rather than
        # leaving the customer staring at silence.
        logger.exception("Could not create a payment for block %s (bot %s)", block.id, bot_id)
        if text:
            await bot.send_message(chat_id, text)
        return False

    label = (content.get("button_label") or "").strip() or f"Оплатить {payment.amount_minor // 100} {payment.currency}"
    keyboard = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=label[:64], url=url)]])
    await bot.send_message(chat_id, text or "Оплата", reply_markup=keyboard)
    return True


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
    keyboard = _build_keyboard(block.id, content) if block.block_type == BlockType.buttons else None

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


async def _walk_chain(
    bot: Bot,
    chat_id: int,
    start_block_id: uuid.UUID,
    bot_id: uuid.UUID,
    db: AsyncSession,
    telegram_user_id: int | None = None,
) -> None:
    """Send `start_block_id` and keep following next_block_id, pausing for
    typing/delay between steps, until the chain ends or hits a branch
    point (a buttons block with at least one connected button)."""

    next_id: uuid.UUID | None = start_block_id
    visited: set[uuid.UUID] = set()
    steps = 0
    first = True

    while next_id is not None:
        steps += 1
        if steps > _MAX_CHAIN_STEPS:
            logger.warning("Bot %s dialogue chain exceeded %d steps — stopping.", bot_id, _MAX_CHAIN_STEPS)
            return
        if next_id in visited:
            # A revisit means a cycle (a real, deliberate pattern in a
            # visual flow graph) with no branch point to break it up — each
            # step in this loop is paced with a real typing delay, so
            # waiting for _MAX_CHAIN_STEPS to catch this could hold a
            # webhook request open for tens of seconds. Catch it the
            # instant it's actually detected instead.
            logger.warning("Bot %s dialogue hit a loop at block %s — stopping.", bot_id, next_id)
            return
        visited.add(next_id)

        result = await db.execute(select(BotBlock).where(BotBlock.id == next_id, BotBlock.bot_id == bot_id))
        block = result.scalar_one_or_none()
        if block is None:
            return  # dangling/removed target — nothing left to do

        try:
            if block.block_type == BlockType.payment:
                if not first:
                    await bot.send_chat_action(chat_id, "typing")
                    await asyncio.sleep(_TYPING_DELAY_MIN)
                if await _send_payment_block(bot, chat_id, block, bot_id, db, telegram_user_id):
                    # Paid delivery waits for the provider's callback — see
                    # payment_service.resume_after_payment.
                    return
            elif block.block_type == BlockType.delay:
                # A bare pause — no message of its own, just stretches the
                # gap before the next block. Clamped defensively: the
                # webhook request stays open for this long, and both
                # Telegram and a reverse proxy in front of us have their
                # own patience limits.
                seconds = (block.content or {}).get("seconds", 2)
                await asyncio.sleep(max(0.0, min(float(seconds), 15.0)))
            else:
                if not first:
                    text = (block.content or {}).get("text") or ""
                    await bot.send_chat_action(chat_id, "typing")
                    await asyncio.sleep(_typing_delay(text))
                await _send_block(bot, chat_id, block)
        except Exception:
            logger.exception("Failed to send block %s for bot %s", block.id, bot_id)

        first = False

        # A buttons block with any branch configured is a real decision
        # point — stop and wait for the tap instead of barrelling through
        # to next_block_id regardless of what the user picks. Without any
        # branch configured it's just another block in the chain (matches
        # every bot built before branching existed).
        if block.block_type == BlockType.buttons and _button_has_branches(block.content or {}):
            return

        next_id = block.next_block_id


async def _handle_callback_query(bot: Bot, callback_query: dict, bot_id: uuid.UUID, db: AsyncSession) -> None:
    # Phase-1-style buttons (no branch configured) still exist and are
    # valid — the tap just has nowhere to go, so acknowledging it (stopping
    # Telegram's loading spinner) is all there is to do.
    try:
        await bot.answer_callback_query(callback_query["id"])
    except Exception:
        logger.exception("Failed to answer callback query for bot %s", bot_id)

    data = callback_query.get("data") or ""
    parts = data.split(":")
    if len(parts) != 3 or parts[0] != _CALLBACK_PREFIX:
        return
    _, block_hex, index_str = parts
    try:
        source_block_id = uuid.UUID(hex=block_hex)
        index = int(index_str)
    except ValueError:
        return

    chat = (callback_query.get("message") or {}).get("chat") or {}
    chat_id = chat.get("id")
    if chat_id is None:
        return

    result = await db.execute(select(BotBlock).where(BotBlock.id == source_block_id, BotBlock.bot_id == bot_id))
    source_block = result.scalar_one_or_none()
    if source_block is None:
        return
    buttons = (source_block.content or {}).get("buttons") or []
    if index >= len(buttons):
        return
    target_raw = (buttons[index].get("target_block_id") or "").strip()
    if not target_raw:
        return  # this particular button isn't wired to anything

    try:
        target_id = uuid.UUID(target_raw)
    except ValueError:
        return

    tapped_by = (callback_query.get("from") or {}).get("id")
    await _walk_chain(bot, chat_id, target_id, bot_id, db, telegram_user_id=tapped_by)


async def process_update(bot: Bot, update: dict, bot_id: uuid.UUID, db: AsyncSession) -> None:
    callback_query = update.get("callback_query")
    if callback_query:
        await _handle_callback_query(bot, callback_query, bot_id, db)
        return

    message = update.get("message")
    if not message:
        return

    chat_id = message.get("chat", {}).get("id")
    text = message.get("text", "") or ""
    sender_id = (message.get("from") or {}).get("id")
    if chat_id is None:
        return

    if not text.startswith("/start"):
        return

    result = await db.execute(select(BotModel.start_block_id).where(BotModel.id == bot_id))
    start_block_id = result.scalar_one_or_none()

    if start_block_id is None:
        await bot.send_message(chat_id, "Этот бот пока пуст 🤷")
        return

    await _walk_chain(bot, chat_id, start_block_id, bot_id, db, telegram_user_id=sender_id)
