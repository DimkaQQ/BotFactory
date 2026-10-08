"""Кабинет владельца прямо в Telegram: боты, цифры, пауза, настройки, поддержка.

Сюда человек попадает по /start. Всё, что можно посмотреть или переключить, не
открывая конструктор, — здесь; а то, что требует холста, — кнопка в конструктор.
Данные и правила — в `app/services/owner_panel.py`, тут только тексты и кнопки.

Сообщение редактируется на месте (а не плодит новые), поэтому меню остаётся
одним экраном, как приложение. Тексты в HTML, а всё, что вводил человек
(названия ботов), экранируется.
"""

from __future__ import annotations

import contextlib
import html
import logging
import uuid

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command, CommandStart
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
    WebAppInfo,
)

from app.config import get_settings
from app.database import AsyncSessionLocal
from app.models.client import Client
from app.services import dates, owner_panel
from app.services.payments import money
from meta_bot.handlers import support

logger = logging.getLogger(__name__)

router = Router(name="menu")

_STATE_EMOJI = {"live": "🟢", "paused": "⏸", "draft": "📝", "disabled": "🔴"}
_STATE_WORD = {
    "live": "работает",
    "paused": "на паузе",
    "draft": "черновик",
    "disabled": "остановлен (не оплачен период)",
}


def _esc(value: object) -> str:
    return html.escape(str(value), quote=False)


def _revenue(pairs: list[tuple[str, int]] | dict[str, int]) -> str:
    items = pairs.items() if isinstance(pairs, dict) else pairs
    rendered = [money(amount, currency) for currency, amount in items if amount]
    return " · ".join(rendered) if rendered else "пока нет"


def _bot_title(card: owner_panel.BotCard) -> str:
    return card.bot.name or "Без названия"


def _constructor_button(path: str = "", text: str = "🛠 Открыть конструктор") -> InlineKeyboardButton:
    return InlineKeyboardButton(text=text, web_app=WebAppInfo(url=get_settings().webapp_url.rstrip("/") + path + "/"))


# ---------------------------------------------------------------- экраны


def _needs_terms(client: Client | None) -> bool:
    """Показывать ли «Принимаю»: документы опубликованы, а человек их ещё не принимал."""
    if not get_settings().legal_ready:
        return False
    from app.routers.legal import REVISION

    return client is None or client.terms_version != REVISION


def main_screen(
    name: str, cards: list[owner_panel.BotCard], client: Client | None = None
) -> tuple[str, InlineKeyboardMarkup]:
    greeting = f"🏭 <b>Bot Factory</b>\nПривет, {_esc(name)}!\n\n"
    if cards:
        total = owner_panel.totals(cards)
        body = (
            f"🤖 Ботов: <b>{total.bots}</b> · работают: <b>{total.live}</b>\n"
            f"👥 Клиентов: <b>{total.clients}</b>\n"
            f"🛒 Оплаченных заказов: <b>{total.orders}</b>\n"
            f"💰 Выручка: <b>{_esc(_revenue(total.revenue))}</b>\n\n"
            "Выбери, что показать 👇"
        )
    else:
        body = (
            "Здесь собирают Telegram-ботов без программирования: бот сам продаёт, принимает оплату и выдаёт "
            "купленное. Собирать и пробовать бесплатно — платишь только за запуск.\n\n"
            "У тебя пока нет ботов. Собери первого в конструкторе — это занимает пару минут 👇"
        )
    needs_terms = _needs_terms(client)
    if needs_terms:
        base = get_settings().public_base_url.rstrip("/")
        body += (
            f'\n\nПродолжая, ты принимаешь <a href="{base}/legal/offer">оферту</a> и '
            f'<a href="{base}/legal/privacy">политику конфиденциальности</a>.'
        )
    rows = [[_constructor_button()]]
    if needs_terms:
        rows.append([InlineKeyboardButton(text="✅ Принимаю условия", callback_data="m:terms")])
    if cards:
        rows.append([InlineKeyboardButton(text="🤖 Мои боты", callback_data="m:bots")])
    rows.append(
        [
            InlineKeyboardButton(text="⚙️ Настройки", callback_data="s:main"),
            InlineKeyboardButton(text="💬 Поддержка", callback_data="sup:start"),
        ]
    )
    rows.append([InlineKeyboardButton(text="💡 Предложить идею", callback_data="idea:start")])
    return greeting + body, InlineKeyboardMarkup(inline_keyboard=rows)


def bots_screen(cards: list[owner_panel.BotCard]) -> tuple[str, InlineKeyboardMarkup]:
    lines = ["🤖 <b>Мои боты</b>\n"]
    rows = []
    for card in cards:
        emoji = _STATE_EMOJI[card.state]
        lines.append(f"{emoji} <b>{_esc(_bot_title(card))}</b> — {_STATE_WORD[card.state]}")
        lines.append(f"     👥 {card.clients} · 🛒 {card.orders}")
        rows.append([InlineKeyboardButton(text=f"{emoji} {_bot_title(card)}"[:60], callback_data=f"b:{card.bot.id}")])
    rows.append([InlineKeyboardButton(text="‹ Назад", callback_data="m:main")])
    return "\n".join(lines), InlineKeyboardMarkup(inline_keyboard=rows)


def bot_screen(card: owner_panel.BotCard) -> tuple[str, InlineKeyboardMarkup]:
    bot = card.bot
    handle = f"@{_esc(bot.telegram_bot_username)} · " if bot.telegram_bot_username else ""
    lines = [
        f"{_STATE_EMOJI[card.state]} <b>{_esc(_bot_title(card))}</b>",
        f"{handle}{_STATE_WORD[card.state]}",
        "",
        f"👥 Клиентов: <b>{card.clients}</b> (за неделю +{card.new_this_week})",
    ]
    if card.blocked:
        lines.append(f"🚫 Заблокировали бота: {card.blocked}")
    if card.active_subscriptions:
        lines.append(f"🔁 Активных подписок: <b>{card.active_subscriptions}</b>")
    lines.append(f"🛒 Оплаченных заказов: <b>{card.orders}</b> (за неделю: {card.orders_this_week})")
    lines.append(f"💰 Выручка: <b>{_esc(_revenue(card.revenue))}</b>")
    if bot.paid_until:
        lines.append(f"⏳ Оплачен до: {_esc(dates.day(bot.paid_until))}")
    if card.state == "paused":
        lines.append("\n⏸ Бот на паузе: новых диалогов нет. Оплаты, возвраты и выдача купленного работают.")
    if card.state == "disabled":
        lines.append("\nПродли период в конструкторе — и бот вернётся сам.")
    if card.state == "draft":
        lines.append("\nБот ещё не опубликован — это делается в конструкторе.")

    rows = []
    if card.state == "live":
        rows.append([InlineKeyboardButton(text="⏸ Поставить на паузу", callback_data=f"bp:{bot.id}")])
    elif card.state == "paused":
        rows.append([InlineKeyboardButton(text="▶️ Включить бота", callback_data=f"br:{bot.id}")])
    rows.append([_constructor_button(f"/bot/{bot.id}", "🛠 Редактировать в конструкторе")])
    rows.append([InlineKeyboardButton(text="‹ К списку", callback_data="m:bots")])
    return "\n".join(lines), InlineKeyboardMarkup(inline_keyboard=rows)


def settings_screen(client: Client | None) -> tuple[str, InlineKeyboardMarkup]:
    notify = True if client is None else client.notify_sales
    text = (
        "⚙️ <b>Настройки</b>\n\n"
        f"🔔 Уведомления о продажах: <b>{'включены' if notify else 'выключены'}</b>\n"
        "Когда кто-то оплатил, я пришлю сюда сообщение: кто и что купил. Если выключить, "
        "заказы всё равно видны в «Моих ботах» и в конструкторе.\n\n"
        "🚪 «Выйти везде» закрывает вход в конструктор на всех устройствах. "
        "Боты, клиенты и заказы остаются на месте."
    )
    rows = [
        [
            InlineKeyboardButton(
                text="🔕 Выключить уведомления" if notify else "🔔 Включить уведомления",
                callback_data="s:notify",
            )
        ],
        [InlineKeyboardButton(text="🚪 Выйти везде", callback_data="s:logout")],
    ]
    settings = get_settings()
    if settings.legal_ready:
        base = settings.public_base_url.rstrip("/")
        rows.append(
            [
                InlineKeyboardButton(text="📄 Оферта", url=f"{base}/legal/offer"),
                InlineKeyboardButton(text="🔒 Политика", url=f"{base}/legal/privacy"),
            ]
        )
    rows.append([InlineKeyboardButton(text="‹ Назад", callback_data="m:main")])
    return text, InlineKeyboardMarkup(inline_keyboard=rows)


def logout_confirm_screen() -> tuple[str, InlineKeyboardMarkup]:
    return (
        "🚪 <b>Выйти на всех устройствах?</b>\n\nВойти снова можно в любой момент через Telegram. "
        "Боты и заказы никуда не денутся.",
        InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(text="Да, выйти", callback_data="s:logout:yes"),
                    InlineKeyboardButton(text="Отмена", callback_data="s:main"),
                ]
            ]
        ),
    )


# ------------------------------------------------------------- хелперы


async def _show(bot: Bot, query: CallbackQuery, text: str, markup: InlineKeyboardMarkup) -> None:
    """Заменить экран на месте. «Не изменилось» — не ошибка: человек нажал то же."""
    if query.message is None:
        return
    with contextlib.suppress(TelegramBadRequest):
        await bot.edit_message_text(
            text=text,
            chat_id=query.message.chat.id,
            message_id=query.message.message_id,
            reply_markup=markup,
            parse_mode="HTML",
        )


async def _answer(bot: Bot, query: CallbackQuery, text: str | None = None, *, alert: bool = False) -> None:
    """Погасить «часики» на кнопке; с текстом — короткое всплывающее сообщение."""
    with contextlib.suppress(TelegramBadRequest):
        await bot.answer_callback_query(query.id, text=text, show_alert=alert)


async def _main_for(user_id: int, name: str) -> tuple[str, InlineKeyboardMarkup]:
    async with AsyncSessionLocal() as db:
        client = await owner_panel.client_by_telegram(db, user_id)
        cards = await owner_panel.list_cards(db, client) if client else []
    return main_screen(name, cards, client)


# ---------------------------------------------------------------- команды


@router.message(CommandStart())
@router.message(Command("menu"))
async def cmd_start(message: Message, bot: Bot) -> None:
    user = message.from_user
    text, markup = await _main_for(message.chat.id, (user.first_name if user else "") or "друг")
    await bot.send_message(message.chat.id, text, reply_markup=markup, parse_mode="HTML")


@router.message(Command("terms"))
async def cmd_terms(message: Message, bot: Bot) -> None:
    """Условия сервиса — Telegram требует ответ на /terms у бота, принимающего оплату."""
    settings = get_settings()
    if settings.legal_ready:
        base = settings.public_base_url.rstrip("/")
        text = f"📄 Условия сервиса: {base}/legal/offer\nПолитика конфиденциальности: {base}/legal/privacy"
    else:
        text = "Условия сервиса скоро появятся. Вопросы — кнопка «Поддержка» в меню (/menu)."
    await bot.send_message(message.chat.id, text)


@router.message(Command("paysupport"))
async def cmd_paysupport(message: Message, bot: Bot) -> None:
    """Вопросы по оплате запуска и продления: открывает диалог с поддержкой."""
    await bot.send_message(
        message.chat.id,
        "💬 По оплате запуска или продления напиши сюда одним сообщением, что случилось (когда платил, "
        "чем, на какую сумму) — мы ответим в этом же чате. Нажми «Поддержка» в меню: /menu",
    )


# ---------------------------------------------------------------- кнопки


@router.callback_query(F.data.startswith(("m:", "b:", "bp:", "br:", "s:")))
async def on_button(query: CallbackQuery, bot: Bot) -> None:
    data = query.data or ""
    user_id = query.from_user.id
    toast: str | None = None

    async with AsyncSessionLocal() as db:
        client = await owner_panel.client_by_telegram(db, user_id)

        if data == "m:main":
            cards = await owner_panel.list_cards(db, client) if client else []
            text, markup = main_screen(query.from_user.first_name or "друг", cards, client)

        elif data == "m:terms":
            client = await owner_panel.accept_terms(db, user_id, query.from_user.full_name)
            cards = await owner_panel.list_cards(db, client)
            toast = "Спасибо! Условия приняты ✅"
            text, markup = main_screen(query.from_user.first_name or "друг", cards, client)

        elif data == "m:bots":
            cards = await owner_panel.list_cards(db, client) if client else []
            text, markup = (
                bots_screen(cards) if cards else main_screen(query.from_user.first_name or "друг", cards, client)
            )

        elif data.startswith(("b:", "bp:", "br:")):
            action, _, raw = data.partition(":")
            try:
                bot_id = uuid.UUID(raw)
            except ValueError:
                await _answer(bot, query)
                return
            if client is None:
                await _answer(bot, query, "Аккаунт не найден — открой конструктор.", alert=True)
                return
            if action in ("bp", "br"):
                try:
                    await owner_panel.set_paused(db, client, bot_id, action == "bp")
                    toast = "Бот на паузе ⏸" if action == "bp" else "Бот включён ▶️"
                except owner_panel.PauseError as exc:
                    await _answer(bot, query, str(exc), alert=True)
                    return
            card = await owner_panel.get_card(db, client, bot_id)
            if card is None:
                await _answer(bot, query, "Бот не найден.", alert=True)
                return
            text, markup = bot_screen(card)

        elif data == "s:main":
            text, markup = settings_screen(client)

        elif data == "s:notify":
            if client is None:
                await _answer(bot, query, "Аккаунт появится после первого входа в конструктор.", alert=True)
                return
            await owner_panel.set_notify_sales(db, client, not client.notify_sales)
            toast = "Уведомления включены 🔔" if client.notify_sales else "Уведомления выключены 🔕"
            text, markup = settings_screen(client)

        elif data == "s:logout":
            text, markup = logout_confirm_screen()

        elif data == "s:logout:yes":
            if client is not None:
                await owner_panel.sign_out_everywhere(db, client)
            toast = "Вышел на всех устройствах"
            text, markup = settings_screen(client)

        else:
            await _answer(bot, query)
            return

    await _answer(bot, query, toast)
    await _show(bot, query, text, markup)


# -------------------------------------------------------------- поддержка


@router.callback_query(F.data == "sup:start")
async def on_support(query: CallbackQuery, bot: Bot) -> None:
    await _answer(bot, query)
    chat_id = query.from_user.id
    admin = get_settings().support_chat
    if admin is None:
        await bot.send_message(chat_id, "Поддержка через бота пока не подключена. Загляните позже 🙏")
        return
    if chat_id == admin:
        await bot.send_message(
            chat_id,
            "💬 <b>Это чат поддержки</b>\n\nСюда приходят сообщения пользователей. Чтобы ответить, "
            "нажми Reply на нужное сообщение — человек получит одно сообщение: его вопросы и твой ответ.",
            parse_mode="HTML",
        )
        return
    support.open_dialog(chat_id)
    await bot.send_message(
        chat_id,
        "💬 <b>Поддержка</b>\n\nПишите сюда своё сообщение — оно уйдёт в техподдержку, "
        "а ответ вы получите здесь же, в этом чате.\n\n"
        "⏱ Мы отвечаем в течение 24 часов.\n"
        "📎 Можно написать несколько сообщений и приложить фото или файл — мы увидим всё.",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[[InlineKeyboardButton(text="🏠 В меню", callback_data="m:main")]]
        ),
    )
