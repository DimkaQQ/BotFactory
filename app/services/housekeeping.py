"""Напоминания о записи и уборка старых данных.

Напоминания: клиенту, у которого подтверждённая запись, бот пишет за сутки и за
два часа до начала (владелец может выключить галочкой в блоке «Запись»).
Каждое напоминание захватывается условным UPDATE, поэтому два воркера не
пришлют его дважды.

Уборка: нажатия кнопок хранятся 180 дней, завершённые и отменённые записи —
365 дней (клиент сохраняется в CRM и без них), устаревшие ожидания ответа,
слепки ключей кассы у неоплаченных счетов старше 48 часов.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.booking import Booking, ChatState
from app.models.bot_block import BotBlock
from app.models.button_click import ButtonClick
from app.services import booking as bk

logger = logging.getLogger(__name__)

CLICKS_KEEP_DAYS = 180
BOOKINGS_KEEP_DAYS = 365


def _reminder_text(label: str, hours_left: float) -> str:
    when = "через пару часов" if hours_left <= 3 else "в ближайшие сутки"
    return f"🔔 Напоминаем о записи: {label} ({when}). Если планы изменились, напишите нам."


async def _enabled(db: AsyncSession, cache: dict, block_id) -> bool:
    if block_id is None:
        return True
    if block_id not in cache:
        block = await db.get(BotBlock, block_id)
        cache[block_id] = block is None or (block.content or {}).get("reminders") is not False
    return cache[block_id]


async def send_reminders(db: AsyncSession, *, now: datetime | None = None) -> int:
    """Отправить напоминания, которым пора. Возвращает, сколько ушло."""
    from app.services import bot_registry

    now = now or datetime.now(timezone.utc)
    horizon = now + timedelta(hours=24)
    rows = (
        await db.execute(
            select(Booking).where(
                Booking.status == "confirmed",
                Booking.chat_id.is_not(None),
                Booking.starts_at > now,
                Booking.starts_at <= horizon,
            ).limit(500)
        )
    ).scalars().all()
    sent = 0
    cache: dict = {}
    for booking in rows:
        left = booking.starts_at - now
        kind = None
        if left <= timedelta(hours=2) and booking.reminded_hours_at is None and booking.created_at <= booking.starts_at - timedelta(hours=2):
            kind = "reminded_hours_at"
        elif (
            left > timedelta(hours=3)
            and booking.reminded_day_at is None
            and booking.created_at <= now - timedelta(hours=1)
        ):
            kind = "reminded_day_at"
        if kind is None:
            continue
        # Захват: пометка ставится условно, победитель отправляет.
        column = getattr(Booking, kind)
        claimed = await db.execute(
            update(Booking).where(Booking.id == booking.id, column.is_(None)).values({kind: now})
        )
        await db.commit()
        if claimed.rowcount != 1:
            continue
        if not await _enabled(db, cache, booking.block_id):
            continue
        schedule, _block = await bk.first_schedule(db, booking.bot_id)
        text = _reminder_text(bk.full_label(schedule, booking.starts_at), left.total_seconds() / 3600)
        try:
            instance = await bot_registry.get_or_create(booking.bot_id, db)
            if instance is not None:
                await asyncio.wait_for(instance.send_message(booking.chat_id, text), timeout=15)
                sent += 1
        except Exception:  # noqa: BLE001
            logger.info("Could not send a booking reminder for %s", booking.id, exc_info=True)
    return sent


async def cleanup(db: AsyncSession, *, now: datetime | None = None) -> dict[str, int]:
    """Убрать устаревшее. Возвращает, сколько записей удалено по видам."""
    from app.services import payment_service

    now = now or datetime.now(timezone.utc)
    counts = {}
    clicks = await db.execute(
        delete(ButtonClick).where(ButtonClick.created_at < now - timedelta(days=CLICKS_KEEP_DAYS))
    )
    counts["button_clicks"] = clicks.rowcount or 0
    states = await db.execute(delete(ChatState).where(ChatState.expires_at < now))
    counts["chat_states"] = states.rowcount or 0
    old = await db.execute(
        delete(Booking).where(
            Booking.starts_at < now - timedelta(days=BOOKINGS_KEEP_DAYS),
        )
    )
    counts["bookings"] = old.rowcount or 0
    await db.commit()
    counts["kassa_snapshots"] = await payment_service.scrub_old_kassa_snapshots(db)
    return counts


async def run_forever(reminder_every: float = 300.0, cleanup_every: float = 6 * 3600.0) -> None:
    from app.database import AsyncSessionLocal

    last_cleanup = 0.0
    loop = asyncio.get_event_loop()
    while True:
        await asyncio.sleep(reminder_every)
        try:
            async with AsyncSessionLocal() as db:
                await send_reminders(db)
            if loop.time() - last_cleanup >= cleanup_every:
                async with AsyncSessionLocal() as db:
                    await cleanup(db)
                last_cleanup = loop.time()
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Housekeeping failed; will try again")
            with contextlib.suppress(Exception):
                await asyncio.sleep(1)
