"""Модерация: жалобы на ботов, их рассмотрение и журнал решений.

Принцип «уведомление и действие», как у обычных сервисов: платформа не читает
чужих ботов заранее и никогда не открывает переписку покупателей; она реагирует
на жалобу, требование органов или платёжной системы. Оператор смотрит только
настройки бота (название, имя в Telegram, владельца), а решение записывает в
журнал. Бот снимается, а не удаляется: ничего не стирается, снять отметку
можно.

Бот, снятый оператором, стоит на паузе (новые диалоги закрыты, отложенные
сообщения отменены), и владелец вернуть его сам не может.
"""

from __future__ import annotations

import re
import uuid
from datetime import datetime, timezone

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.bot import Bot
from app.models.client import Client
from app.models.moderation import AbuseReport, ModerationAction
from app.models.scheduled_step import ScheduledStep, StepStatus

#: Что можно выбрать в форме жалобы. Ключ — в базе, подпись — на странице.
CATEGORIES: dict[str, str] = {
    "fraud": "Мошенничество или обман покупателей",
    "illegal": "Запрещённый законом товар или услуга",
    "copyright": "Нарушение авторских прав",
    "adult": "Сексуальный контент с участием несовершеннолетних, насилие, экстремизм",
    "spam": "Спам и рассылки без согласия",
    "other": "Другое",
}

MAX_DETAILS = 3000
MAX_REF = 255
MAX_CONTACT = 255
OPEN_STATUS = "new"


class ModerationError(Exception):
    """Причина отказа человеческим языком."""


def parse_bot_ref(raw: str) -> str:
    """Имя бота из того, что прислал человек: @name, t.me/name, https://t.me/name?start=..."""
    value = (raw or "").strip()
    value = re.sub(r"^https?://", "", value, flags=re.IGNORECASE)
    value = re.sub(r"^(www\.)?(t\.me|telegram\.me)/", "", value, flags=re.IGNORECASE)
    value = value.split("?")[0].split("/")[0].lstrip("@").strip()
    return value


async def find_bot_by_username(db: AsyncSession, raw: str) -> Bot | None:
    name = parse_bot_ref(raw).lower()
    if not name or not re.fullmatch(r"[a-z0-9_]{3,64}", name):
        return None
    result = await db.execute(select(Bot).where(Bot.telegram_bot_username.ilike(name)))
    return result.scalars().first()


async def submit_report(
    db: AsyncSession, *, bot_ref: str, category: str, details: str, contact: str = ""
) -> AbuseReport:
    ref = (bot_ref or "").strip()[:MAX_REF]
    text = (details or "").strip()
    if not ref:
        raise ModerationError("Укажите имя бота или ссылку на него.")
    if len(text) < 10:
        raise ModerationError("Опишите, что произошло, хотя бы в двух словах.")
    bot = await find_bot_by_username(db, ref)
    report = AbuseReport(
        bot_id=bot.id if bot else None,
        bot_ref=ref,
        category=category if category in CATEGORIES else "other",
        details=text[:MAX_DETAILS],
        contact=(contact or "").strip()[:MAX_CONTACT] or None,
    )
    db.add(report)
    await db.commit()
    return report


def _log(
    db: AsyncSession,
    *,
    action: str,
    actor: str,
    reason: str = "",
    report_id: uuid.UUID | None = None,
    bot_id: uuid.UUID | None = None,
    client_telegram_id: int | None = None,
) -> ModerationAction:
    entry = ModerationAction(
        action=action,
        actor=actor[:64],
        reason=(reason or "").strip(),
        report_id=report_id,
        bot_id=bot_id,
        client_telegram_id=client_telegram_id,
    )
    db.add(entry)
    return entry


async def _owner_telegram_id(db: AsyncSession, bot: Bot) -> int | None:
    result = await db.execute(select(Client.telegram_user_id).where(Client.id == bot.client_id))
    return result.scalar_one_or_none()


async def _close_report(db: AsyncSession, report_id: uuid.UUID | None, status: str) -> None:
    if report_id is None:
        return
    await db.execute(
        update(AbuseReport)
        .where(AbuseReport.id == report_id, AbuseReport.status == OPEN_STATUS)
        .values(status=status, resolved_at=datetime.now(timezone.utc))
    )


async def block_bot(
    db: AsyncSession, bot_id: uuid.UUID, *, actor: str, reason: str = "", report_id: uuid.UUID | None = None
) -> Bot:
    """Снять бота: пауза, отметка оператора, отложенные сообщения отменены."""
    bot = (await db.execute(select(Bot).where(Bot.id == bot_id))).scalar_one_or_none()
    if bot is None:
        raise ModerationError("Бот не найден.")
    bot.paused = True
    bot.moderation_blocked_at = datetime.now(timezone.utc)
    await db.execute(
        update(ScheduledStep)
        .where(ScheduledStep.bot_id == bot.id, ScheduledStep.status == StepStatus.pending)
        .values(status=StepStatus.cancelled, last_error=f"бот снят оператором: {reason}"[:500])
    )
    _log(
        db,
        action="block_bot",
        actor=actor,
        reason=reason,
        report_id=report_id,
        bot_id=bot.id,
        client_telegram_id=await _owner_telegram_id(db, bot),
    )
    await _close_report(db, report_id, "actioned")
    await db.commit()
    return bot


async def restore_bot(db: AsyncSession, bot_id: uuid.UUID, *, actor: str, reason: str = "") -> Bot:
    bot = (await db.execute(select(Bot).where(Bot.id == bot_id))).scalar_one_or_none()
    if bot is None:
        raise ModerationError("Бот не найден.")
    if bot.moderation_blocked_at is None:
        raise ModerationError("Этот бот не снят оператором.")
    bot.moderation_blocked_at = None
    bot.paused = False
    _log(
        db,
        action="restore_bot",
        actor=actor,
        reason=reason,
        bot_id=bot.id,
        client_telegram_id=await _owner_telegram_id(db, bot),
    )
    await db.commit()
    return bot


async def ban_client(
    db: AsyncSession,
    telegram_id: int,
    *,
    actor: str,
    reason: str = "",
    report_id: uuid.UUID | None = None,
) -> str:
    """Заблокировать аккаунт (вход закрыт, боты на паузе) — см. `app.admin.ban`."""
    from app.admin import ban

    try:
        summary = await ban(db, telegram_id, reason)
    except SystemExit as exc:  # `_client` в CLI завершает процесс, здесь это обычная ошибка
        raise ModerationError(str(exc)) from exc
    _log(db, action="ban_client", actor=actor, reason=reason, report_id=report_id, client_telegram_id=telegram_id)
    await _close_report(db, report_id, "actioned")
    await db.commit()
    return summary


async def unban_client(db: AsyncSession, telegram_id: int, *, actor: str, reason: str = "") -> str:
    from app.admin import unban

    try:
        summary = await unban(db, telegram_id)
    except SystemExit as exc:
        raise ModerationError(str(exc)) from exc
    _log(db, action="unban_client", actor=actor, reason=reason, client_telegram_id=telegram_id)
    await db.commit()
    return summary


async def dismiss_report(db: AsyncSession, report_id: uuid.UUID, *, actor: str, reason: str = "") -> None:
    report = (await db.execute(select(AbuseReport).where(AbuseReport.id == report_id))).scalar_one_or_none()
    if report is None:
        raise ModerationError("Жалоба не найдена.")
    report.status = "dismissed"
    report.resolved_at = datetime.now(timezone.utc)
    _log(db, action="dismiss_report", actor=actor, reason=reason, report_id=report.id, bot_id=report.bot_id)
    await db.commit()


async def open_reports(db: AsyncSession, limit: int = 10) -> list[AbuseReport]:
    result = await db.execute(
        select(AbuseReport)
        .where(AbuseReport.status == OPEN_STATUS)
        .order_by(AbuseReport.created_at.desc())
        .limit(limit)
    )
    return list(result.scalars())


async def journal(db: AsyncSession, limit: int = 20) -> list[ModerationAction]:
    result = await db.execute(select(ModerationAction).order_by(ModerationAction.created_at.desc()).limit(limit))
    return list(result.scalars())


async def platform_stats(db: AsyncSession) -> dict[str, int]:
    """Сводка для оператора: сколько людей, ботов и жалоб. Только числа."""
    from app.models.bot import BotStatus
    from app.models.payment import Payment, PaymentStatus

    async def count(stmt) -> int:
        return int((await db.execute(stmt)).scalar_one() or 0)

    return {
        "clients": await count(select(func.count()).select_from(Client)),
        "banned": await count(select(func.count()).select_from(Client).where(Client.banned_at.is_not(None))),
        "bots": await count(select(func.count()).select_from(Bot)),
        "active": await count(select(func.count()).select_from(Bot).where(Bot.status == BotStatus.active)),
        "disabled": await count(select(func.count()).select_from(Bot).where(Bot.status == BotStatus.disabled)),
        "paused": await count(select(func.count()).select_from(Bot).where(Bot.paused.is_(True))),
        "blocked": await count(
            select(func.count()).select_from(Bot).where(Bot.moderation_blocked_at.is_not(None))
        ),
        "paid_orders": await count(
            select(func.count()).select_from(Payment).where(Payment.status == PaymentStatus.paid)
        ),
        "open_reports": await count(
            select(func.count()).select_from(AbuseReport).where(AbuseReport.status == OPEN_STATUS)
        ),
    }


async def find(db: AsyncSession, arg: str) -> tuple[Client | None, Bot | None]:
    """Найти по Telegram id владельца (число) или по имени бота (@имя, ссылка)."""
    value = (arg or "").strip()
    if value.lstrip("-").isdigit():
        client = (
            await db.execute(select(Client).where(Client.telegram_user_id == int(value)))
        ).scalar_one_or_none()
        return client, None
    bot = await find_bot_by_username(db, value)
    if bot is None:
        return None, None
    client = (await db.execute(select(Client).where(Client.id == bot.client_id))).scalar_one_or_none()
    return client, bot


async def export_client(db: AsyncSession, telegram_id: int, *, actor: str) -> dict:
    """Выгрузка данных владельца (без токенов и ключей), с записью в журнал."""
    from app.admin import export

    try:
        data = await export(db, telegram_id)
    except SystemExit as exc:
        raise ModerationError(str(exc)) from exc
    _log(db, action="export_client", actor=actor, client_telegram_id=telegram_id)
    await db.commit()
    return data


async def delete_client(db: AsyncSession, telegram_id: int, *, actor: str, reason: str = "") -> str:
    """Удалить аккаунт со всеми ботами (необратимо). Платёжные записи остаются обезличенными."""
    from app.admin import delete

    try:
        summary = await delete(db, telegram_id)
    except SystemExit as exc:
        raise ModerationError(str(exc)) from exc
    _log(db, action="delete_account", actor=actor, reason=reason, client_telegram_id=telegram_id)
    await db.commit()
    return summary
