"""Идеи и пожелания владельцев ботов: приём, лимиты, рассмотрение оператором.

Отправить идею просто (кнопка в конструкторе, команда /idea в мета-боте), а
оператору она приходит сразу с кнопками «беру в работу», «сделано» и
«игнорировать». Плохую идею оператор игнорирует — автору ничего не отправляется,
в его списке она остаётся «на рассмотрении». Когда идея сделана, автору приходит
сообщение: так видно, что идеи читают.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import uuid
from datetime import datetime, timedelta, timezone
from html import escape

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models.client import Client
from app.models.suggestion import Suggestion

logger = logging.getLogger(__name__)

CATEGORIES = {"idea": "💡 Идея", "bug": "🐞 Ошибка", "question": "❓ Вопрос"}
MIN_LEN = 10
MAX_LEN = 2000
PER_DAY = 5

#: Что видит автор вместо внутренних статусов: «не берём» ему не показывается.
CLIENT_STATUS = {
    "new": "на рассмотрении",
    "ignored": "на рассмотрении",
    "planned": "берём в работу",
    "done": "сделано",
}
OPERATOR_ACTIONS = {"p": "planned", "d": "done", "i": "ignored"}


class SuggestionError(Exception):
    """Причина отказа человеческим языком."""


def _norm(text: str) -> str:
    return " ".join((text or "").lower().split())


async def submit(db: AsyncSession, client: Client, *, text: str, category: str = "idea") -> Suggestion:
    body = (text or "").strip()
    if len(body) < MIN_LEN:
        raise SuggestionError("Опишите идею хотя бы в двух-трёх словах (от 10 символов).")
    if len(body) > MAX_LEN:
        raise SuggestionError(f"Слишком длинно: не больше {MAX_LEN} символов.")
    now = datetime.now(timezone.utc)
    sent_today = (
        await db.execute(
            select(func.count(Suggestion.id)).where(
                Suggestion.client_id == client.id, Suggestion.created_at > now - timedelta(days=1)
            )
        )
    ).scalar_one()
    if sent_today >= PER_DAY:
        raise SuggestionError("Сегодня вы уже прислали несколько идей — спасибо! Продолжите завтра.")
    recent = (
        await db.execute(
            select(Suggestion.text).where(
                Suggestion.client_id == client.id, Suggestion.created_at > now - timedelta(days=30)
            )
        )
    ).scalars().all()
    if _norm(body) in {_norm(t) for t in recent}:
        raise SuggestionError("Такую идею вы уже присылали — мы её видели.")
    item = Suggestion(client_id=client.id, category=category if category in CATEGORIES else "idea", text=body)
    db.add(item)
    await db.commit()
    await db.refresh(item)
    return item


async def mine(db: AsyncSession, client: Client, limit: int = 30) -> list[Suggestion]:
    return list(
        (
            await db.execute(
                select(Suggestion).where(Suggestion.client_id == client.id).order_by(Suggestion.created_at.desc()).limit(limit)
            )
        ).scalars()
    )


async def open_for_operator(db: AsyncSession, limit: int = 10) -> list[Suggestion]:
    """Новые и взятые в работу, самые свежие сверху."""
    return list(
        (
            await db.execute(
                select(Suggestion)
                .where(Suggestion.status.in_(("new", "planned")))
                .order_by(Suggestion.created_at.desc())
                .limit(limit)
            )
        ).scalars()
    )


def card_text(item: Suggestion, author: Client | None) -> str:
    who = f"<code>{author.telegram_user_id}</code>" if author else "—"
    label = CATEGORIES.get(item.category, item.category)
    status = {"new": "новая", "planned": "в работе", "done": "сделано", "ignored": "игнор"}.get(item.status, item.status)
    return f"{label} · {status} · {item.created_at:%d.%m %H:%M} UTC\nАвтор: {who}\n\n{escape(item.text[:3000])}"


async def set_status(db: AsyncSession, suggestion_id: uuid.UUID, action: str) -> Suggestion:
    if action not in OPERATOR_ACTIONS:
        raise SuggestionError("Неизвестное действие.")
    item = (await db.execute(select(Suggestion).where(Suggestion.id == suggestion_id))).scalar_one_or_none()
    if item is None:
        raise SuggestionError("Идея не найдена.")
    previous = item.status
    item.status = OPERATOR_ACTIONS[action]
    await db.commit()
    await db.refresh(item)
    # Автору — только хорошие новости, и один раз.
    if item.status in ("planned", "done") and previous != item.status:
        await _tell_author(db, item)
    return item


async def _meta():
    from app.services import platform_billing

    return platform_billing._meta_bot()


async def _tell_author(db: AsyncSession, item: Suggestion) -> None:
    author = (await db.execute(select(Client).where(Client.id == item.client_id))).scalar_one_or_none()
    meta = await _meta()
    if author is None or meta is None or not author.telegram_user_id:
        return
    snippet = item.text if len(item.text) <= 140 else item.text[:137] + "…"
    if item.status == "done":
        text = f"🎉 Ваша идея реализована!\n«{snippet}»\nСпасибо, что помогаете делать сервис лучше."
    else:
        text = f"👍 Вашу идею берём в работу:\n«{snippet}»"
    with contextlib.suppress(Exception):
        await asyncio.wait_for(meta.send_message(author.telegram_user_id, text), timeout=10)


async def notify_operators(item: Suggestion, author: Client | None) -> None:
    """Новая идея оператору в мета-бот, сразу с кнопками. Не обязательно:
    без мета-бота или адресатов идея просто лежит в базе."""
    from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

    settings = get_settings()
    chats = set(settings.admin_ids)
    if not chats and settings.support_chat is not None:
        chats.add(settings.support_chat)
    meta = await _meta()
    if meta is None or not chats:
        return
    h = item.id.hex
    markup = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Беру", callback_data=f"sg:{h}:p"),
                InlineKeyboardButton(text="✔ Сделано", callback_data=f"sg:{h}:d"),
                InlineKeyboardButton(text="🗑 Игнор", callback_data=f"sg:{h}:i"),
            ]
        ]
    )
    for chat in chats:
        try:
            await asyncio.wait_for(
                meta.send_message(chat, "Новая идея от владельца бота\n\n" + card_text(item, author), parse_mode="HTML", reply_markup=markup),
                timeout=10,
            )
        except Exception:  # noqa: BLE001
            logger.info("Could not notify operator %s about suggestion %s", chat, item.id, exc_info=True)
