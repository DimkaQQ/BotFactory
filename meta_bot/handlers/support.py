"""Поддержка прямо в боте: человек пишет @DragDropBot — владелец отвечает.

Всё, что прислано не командой, копируется в чат владельца (`SUPPORT_CHAT_ID`).
Ответ владельца — обычный «ответ» (Reply) на это сообщение: бот копирует его
тому, кто писал. Так не нужен ни отдельный сервис обращений, ни второй
аккаунт: поддержка живёт там же, где человек уже находится.

Сообщения копируются, а не пересылаются (`copy_message`): пересылка
показывает автора только при его согласии, и ответить было бы некому. Кому
принадлежит сообщение в чате владельца, хранится в `support_relay`.
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta, timezone

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramAPIError, TelegramForbiddenError
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message
from sqlalchemy import select

from app.config import get_settings
from app.database import AsyncSessionLocal
from app.models.support_relay import SupportRelay

logger = logging.getLogger(__name__)

router = Router(name="support")

#: Не больше стольких сообщений от одного человека за окно. Поддержка — это
#: чат владельца, и один спамер не должен его заваливать.
WINDOW_SECONDS = 600
LIMIT = 12
#: Как часто подтверждать «принято», чтобы не отвечать на каждое слово.
ACK_EVERY_SECONDS = 6 * 3600

#: Сколько после обращения (или ответа владельца) разговор считается открытым:
#: человек может продолжать писать без повторного нажатия «Поддержка».
DIALOG_SECONDS = 24 * 3600

_dialogs: dict[int, float] = {}
_recent: dict[int, list[float]] = {}
_acknowledged: dict[int, float] = {}
_warned: set[int] = set()


def open_dialog(user_id: int, seconds: float = DIALOG_SECONDS) -> None:
    """Кнопка «Поддержка» нажата или владелец ответил: можно писать."""
    if len(_dialogs) > 10_000:
        _dialogs.clear()
    _dialogs[user_id] = time.monotonic() + seconds


async def _dialog_open(user_id: int) -> bool:
    if _dialogs.get(user_id, 0) > time.monotonic():
        return True
    # После перезапуска бота память пуста, а разговор не должен рваться: если
    # человек писал нам за последние сутки, он по-прежнему на связи.
    async with AsyncSessionLocal() as db:
        found = await db.execute(
            select(SupportRelay.admin_message_id)
            .where(
                SupportRelay.user_chat_id == user_id,
                SupportRelay.created_at > datetime.now(timezone.utc) - timedelta(seconds=DIALOG_SECONDS),
            )
            .limit(1)
        )
        return found.scalar_one_or_none() is not None


def _throttled(user_id: int) -> bool:
    now = time.monotonic()
    if len(_recent) > 10_000:
        _recent.clear()
    window = [t for t in _recent.get(user_id, []) if now - t < WINDOW_SECONDS]
    window.append(now)
    _recent[user_id] = window
    return len(window) > LIMIT


def _is_plain(message: Message) -> bool:
    """Не команда: команды (/start и прочие) обрабатываются другими роутерами."""
    return not (message.text or "").startswith("/")


async def _remember(admin_message_id: int, user_chat_id: int) -> None:
    async with AsyncSessionLocal() as db:
        await db.merge(SupportRelay(admin_message_id=admin_message_id, user_chat_id=user_chat_id))
        await db.commit()


async def _owner_of(admin_message_id: int) -> int | None:
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(SupportRelay.user_chat_id).where(SupportRelay.admin_message_id == admin_message_id)
        )
        return result.scalar_one_or_none()


async def _to_owner(message: Message, bot: Bot, admin: int) -> None:
    user = message.from_user
    user_id = message.chat.id

    if _throttled(user_id):
        if user_id not in _warned:
            _warned.add(user_id)
            await bot.send_message(user_id, "Слишком много сообщений подряд — подожди немного, я всё вижу 🙏")
        return
    _warned.discard(user_id)

    name = " ".join(filter(None, [user.first_name, user.last_name])) if user else ""
    handle = f"@{user.username}" if user and user.username else "без username"
    header = await bot.send_message(
        admin,
        f"📩 {name or 'Без имени'} · {handle} · id {user_id}\n"
        "Ответь (Reply) на это сообщение или на копию ниже — ответ уйдёт человеку.",
    )
    copied = await bot.copy_message(admin, from_chat_id=user_id, message_id=message.message_id)
    await _remember(header.message_id, user_id)
    await _remember(copied.message_id, user_id)

    now = time.monotonic()
    if now - _acknowledged.get(user_id, -ACK_EVERY_SECONDS) >= ACK_EVERY_SECONDS:
        _acknowledged[user_id] = now
        await bot.send_message(user_id, "✅ Принято. Отвечу сюда же, как только смогу.")


async def _from_owner(message: Message, bot: Bot, admin: int) -> None:
    reply = message.reply_to_message
    if reply is None:
        await bot.send_message(
            admin, "Чтобы ответить человеку, сделай Reply на его сообщение — тогда я передам ответ."
        )
        return

    user_chat = await _owner_of(reply.message_id)
    if user_chat is None:
        await bot.send_message(
            admin, "Не нашёл, кому это адресовано. Ответь на сообщение «📩 …» или на копию письма."
        )
        return

    try:
        await bot.copy_message(user_chat, from_chat_id=admin, message_id=message.message_id)
    except TelegramForbiddenError:
        await bot.send_message(admin, "Человек заблокировал бота — ответ не доставлен.")
    except TelegramAPIError as exc:
        logger.warning("Support reply to %s failed: %s", user_chat, exc)
        await bot.send_message(admin, f"Не доставлено: {exc.message}")
    else:
        # Ответ владельца открывает разговор: человек вправе ответить, а ответ на
        # ответ должен дойти (поэтому и сообщение владельца запоминается).
        await _remember(message.message_id, user_chat)
        open_dialog(user_chat)
        await bot.send_message(admin, "✓ Отправлено", reply_to_message_id=message.message_id)


@router.message(F.chat.type == "private", _is_plain)
async def relay(message: Message, bot: Bot) -> None:
    admin = get_settings().support_chat
    if admin is None:
        await bot.send_message(message.chat.id, "Поддержка через бота пока не подключена. Напиши позже 🙏")
        return
    if message.chat.id == admin:
        await _from_owner(message, bot, admin)
    elif await _dialog_open(message.chat.id):
        await _to_owner(message, bot, admin)
    else:
        # Без нажатия «Поддержка» бот не лезет в личную переписку владельца
        # чужими случайными сообщениями — подсказывает, где кнопка.
        await bot.send_message(
            message.chat.id,
            "Чтобы написать нам, нажми «💬 Поддержка» в меню 👇",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(text="💬 Поддержка", callback_data="sup:start"),
                        InlineKeyboardButton(text="🏠 Меню", callback_data="m:main"),
                    ]
                ]
            ),
        )
