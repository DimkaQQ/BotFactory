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

from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.booking import ACTIVE, Booking
from app.models.bot_block import BlockType, BotBlock

logger = logging.getLogger(__name__)

HOLD_MINUTES = 60
#: Сколько подтверждённых будущих записей может быть у одного человека в боте.
MAX_ACTIVE_PER_PERSON = 3


class BookingLimitError(Exception):
    """У человека уже максимум активных записей."""


#: Часовой пояс по умолчанию, если владелец ничего не выбрал (редактор сам
#: подставляет пояс из браузера владельца).
DEFAULT_TZ = "UTC"
WEEKDAYS = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]
MONTHS = ["янв", "фев", "мар", "апр", "мая", "июн", "июл", "авг", "сен", "окт", "ноя", "дек"]
MAX_INTERVALS_PER_DAY = 6
MAX_EXCEPTIONS = 366

Interval = tuple[time, time]


@dataclass(frozen=True)
class Schedule:
    #: Рабочие часы по дням недели (0 = понедельник): несколько промежутков на день.
    weekly: dict[int, tuple[Interval, ...]]
    #: Исключения по датам: пустой список — день закрыт, иначе свои часы только на эту дату.
    exceptions: dict[date, tuple[Interval, ...]]
    slot_minutes: int
    horizon_days: int
    notice_hours: int
    tz: ZoneInfo
    tz_name: str

    @property
    def days(self) -> tuple[int, ...]:
        return tuple(sorted(d for d, intervals in self.weekly.items() if intervals))


def _parse_time(value, default: time | None = None) -> time | None:
    try:
        hours, minutes = str(value).split(":")[:2]
        return time(int(hours), int(minutes))
    except (ValueError, TypeError):
        return default


def _parse_intervals(raw) -> tuple[Interval, ...]:
    """[["10:00","13:00"], ["14:00","19:00"]] → отсортированные непересекающиеся промежутки."""
    if not isinstance(raw, (list, tuple)):
        return ()
    found: list[Interval] = []
    for item in raw[:MAX_INTERVALS_PER_DAY * 2]:
        if not isinstance(item, (list, tuple)) or len(item) != 2:
            continue
        start, end = _parse_time(item[0]), _parse_time(item[1])
        if start is None or end is None or end <= start:
            continue
        found.append((start, end))
    found.sort()
    merged: list[Interval] = []
    for start, end in found:
        if merged and start < merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))
    return tuple(merged[:MAX_INTERVALS_PER_DAY])


def schedule_of(content: dict | None) -> Schedule:
    content = content or {}
    weekly: dict[int, tuple[Interval, ...]] = {}
    raw_weekly = content.get("weekly")
    if isinstance(raw_weekly, dict):
        for key, raw in raw_weekly.items():
            if str(key).isdigit() and 0 <= int(key) <= 6:
                weekly[int(key)] = _parse_intervals(raw)
    else:
        # Прежний формат: одни часы на выбранные дни недели.
        raw_days = content.get("days")
        if not isinstance(raw_days, (list, tuple)):
            raw_days = [0, 1, 2, 3, 4]
        start = _parse_time(content.get("start"), time(10, 0))
        end = _parse_time(content.get("end"), time(19, 0))
        # Список без единого дня — это «запись закрыта», а не «будни».
        for d in {int(d) for d in raw_days if str(d).isdigit() and 0 <= int(d) <= 6}:
            weekly[d] = _parse_intervals([[start.strftime("%H:%M"), end.strftime("%H:%M")]])

    exceptions: dict[date, tuple[Interval, ...]] = {}
    raw_exceptions = content.get("exceptions")
    if isinstance(raw_exceptions, dict):
        for key, raw in list(raw_exceptions.items())[:MAX_EXCEPTIONS]:
            try:
                day = date.fromisoformat(str(key))
            except ValueError:
                continue
            exceptions[day] = _parse_intervals(raw)

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
        weekly=weekly,
        exceptions=exceptions,
        slot_minutes=max(15, min(slot, 480)),
        horizon_days=max(1, min(horizon, 60)),
        notice_hours=max(0, min(notice, 168)),
        tz=tz,
        tz_name=tz_name,
    )


def intervals_for(schedule: Schedule, day: date) -> tuple[Interval, ...]:
    if day in schedule.exceptions:
        return schedule.exceptions[day]
    return schedule.weekly.get(day.weekday(), ())


def day_slots(schedule: Schedule, day: date) -> list[datetime]:
    """Все возможные начала слотов в этот день (UTC), без учёта занятости."""
    out: list[datetime] = []
    step = timedelta(minutes=schedule.slot_minutes)
    for start_t, end_t in intervals_for(schedule, day):
        cursor = datetime.combine(day, start_t, tzinfo=schedule.tz)
        end = datetime.combine(day, end_t, tzinfo=schedule.tz)
        while cursor + step <= end:
            start = cursor.astimezone(timezone.utc)
            # Переход на летнее время: «02:30» может не существовать — такой слот пропускаем,
            # иначе кнопка вела бы на другое время, а запись бы отклонялась.
            if start.astimezone(schedule.tz).replace(tzinfo=None) == cursor.replace(tzinfo=None) and start not in out:
                out.append(start)
            cursor += step
    out.sort()
    return out


def clean_schedule(payload: dict) -> dict:
    """Привести присланное из редактора к безопасному виду (для сохранения в блок)."""
    schedule = schedule_of(payload)
    return {
        "weekly": {
            str(d): [[a.strftime("%H:%M"), b.strftime("%H:%M")] for a, b in schedule.weekly.get(d, ())] for d in range(7)
        },
        "exceptions": {
            day.isoformat(): [[a.strftime("%H:%M"), b.strftime("%H:%M")] for a, b in intervals]
            for day, intervals in sorted(schedule.exceptions.items())
        },
        "slot_minutes": schedule.slot_minutes,
        "horizon_days": schedule.horizon_days,
        "notice_hours": schedule.notice_hours,
        "tz": schedule.tz_name,
    }


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
    if status == "held" and telegram_user_id is not None:
        active = (
            await db.execute(
                select(func.count(Booking.id)).where(
                    Booking.bot_id == bot_id,
                    Booking.telegram_user_id == telegram_user_id,
                    Booking.status == "confirmed",
                    Booking.starts_at > now,
                )
            )
        ).scalar_one()
        if active >= MAX_ACTIVE_PER_PERSON:
            raise BookingLimitError(active)
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
    # Только живая придержка: просроченная (статус ещё «held», пока кто-то не занял время) не
    # должна цепляться к чужой по смыслу покупке и подтверждаться её оплатой.
    return (
        await db.execute(
            select(Booking)
            .where(
                Booking.bot_id == bot_id,
                Booking.telegram_user_id == telegram_user_id,
                Booking.status == "held",
                Booking.held_until > datetime.now(timezone.utc),
            )
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


async def schedule_for(db: AsyncSession, booking: Booking) -> Schedule:
    """Расписание блока, через который сделана эта запись (у блоков может быть свой часовой пояс)."""
    if booking.block_id is not None:
        block = await db.get(BotBlock, booking.block_id)
        if block is not None and block.bot_id == booking.bot_id:
            return schedule_of(block.content)
    return (await first_schedule(db, booking.bot_id))[0]


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
