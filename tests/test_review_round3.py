"""Раунд ревью 3: сверка сумм без «пустой суммы = ок», чужой счёт в вебхуке lava.top, Payme с не-ASCII."""

from __future__ import annotations

import base64
import json
import uuid

import httpx
import pytest

from app.models.payment import PaymentStatus
from app.services.payments import get_provider
from app.services.payments.base import ProviderError

PAYMENT_ID = uuid.UUID("11111111-2222-3333-4444-555555555555")
OWN = "c5a0cacc-3453-44b0-9532-aa492f1ba191"
OTHER = "d41db415-ad71-4f2a-8d8c-27eefee91e66"
LAVA = {"api_key": "k", "buyer_email": "shop@example.com"}


async def test_lava_reads_our_own_invoice_not_the_contract_named_in_an_unsigned_body(mock_http):
    """Тело вебхука lava.top не подписано. Чужой оплаченный счёт той же цены не должен
    «оплатить» наш заказ: читаем счёт, id которого сохранён при создании."""
    asked = []

    def handler(req: httpx.Request) -> httpx.Response:
        asked.append(req.url.path.rsplit("/", 1)[-1])
        paid = req.url.path.endswith(OTHER)
        return httpx.Response(
            200, json={"status": "COMPLETED" if paid else "NEW", "receipt": {"amount": 990.0, "currency": "RUB"}}
        )

    forged = json.dumps({"eventType": "payment.success", "contractId": OTHER}).encode()
    with mock_http(handler):
        result = await get_provider("lavatop").verify_webhook(
            headers={}, raw_body=forged, form={}, credentials=LAVA, amount_minor=99000, invoice_no=1,
            payment_id=PAYMENT_ID, provider_payment_id=OWN, currency="RUB",
        )
    assert result.status is PaymentStatus.pending
    assert asked == [OWN]


async def test_lava_refuses_a_contract_id_that_would_leave_the_api_path(mock_http):
    forged = json.dumps({"eventType": "payment.success", "contractId": "../../x"}).encode()
    with pytest.raises(ProviderError):
        await get_provider("lavatop").verify_webhook(
            headers={}, raw_body=forged, form={}, credentials=LAVA, amount_minor=99000, invoice_no=1,
            payment_id=PAYMENT_ID, provider_payment_id=None, currency="RUB",
        )


async def test_yookassa_without_an_amount_is_not_paid(mock_http):
    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"status": "succeeded", "paid": True, "metadata": {"order_id": str(PAYMENT_ID)}})

    with mock_http(handler), pytest.raises(ProviderError, match="сумма"):
        await get_provider("yookassa").check_status(
            credentials={"shop_id": "1", "secret_key": "k"}, amount_minor=99000, invoice_no=1,
            payment_id=PAYMENT_ID, provider_payment_id="pay-1", meta={}, currency="RUB",
        )


async def test_tbank_without_an_amount_is_not_paid(mock_http):
    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, json={"Success": True, "ErrorCode": "0", "Status": "CONFIRMED", "OrderId": PAYMENT_ID.hex}
        )

    with mock_http(handler), pytest.raises(ProviderError, match="сумма"):
        await get_provider("tbank").check_status(
            credentials={"terminal_key": "T", "password": "p"}, amount_minor=99000, invoice_no=1,
            payment_id=PAYMENT_ID, provider_payment_id="123", meta={}, currency="RUB",
        )


def test_payme_basic_auth_with_non_ascii_password_is_just_refused():
    from app.services.payments import payme

    header = "Basic " + base64.b64encode("Paycom:ключ".encode()).decode()
    assert payme._authorised({"authorization": header}, "key") is False
    good = "Basic " + base64.b64encode(b"Paycom:key").decode()
    assert payme._authorised({"authorization": good}, "key") is True


# ------------------------------------------------------------ опрос: лимиты Telegram


async def test_poll_question_and_options_are_cut_to_telegram_limits(db, owner, make_bot, as_bot):
    from app.models.bot_block import BlockType
    from app.services import bot_dispatcher

    bot, blocks = await make_bot(
        owner,
        [(BlockType.poll, {"question": "в" * 400, "options": [f"{i}" + "о" * 150 for i in range(12)]})],
    )
    as_bot.send_poll.return_value = type("Sent", (), {"poll": type("P", (), {"id": "p1"})()})()
    await bot_dispatcher._send_block(as_bot, 1, blocks[0], db)
    kwargs = as_bot.send_poll.call_args.kwargs
    assert len(kwargs["question"]) == 300
    assert len(kwargs["options"]) == 10 and all(len(o) <= 100 for o in kwargs["options"])


# ------------------------------------------------------------ запись


def _cfg(**extra):
    return {"days": [0, 1, 2, 3, 4, 5, 6], "start": "10:00", "end": "13:00", "slot_minutes": 60,
            "horizon_days": 7, "notice_hours": 0, "tz": "Asia/Almaty", **extra}


async def test_an_expired_hold_is_not_attached_to_an_unrelated_purchase(db, owner, make_bot):
    from datetime import datetime, timedelta, timezone

    from app.models.bot_block import BlockType
    from app.services import booking as bk

    bot, blocks = await make_bot(owner, [(BlockType.booking, _cfg())])
    schedule = bk.schedule_of(blocks[0].content)
    day = bk.local_day(schedule, datetime.now(timezone.utc)) + timedelta(days=2)
    start = bk.day_slots(schedule, day)[0]
    held = await bk.reserve(db, bot_id=bot.id, block=blocks[0], schedule=schedule, start=start,
                            telegram_user_id=42, chat_id=42)
    assert await bk.latest_held(db, bot.id, 42) is not None
    held.held_until = datetime.now(timezone.utc) - timedelta(minutes=1)
    await db.commit()
    assert await bk.latest_held(db, bot.id, 42) is None


def test_slots_skip_local_times_that_do_not_exist_at_the_dst_jump():
    from datetime import date

    from app.services import booking as bk

    schedule = bk.schedule_of({"days": [6], "start": "02:00", "end": "04:00", "slot_minutes": 30,
                               "tz": "America/New_York"})
    slots = bk.day_slots(schedule, date(2026, 3, 8))  # в 2:00 часы переводят на 3:00
    local = [s.astimezone(schedule.tz).strftime("%H:%M") for s in slots]
    assert local == ["03:00", "03:30"]
    normal = bk.day_slots(schedule, date(2026, 3, 15))
    assert [s.astimezone(schedule.tz).strftime("%H:%M") for s in normal] == ["02:00", "02:30", "03:00", "03:30"]


# ------------------------------------------------------------ оформление бота


def test_telegram_errors_in_the_profile_are_russian_and_never_carry_the_token():
    from app.routers.bot_profile import _telegram_error

    token = "123456:SECRET-token-value"
    exc = _telegram_error(Exception(f"Bad Request: wrong file at https://api.telegram.org/bot{token}/setMyProfilePhoto"), token)
    assert token not in exc.detail and "SECRET" not in exc.detail
    assert "фото" in exc.detail
    assert not exc.detail.isascii()


# ------------------------------------------------------------ быстрые кнопки и оплата


async def _text_to(as_bot, bot, db, text, chat=777):
    from app.services import background, bot_dispatcher

    before = len(as_bot.sent())
    await bot_dispatcher.process_update(
        as_bot, {"message": {"chat": {"id": chat}, "from": {"id": chat}, "text": text}}, bot.id, db
    )
    await background.wait_for_all()
    return as_bot.sent()[before:]


async def _reply_shop(db, owner, make_bot, target):
    """Меню с быстрыми кнопками; target — какой блок оплаченной цепочки открывает вторая кнопка."""
    from app.models.bot_block import BlockType

    bot, blocks = await make_bot(
        owner,
        [
            (BlockType.buttons, {"text": "Меню", "keyboard": "reply",
                                 "buttons": [{"label": "Купить", "action_type": "text"},
                                             {"label": "Забрать", "action_type": "text"}]}),
            (BlockType.payment, {"title": "Гайд", "price": "100", "currency": "RUB"}),
            (BlockType.description, {"text": "СЕКРЕТНЫЙ ТЕКСТ ГАЙДА"}),
            (BlockType.delivery, {"text": "ВЫДАЧА"}),
        ],
        provider="test", is_test=True,
    )
    blocks[0].next_block_id = None
    blocks[1].next_block_id = blocks[2].id
    blocks[2].next_block_id = blocks[3].id
    blocks[0].content = {**blocks[0].content, "buttons": [
        {"label": "Купить", "action_type": "text", "target_block_id": str(blocks[1].id)},
        {"label": "Забрать", "action_type": "text", "target_block_id": str(blocks[target].id)},
    ]}
    await db.commit()
    return bot, blocks


async def test_a_quick_button_cannot_open_paid_text_without_paying(db, owner, make_bot, as_bot):
    bot, _blocks = await _reply_shop(db, owner, make_bot, target=2)
    got = await _text_to(as_bot, bot, db, "Забрать")
    assert not any("СЕКРЕТНЫЙ" in t or "ВЫДАЧА" in t for t in got)


async def test_a_quick_button_cannot_open_delivery_without_paying(db, owner, make_bot, as_bot):
    bot, _blocks = await _reply_shop(db, owner, make_bot, target=3)
    got = await _text_to(as_bot, bot, db, "Забрать")
    assert not any("ВЫДАЧА" in t for t in got)


async def test_a_quick_button_to_the_payment_block_still_sells(db, owner, make_bot, as_bot):
    bot, _blocks = await _reply_shop(db, owner, make_bot, target=1)
    got = await _text_to(as_bot, bot, db, "Забрать")
    assert got, "кнопка на блок оплаты должна выставить счёт"
    assert not any("СЕКРЕТНЫЙ" in t for t in got)


# ------------------------------------------------------------ контакты: что считается номером


def test_phone_shape_is_digits_not_any_text_with_digits_in_it():
    from app.services.booking_flow import clean_name, normalize_phone

    assert normalize_phone("+7 (700) 123-45-67") == "+77001234567"
    assert normalize_phone("77001234567") == "+77001234567"
    assert normalize_phone("ул. Ленина 1234 дом 567") is None
    assert normalize_phone("не скажу") is None
    assert normalize_phone("12345") is None
    assert normalize_phone("+" + "9" * 20) is None
    assert clean_name("  Анна \n\t Иванова\u0007 ") == "Анна Иванова"


async def test_someone_elses_contact_card_is_not_taken_as_my_number(db, owner, make_bot, as_bot):
    from sqlalchemy import select

    from app.models.bot_block import BlockType
    from app.models.bot_subscriber import BotSubscriber
    from app.services import bot_dispatcher

    bot, _blocks = await make_bot(owner, [(BlockType.contact, {"ask_phone": True, "text": "Контакты"})])
    me = {"id": 909, "first_name": "Анна"}
    await bot_dispatcher.process_update(
        as_bot, {"message": {"chat": {"id": 909}, "from": me, "text": "/start"}}, bot.id, db
    )
    await bot_dispatcher.process_update(
        as_bot,
        {"message": {"chat": {"id": 909}, "from": me, "contact": {"phone_number": "79990001122", "user_id": 5}}},
        bot.id, db,
    )
    sub = (await db.execute(select(BotSubscriber).where(BotSubscriber.bot_id == bot.id))).scalar_one()
    await db.refresh(sub)
    assert not sub.phone
    await bot_dispatcher.process_update(
        as_bot,
        {"message": {"chat": {"id": 909}, "from": me, "contact": {"phone_number": "79990001122", "user_id": 909}}},
        bot.id, db,
    )
    await db.refresh(sub)
    assert sub.phone == "+79990001122"
