"""Мини-CRM и календарь записи для владельца бота.

Клиенты — это люди, которые писали боту (`BotSubscriber`): Telegram-данные
приходят сами, телефон и имя — только если владелец включил блок «Контакты».
Всё доступно только владельцу бота; чужие боты отвечают 404.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.deps import get_current_client, get_owned_bot
from app.models.booking import Booking
from app.models.bot import Bot
from app.models.bot_subscriber import BotSubscriber
from app.models.client import Client
from app.models.payment import Payment, PaymentKind, PaymentStatus
from app.services import booking as bk

router = APIRouter(prefix="/api", tags=["crm"])


def _name(sub: BotSubscriber) -> str:
    return sub.contact_name or f"{sub.first_name} {sub.last_name}".strip() or (f"@{sub.username}" if sub.username else f"id {sub.telegram_user_id}")


def _profile(sub: BotSubscriber, bot_name: str) -> dict:
    return {
        "bot_id": str(sub.bot_id),
        "bot_name": bot_name,
        "telegram_user_id": sub.telegram_user_id,
        "name": _name(sub),
        "username": sub.username,
        "phone": sub.phone,
        "note": sub.note,
        "first_seen_at": sub.first_seen_at,
        "last_seen_at": sub.last_seen_at,
    }


def _bot_label(bot: Bot) -> str:
    return bot.name or (f"@{bot.telegram_bot_username}" if bot.telegram_bot_username else "Без названия")


@router.get("/crm/customers")
async def list_customers(
    bot_id: uuid.UUID | None = None,
    q: str = "",
    limit: int = Query(200, ge=1, le=500),
    client: Client = Depends(get_current_client),
    db: AsyncSession = Depends(get_db),
) -> dict:
    bots = (await db.execute(select(Bot).where(Bot.client_id == client.id))).scalars().all()
    by_id = {b.id: b for b in bots}
    if bot_id is not None and bot_id not in by_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Bot not found")
    wanted = [bot_id] if bot_id else list(by_id)
    if not wanted:
        return {"customers": []}

    stmt = select(BotSubscriber).where(BotSubscriber.bot_id.in_(wanted))
    needle = q.strip()
    if needle:
        # «%» и «_» в строке поиска — обычные символы, а не подстановки LIKE.
        def like_of(text: str) -> str:
            return "%" + text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"

        stmt = stmt.where(
            or_(
                BotSubscriber.first_name.ilike(like_of(needle), escape="\\"),
                BotSubscriber.last_name.ilike(like_of(needle), escape="\\"),
                BotSubscriber.username.ilike(like_of(needle.lstrip("@")), escape="\\"),
                BotSubscriber.contact_name.ilike(like_of(needle), escape="\\"),
                BotSubscriber.phone.ilike(like_of(needle), escape="\\"),
            )
        )
    subs = (await db.execute(stmt.order_by(BotSubscriber.last_seen_at.desc()).limit(limit))).scalars().all()
    if not subs:
        return {"customers": []}
    user_ids = {s.telegram_user_id for s in subs}

    paid_rows = (
        await db.execute(
            select(Payment.bot_id, Payment.telegram_user_id, Payment.currency, func.count(Payment.id), func.sum(Payment.amount_minor))
            .where(
                Payment.bot_id.in_(wanted),
                Payment.kind == PaymentKind.order,
                Payment.status == PaymentStatus.paid,
                Payment.telegram_user_id.in_(user_ids),
            )
            .group_by(Payment.bot_id, Payment.telegram_user_id, Payment.currency)
        )
    ).all()
    paid: dict[tuple, list[dict]] = {}
    for b_id, u_id, currency, count, total in paid_rows:
        paid.setdefault((b_id, u_id), []).append({"currency": currency, "count": int(count), "total_minor": int(total or 0)})

    booking_rows = (
        await db.execute(
            select(Booking.bot_id, Booking.telegram_user_id, func.count(Booking.id), func.max(Booking.starts_at))
            .where(Booking.bot_id.in_(wanted), Booking.status == "confirmed", Booking.telegram_user_id.in_(user_ids))
            .group_by(Booking.bot_id, Booking.telegram_user_id)
        )
    ).all()
    bookings = {(b, u): (int(c), last) for b, u, c, last in booking_rows}

    out = []
    for sub in subs:
        key = (sub.bot_id, sub.telegram_user_id)
        count, last = bookings.get(key, (0, None))
        out.append(
            {
                **_profile(sub, _bot_label(by_id[sub.bot_id])),
                "orders": paid.get(key, []),
                "bookings": count,
                "last_booking_at": last,
            }
        )
    return {"customers": out}


class CustomerPatch(BaseModel):
    contact_name: str | None = Field(default=None, max_length=128)
    phone: str | None = Field(default=None, max_length=32)
    note: str | None = Field(default=None, max_length=4000)


async def _subscriber(db: AsyncSession, bot: Bot, telegram_user_id: int) -> BotSubscriber:
    sub = (
        await db.execute(
            select(BotSubscriber).where(BotSubscriber.bot_id == bot.id, BotSubscriber.telegram_user_id == telegram_user_id)
        )
    ).scalar_one_or_none()
    if sub is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Клиент не найден")
    return sub


@router.get("/crm/customers/{bot_id}/{telegram_user_id}")
async def customer_card(
    telegram_user_id: int, bot: Bot = Depends(get_owned_bot), db: AsyncSession = Depends(get_db)
) -> dict:
    sub = await _subscriber(db, bot, telegram_user_id)
    schedule, _block = await bk.first_schedule(db, bot.id)
    bookings = (
        await db.execute(
            select(Booking)
            .where(Booking.bot_id == bot.id, Booking.telegram_user_id == telegram_user_id, Booking.status != "blocked")
            .order_by(Booking.starts_at.desc())
            .limit(50)
        )
    ).scalars().all()
    orders = (
        await db.execute(
            select(Payment)
            .where(Payment.bot_id == bot.id, Payment.telegram_user_id == telegram_user_id, Payment.kind == PaymentKind.order)
            .order_by(Payment.created_at.desc())
            .limit(50)
        )
    ).scalars().all()
    return {
        **_profile(sub, _bot_label(bot)),
        "bookings": [
            {"id": str(b.id), "status": b.status, "starts_at": b.starts_at, "label": bk.full_label(schedule, b.starts_at)}
            for b in bookings
        ],
        "orders": [
            {
                "id": str(o.id), "invoice_no": o.invoice_no, "status": o.status, "description": o.description,
                "amount_minor": o.amount_minor, "currency": o.currency, "created_at": o.created_at,
                "choices": (o.meta or {}).get("choices") or [],
            }
            for o in orders
        ],
    }


@router.patch("/crm/customers/{bot_id}/{telegram_user_id}")
async def update_customer(
    telegram_user_id: int,
    payload: CustomerPatch,
    bot: Bot = Depends(get_owned_bot),
    db: AsyncSession = Depends(get_db),
) -> dict:
    sub = await _subscriber(db, bot, telegram_user_id)
    if payload.contact_name is not None:
        sub.contact_name = payload.contact_name.strip()
    if payload.phone is not None:
        sub.phone = payload.phone.strip()
    if payload.note is not None:
        sub.note = payload.note
    await db.commit()
    await db.refresh(sub)
    await db.refresh(bot)
    return _profile(sub, _bot_label(bot))


# ---------------------------------------------------------------- календарь


@router.get("/bots/{bot_id}/calendar")
async def calendar(
    start: date | None = None,
    days: int = Query(7, ge=1, le=31),
    bot: Bot = Depends(get_owned_bot),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Сетка слотов по дням с записями: свободно, занято, придержано, закрыто."""
    schedule, block = await bk.first_schedule(db, bot.id)
    now = datetime.now(timezone.utc)
    first = start or bk.local_day(schedule, now)
    all_days = [first + timedelta(days=i) for i in range(days)]

    slots_by_day = {d: bk.day_slots(schedule, d) for d in all_days}
    flat = [s for slots in slots_by_day.values() for s in slots]
    lo = min(flat) if flat else now
    hi = (max(flat) + timedelta(hours=1)) if flat else now
    rows = (
        await db.execute(
            select(Booking).where(
                Booking.bot_id == bot.id,
                Booking.status.in_(("held", "confirmed", "blocked")),
                Booking.starts_at >= lo - timedelta(days=1),
                Booking.starts_at <= hi,
            )
        )
    ).scalars().all()
    by_start = {b.starts_at: b for b in rows if not (b.status == "held" and b.held_until and b.held_until <= now)}
    names: dict[int, str] = {}
    ids = {b.telegram_user_id for b in by_start.values() if b.telegram_user_id}
    if ids:
        subs = (
            await db.execute(select(BotSubscriber).where(BotSubscriber.bot_id == bot.id, BotSubscriber.telegram_user_id.in_(ids)))
        ).scalars().all()
        names = {s.telegram_user_id: _name(s) for s in subs}
        phones = {s.telegram_user_id: s.phone for s in subs}
    else:
        phones = {}

    def slot_view(start_at: datetime) -> dict:
        booking = by_start.get(start_at)
        state = "free"
        if start_at < now:
            state = "past"
        if booking is not None:
            state = booking.status
        return {
            "starts_at": start_at,
            "time": bk.slot_label(schedule, start_at),
            "state": state,
            "booking_id": str(booking.id) if booking else None,
            "client": names.get(booking.telegram_user_id) if booking and booking.telegram_user_id else None,
            "phone": phones.get(booking.telegram_user_id) if booking and booking.telegram_user_id else None,
            "telegram_user_id": booking.telegram_user_id if booking else None,
        }

    return {
        "tz": schedule.tz_name,
        "configured": block is not None,
        "slot_minutes": schedule.slot_minutes,
        "days": [
            {"date": d.isoformat(), "label": bk.day_label(d), "slots": [slot_view(s) for s in slots_by_day[d]]}
            for d in all_days
        ],
    }


class BlockSlot(BaseModel):
    starts_at: datetime


@router.post("/bots/{bot_id}/calendar/block", status_code=status.HTTP_201_CREATED)
async def block_slot(
    payload: BlockSlot, bot: Bot = Depends(get_owned_bot), db: AsyncSession = Depends(get_db)
) -> dict:
    """Закрыть время (перерыв, выходной): клиенты его не увидят."""
    schedule, block = await bk.first_schedule(db, bot.id)
    start = payload.starts_at if payload.starts_at.tzinfo else payload.starts_at.replace(tzinfo=timezone.utc)
    booking = await bk.reserve(
        db, bot_id=bot.id, block=block, schedule=schedule, start=start.astimezone(timezone.utc),
        telegram_user_id=None, chat_id=None, status="blocked",
    )
    if booking is None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Это время уже занято")
    return {"id": str(booking.id)}


@router.post("/bots/{bot_id}/bookings/{booking_id}/cancel")
async def cancel_booking(
    booking_id: uuid.UUID,
    notify: bool = True,
    bot: Bot = Depends(get_owned_bot),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Отменить запись (или снять закрытие времени). Клиенту уйдёт сообщение."""
    from app.services import bot_registry

    booking = (
        await db.execute(select(Booking).where(Booking.id == booking_id, Booking.bot_id == bot.id))
    ).scalar_one_or_none()
    if booking is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Запись не найдена")
    was_client = booking.status in ("held", "confirmed") and booking.chat_id is not None
    label = bk.full_label(await bk.schedule_for(db, booking), booking.starts_at)
    if not await bk.cancel(db, booking):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Запись уже отменена")
    informed = False
    if notify and was_client:
        try:
            instance = await bot_registry.get_or_create(bot.id, db)
            if instance is not None:
                await instance.send_message(
                    booking.chat_id, f"Запись на {label} отменена. Если нужно, выберите другое время — /start."
                )
                informed = True
        except Exception:  # noqa: BLE001
            informed = False
    return {"cancelled": True, "informed": informed}
