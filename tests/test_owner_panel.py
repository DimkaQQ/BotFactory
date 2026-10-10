"""Кабинет владельца в мета-боте: цифры, пауза, настройки, меню."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from _tg_fakes import FakeSession, button_update, text_update
from aiogram import Bot
from aiogram.methods import EditMessageText, SendMessage
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.bot import Bot as BotModel
from app.models.bot import BotStatus
from app.models.bot_block import BlockType
from app.models.bot_subscriber import BotSubscriber
from app.models.client import Client
from app.models.payment import Payment, PaymentKind, PaymentStatus
from app.services import owner_panel

BUYER = 990_800_001
CHAT = 990_800_002


async def _sell(db: AsyncSession, bot: BotModel, *, amount=99000, currency="RUB", paid_at=None, status=PaymentStatus.paid):
    db.add(
        Payment(
            id=uuid.uuid4(), kind=PaymentKind.order, status=status, provider="test",
            amount_minor=amount, currency=currency, description="товар", bot_id=bot.id,
            telegram_user_id=BUYER, chat_id=CHAT, meta={}, paid_at=paid_at or datetime.now(timezone.utc),
        )
    )


# ------------------------------------------------------------ цифры


@pytest.mark.asyncio
async def test_a_card_counts_clients_orders_and_revenue_by_currency(db: AsyncSession, owner: Client, make_bot):
    bot, _ = await make_bot(owner, [(BlockType.welcome, {"text": "привет"})])
    now = datetime.now(timezone.utc)
    db.add_all([
        BotSubscriber(id=uuid.uuid4(), bot_id=bot.id, telegram_user_id=BUYER, chat_id=CHAT, first_seen_at=now),
        BotSubscriber(id=uuid.uuid4(), bot_id=bot.id, telegram_user_id=BUYER + 1, chat_id=CHAT + 1,
                      first_seen_at=now - timedelta(days=30), blocked_at=now),
    ])
    await _sell(db, bot, amount=99000, currency="RUB")
    await _sell(db, bot, amount=50000, currency="RUB", paid_at=now - timedelta(days=20))
    await _sell(db, bot, amount=250, currency="XTR")
    await _sell(db, bot, amount=777, currency="RUB", status=PaymentStatus.pending)  # не оплачен — не считается
    await db.commit()

    cards = await owner_panel.list_cards(db, owner)
    assert len(cards) == 1
    card = cards[0]
    assert (card.clients, card.new_this_week, card.blocked) == (2, 1, 1)
    assert (card.orders, card.orders_this_week) == (3, 2)
    assert dict(card.revenue) == {"RUB": 149000, "XTR": 250}, "валюты нельзя складывать, а неоплаченное — считать"
    total = owner_panel.totals(cards)
    assert total.bots == 1 and total.live == 1 and total.clients == 2 and total.orders == 3


@pytest.mark.asyncio
async def test_an_owner_sees_only_their_own_bots(db: AsyncSession, owner: Client, stranger: Client, make_bot):
    mine, _ = await make_bot(owner, [(BlockType.welcome, {"text": "я"})])
    theirs, _ = await make_bot(stranger, [(BlockType.welcome, {"text": "они"})])
    assert [c.bot.id for c in await owner_panel.list_cards(db, owner)] == [mine.id]
    assert await owner_panel.get_card(db, owner, theirs.id) is None, "чужой бот открылся по id"


@pytest.mark.asyncio
async def test_a_card_says_in_one_word_what_state_the_bot_is_in(db: AsyncSession, owner: Client, make_bot):
    live, _ = await make_bot(owner, [(BlockType.welcome, {"text": "а"})])
    draft, _ = await make_bot(owner, [(BlockType.welcome, {"text": "б"})], status=BotStatus.draft)
    off, _ = await make_bot(owner, [(BlockType.welcome, {"text": "в"})], status=BotStatus.disabled)
    paused, _ = await make_bot(owner, [(BlockType.welcome, {"text": "г"})])
    paused.paused = True
    await db.commit()
    states = {c.bot.id: c.state for c in await owner_panel.list_cards(db, owner)}
    assert states == {live.id: "live", draft.id: "draft", off.id: "disabled", paused.id: "paused"}


# ------------------------------------------------------------ пауза


@pytest.mark.asyncio
async def test_pausing_and_resuming_follow_the_rules(db: AsyncSession, owner: Client, stranger: Client, make_bot):
    bot, _ = await make_bot(owner, [(BlockType.welcome, {"text": "а"})])
    draft, _ = await make_bot(owner, [(BlockType.welcome, {"text": "б"})], status=BotStatus.draft)
    off, _ = await make_bot(owner, [(BlockType.welcome, {"text": "в"})], status=BotStatus.disabled)

    await owner_panel.set_paused(db, owner, bot.id, True)
    await db.refresh(bot)
    assert bot.paused is True
    await owner_panel.set_paused(db, owner, bot.id, False)
    await db.refresh(bot)
    assert bot.paused is False

    for blocked in (draft.id, off.id):
        with pytest.raises(owner_panel.PauseError):
            await owner_panel.set_paused(db, owner, blocked, True)
    with pytest.raises(owner_panel.PauseError):  # чужой бот
        await owner_panel.set_paused(db, stranger, bot.id, True)


@pytest.mark.asyncio
async def test_a_paused_bot_starts_no_new_conversations_but_still_honours_stop(
    db: AsyncSession, owner: Client, make_bot, telegram
):
    from app.services import bot_dispatcher

    bot, _ = await make_bot(owner, [(BlockType.welcome, {"text": "привет, это магазин"})])
    bot.paused = True
    await db.commit()

    message = {"chat": {"id": CHAT}, "from": {"id": BUYER}, "text": "/start"}
    await bot_dispatcher.process_update(telegram, {"message": message}, bot.id, db)
    said = telegram.sent()
    assert said and "на паузе" in said[-1]
    assert not any("магазин" in line for line in said), "на паузе бот начал диалог"

    telegram.reset_mock()
    await bot_dispatcher.process_update(telegram, {"message": {**message, "text": "/stop"}}, bot.id, db)
    assert "рассылку больше не пришлю" in telegram.sent()[-1], "пауза сломала /stop"

    telegram.reset_mock()
    await bot_dispatcher.process_update(telegram, {"message": {**message, "text": "/paysupport"}}, bot.id, db)
    assert "возврат" in telegram.sent()[-1], "пауза сломала /paysupport"


@pytest.mark.asyncio
async def test_resuming_brings_the_dialogue_back(db: AsyncSession, owner: Client, make_bot, telegram):
    from app.services import bot_dispatcher

    bot, _ = await make_bot(owner, [(BlockType.welcome, {"text": "привет, это магазин"})])
    await owner_panel.set_paused(db, owner, bot.id, True)
    await owner_panel.set_paused(db, owner, bot.id, False)
    message = {"chat": {"id": CHAT}, "from": {"id": BUYER}, "text": "/start"}
    await bot_dispatcher.process_update(telegram, {"message": message}, bot.id, db)
    assert any("магазин" in line for line in telegram.sent())


@pytest.mark.asyncio
async def test_a_broadcast_is_refused_while_the_bot_is_paused(api, auth, db: AsyncSession, owner: Client, make_bot):
    bot, blocks = await make_bot(owner, [(BlockType.welcome, {"text": "акция"})])
    bot.paused = True
    await db.commit()
    response = await api.post(
        f"/api/bots/{bot.id}/broadcast", headers=auth(owner), json={"block_id": str(blocks[0].id), "audience": "all"}
    )
    assert response.status_code == 400 and "паузе" in response.json()["detail"]


@pytest.mark.asyncio
async def test_the_constructor_api_shows_and_sets_the_pause(api, auth, db: AsyncSession, owner: Client, make_bot):
    bot, _ = await make_bot(owner, [(BlockType.welcome, {"text": "а"})])
    ok = await api.patch(f"/api/bots/{bot.id}", headers=auth(owner), json={"paused": True})
    assert ok.status_code == 200 and ok.json()["paused"] is True
    draft, _ = await make_bot(owner, [(BlockType.welcome, {"text": "б"})], status=BotStatus.draft)
    bad = await api.patch(f"/api/bots/{draft.id}", headers=auth(owner), json={"paused": True})
    assert bad.status_code == 400


# --------------------------------------------------------- настройки


@pytest.mark.asyncio
async def test_turning_off_sale_notifications_silences_the_owner_message(
    db: AsyncSession, owner: Client, make_bot, as_bot
):
    from app.services import payment_service

    bot, blocks = await make_bot(owner, [(BlockType.welcome, {"text": "а"})])
    payment = Payment(
        id=uuid.uuid4(), kind=PaymentKind.order, status=PaymentStatus.paid, provider="test",
        amount_minor=99000, currency="RUB", description="товар", bot_id=bot.id, block_id=blocks[0].id,
        telegram_user_id=BUYER, chat_id=CHAT, meta={}, paid_at=datetime.now(timezone.utc),
    )
    db.add(payment)
    await db.commit()

    await payment_service._notify_owner_of_sale(db, payment)
    to_owner = [c for c in as_bot.method_calls if c[0] == "send_message" and c.args[0] == owner.telegram_user_id]
    assert to_owner, "по умолчанию владелец должен узнавать о продаже"

    as_bot.reset_mock()
    await owner_panel.set_notify_sales(db, owner, False)
    await payment_service._notify_owner_of_sale(db, payment)
    assert not [c for c in as_bot.method_calls if c[0] == "send_message"], "уведомление пришло при выключенных"


@pytest.mark.asyncio
async def test_signing_out_everywhere_sets_the_revocation_mark(db: AsyncSession, owner: Client):
    assert owner.sessions_valid_from is None
    await owner_panel.sign_out_everywhere(db, owner)
    await db.refresh(owner)
    assert owner.sessions_valid_from is not None


# ----------------------------------------------- меню: сквозной прогон


def _texts(session: FakeSession, kind):
    return [getattr(c, "text", "") for c in session.of(kind)]


def _buttons(call) -> list[tuple[str, str]]:
    """(подпись, callback_data или 'web_app'/'url') всех кнопок сообщения."""
    out = []
    for row in call.reply_markup.inline_keyboard:
        for b in row:
            out.append((b.text, b.callback_data or ("web_app" if b.web_app else "url")))
    return out


async def _feed(dp, bot, update):
    await dp.feed_update(bot, update)


@pytest.mark.asyncio
async def test_the_start_menu_shows_bots_numbers_settings_and_support(db: AsyncSession, owner: Client, make_bot, meta_dp):
    bot, _ = await make_bot(owner, [(BlockType.welcome, {"text": "а"})])
    await _sell(db, bot, amount=99000)
    await db.commit()

    session = FakeSession()
    tg = Bot("123456:AAAA-testtoken", session=session)
    dp = meta_dp
    await _feed(dp, tg, text_update(1, owner.telegram_user_id, 1, "/start"))

    sent = session.of(SendMessage)
    assert sent, "/start остался без ответа"
    text = sent[0].text
    assert "Ботов: <b>1</b>" in text and "Оплаченных заказов: <b>1</b>" in text and "990" in text
    labels = dict(_buttons(sent[0]))
    assert labels["🛠 Открыть конструктор"] == "web_app"
    assert labels["🤖 Мои боты"] == "m:bots"
    assert labels["⚙️ Настройки"] == "s:main" and labels["💬 Поддержка"] == "sup:start"
    await tg.session.close()


@pytest.mark.asyncio
async def test_a_person_without_bots_still_gets_the_constructor_and_support(db: AsyncSession, meta_dp):
    session = FakeSession()
    tg = Bot("123456:AAAA-testtoken", session=session)
    await _feed(meta_dp, tg, text_update(1, 990_800_777, 1, "/start"))
    sent = session.of(SendMessage)[0]
    labels = dict(_buttons(sent))
    assert "🛠 Открыть конструктор" in labels and "💬 Поддержка" in labels and "🤖 Мои боты" not in labels
    await tg.session.close()


@pytest.mark.asyncio
async def test_the_bot_card_pauses_and_resumes_from_the_buttons(db: AsyncSession, owner: Client, make_bot, meta_dp):
    bot, _ = await make_bot(owner, [(BlockType.welcome, {"text": "а"})])
    session = FakeSession()
    tg = Bot("123456:AAAA-testtoken", session=session)
    dp = meta_dp
    uid = owner.telegram_user_id

    await _feed(dp, tg, button_update(1, uid, "m:bots"))
    await _feed(dp, tg, button_update(2, uid, f"b:{bot.id}"))
    card = session.of(EditMessageText)[-1]
    assert "Клиентов" in card.text and "работает" in card.text
    assert any(data == f"bp:{bot.id}" for _, data in _buttons(card))

    await _feed(dp, tg, button_update(3, uid, f"bp:{bot.id}"))
    await db.refresh(bot)
    assert bot.paused is True
    card = session.of(EditMessageText)[-1]
    assert "на паузе" in card.text and any(data == f"br:{bot.id}" for _, data in _buttons(card))

    await _feed(dp, tg, button_update(4, uid, f"br:{bot.id}"))
    await db.refresh(bot)
    assert bot.paused is False
    await tg.session.close()


@pytest.mark.asyncio
async def test_a_stranger_cannot_pause_or_open_someone_elses_bot(db: AsyncSession, owner: Client, make_bot, meta_dp):
    bot, _ = await make_bot(owner, [(BlockType.welcome, {"text": "а"})])
    session = FakeSession()
    tg = Bot("123456:AAAA-testtoken", session=session)
    dp = meta_dp
    intruder = 990_800_888

    await _feed(dp, tg, button_update(1, intruder, f"bp:{bot.id}"))
    await db.refresh(bot)
    assert bot.paused is False, "чужой человек поставил бота на паузу"
    assert not session.of(EditMessageText), "чужая карточка открылась"
    await tg.session.close()


@pytest.mark.asyncio
async def test_settings_toggle_notifications_and_confirm_the_logout(db: AsyncSession, owner: Client, meta_dp):
    session = FakeSession()
    tg = Bot("123456:AAAA-testtoken", session=session)
    dp = meta_dp
    uid = owner.telegram_user_id

    await _feed(dp, tg, button_update(1, uid, "s:notify"))
    await db.refresh(owner)
    assert owner.notify_sales is False
    await _feed(dp, tg, button_update(2, uid, "s:notify"))
    await db.refresh(owner)
    assert owner.notify_sales is True

    # выход сначала спрашивает, и без «Да» ничего не закрывает
    await _feed(dp, tg, button_update(3, uid, "s:logout"))
    assert "Выйти на всех устройствах" in session.of(EditMessageText)[-1].text
    await db.refresh(owner)
    assert owner.sessions_valid_from is None
    await _feed(dp, tg, button_update(4, uid, "s:logout:yes"))
    await db.refresh(owner)
    assert owner.sessions_valid_from is not None
    await tg.session.close()


@pytest.mark.asyncio
async def test_support_button_opens_a_dialog_and_the_next_message_reaches_the_owner(
    db: AsyncSession, owner: Client, monkeypatch, meta_dp
):
    from app.config import get_settings
    from meta_bot.handlers import support

    admin = 990_800_900
    monkeypatch.setenv("SUPPORT_CHAT_ID", str(admin))
    get_settings.cache_clear()
    support._dialogs.clear()
    session = FakeSession()
    tg = Bot("123456:AAAA-testtoken", session=session)
    dp = meta_dp
    uid = owner.telegram_user_id
    try:
        # без кнопки сообщение не уходит владельцу, а человек получает подсказку
        await _feed(dp, tg, text_update(1, uid, 1, "привет, есть вопрос"))
        assert "Поддержка" in session.of(SendMessage)[-1].text
        assert not [c for c in session.calls if getattr(c, "chat_id", None) == admin]

        await _feed(dp, tg, button_update(2, uid, "sup:start"))
        assert "Пишите сюда своё сообщение" in session.of(SendMessage)[-1].text

        await _feed(dp, tg, text_update(3, uid, 3, "не открывается конструктор"))
        to_admin = [c for c in session.calls if getattr(c, "chat_id", None) == admin]
        assert to_admin, "обращение не дошло до владельца"
    finally:
        async with __import__("app.database", fromlist=["AsyncSessionLocal"]).AsyncSessionLocal() as s:
            from sqlalchemy import delete

            from app.models.support_relay import SupportRelay

            await s.execute(delete(SupportRelay).where(SupportRelay.user_chat_id == uid))
            await s.commit()
        support._dialogs.clear()
        get_settings.cache_clear()
        await tg.session.close()


@pytest.mark.asyncio
async def test_terms_are_offered_once_and_accepting_is_recorded(db: AsyncSession, owner: Client, meta_dp, monkeypatch):
    from app.config import get_settings
    from app.routers.legal import REVISION

    monkeypatch.setattr(type(get_settings()), "legal_ready", property(lambda self: True))
    owner.terms_version = None
    await db.commit()

    session = FakeSession()
    tg = Bot("123456:AAAA-testtoken", session=session)
    uid = owner.telegram_user_id

    await _feed(meta_dp, tg, text_update(1, uid, 1, "/start"))
    sent = session.of(SendMessage)[0]
    assert "принимаешь" in sent.text
    assert "✅ Принимаю условия" in dict(_buttons(sent))

    await _feed(meta_dp, tg, button_update(2, uid, "m:terms"))
    await db.refresh(owner)
    assert owner.terms_version == REVISION and owner.terms_accepted_at is not None
    assert "принимаешь" not in session.of(EditMessageText)[-1].text
    await tg.session.close()
