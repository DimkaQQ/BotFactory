"""Календарь записи и контакты: слоты, гонка за время, подтверждение после оплаты, мини-CRM."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app.models.booking import Booking
from app.models.bot_block import BlockType
from app.models.bot_subscriber import BotSubscriber
from app.models.payment import Payment
from app.services import background, bot_dispatcher
from app.services import booking as bk

CHAT = 5151


def _cfg(**extra):
    return {"days": [0, 1, 2, 3, 4, 5, 6], "start": "10:00", "end": "13:00", "slot_minutes": 60,
            "horizon_days": 7, "notice_hours": 0, "tz": "Asia/Almaty", **extra}


def test_day_slots_follow_hours_and_weekdays():
    schedule = bk.schedule_of({"days": [0], "start": "10:00", "end": "12:00", "slot_minutes": 30, "tz": "UTC"})
    monday = datetime(2026, 10, 12).date()
    assert len(bk.day_slots(schedule, monday)) == 4
    assert bk.day_slots(schedule, monday + timedelta(days=1)) == []  # вторник не рабочий


async def test_one_slot_cannot_be_booked_twice(db, owner, make_bot):
    bot, blocks = await make_bot(owner, [(BlockType.booking, _cfg())])
    bot_id = bot.id
    schedule = bk.schedule_of(blocks[0].content)
    day = bk.local_day(schedule, datetime.now(timezone.utc)) + timedelta(days=2)
    start = bk.day_slots(schedule, day)[0]
    first = await bk.reserve(db, bot_id=bot_id, block=blocks[0], schedule=schedule, start=start, telegram_user_id=1, chat_id=1)
    second = await bk.reserve(db, bot_id=bot_id, block=blocks[0], schedule=schedule, start=start, telegram_user_id=2, chat_id=2)
    await db.refresh(first)  # откат после гонки сбросил состояние
    assert first is not None and second is None
    assert start not in await bk.free_slots(db, bot_id, schedule, day)
    await bk.cancel(db, first)
    assert start in await bk.free_slots(db, bot_id, schedule, day)


async def test_expired_hold_frees_the_slot(db, owner, make_bot):
    bot, blocks = await make_bot(owner, [(BlockType.booking, _cfg())])
    schedule = bk.schedule_of(blocks[0].content)
    day = bk.local_day(schedule, datetime.now(timezone.utc)) + timedelta(days=2)
    start = bk.day_slots(schedule, day)[0]
    held = await bk.reserve(db, bot_id=bot.id, block=blocks[0], schedule=schedule, start=start, telegram_user_id=1, chat_id=1)
    held.held_until = datetime.now(timezone.utc) - timedelta(minutes=1)
    await db.commit()
    assert start in await bk.free_slots(db, bot.id, schedule, day)
    again = await bk.reserve(db, bot_id=bot.id, block=blocks[0], schedule=schedule, start=start, telegram_user_id=2, chat_id=2)
    assert again is not None


async def _press(as_bot, bot_id, db, data, user=CHAT):
    await bot_dispatcher.process_update(
        as_bot,
        {"callback_query": {"id": "c", "data": data, "from": {"id": user},
                            "message": {"chat": {"id": user}, "message_id": 9}}},
        bot_id, db,
    )
    await background.wait_for_all()


async def test_booking_without_payment_confirms_at_once(api, auth, owner, make_bot, db, as_bot):
    bot, blocks = await make_bot(owner, [(BlockType.booking, _cfg(text="Выберите день")),
                                         (BlockType.delivery, {"text": "Ждём вас!"})], provider="test", is_test=True)
    blocks[0].next_block_id = blocks[1].id
    await db.commit()
    bot_id, block_hex = bot.id, blocks[0].id.hex
    await bot_dispatcher.process_update(
        as_bot, {"message": {"chat": {"id": CHAT}, "from": {"id": CHAT, "first_name": "Анна"}, "text": "/start"}}, bot.id, db
    )
    # start-блока нет: идём в блок записи напрямую
    bot.start_block_id = blocks[0].id
    await db.commit()
    await bot_dispatcher.process_update(
        as_bot, {"message": {"chat": {"id": CHAT}, "from": {"id": CHAT, "first_name": "Анна"}, "text": "/start"}}, bot.id, db
    )
    await background.wait_for_all()

    schedule = bk.schedule_of(blocks[0].content)
    day = bk.local_day(schedule, datetime.now(timezone.utc)) + timedelta(days=1)
    await _press(as_bot, bot.id, db, f"bk:{blocks[0].id.hex}:d:{day:%Y%m%d}")
    local_start = bk.day_slots(schedule, day)[0].astimezone(schedule.tz)
    await _press(as_bot, bot.id, db, f"bk:{blocks[0].id.hex}:s:{local_start:%Y%m%d%H%M}")

    booking = (await db.execute(select(Booking).where(Booking.bot_id == bot.id))).scalar_one()
    assert booking.status == "confirmed"
    assert any("Ждём вас!" in t for t in as_bot.sent())

    # занятое время больше не предлагается и не бронируется вторым человеком
    await _press(as_bot, bot_id, db, f"bk:{block_hex}:s:{local_start:%Y%m%d%H%M}", user=777)
    confirmed = (await db.execute(select(Booking).where(Booking.bot_id == bot_id, Booking.status == "confirmed"))).scalars().all()
    assert len(confirmed) == 1


async def test_booking_before_payment_is_held_then_confirmed_when_paid(api, auth, owner, make_bot, db, as_bot):
    bot, blocks = await make_bot(
        owner,
        [(BlockType.booking, _cfg()), (BlockType.payment, {"title": "Предоплата", "price": "500", "currency": "RUB"}),
         (BlockType.delivery, {"text": "Спасибо!"})],
        provider="test", is_test=True,
    )
    blocks[0].next_block_id = blocks[1].id
    blocks[1].next_block_id = blocks[2].id
    bot.start_block_id = blocks[0].id
    await db.commit()
    await bot_dispatcher.process_update(
        as_bot, {"message": {"chat": {"id": CHAT}, "from": {"id": CHAT, "first_name": "Анна"}, "text": "/start"}}, bot.id, db
    )
    schedule = bk.schedule_of(blocks[0].content)
    day = bk.local_day(schedule, datetime.now(timezone.utc)) + timedelta(days=1)
    local_start = bk.day_slots(schedule, day)[1].astimezone(schedule.tz)
    await _press(as_bot, bot.id, db, f"bk:{blocks[0].id.hex}:s:{local_start:%Y%m%d%H%M}")

    booking = (await db.execute(select(Booking).where(Booking.bot_id == bot.id))).scalar_one()
    assert booking.status == "held"
    payment = (await db.execute(select(Payment).where(Payment.bot_id == bot.id))).scalar_one()
    assert payment.meta["booking_id"] == str(booking.id)
    assert payment.meta["choices"] and local_start.strftime("%H:%M") in payment.meta["choices"][0]

    await api.get(f"/webhook/pay/test/{payment.id}")
    await background.wait_for_all()
    await db.refresh(booking)
    assert booking.status == "confirmed"
    assert any("Вы записаны" in t for t in as_bot.sent())


async def test_contact_block_asks_only_what_is_missing_and_saves_it(db, owner, make_bot, as_bot):
    bot, blocks = await make_bot(
        owner,
        [(BlockType.contact, {"ask_name": True, "ask_phone": True, "text": "Оставьте контакты"}),
         (BlockType.delivery, {"text": "Готово, спасибо"})],
    )
    blocks[0].next_block_id = blocks[1].id
    bot.start_block_id = blocks[0].id
    await db.commit()
    user = {"id": CHAT, "first_name": "Анна", "username": "anna"}
    await bot_dispatcher.process_update(as_bot, {"message": {"chat": {"id": CHAT}, "from": user, "text": "/start"}}, bot.id, db)
    await background.wait_for_all()
    assert any("Как к вам обращаться" in t for t in as_bot.sent())

    await bot_dispatcher.process_update(as_bot, {"message": {"chat": {"id": CHAT}, "from": user, "text": "Анна Иванова"}}, bot.id, db)
    assert any("номер телефона" in t for t in as_bot.sent())
    # неверный номер переспрашивается
    await bot_dispatcher.process_update(as_bot, {"message": {"chat": {"id": CHAT}, "from": user, "text": "abc"}}, bot.id, db)
    assert any("разобрать номер" in t for t in as_bot.sent())
    await bot_dispatcher.process_update(
        as_bot, {"message": {"chat": {"id": CHAT}, "from": user, "contact": {"phone_number": "77001234567"}}}, bot.id, db
    )
    await background.wait_for_all()

    sub = (await db.execute(select(BotSubscriber).where(BotSubscriber.bot_id == bot.id))).scalar_one()
    assert sub.contact_name == "Анна Иванова" and sub.phone == "+77001234567"
    assert any("Готово, спасибо" in t for t in as_bot.sent())

    # повторный проход: уже всё известно — не спрашиваем
    as_bot.reset_mock()
    await bot_dispatcher.process_update(as_bot, {"message": {"chat": {"id": CHAT}, "from": user, "text": "/start"}}, bot.id, db)
    await background.wait_for_all()
    assert not any("Как к вам обращаться" in t for t in as_bot.sent())
    assert any("Готово, спасибо" in t for t in as_bot.sent())


async def test_telegram_only_contact_block_asks_nothing(db, owner, make_bot, as_bot):
    bot, blocks = await make_bot(
        owner, [(BlockType.contact, {"ask_name": False, "ask_phone": False}), (BlockType.delivery, {"text": "Дальше"})]
    )
    blocks[0].next_block_id = blocks[1].id
    bot.start_block_id = blocks[0].id
    await db.commit()
    await bot_dispatcher.process_update(
        as_bot, {"message": {"chat": {"id": CHAT}, "from": {"id": CHAT, "first_name": "Анна"}, "text": "/start"}}, bot.id, db
    )
    await background.wait_for_all()
    assert any("Дальше" in t for t in as_bot.sent())


async def test_crm_lists_customers_and_calendar_is_private(api, auth, owner, stranger, make_bot, db):
    bot, blocks = await make_bot(owner, [(BlockType.booking, _cfg())])
    bot_id = bot.id
    mine, theirs = auth(owner), auth(stranger)
    db.add(BotSubscriber(bot_id=bot.id, telegram_user_id=42, chat_id=42, first_name="Мария", username="maria"))
    await db.commit()

    listed = (await api.get("/api/crm/customers", headers=mine)).json()["customers"]
    assert listed and listed[0]["name"] == "Мария"
    found = (await api.get("/api/crm/customers?q=maria", headers=mine)).json()["customers"]
    assert len(found) == 1
    saved = await api.patch(f"/api/crm/customers/{bot_id}/42", headers=mine, json={"phone": "+7 700 000", "note": "VIP"})
    assert saved.status_code == 200
    card = (await api.get(f"/api/crm/customers/{bot_id}/42", headers=mine)).json()
    assert card["note"] == "VIP" and card["phone"] == "+7 700 000"

    # чужой владелец ничего не видит
    assert (await api.get(f"/api/crm/customers/{bot_id}/42", headers=theirs)).status_code == 404
    assert (await api.get(f"/api/bots/{bot_id}/calendar", headers=theirs)).status_code == 404
    assert (await api.get("/api/crm/customers", headers=theirs)).json()["customers"] == []

    calendar = (await api.get(f"/api/bots/{bot_id}/calendar?days=3", headers=mine)).json()
    assert len(calendar["days"]) == 3 and calendar["days"][0]["slots"]
    slot = next(s for d in calendar["days"] for s in d["slots"] if s["state"] == "free")
    blocked = await api.post(f"/api/bots/{bot_id}/calendar/block", headers=mine, json={"starts_at": slot["starts_at"]})
    assert blocked.status_code == 201
    again = await api.post(f"/api/bots/{bot_id}/calendar/block", headers=mine, json={"starts_at": slot["starts_at"]})
    assert again.status_code == 409
    cancelled = await api.post(f"/api/bots/{bot_id}/bookings/{blocked.json()['id']}/cancel", headers=mine)
    assert cancelled.json()["cancelled"] is True


async def test_one_person_cannot_hold_more_than_three_active_bookings(db, owner, make_bot):
    bot, blocks = await make_bot(owner, [(BlockType.booking, _cfg())])
    bot_id = bot.id
    schedule = bk.schedule_of(blocks[0].content)
    day = bk.local_day(schedule, datetime.now(timezone.utc)) + timedelta(days=2)
    slots = bk.day_slots(schedule, day)
    for start in slots[:3]:
        booking = await bk.reserve(db, bot_id=bot_id, block=blocks[0], schedule=schedule, start=start, telegram_user_id=9, chat_id=9)
        assert booking is not None and await bk.confirm(db, booking)
    try:
        await bk.reserve(db, bot_id=bot_id, block=blocks[0], schedule=schedule, start=slots[0] + timedelta(days=1), telegram_user_id=9, chat_id=9)
    except bk.BookingLimitError:
        pass
    else:
        raise AssertionError("четвёртая запись должна быть отклонена")
    # другой человек не затронут
    other = await bk.reserve(db, bot_id=bot_id, block=blocks[0], schedule=schedule, start=bk.day_slots(schedule, day + timedelta(days=1))[0], telegram_user_id=10, chat_id=10)
    assert other is not None


def test_each_weekday_has_its_own_hours_with_a_break_and_dates_can_override():
    schedule = bk.schedule_of(
        {
            "tz": "UTC",
            "slot_minutes": 60,
            "weekly": {"0": [["10:00", "12:00"], ["14:00", "16:00"]], "1": [["09:00", "10:00"]]},
            "exceptions": {"2026-10-19": [], "2026-10-20": [["18:00", "20:00"]]},
        }
    )
    monday, tuesday, wednesday = datetime(2026, 10, 12).date(), datetime(2026, 10, 13).date(), datetime(2026, 10, 14).date()
    assert [s.strftime("%H:%M") for s in bk.day_slots(schedule, monday)] == ["10:00", "11:00", "14:00", "15:00"]
    assert [s.strftime("%H:%M") for s in bk.day_slots(schedule, tuesday)] == ["09:00"]
    assert bk.day_slots(schedule, wednesday) == []  # день не задан — выходной
    assert bk.day_slots(schedule, datetime(2026, 10, 19).date()) == []  # понедельник закрыт датой
    assert [s.strftime("%H:%M") for s in bk.day_slots(schedule, datetime(2026, 10, 20).date())] == ["18:00", "19:00"]


def test_broken_intervals_are_ignored_and_default_timezone_is_not_almaty():
    schedule = bk.schedule_of({"weekly": {"0": [["12:00", "10:00"], ["x", "y"], ["10:00", "11:00"], ["10:30", "12:00"]]}})
    assert [(a.strftime("%H:%M"), b.strftime("%H:%M")) for a, b in schedule.weekly[0]] == [("10:00", "12:00")]
    assert schedule.tz_name == "UTC"


async def test_schedule_can_be_edited_from_the_calendar(api, auth, owner, stranger, make_bot, db):
    bot, _blocks = await make_bot(owner, [(BlockType.booking, _cfg())])
    bot_id = bot.id
    mine, theirs = auth(owner), auth(stranger)

    current = (await api.get(f"/api/bots/{bot_id}/booking-schedule", headers=mine)).json()
    assert current["configured"] and current["weekly"]["0"]

    saved = await api.put(
        f"/api/bots/{bot_id}/booking-schedule",
        headers=mine,
        json={"weekly": {"0": [["09:00", "12:00"], ["13:00", "17:00"]], "5": []}, "exceptions": {"2026-12-31": []},
              "tz": "Europe/Moscow", "slot_minutes": 30},
    )
    assert saved.status_code == 200
    body = saved.json()
    assert body["weekly"]["0"] == [["09:00", "12:00"], ["13:00", "17:00"]] and body["weekly"]["5"] == []
    assert body["exceptions"] == {"2026-12-31": []} and body["tz"] == "Europe/Moscow" and body["slot_minutes"] == 30

    bad_tz = await api.put(f"/api/bots/{bot_id}/booking-schedule", headers=mine, json={"tz": "Mars/Base"})
    assert bad_tz.status_code == 400
    assert (await api.get(f"/api/bots/{bot_id}/booking-schedule", headers=theirs)).status_code == 404
    assert (await api.put(f"/api/bots/{bot_id}/booking-schedule", headers=theirs, json={"slot_minutes": 15})).status_code == 404
