"""Идеи и пожелания: владелец бота присылает их в мета-бота, оператор разбирает.

Владелец: кнопка «💡 Идея» в меню или команда `/idea текст`. Бот просит
написать идею одним сообщением, принимает её и благодарит. Оператор (`ADMIN_TELEGRAM_IDS`):
идея приходит сразу с кнопками «Беру», «Сделано», «Игнор»; список открытых —
`/ideas`. Игнор молчаливый: автору ничего не уходит.
"""

from __future__ import annotations

import logging
import time
import uuid
from html import escape

from aiogram import F, Router
from aiogram.filters import Command, CommandObject
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from sqlalchemy import select

from app.config import get_settings
from app.database import AsyncSessionLocal
from app.models.client import Client
from app.models.suggestion import Suggestion
from app.services import suggestions

logger = logging.getLogger(__name__)

router = Router(name="ideas")

#: Кто сейчас пишет идею: следующее сообщение — это она. Живёт 10 минут.
_awaiting: dict[int, float] = {}
WAIT_SECONDS = 600


def _is_admin(user_id: int | None) -> bool:
    return user_id is not None and user_id in get_settings().admin_ids


def _waiting(message: Message) -> bool:
    user = message.from_user.id if message.from_user else None
    if user is None or not message.text or message.text.startswith("/"):
        return False
    return _awaiting.get(user, 0) > time.monotonic()


async def _accept(message: Message, text: str) -> None:
    user = message.from_user.id
    async with AsyncSessionLocal() as db:
        client = (await db.execute(select(Client).where(Client.telegram_user_id == user))).scalar_one_or_none()
        if client is None:
            await message.answer("Сначала войдите в конструктор через Telegram — тогда мы поймём, от кого идея.")
            return
        try:
            item = await suggestions.submit(db, client, text=text)
        except suggestions.SuggestionError as exc:
            await message.answer(str(exc))
            return
        _awaiting.pop(user, None)
        await message.answer(
            "Спасибо! 💛 Идея принята. Мы читаем всё, что присылаете. "
            "Если возьмём в работу или сделаем, сообщим здесь."
        )
        await suggestions.notify_operators(item, client)


@router.message(Command("idea"))
async def idea_command(message: Message, command: CommandObject) -> None:
    text = (command.args or "").strip()
    if text:
        await _accept(message, text)
        return
    if message.from_user is None:
        return
    if len(_awaiting) > 10_000:
        _awaiting.clear()
    _awaiting[message.from_user.id] = time.monotonic() + WAIT_SECONDS
    await message.answer(
        "💡 Напишите идею или пожелание одним сообщением: чего не хватает, что неудобно, что добавить. "
        "Можно и про ошибку. Чем конкретнее, тем быстрее сделаем."
    )


@router.callback_query(F.data == "idea:start")
async def idea_button(query: CallbackQuery) -> None:
    await query.answer()
    _awaiting[query.from_user.id] = time.monotonic() + WAIT_SECONDS
    await query.message.answer(
        "💡 Напишите идею или пожелание одним сообщением: чего не хватает, что неудобно, что добавить. "
        "Можно и про ошибку. Чем конкретнее, тем быстрее сделаем."
    )


@router.message(F.text, _waiting)
async def idea_text(message: Message) -> None:
    await _accept(message, message.text or "")


# ------------------------------------------------------------ оператор


def _markup(item: Suggestion) -> InlineKeyboardMarkup:
    h = item.id.hex
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Беру", callback_data=f"sg:{h}:p"),
                InlineKeyboardButton(text="✔ Сделано", callback_data=f"sg:{h}:d"),
                InlineKeyboardButton(text="🗑 Игнор", callback_data=f"sg:{h}:i"),
            ]
        ]
    )


@router.message(Command("ideas"), F.from_user.id.func(_is_admin))
async def list_ideas(message: Message) -> None:
    async with AsyncSessionLocal() as db:
        items = await suggestions.open_for_operator(db, limit=10)
        if not items:
            await message.answer("Новых идей нет ✅")
            return
        for item in items:
            author = (await db.execute(select(Client).where(Client.id == item.client_id))).scalar_one_or_none()
            await message.answer(suggestions.card_text(item, author), parse_mode="HTML", reply_markup=_markup(item))


@router.callback_query(F.data.startswith("sg:"), F.from_user.id.func(_is_admin))
async def decide(query: CallbackQuery) -> None:
    try:
        _, hexed, action = (query.data or "").split(":")
        suggestion_id = uuid.UUID(hexed)
    except ValueError:
        await query.answer("Не разобрал кнопку", show_alert=True)
        return
    async with AsyncSessionLocal() as db:
        try:
            item = await suggestions.set_status(db, suggestion_id, action)
        except suggestions.SuggestionError as exc:
            await query.answer(str(exc), show_alert=True)
            return
        author = (await db.execute(select(Client).where(Client.id == item.client_id))).scalar_one_or_none()
    label = {"planned": "✅ В работе", "done": "✔ Сделано, автору сообщили", "ignored": "🗑 Проигнорировано"}[item.status]
    await query.answer(label)
    try:
        await query.message.edit_text(
            suggestions.card_text(item, author) + f"\n\n{escape(label)}",
            parse_mode="HTML",
            reply_markup=None if item.status in ("done", "ignored") else _markup(item),
        )
    except Exception:  # noqa: BLE001
        logger.info("Could not edit the suggestion card %s", item.id, exc_info=True)
