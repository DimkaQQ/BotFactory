"""Напоминания о записи и уборка старых данных."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app.models.booking import Booking
from app.models.bot_block import BlockType
from app.models.button_click import ButtonClick
from app.services import housekeeping


async def _booking(db, bot, block, *, starts_in_hours, created_hours_ago=48, **extra):
    now = datetime.now(timezone.utc)
    booking = Booking(
        bot_id=bot.id, block_id=block.id, telegram_user_id=7, chat_id=7,
        starts_at=now + timedelta(hours=starts_in_hours), ends_at=now + timedelta(hours=starts_in_hours + 1),
        status="confirmed", created_at=now - timedelta(hours=created_hours_ago), **extra,
    )
    db.add(booking)
    await db.commit()
    await db.refresh(booking)
    return booking


async def test_reminder_goes_once_per_stage(db, owner, make_bot, as_bot):
    bot, blocks = await make_bot(owner, [(BlockType.booking, {"days": [0, 1, 2, 3, 4, 5, 6]})])
    booking = await _booking(db, bot, blocks[0], starts_in_hours=20)
    booking_id = booking.id

    assert await housekeeping.send_reminders(db) == 1
    assert await housekeeping.send_reminders(db) == 0  # второй раз за сутки не пишем
    assert any("Напоминаем о записи" in t for t in as_bot.sent())

    row = (await db.execute(select(Booking).where(Booking.id == booking_id))).scalar_one()
    row.starts_at = datetime.now(timezone.utc) + timedelta(hours=1)
    await db.commit()
    assert await housekeeping.send_reminders(db) == 1  # за 2 часа — отдельное напоминание


async def test_reminders_can_be_switched_off_and_skip_last_minute_bookings(db, owner, make_bot, as_bot):
    bot, blocks = await make_bot(owner, [(BlockType.booking, {"reminders": False})])
    await _booking(db, bot, blocks[0], starts_in_hours=20)
    assert await housekeeping.send_reminders(db) == 0

    bot2, blocks2 = await make_bot(owner, [(BlockType.booking, {})])
    await _booking(db, bot2, blocks2[0], starts_in_hours=20, created_hours_ago=0)  # записались только что
    assert await housekeeping.send_reminders(db) == 0


async def test_cleanup_removes_old_clicks_but_keeps_recent(db, owner, make_bot):
    bot, _blocks = await make_bot(owner, [(BlockType.welcome, {"text": "Hi"})])
    now = datetime.now(timezone.utc)
    db.add(ButtonClick(bot_id=bot.id, label="старое", telegram_user_id=1, created_at=now - timedelta(days=200)))
    db.add(ButtonClick(bot_id=bot.id, label="свежее", telegram_user_id=1, created_at=now - timedelta(days=5)))
    await db.commit()
    counts = await housekeeping.cleanup(db)
    assert counts["button_clicks"] == 1
    labels = [c.label for c in (await db.execute(select(ButtonClick))).scalars()]
    assert labels == ["свежее"]


def test_cors_defaults_to_own_origin_only():
    from app.config import Settings

    own = Settings(_env_file=None, public_base_url="https://bot.example.com/", cors_origins="")
    assert own.cors_origin_list == ["https://bot.example.com"]
    assert Settings(_env_file=None, cors_origins="*").cors_origin_list == ["*"]
    assert Settings(_env_file=None, cors_origins="https://a.example, https://b.example").cors_origin_list == [
        "https://a.example", "https://b.example",
    ]
