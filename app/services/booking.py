"""Календарь записи: свободные слоты, бронирование, отмена, подтверждение после оплаты.

Расписание задаёт сам блок «Запись» (`content`): рабочие дни, часы, длительность
слота, на сколько дней вперёд открыта запись, часовой пояс. Календарь один на
бота: два блока «Запись» в одном боте делят время.

Время хранится в UTC; рабочие часы считаются в часовом поясе блока. Слот
занимает одна активная запись (см. `Booking`): параллельные нажатия не дадут
записать двоих на одно время.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.booking import ACTIVE, Booking
from app.models.bot_block import BlockType, BotBlock

logger = logging.getLogger(__name__)

HOLD_MINUTES = 60
DEFAULT_TZ = "Asia/Almaty"
WEEKDAYS = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]
MONTHS = ["янв", "фев", "мар", "апр", "мая", "июн", "июл", "авг", "сен", "окт", "ноя", "дек"]


@dataclass(frozen=True)
class Schedule:
    days: tuple[int, ...]
    start: time
    end: time
    slot_minutes: int
    horizon_days: int
    notice_hours: int
    tz: ZoneInfo
    tz_name: str


def _parse_time(value, default: time) -> time:
    try:
        hours, minutes = str(value).split(":")[:2]
        return time(int(hours), int(minutes))
    except (ValueError, TypeError):
        return default


def schedule_of(content: dict | None) -> Schedule:
    content = content or {}
    days = tuple(
        sorted({int(d) for d in (content.get("days") or [0, 1, 2, 3, 4]) if str(d).isdigit() and 0 <= int(d) <= 6})
    ) or (0, 1, 2, 3, 4)
    tz_name = str(content.get("tz") or DEFAULT_TZ)
    try:
        tz = ZoneInfo(tz_name)
    except Exception:  # noqa: BLE001
        tz, tz_name = ZoneInfo(DEFAULT_TZ), DEFAULT_TZ
    try:
        slot = int(content.get("slot_minutes") or 60)
    except (TypeError, ValueError):
        slot = 60
    try:
        horizon = int(content.get("horizon_days") or 14)
    except (TypeError, ValueError):
        horizon = 14
    try:
        notice = int(content.get("notice_hours") if content.get("notice_hours") is not None else 2)
    except (TypeError, ValueError):
        notice = 2
    return Schedule(
        days=days,
        start=_parse_time(content.get("start"), time(10, 0)),
        end=_parse_time(content.get("end"), time(19, 0)),
        slot_minutes=max(15, min(slot, 480)),
        horizon_days=max(1, min(horizon, 60)),
        notice_hours=max(0, min(notice, 168)),
        tz=tz,
        tz_name=tz_name,
    )


def day_slots(schedule: Schedule, day: date) -> list[datetime]:
    """Все возможные начала слотов в этот день (UTC), без учёта занятости."""
    if day.weekday() not in schedule.days:
        return []
    cursor = datetime.combine(day, schedule.start, tzinfo=schedule.tz)
    end = datetime.combine(day, schedule.end, tzinfo=schedule.tz)
    step = timedelta(minutes=schedule.slot_minutes)
    out = []
    while cursor + step <= end:
        out.append(cursor.astimezone(timezone.utc))
        cursor += step
    return out


def local_day(schedule: Schedule, moment: datetime) -> date:
    return moment.astimezone(schedule.tz).date()


def day_label(day: date) -> str:
    return f"{WEEKDAYS[day.weekday()]} {day.day} {MONTHS[day.month - 1]}"


def slot_label(schedule: Schedule, start: datetime) -> str:
    return start.astimezone(schedule.tz).strftime("%H:%M")


def full_label(schedule: Schedule, start: datetime) -> str:
    local = start.astimezone(schedule.tz)
    return f"{day_label(local.date())}, {local:%H:%M}"


async def taken_starts(
    db: AsyncSession, bot_id: uuid.UUID, since: datetime, until: datetime, *, now: datetime | None = None
) -> set[datetime]:
    """Времена, занятые активными записями (просроченные придержки не в счёт)."""
    now = now or datetime.now(timezone.utc)
    rows = (
        await db.execute(
            select(Booking.starts_at, Booking.status, Booking.held_until).where(
                Booking.bot_id == bot_id,
                Booking.status.in_(ACTIVE),
                Booking.starts_at >= since,
                Booking.starts_at < until,
            )
        )
    ).all()
    busy = set()
    for starts_at, status, held_until in rows:
        if status == "held" and held_until is not None and held_until <= now:
            continue
        busy.add(starts_at)
    return busy


async def free_slots(
    db: AsyncSession, bot_id: uuid.UUID, schedule: Schedule, day: date, *, now: datetime | None = None
) -> list[datetime]:
    now = now or datetime.now(timezone.utc)
    candidates = [s for s in day_slots(schedule, day) if s >= now + timedelta(hours=schedule.notice_hours)]
    if not candidates:
        return []
    busy = await taken_starts(db, bot_id, candidates[0], candidates[-1] + timedelta(minutes=1), now=now)
    return [s for s in candidates if s not in busy]


async def open_days(
    db: AsyncSession, bot_id: uuid.UUID, schedule: Schedule, *, now: datetime | None = None, limit: int = 14
) -> list[date]:
    """Ближайшие дни, где ещё есть свободное время."""
    now = now or datetime.now(timezone.utc)
    today = local_day(schedule, now)
    out: list[date] = []
    for offset in range(schedule.horizon_days + 1):
        day = today + timedelta(days=offset)
        if await free_slots(db, bot_id, schedule, day, now=now):
            out.append(day)
        if len(out) >= limit:
            break
    return out


async def reserve(
    db: AsyncSession,
    *,
    bot_id: uuid.UUID,
    block: BotBlock | None,
    schedule: Schedule,
    start: datetime,
    telegram_user_id: int | None,
    chat_id: int | None,
    status: str = "held",
    note: str = "",
) -> Booking | None:
    """Занять время. None — его только что заняли (или оно не из расписания)."""
    now = datetime.now(timezone.utc)
    if status != "blocked" and start not in day_slots(schedule, local_day(schedule, start)):
        return None
    # Просроченную придержку на этом времени убираем: иначе она держит уникальный индекс.
    await db.execute(
        update(Booking)
        .where(
            Booking.bot_id == bot_id,
            Booking.starts_at == start,
            Booking.status == "held",
            Booking.held_until <= now,
        )
        .values(status="cancelled")
    )
    # Свою же прежнюю придержку человек может сменить: освобождаем её.
    if telegram_user_id is not None and status == "held":
        await db.execute(
            update(Booking)
            .where(Booking.bot_id == bot_id, Booking.telegram_user_id == telegram_user_id, Booking.status == "held")
            .values(status="cancelled")
        )
    booking = Booking(
        bot_id=bot_id,
        block_id=block.id if block is not None else None,
        telegram_user_id=telegram_user_id,
        chat_id=chat_id,
        starts_at=start,
        ends_at=start + timedelta(minutes=schedule.slot_minutes),
        status=status,
        held_until=now + timedelta(minutes=HOLD_MINUTES) if status == "held" else None,
        note=note,
    )
    db.add(booking)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        return None
    await db.refresh(booking)
    return booking


async def confirm(db: AsyncSession, booking: Booking) -> bool:
    """held → confirmed. False — запись уже отменена или была подтверждена."""
    result = await db.execute(
        update(Booking)
        .where(Booking.id == booking.id, Booking.status == "held")
        .values(status="confirmed", held_until=None)
    )
    await db.commit()
    return result.rowcount == 1


async def cancel(db: AsyncSession, booking: Booking) -> bool:
    result = await db.execute(
        update(Booking).where(Booking.id == booking.id, Booking.status.in_(ACTIVE)).values(status="cancelled")
    )
    await db.commit()
    return result.rowcount == 1


async def latest_held(db: AsyncSession, bot_id: uuid.UUID, telegram_user_id: int | None) -> Booking | None:
    if telegram_user_id is None:
        return None
    return (
        await db.execute(
            select(Booking)
            .where(Booking.bot_id == bot_id, Booking.telegram_user_id == telegram_user_id, Booking.status == "held")
            .order_by(Booking.created_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()


async def chain_needs_payment(db: AsyncSession, bot_id: uuid.UUID, start_id: uuid.UUID | None) -> bool:
    """Ведёт ли цепочка после блока записи к оплате (по стрелкам «дальше»)."""
    if start_id is None:
        return False
    rows = (await db.execute(select(BotBlock).where(BotBlock.bot_id == bot_id))).scalars().all()
    by_id = {b.id: b for b in rows}
    current = by_id.get(start_id)
    seen: set[uuid.UUID] = set()
    while current is not None and current.id not in seen:
        seen.add(current.id)
        if current.block_type == BlockType.payment:
            return True
        current = by_id.get(current.next_block_id) if current.next_block_id else None
    return False


async def first_schedule(db: AsyncSession, bot_id: uuid.UUID) -> tuple[Schedule, BotBlock | None]:
    """Расписание календаря бота — из первого блока «Запись» (иначе по умолчанию)."""
    block = (
        await db.execute(
            select(BotBlock)
            .where(BotBlock.bot_id == bot_id, BotBlock.block_type == BlockType.booking)
            .order_by(BotBlock.order_index, BotBlock.created_at)
            .limit(1)
        )
    ).scalar_one_or_none()
    return schedule_of(block.content if block else None), block
