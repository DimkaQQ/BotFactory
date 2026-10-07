"""Панель оператора в мета-боте: жалобы, журнал решений, снятие бота и блокировка.

Доступна только Telegram id из `ADMIN_TELEGRAM_IDS`. Пусто — панели нет (ни
одна команда не отвечает), остаётся командная строка `python -m app.admin`.

Команды (они же в меню команд Telegram у оператора, см. `set_admin_commands`):
    /admin                    меню с кнопками
    /reports                  открытые жалобы с кнопками
    /journal                  последние решения
    /stats                    сводка по платформе
    /find 123456789 | @бот    карточка владельца или бота с кнопками действий
    /block @имя_бота причина  снять бота (пауза, владелец вернуть не может)
    /restore @имя_бота        вернуть снятого бота
    /ban 123456789 причина    заблокировать владельца (вход закрыт, боты на паузе)
    /unban 123456789          снять блокировку
    /export 123456789         выгрузка данных владельца файлом (запрос человека, GDPR)
    /delete 123456789         удалить аккаунт (необратимо, с подтверждением)
    /adminhelp                список команд

Из жалобы действие делается кнопкой с подтверждением: снять бота и
заблокировать аккаунт случайным нажатием нельзя. Всё записывается в журнал.
"""

from __future__ import annotations

import logging
import uuid
from html import escape

from aiogram import F, Router
from aiogram.filters import Command, CommandObject
from aiogram.types import (
    BotCommand,
    BotCommandScopeChat,
    BufferedInputFile,
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)
from sqlalchemy import select

from app.config import get_settings
from app.database import AsyncSessionLocal
from app.models.bot import Bot
from app.models.client import Client
from app.models.moderation import AbuseReport
from app.services import moderation

logger = logging.getLogger(__name__)

router = Router(name="admin")

MAX_TEXT = 3900


def _is_admin(user_id: int | None) -> bool:
    return user_id is not None and user_id in get_settings().admin_ids


def _actor(user_id: int) -> str:
    return f"tg:{user_id}"


def _btn(text: str, data: str) -> InlineKeyboardButton:
    return InlineKeyboardButton(text=text, callback_data=data)


def _uid(hexed: str) -> uuid.UUID | None:
    try:
        return uuid.UUID(hexed)
    except ValueError:
        return None


async def _card(db, report: AbuseReport) -> tuple[str, InlineKeyboardMarkup]:
    bot = (await db.execute(select(Bot).where(Bot.id == report.bot_id))).scalar_one_or_none() if report.bot_id else None
    owner = (
        (await db.execute(select(Client).where(Client.id == bot.client_id))).scalar_one_or_none() if bot else None
    )
    lines = [
        f"🚩 Жалоба · {escape(moderation.CATEGORIES.get(report.category, report.category))}",
        f"Статус: {report.status} · {report.created_at:%d.%m.%Y %H:%M} UTC",
        f"Что указал жалобщик: {escape(report.bot_ref)}",
    ]
    rows: list[list[InlineKeyboardButton]] = []
    if bot is None:
        lines.append("Бот в базе не найден (имя неточное или бот удалён).")
    else:
        state = "снят оператором" if bot.moderation_blocked_at else ("на паузе" if bot.paused else bot.status.value)
        username = f"@{escape(bot.telegram_bot_username)}" if bot.telegram_bot_username else "без имени в Telegram"
        lines.append(f"Бот: {escape(bot.name or '—')} · {username} · {state}")
        if owner is not None:
            banned = " · заблокирован" if owner.banned_at else ""
            lines.append(f"Владелец: <code>{owner.telegram_user_id}</code>{banned}")
        if report.status == moderation.OPEN_STATUS:
            if bot.moderation_blocked_at is None:
                rows.append([_btn("⛔ Снять бота", f"rb:{report.id.hex}")])
            if owner is not None and owner.banned_at is None:
                rows.append([_btn("🚫 Заблокировать владельца", f"rn:{report.id.hex}")])
        if bot.moderation_blocked_at is not None:
            rows.append([_btn("↩ Вернуть бота", f"rr:{bot.id.hex}")])
    lines += ["", escape(report.details)]
    if report.contact:
        lines.append(f"\nКонтакт жалобщика: {escape(report.contact)}")
    if report.status == moderation.OPEN_STATUS:
        rows.append([_btn("✖ Отклонить жалобу", f"rd:{report.id.hex}")])
    return "\n".join(lines)[:MAX_TEXT], InlineKeyboardMarkup(inline_keyboard=rows)


async def _reports_view() -> tuple[str, InlineKeyboardMarkup | None]:
    async with AsyncSessionLocal() as db:
        reports = await moderation.open_reports(db, limit=10)
    if not reports:
        return "Открытых жалоб нет ✅", None
    rows = [
        [_btn(f"{r.created_at:%d.%m %H:%M} · {escape(r.bot_ref)[:30]}", f"rp:{r.id.hex}")] for r in reports
    ]
    return (
        f"Открытых жалоб: {len(reports)}. Выбери, чтобы открыть:",
        InlineKeyboardMarkup(inline_keyboard=rows),
    )


@router.message(Command("reports"), F.from_user.id.func(_is_admin))
async def list_reports(message: Message) -> None:
    text, markup = await _reports_view()
    await message.answer(text, reply_markup=markup)


@router.callback_query(F.data.startswith("rp:"), F.from_user.id.func(_is_admin))
async def open_report(query: CallbackQuery) -> None:
    report_id = _uid((query.data or "")[3:])
    async with AsyncSessionLocal() as db:
        report = (
            (await db.execute(select(AbuseReport).where(AbuseReport.id == report_id))).scalar_one_or_none()
            if report_id
            else None
        )
        if report is None:
            await query.answer("Жалоба не найдена", show_alert=True)
            return
        text, markup = await _card(db, report)
    await query.message.answer(text, parse_mode="HTML", reply_markup=markup)
    await query.answer()


def _confirm(action: str, hexed: str, what: str) -> tuple[str, InlineKeyboardMarkup]:
    return (
        f"Подтвердить: {what}?",
        InlineKeyboardMarkup(inline_keyboard=[[_btn("Да", f"{action}c:{hexed}"), _btn("Нет", "nop:0")]]),
    )


@router.callback_query(F.data.startswith(("rb:", "rn:")), F.from_user.id.func(_is_admin))
async def ask_confirm(query: CallbackQuery) -> None:
    data = query.data or ""
    action, hexed = data.split(":", 1)
    what = "снять бота с эфира" if action == "rb" else "заблокировать владельца (вход закрыт, боты на паузе)"
    text, markup = _confirm(action, hexed, what)
    await query.message.answer(text, reply_markup=markup)
    await query.answer()


@router.callback_query(F.data == "nop:0", F.from_user.id.func(_is_admin))
async def cancelled(query: CallbackQuery) -> None:
    await query.message.edit_text("Отменено.")
    await query.answer()


@router.callback_query(F.data.startswith(("rbc:", "rnc:", "rd:", "rr:")), F.from_user.id.func(_is_admin))
async def do_action(query: CallbackQuery) -> None:
    action, hexed = (query.data or "").split(":", 1)
    target = _uid(hexed)
    actor = _actor(query.from_user.id)
    async with AsyncSessionLocal() as db:
        try:
            if target is None:
                raise moderation.ModerationError("Не разобрал идентификатор.")
            if action == "rbc":
                report = (await db.execute(select(AbuseReport).where(AbuseReport.id == target))).scalar_one_or_none()
                if report is None or report.bot_id is None:
                    raise moderation.ModerationError("У жалобы нет бота.")
                await moderation.block_bot(
                    db, report.bot_id, actor=actor, reason=f"жалоба: {report.category}", report_id=report.id
                )
                result = "⛔ Бот снят. Новые диалоги закрыты, отложенные сообщения отменены."
            elif action == "rnc":
                report = (await db.execute(select(AbuseReport).where(AbuseReport.id == target))).scalar_one_or_none()
                bot = (
                    (await db.execute(select(Bot).where(Bot.id == report.bot_id))).scalar_one_or_none()
                    if report and report.bot_id
                    else None
                )
                owner = (
                    (await db.execute(select(Client).where(Client.id == bot.client_id))).scalar_one_or_none()
                    if bot
                    else None
                )
                if owner is None:
                    raise moderation.ModerationError("Владелец не найден.")
                result = "🚫 " + await moderation.ban_client(
                    db, owner.telegram_user_id, actor=actor, reason=f"жалоба: {report.category}", report_id=report.id
                )
            elif action == "rd":
                await moderation.dismiss_report(db, target, actor=actor)
                result = "✖ Жалоба отклонена."
            else:  # rr
                await moderation.restore_bot(db, target, actor=actor)
                result = "↩ Бот возвращён. Владелец может снова управлять паузой."
        except moderation.ModerationError as exc:
            await query.answer(str(exc), show_alert=True)
            return
    await query.message.answer(escape(result))
    await query.answer("Готово")


async def _bot_from_arg(db, arg: str) -> Bot | None:
    return await moderation.find_bot_by_username(db, arg)


@router.message(Command("block"), F.from_user.id.func(_is_admin))
async def block_command(message: Message, command: CommandObject) -> None:
    parts = (command.args or "").split(maxsplit=1)
    if not parts:
        await message.answer("Формат: /block @имя_бота причина")
        return
    async with AsyncSessionLocal() as db:
        bot = await _bot_from_arg(db, parts[0])
        if bot is None:
            await message.answer("Бот с таким именем не найден.")
            return
        await moderation.block_bot(
            db, bot.id, actor=_actor(message.from_user.id), reason=parts[1] if len(parts) > 1 else ""
        )
    await message.answer("⛔ Бот снят.")


@router.message(Command("restore"), F.from_user.id.func(_is_admin))
async def restore_command(message: Message, command: CommandObject) -> None:
    arg = (command.args or "").strip()
    if not arg:
        await message.answer("Формат: /restore @имя_бота")
        return
    async with AsyncSessionLocal() as db:
        bot = await _bot_from_arg(db, arg)
        if bot is None:
            await message.answer("Бот с таким именем не найден.")
            return
        try:
            await moderation.restore_bot(db, bot.id, actor=_actor(message.from_user.id))
        except moderation.ModerationError as exc:
            await message.answer(str(exc))
            return
    await message.answer("↩ Бот возвращён.")


def _telegram_id_arg(command: CommandObject) -> tuple[int | None, str]:
    parts = (command.args or "").split(maxsplit=1)
    if not parts or not parts[0].lstrip("-").isdigit():
        return None, ""
    return int(parts[0]), parts[1] if len(parts) > 1 else ""


@router.message(Command("ban"), F.from_user.id.func(_is_admin))
async def ban_command(message: Message, command: CommandObject) -> None:
    telegram_id, reason = _telegram_id_arg(command)
    if telegram_id is None:
        await message.answer("Формат: /ban 123456789 причина")
        return
    async with AsyncSessionLocal() as db:
        try:
            result = await moderation.ban_client(db, telegram_id, actor=_actor(message.from_user.id), reason=reason)
        except moderation.ModerationError as exc:
            await message.answer(escape(str(exc)))
            return
    await message.answer("🚫 " + escape(result))


@router.message(Command("unban"), F.from_user.id.func(_is_admin))
async def unban_command(message: Message, command: CommandObject) -> None:
    telegram_id, reason = _telegram_id_arg(command)
    if telegram_id is None:
        await message.answer("Формат: /unban 123456789")
        return
    async with AsyncSessionLocal() as db:
        try:
            result = await moderation.unban_client(db, telegram_id, actor=_actor(message.from_user.id), reason=reason)
        except moderation.ModerationError as exc:
            await message.answer(escape(str(exc)))
            return
    await message.answer(escape(result))


async def _journal_text() -> str:
    async with AsyncSessionLocal() as db:
        entries = await moderation.journal(db, limit=20)
        names: dict[uuid.UUID, str] = {}
        for entry in entries:
            if entry.bot_id and entry.bot_id not in names:
                bot = (await db.execute(select(Bot).where(Bot.id == entry.bot_id))).scalar_one_or_none()
                names[entry.bot_id] = f"@{bot.telegram_bot_username}" if bot and bot.telegram_bot_username else "бот"
    if not entries:
        return "Журнал пуст."
    lines = []
    for e in entries:
        target = names.get(e.bot_id, "") if e.bot_id else ""
        owner = f" · владелец {e.client_telegram_id}" if e.client_telegram_id else ""
        reason = f" — {escape(e.reason)}" if e.reason else ""
        lines.append(f"{e.created_at:%d.%m %H:%M} · {e.action} · {escape(target)}{owner} · {escape(e.actor)}{reason}")
    return "\n".join(lines)[:MAX_TEXT]


@router.message(Command("journal"), F.from_user.id.func(_is_admin))
async def journal_command(message: Message) -> None:
    await message.answer(await _journal_text(), parse_mode="HTML")


# ------------------------------------------------------------ меню и быстрые команды

ADMIN_COMMANDS: list[tuple[str, str]] = [
    ("admin", "Меню оператора"),
    ("reports", "Открытые жалобы"),
    ("journal", "Журнал решений"),
    ("stats", "Сводка по платформе"),
    ("find", "Найти владельца или бота"),
    ("block", "Снять бота: /block @бот причина"),
    ("restore", "Вернуть бота: /restore @бот"),
    ("ban", "Заблокировать владельца: /ban id причина"),
    ("unban", "Разблокировать: /unban id"),
    ("export", "Выгрузка данных владельца"),
    ("delete", "Удалить аккаунт (с подтверждением)"),
    ("adminhelp", "Список команд"),
]


async def set_admin_commands(bot) -> None:
    """Меню команд в Telegram только у операторов: остальные его не видят.

    Команда ставится на чат оператора, а Telegram знает этот чат лишь после того,
    как оператор хоть раз написал боту, поэтому отказ не ошибка: меню появится
    после его первого сообщения (и при следующем запуске бота).
    """
    commands = [BotCommand(command=name, description=text) for name, text in ADMIN_COMMANDS]
    for admin_id in get_settings().admin_ids:
        try:
            await bot.set_my_commands(commands, scope=BotCommandScopeChat(chat_id=admin_id))
        except Exception:  # noqa: BLE001
            logger.info("Could not set the command menu for operator %s", admin_id, exc_info=True)


def _help_text() -> str:
    return "Команды оператора:\n" + "\n".join(f"/{name} — {escape(text)}" for name, text in ADMIN_COMMANDS)


def _menu_markup() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [_btn("🚩 Жалобы", "am:reports"), _btn("📜 Журнал", "am:journal")],
            [_btn("📊 Сводка", "am:stats"), _btn("ℹ️ Команды", "am:help")],
        ]
    )


@router.message(Command("admin"), F.from_user.id.func(_is_admin))
async def admin_menu(message: Message) -> None:
    await message.answer("Панель оператора. Выбери действие или найди человека: /find 123456789 или /find @бот", reply_markup=_menu_markup())


@router.message(Command("adminhelp"), F.from_user.id.func(_is_admin))
async def admin_help(message: Message) -> None:
    await message.answer(_help_text())


async def _stats_text() -> str:
    async with AsyncSessionLocal() as db:
        s = await moderation.platform_stats(db)
    return (
        "📊 Сводка\n"
        f"Владельцев: {s['clients']} (заблокировано: {s['banned']})\n"
        f"Ботов: {s['bots']} · в эфире: {s['active']} · остановлено за неоплату: {s['disabled']}\n"
        f"На паузе: {s['paused']} · снято оператором: {s['blocked']}\n"
        f"Оплаченных заказов за всё время: {s['paid_orders']}\n"
        f"Открытых жалоб: {s['open_reports']}"
    )


@router.message(Command("stats"), F.from_user.id.func(_is_admin))
async def stats_command(message: Message) -> None:
    await message.answer(await _stats_text())


@router.callback_query(F.data.startswith("am:"), F.from_user.id.func(_is_admin))
async def menu_button(query: CallbackQuery) -> None:
    what = (query.data or "")[3:]
    if what == "reports":
        text, markup = await _reports_view()
        await query.message.answer(text, reply_markup=markup)
    elif what == "journal":
        await query.message.answer(await _journal_text(), parse_mode="HTML")
    elif what == "stats":
        await query.message.answer(await _stats_text())
    else:
        await query.message.answer(_help_text())
    await query.answer()


async def _find_card(db, arg: str) -> tuple[str, InlineKeyboardMarkup | None]:
    client, bot = await moderation.find(db, arg)
    if client is None and bot is None:
        return "Не нашёл. Нужен Telegram id владельца или имя бота (@имя).", None
    lines: list[str] = []
    rows: list[list[InlineKeyboardButton]] = []
    if bot is not None:
        state = "снят оператором" if bot.moderation_blocked_at else ("на паузе" if bot.paused else bot.status.value)
        username = f"@{escape(bot.telegram_bot_username)}" if bot.telegram_bot_username else "без имени в Telegram"
        lines.append(f"Бот: {escape(bot.name or '—')} · {username} · {state}")
        if bot.moderation_blocked_at is None:
            rows.append([_btn("⛔ Снять бота", f"xb:{bot.id.hex}")])
        else:
            rows.append([_btn("↩ Вернуть бота", f"xr:{bot.id.hex}")])
    if client is not None:
        tid = client.telegram_user_id
        count = len((await db.execute(select(Bot.id).where(Bot.client_id == client.id))).scalars().all())
        banned = "заблокирован" if client.banned_at else "активен"
        lines.append(f"Владелец: <code>{tid}</code> · {escape(client.full_name or '—')} · {banned} · ботов: {count}")
        rows.append(
            [_btn("🚫 Заблокировать", f"xn:{tid}")] if client.banned_at is None else [_btn("✅ Разблокировать", f"xu:{tid}")]
        )
        rows.append([_btn("📦 Выгрузка данных", f"xe:{tid}"), _btn("🗑 Удалить аккаунт", f"xd:{tid}")])
    return "\n".join(lines), InlineKeyboardMarkup(inline_keyboard=rows)


@router.message(Command("find"), F.from_user.id.func(_is_admin))
async def find_command(message: Message, command: CommandObject) -> None:
    arg = (command.args or "").strip()
    if not arg:
        await message.answer("Формат: /find 123456789 или /find @имя_бота")
        return
    async with AsyncSessionLocal() as db:
        text, markup = await _find_card(db, arg)
    await message.answer(text, parse_mode="HTML", reply_markup=markup)


async def _send_export(message: Message, telegram_id: int, actor: str) -> None:
    import json

    async with AsyncSessionLocal() as db:
        data = await moderation.export_client(db, telegram_id, actor=actor)
    payload = json.dumps(data, ensure_ascii=False, indent=2).encode()
    await message.answer_document(
        BufferedInputFile(payload, filename=f"export_{telegram_id}.json"),
        caption="Данные владельца без токенов и ключей. Отправь человеку в течение 30 дней после запроса.",
    )


@router.message(Command("export"), F.from_user.id.func(_is_admin))
async def export_command(message: Message, command: CommandObject) -> None:
    telegram_id, _ = _telegram_id_arg(command)
    if telegram_id is None:
        await message.answer("Формат: /export 123456789")
        return
    try:
        await _send_export(message, telegram_id, _actor(message.from_user.id))
    except moderation.ModerationError as exc:
        await message.answer(escape(str(exc)))


@router.message(Command("delete"), F.from_user.id.func(_is_admin))
async def delete_command(message: Message, command: CommandObject) -> None:
    telegram_id, _ = _telegram_id_arg(command)
    if telegram_id is None:
        await message.answer("Формат: /delete 123456789 (удаление необратимо, дальше попрошу подтвердить)")
        return
    text, markup = _confirm("xd", str(telegram_id), f"удалить аккаунт {telegram_id} со всеми ботами, без возврата")
    await message.answer(text, reply_markup=markup)


@router.callback_query(F.data.startswith(("xb:", "xn:", "xd:")), F.from_user.id.func(_is_admin))
async def ask_confirm_direct(query: CallbackQuery) -> None:
    action, value = (query.data or "").split(":", 1)
    what = {
        "xb": "снять бота с эфира",
        "xn": "заблокировать владельца (вход закрыт, боты на паузе)",
        "xd": "удалить аккаунт со всеми ботами, без возврата",
    }[action]
    text, markup = _confirm(action, value, what)
    await query.message.answer(text, reply_markup=markup)
    await query.answer()


@router.callback_query(F.data.startswith(("xbc:", "xnc:", "xdc:", "xr:", "xu:", "xe:")), F.from_user.id.func(_is_admin))
async def do_direct_action(query: CallbackQuery) -> None:
    action, value = (query.data or "").split(":", 1)
    actor = _actor(query.from_user.id)
    async with AsyncSessionLocal() as db:
        try:
            if action in {"xbc", "xr"}:
                bot_id = _uid(value)
                if bot_id is None:
                    raise moderation.ModerationError("Не разобрал идентификатор.")
                if action == "xbc":
                    await moderation.block_bot(db, bot_id, actor=actor, reason="решение оператора")
                    result = "⛔ Бот снят."
                else:
                    await moderation.restore_bot(db, bot_id, actor=actor)
                    result = "↩ Бот возвращён."
            else:
                if not value.lstrip("-").isdigit():
                    raise moderation.ModerationError("Не разобрал Telegram id.")
                telegram_id = int(value)
                if action == "xnc":
                    result = "🚫 " + await moderation.ban_client(db, telegram_id, actor=actor, reason="решение оператора")
                elif action == "xu":
                    result = await moderation.unban_client(db, telegram_id, actor=actor)
                elif action == "xdc":
                    result = "🗑 " + await moderation.delete_client(
                        db, telegram_id, actor=actor, reason="решение оператора"
                    )
                else:  # xe
                    await _send_export(query.message, telegram_id, actor)
                    await query.answer("Готово")
                    return
        except moderation.ModerationError as exc:
            await query.answer(str(exc), show_alert=True)
            return
    await query.message.answer(escape(result))
    await query.answer("Готово")
