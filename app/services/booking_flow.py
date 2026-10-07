"""Диалог записи и сбора контактов (блоки «Запись» и «Контакты»).

Запись: бот показывает дни с свободным временем, потом время; выбранное время
придерживается (если дальше оплата) или подтверждается сразу. Контакты: Telegram
уже даёт имя и @username — бот спрашивает только то, что включил владелец
(имя, телефон) и чего ещё нет у этого человека.
"""

from __future__ import annotations

import contextlib
import logging
import re
import uuid
from datetime import datetime, timedelta, timezone

from aiogram import Bot
from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
)
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.booking import Booking, ChatState
from app.models.bot_block import BotBlock
from app.models.button_click import ButtonClick
from app.services import booking as bk
from app.services import subscribers

logger = logging.getLogger(__name__)

PREFIX = "bk"
STATE_TTL = timedelta(hours=2)


def _rows(buttons: list[InlineKeyboardButton], per_row: int) -> list[list[InlineKeyboardButton]]:
    return [buttons[i : i + per_row] for i in range(0, len(buttons), per_row)]


async def _show(bot: Bot, chat_id: int, message_id: int | None, text: str, markup: InlineKeyboardMarkup | None) -> None:
    """Обновить сообщение выбора на месте, а если нельзя — прислать новое."""
    if message_id is not None:
        with contextlib.suppress(Exception):
            await bot.edit_message_text(text, chat_id=chat_id, message_id=message_id, reply_markup=markup)
            return
    await bot.send_message(chat_id, text, reply_markup=markup)


async def _days_keyboard(db: AsyncSession, bot_id: uuid.UUID, block: BotBlock, schedule: bk.Schedule):
    days = await bk.open_days(db, bot_id, schedule)
    if not days:
        return None
    buttons = [
        InlineKeyboardButton(text=bk.day_label(d), callback_data=f"{PREFIX}:{block.id.hex}:d:{d:%Y%m%d}") for d in days
    ]
    return InlineKeyboardMarkup(inline_keyboard=_rows(buttons, 3))


async def send_days(
    bot: Bot, chat_id: int, block: BotBlock, bot_id: uuid.UUID, db: AsyncSession, *, message_id: int | None = None
) -> None:
    schedule = bk.schedule_of(block.content)
    markup = await _days_keyboard(db, bot_id, block, schedule)
    if markup is None:
        await _show(bot, chat_id, message_id, "Свободного времени пока нет. Загляните чуть позже 🙏", None)
        return
    text = str((block.content or {}).get("text") or "").strip() or "Выберите день:"
    await _show(bot, chat_id, message_id, text, markup)


async def _show_slots(
    bot: Bot, chat_id: int, message_id: int | None, block: BotBlock, bot_id: uuid.UUID, db: AsyncSession, day, note: str = ""
) -> None:
    schedule = bk.schedule_of(block.content)
    slots = await bk.free_slots(db, bot_id, schedule, day)
    if not slots:
        await send_days(bot, chat_id, block, bot_id, db, message_id=message_id)
        return
    local = [s.astimezone(schedule.tz) for s in slots]
    buttons = [
        InlineKeyboardButton(text=f"{t:%H:%M}", callback_data=f"{PREFIX}:{block.id.hex}:s:{t:%Y%m%d%H%M}") for t in local
    ]
    rows = _rows(buttons, 3) + [[InlineKeyboardButton(text="← Другой день", callback_data=f"{PREFIX}:{block.id.hex}:b:0")]]
    await _show(
        bot, chat_id, message_id, f"{note}{bk.day_label(day)}. Выберите время:", InlineKeyboardMarkup(inline_keyboard=rows)
    )


def _local_dt(schedule: bk.Schedule, compact: str) -> datetime | None:
    try:
        return datetime.strptime(compact, "%Y%m%d%H%M").replace(tzinfo=schedule.tz).astimezone(timezone.utc)
    except ValueError:
        return None


async def handle_callback(bot: Bot, callback_query: dict, bot_id: uuid.UUID, db: AsyncSession, parts: list[str]) -> None:
    from app.services import bot_dispatcher as dp

    if len(parts) != 4:
        return
    message = callback_query.get("message") or {}
    chat_id = (message.get("chat") or {}).get("id")
    message_id = message.get("message_id")
    user_id = (callback_query.get("from") or {}).get("id")
    if chat_id is None:
        return
    if await dp._is_paused(db, bot_id):
        await bot.send_message(chat_id, dp._PAUSED_TEXT)
        return
    try:
        block_id = uuid.UUID(hex=parts[1])
    except ValueError:
        return
    block = (
        await db.execute(select(BotBlock).where(BotBlock.id == block_id, BotBlock.bot_id == bot_id))
    ).scalar_one_or_none()
    if block is None:
        return
    schedule = bk.schedule_of(block.content)
    kind, value = parts[2], parts[3]

    if kind == "b":
        await send_days(bot, chat_id, block, bot_id, db, message_id=message_id)
        return
    if kind == "d":
        try:
            day = datetime.strptime(value, "%Y%m%d").date()
        except ValueError:
            return
        await _show_slots(bot, chat_id, message_id, block, bot_id, db, day)
        return
    if kind != "s":
        return

    start = _local_dt(schedule, value)
    now = datetime.now(timezone.utc)
    if start is None or start < now + timedelta(hours=schedule.notice_hours):
        await send_days(bot, chat_id, block, bot_id, db, message_id=message_id)
        return
    booking = await bk.reserve(
        db, bot_id=bot_id, block=block, schedule=schedule, start=start, telegram_user_id=user_id, chat_id=chat_id
    )
    local_day = bk.local_day(schedule, start)
    if booking is None:
        await db.refresh(block)  # откат после гонки сбросил состояние объектов
        await _show_slots(
            bot, chat_id, message_id, block, bot_id, db, local_day, note="Это время только что заняли 😕 "
        )
        return

    label = bk.full_label(schedule, start)
    # Выбранное время попадёт в заказ («Выбрал: …») как выбор покупателя.
    with contextlib.suppress(Exception):
        db.add(
            ButtonClick(
                bot_id=bot_id, block_id=block.id, button_index=0, label=label[:64], collect_choice=True,
                telegram_user_id=user_id,
            )
        )
        await db.commit()

    if await bk.chain_needs_payment(db, bot_id, block.next_block_id):
        await _show(
            bot, chat_id, message_id,
            f"✅ Время {label} придержано на {bk.HOLD_MINUTES} минут. Оплатите, чтобы запись подтвердилась.", None,
        )
    else:
        await bk.confirm(db, booking)
        await _show(bot, chat_id, message_id, f"✅ Вы записаны: {label}", None)
        await announce_confirmed(db, booking, label, instance=bot)
    if block.next_block_id is not None:
        await dp.walk_chain(bot, chat_id, block.next_block_id, bot_id, db, telegram_user_id=user_id)


async def _who(db: AsyncSession, bot_id: uuid.UUID, user_id: int | None) -> str:
    sub = await subscribers.get(db, bot_id, user_id)
    if sub is None:
        return f"id {user_id}"
    name = sub.contact_name or f"{sub.first_name} {sub.last_name}".strip() or f"id {user_id}"
    parts = [name]
    if sub.username:
        parts.append(f"@{sub.username}")
    if sub.phone:
        parts.append(sub.phone)
    return ", ".join(parts)


async def announce_confirmed(db: AsyncSession, booking: Booking, label: str, instance=None) -> None:
    """Сообщить владельцу о подтверждённой записи (покупателю уже сказали)."""
    from app.services import payment_service

    with contextlib.suppress(Exception):
        found = await payment_service._owner_of(db, booking.bot_id)
        if found is None:
            return
        owner_id, shop_bot = found
        who = await _who(db, booking.bot_id, booking.telegram_user_id)
        await payment_service.tell_owner(owner_id, shop_bot, f"📅 Новая запись: {label}\nКлиент: {who}")


async def confirm_after_payment(db: AsyncSession, payment) -> None:
    """Оплата прошла — подтвердить придержанное время и сказать обоим."""
    from app.services import bot_registry

    meta = payment.meta or {}
    raw = meta.get("booking_id")
    if not raw or payment.bot_id is None:
        return
    try:
        booking = await db.get(Booking, uuid.UUID(str(raw)))
    except ValueError:
        return
    if booking is None:
        return
    if booking.bot_id != payment.bot_id:
        return  # чужая запись в meta платежа — не трогаем
    schedule = await bk.schedule_for(db, booking)
    label = bk.full_label(schedule, booking.starts_at)
    if booking.status == "confirmed":
        return
    ok = await bk.confirm(db, booking) if booking.status == "held" else False
    instance = None
    with contextlib.suppress(Exception):
        instance = await bot_registry.get_or_create(payment.bot_id, db)
    if ok:
        if instance is not None and booking.chat_id is not None:
            with contextlib.suppress(Exception):
                await instance.send_message(booking.chat_id, f"✅ Вы записаны: {label}")
        await announce_confirmed(db, booking, label, instance)
        return
    # Оплата пришла, а время уже не наше: человек должен получить деньги назад
    # или другое время — это решает владелец.
    from app.services import payment_service

    with contextlib.suppress(Exception):
        found = await payment_service._owner_of(db, payment.bot_id)
        if found is not None:
            who = await _who(db, payment.bot_id, booking.telegram_user_id)
            await payment_service.tell_owner(
                found[0], found[1],
                f"⚠️ Оплата за запись пришла, но время {label} уже не закреплено за клиентом.\n"
                f"Клиент: {who}\nСвяжитесь с ним: назначьте другое время или верните деньги.",
            )


# ---------------------------------------------------------------- контакты


_PHONE_RE = re.compile(r"\D+")


def normalize_phone(raw: str) -> str | None:
    digits = _PHONE_RE.sub("", raw or "")
    if not 7 <= len(digits) <= 15:
        return None
    return "+" + digits


async def _set_state(db: AsyncSession, bot_id: uuid.UUID, user_id: int, kind: str, payload: dict) -> None:
    await db.execute(delete(ChatState).where(ChatState.bot_id == bot_id, ChatState.telegram_user_id == user_id))
    db.add(
        ChatState(
            bot_id=bot_id, telegram_user_id=user_id, kind=kind, payload=payload,
            expires_at=datetime.now(timezone.utc) + STATE_TTL,
        )
    )
    await db.commit()


async def _clear_state(db: AsyncSession, bot_id: uuid.UUID, user_id: int) -> None:
    await db.execute(delete(ChatState).where(ChatState.bot_id == bot_id, ChatState.telegram_user_id == user_id))
    await db.commit()


async def _ask(bot: Bot, chat_id: int, step: str, block: BotBlock, first: bool = True) -> None:
    intro = str((block.content or {}).get("text") or "").strip() if first else ""
    prefix = intro + "\n\n" if intro else ""
    if step == "name":
        await bot.send_message(chat_id, prefix + "Как к вам обращаться?", reply_markup=ReplyKeyboardRemove())
        return
    markup = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="📱 Отправить мой номер", request_contact=True)]],
        resize_keyboard=True,
        one_time_keyboard=True,
    )
    await bot.send_message(
        chat_id,
        prefix + "Оставьте номер телефона: нажмите кнопку ниже или напишите его сообщением.",
        reply_markup=markup,
    )


def _next_step(content: dict, sub, after: str | None) -> str | None:
    """Какой вопрос задавать дальше: имя, затем телефон — только то, чего ещё нет."""
    if after is None and content.get("ask_name") and not (sub and sub.contact_name):
        return "name"
    if after in (None, "name") and content.get("ask_phone") and not (sub and sub.phone):
        return "phone"
    return None


async def start_contact(
    bot: Bot, chat_id: int, block: BotBlock, bot_id: uuid.UUID, db: AsyncSession, user_id: int | None
) -> bool:
    """True — бот задал вопрос и ждёт ответа; False — спрашивать нечего, идём дальше."""
    if user_id is None:
        return False
    content = block.content or {}
    sub = await subscribers.get(db, bot_id, user_id)
    step = _next_step(content, sub, None)
    if step is None:
        return False
    await _set_state(db, bot_id, user_id, "contact", {"block_id": str(block.id), "step": step})
    await _ask(bot, chat_id, step, block)
    return True


async def handle_message(bot: Bot, message: dict, bot_id: uuid.UUID, db: AsyncSession) -> bool:
    """Ответ на вопрос блока «Контакты». True — сообщение обработано здесь."""
    from app.services import bot_dispatcher as dp

    user_id = (message.get("from") or {}).get("id")
    chat_id = (message.get("chat") or {}).get("id")
    if user_id is None or chat_id is None:
        return False
    state = (
        await db.execute(select(ChatState).where(ChatState.bot_id == bot_id, ChatState.telegram_user_id == user_id))
    ).scalar_one_or_none()
    if state is None or state.kind != "contact":
        return False
    text = str(message.get("text") or "").strip()
    if state.expires_at <= datetime.now(timezone.utc) or text.startswith("/"):
        await _clear_state(db, bot_id, user_id)
        return False

    block_id = uuid.UUID(str(state.payload.get("block_id")))
    block = (
        await db.execute(select(BotBlock).where(BotBlock.id == block_id, BotBlock.bot_id == bot_id))
    ).scalar_one_or_none()
    sub = await subscribers.get(db, bot_id, user_id)
    if block is None or sub is None:
        await _clear_state(db, bot_id, user_id)
        return False

    step = state.payload.get("step")
    if step == "name":
        if not text:
            await _ask(bot, chat_id, "name", block, first=False)
            return True
        sub.contact_name = text[:128]
    else:
        raw = (message.get("contact") or {}).get("phone_number") or text
        phone = normalize_phone(raw)
        if phone is None:
            await bot.send_message(chat_id, "Не получилось разобрать номер. Напишите его цифрами, например +7 700 123 45 67.")
            return True
        sub.phone = phone
    await db.commit()

    following = _next_step(block.content or {}, sub, step)
    if following is not None:
        await _set_state(db, bot_id, user_id, "contact", {"block_id": str(block.id), "step": following})
        await _ask(bot, chat_id, following, block, first=False)
        return True

    await _clear_state(db, bot_id, user_id)
    await bot.send_message(chat_id, "Спасибо, записал(а) ✅", reply_markup=ReplyKeyboardRemove())
    if block.next_block_id is not None:
        await dp.walk_chain(bot, chat_id, block.next_block_id, bot_id, db, telegram_user_id=user_id)
    return True
