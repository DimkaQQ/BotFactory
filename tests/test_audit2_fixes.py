"""Находки второй независимой проверки и то, что их закрывает.

Общая тема этого захода — не «сломалось», а «тихо не работает»: продавец не
получает денег за второй заказ, владелец не получает предупреждения, файл не
доходит до покупателя, ответы опроса записываются в никуда. Всё это система
раньше считала нормальной работой.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models.bot import Bot as BotModel
from app.models.bot import BotStatus
from app.models.bot_block import BlockType
from app.models.client import Client
from app.models.payment import Payment, PaymentKind, PaymentStatus
from app.services import bot_dispatcher, payment_service, platform_billing

CHAT_ID = 4242
USER_ID = 900070001


# --------------------------------------------- Б1: повторная продажа


@pytest.mark.asyncio
async def test_a_repeatable_product_can_be_bought_again(
    db: AsyncSession, owner: Client, make_bot, telegram, monkeypatch
):
    """Коуч продаёт вторую консультацию тому же клиенту. Раньше бот отвечал
    «уже оплачено» и выдавал сессию бесплатно."""
    bot, blocks = await make_bot(
        owner,
        [(BlockType.payment, {"title": "Личная сессия", "price": "3000", "repeatable": True}),
         (BlockType.delivery, {"text": "ссылка на созвон"})],
        provider="test",
        credentials={},
    )
    paid = Payment(
        id=uuid.uuid4(), kind=PaymentKind.order, status=PaymentStatus.paid,
        provider="test", amount_minor=300000, currency="RUB", description="Личная сессия",
        bot_id=bot.id, block_id=blocks[0].id, telegram_user_id=USER_ID, chat_id=CHAT_ID,
        meta={}, paid_at=datetime.now(timezone.utc),
    )
    db.add(paid)
    await db.commit()

    await bot_dispatcher._send_payment_block(telegram, CHAT_ID, blocks[0], bot.id, db, USER_ID)

    said = " ".join(str(c) for c in telegram.send_message.call_args_list)
    assert "уже есть доступ" not in said, "бот отказался продавать вторую сессию"
    orders = (
        await db.execute(
            select(Payment).where(Payment.block_id == blocks[0].id, Payment.telegram_user_id == USER_ID)
        )
    ).scalars().all()
    assert len(orders) == 2, "второй счёт не создан — продавец не получит денег"


@pytest.mark.asyncio
async def test_a_one_off_product_is_still_not_sold_twice(
    db: AsyncSession, owner: Client, make_bot, telegram
):
    """Обратная сторона: гайд по-прежнему продаётся один раз, а вернувшийся
    покупатель получает купленное, не платя снова."""
    bot, blocks = await make_bot(
        owner,
        [(BlockType.payment, {"title": "Том 1", "price": "990"}),
         (BlockType.delivery, {"text": "вот файл"})],
        provider="test",
        credentials={},
    )
    paid = Payment(
        id=uuid.uuid4(), kind=PaymentKind.order, status=PaymentStatus.paid,
        provider="test", amount_minor=99000, currency="RUB", description="Том 1",
        bot_id=bot.id, block_id=blocks[0].id, telegram_user_id=USER_ID, chat_id=CHAT_ID,
        meta={}, paid_at=datetime.now(timezone.utc),
    )
    db.add(paid)
    await db.commit()

    kept_going = await bot_dispatcher._send_payment_block(
        telegram, CHAT_ID, blocks[0], bot.id, db, USER_ID
    )

    said = " ".join(str(c) for c in telegram.send_message.call_args_list)
    assert "уже есть доступ" in said
    # False = цепочка продолжается в выдачу: купленное отдаём снова.
    assert kept_going is False
    orders = (
        await db.execute(select(Payment).where(Payment.block_id == blocks[0].id))
    ).scalars().all()
    assert len(orders) == 1, "создан второй счёт за то, что уже куплено"


# ------------------------------------------------ Б2: длинная подпись к файлу


def test_a_long_caption_rides_with_the_file_and_the_rest_follows():
    """Telegram режет подпись на 1024 и отклоняет вызов целиком — а файл с
    инструкцией это самая ходовая «Выдача»."""
    text = "\n\n".join(f"Шаг {i}. " + "подробности " * 30 for i in range(12))
    assert len(text) > 1024

    caption, rest = bot_dispatcher._caption_and_rest(text)

    assert caption is not None and len(caption) <= 1024
    assert rest and all(len(piece) <= 4096 for piece in rest)
    # Ничего не потеряно.
    joined = (caption + " " + " ".join(rest)).split()
    assert joined == text.split()
    # Короткое остаётся одной подписью, пустое — ничем.
    assert bot_dispatcher._caption_and_rest("привет") == ("привет", [])
    assert bot_dispatcher._caption_and_rest("   ") == (None, [])


# ------------------------------------- Б3: предупреждение владельцу теряется


@pytest.mark.asyncio
async def test_an_unreachable_owner_is_told_on_a_later_sweep(
    db: AsyncSession, owner: Client, make_bot, monkeypatch
):
    """Бот не может написать первым тому, кто ему не писал, — а это каждый,
    кто вошёл через веб. Раньше стадия занималась до отправки, и напоминание
    пропадало навсегда."""
    monkeypatch.setattr(
        get_settings(), "platform_payment_methods",
        json.dumps([{"provider": "stripe", "price_minor": 9900, "renewal_price_minor": 990,
                     "currency": "USD", "credentials": {}}]),
        raising=False,
    )
    bot, _ = await make_bot(owner, [(BlockType.welcome, {"text": "привет"})], status=BotStatus.active)
    bot.paid_until = datetime.now(timezone.utc) + timedelta(days=2)
    await db.commit()

    monkeypatch.setattr(
        platform_billing, "_tell_owner",
        AsyncMock(side_effect=Exception("Forbidden: bot can't initiate conversation with a user")),
    )
    await platform_billing.sweep(db)
    await db.refresh(bot)
    assert bot.billing_notice_stage == platform_billing.NOTICE_NONE, "стадия занята, а сообщение не ушло"

    # Владелец открыл бота — следующий проход обязан достучаться.
    said = []

    async def works(db_, bot_, text):
        said.append(text)

    monkeypatch.setattr(platform_billing, "_tell_owner", works)
    await platform_billing.sweep(db)

    assert len(said) == 1 and "заканчивается" in said[0]


@pytest.mark.asyncio
async def test_an_unreachable_owner_does_not_keep_a_free_bot_forever(
    db: AsyncSession, owner: Client, make_bot, monkeypatch
):
    """Но недостижимость не должна отменять снятие с эфира: неоплаченный
    магазин выключается, даже если сказать об этом некому."""
    monkeypatch.setattr(
        get_settings(), "platform_payment_methods",
        json.dumps([{"provider": "stripe", "price_minor": 9900, "renewal_price_minor": 990,
                     "currency": "USD", "credentials": {}}]),
        raising=False,
    )
    bot, _ = await make_bot(owner, [(BlockType.welcome, {"text": "привет"})], status=BotStatus.active)
    bot.paid_until = datetime.now(timezone.utc) - timedelta(days=30)
    await db.commit()
    monkeypatch.setattr(platform_billing, "_tell_owner", AsyncMock(side_effect=Exception("Forbidden")))
    monkeypatch.setattr("app.services.bot_registry.remove", AsyncMock())

    await platform_billing.sweep(db)
    await db.refresh(bot)

    assert bot.status == BotStatus.disabled


# ------------------------------------------------- С1: двойная выдача


@pytest.mark.asyncio
async def test_two_sweeps_cannot_hand_over_the_same_order(
    db: AsyncSession, owner: Client, make_bot
):
    """Подметальщик выдачи — единственное место, отдающее товар, и claim'а в
    нём не было. Для блока с доступом в группу двойная выдача означает вторую
    одноразовую ссылку-приглашение."""
    bot, blocks = await make_bot(
        owner, [(BlockType.delivery, {"text": "вот гайд"})], provider="test"
    )
    payment = Payment(
        id=uuid.uuid4(), kind=PaymentKind.order, status=PaymentStatus.paid,
        provider="test", amount_minor=99000, currency="RUB", description="Гайд",
        bot_id=bot.id, block_id=blocks[0].id, telegram_user_id=USER_ID, chat_id=CHAT_ID,
        meta={"deliver_from": str(blocks[0].id)}, paid_at=datetime.now(timezone.utc),
    )
    db.add(payment)
    await db.commit()

    # Две сессии, каждая со своим экземпляром строки: ровно то, что делают
    # два прохода подметальщика. Последовательные вызовы в одной сессии —
    # это законный повтор после неудачи, и он остаётся разрешённым.
    from app.database import AsyncSessionLocal

    async with AsyncSessionLocal() as one, AsyncSessionLocal() as two:
        mine = (await one.execute(select(Payment).where(Payment.id == payment.id))).scalar_one()
        theirs = (await two.execute(select(Payment).where(Payment.id == payment.id))).scalar_one()

        first = await payment_service._claim_delivery(one, mine)
        second = await payment_service._claim_delivery(two, theirs)

    assert first == 1
    assert second is None, "вторая выдача того же заказа не остановлена"


# ------------------------------------------ Б4: квота на загруженные файлы


@pytest.mark.asyncio
async def test_uploads_are_capped_per_account(api, auth, owner: Client, make_bot, monkeypatch):
    monkeypatch.setattr(get_settings(), "media_quota_mb_per_client", 1, raising=False)
    bot, _ = await make_bot(owner, [])
    png = b"\x89PNG\r\n\x1a\n" + b"\x00" * (600 * 1024)

    codes = []
    for _ in range(3):
        response = await api.post(
            f"/api/bots/{bot.id}/media/upload",
            headers=auth(owner),
            files={"file": ("x.png", png, "image/png")},
        )
        codes.append(response.status_code)

    assert codes[0] == 201
    assert 413 in codes, "квота не сработала — один аккаунт может залить диск"


# ------------------------------- касса платформы не может быть «тестовой»


def test_the_platform_refuses_its_own_test_till(monkeypatch):
    """У кассы клиента это запрещено давно («отдаёт товар без денег»), а нашу
    не защищало ничто, при том что `test` стоял дефолтом."""
    settings = get_settings()
    monkeypatch.setattr(
        settings, "platform_payment_methods",
        json.dumps([{"provider": "test", "price_minor": 9900, "currency": "USD", "credentials": {}}]),
        raising=False,
    )
    monkeypatch.setattr(settings, "platform_allow_test_till", False, raising=False)

    # Отказ в сторону «публикация бесплатна», а не «оплачено без денег».
    assert payment_service.platform_methods() == []

    monkeypatch.setattr(settings, "platform_allow_test_till", True, raising=False)
    assert [m.provider for m in payment_service.platform_methods()] == ["test"]


# ------------------------------------------- цикл через «Паузу» не вечен


@pytest.mark.asyncio
async def test_a_pause_loop_is_eventually_refused(db: AsyncSession, owner: Client, make_bot):
    """`_MAX_CHAIN_STEPS` и `visited` живут внутри одного прохода, а пауза
    начинает новый — поэтому цикл через «Паузу» крутился бесконечно."""
    from app.services import scheduler

    bot, blocks = await make_bot(owner, [(BlockType.description, {"text": "по кругу"})])

    queued = 0
    for _ in range(scheduler._MAX_PAUSED_HOPS + 5):
        step = await scheduler.schedule(
            db, bot_id=bot.id, block_id=blocks[0].id, chat_id=CHAT_ID,
            telegram_user_id=USER_ID, delay_seconds=3600, reason="delay",
        )
        if step is not None:
            queued += 1

    assert queued == scheduler._MAX_PAUSED_HOPS


# ---------------------------------- опрос помнит каждую отправку, не последнюю


@pytest.mark.asyncio
async def test_every_subscriber_s_poll_answer_is_recorded(
    db: AsyncSession, owner: Client, make_bot, telegram
):
    """Telegram выдаёт новый poll_id на каждый чат. Хранилось одно поле на
    блок, поэтому засчитывался только последний подписчик."""
    from app.models.poll_answer import PollAnswer

    bot, blocks = await make_bot(
        owner, [(BlockType.poll, {"question": "Что дальше?", "options": ["Ноги", "Спина"]})]
    )
    poll_block = blocks[0]

    for poll_id, chat in (("poll-AAA", 111), ("poll-BBB", 222)):
        telegram.send_poll.return_value = type(
            "Sent", (), {"poll": type("P", (), {"id": poll_id})(), "chat": type("C", (), {"id": chat})()}
        )()
        await bot_dispatcher._send_block(telegram, chat, poll_block, db)

    for poll_id, user in (("poll-AAA", 111), ("poll-BBB", 222)):
        await bot_dispatcher._handle_poll_answer(
            {"poll_id": poll_id, "user": {"id": user}, "option_ids": [1]}, bot.id, db
        )

    saved = (
        await db.execute(select(PollAnswer).where(PollAnswer.block_id == poll_block.id))
    ).scalars().all()
    assert len(saved) == 2, "ответ первого подписчика выброшен"


@pytest.mark.asyncio
async def test_poll_results_are_readable(api, auth, owner: Client, make_bot, db):
    """Ответы писались в таблицу, которую никто не читал: ни эндпоинта, ни
    экрана."""
    from app.models.poll_answer import PollAnswer

    bot, blocks = await make_bot(
        owner, [(BlockType.poll, {"question": "Что дальше?", "options": ["Ноги", "Спина"]})]
    )
    db.add(PollAnswer(
        id=uuid.uuid4(), bot_id=bot.id, block_id=blocks[0].id,
        telegram_user_id=USER_ID, telegram_poll_id="p1", option_ids=[1],
    ))
    await db.commit()

    report = (await api.get(f"/api/bots/{bot.id}/polls", headers=auth(owner))).json()

    assert report["polls"][0]["question"] == "Что дальше?"
    assert report["polls"][0]["answered"] == 1
    assert [o["votes"] for o in report["polls"][0]["options"]] == [0, 1]


# ------------------------------- перевыпуск токена снимает старый вебхук


@pytest.mark.asyncio
async def test_republishing_with_a_new_token_drops_the_old_webhook(
    api, auth, owner: Client, make_bot, db, monkeypatch
):
    """Секрет вебхука выводится из id бота, а не из токена, поэтому старый
    бот продолжал слать апдейты, и диспетчер отвечал от имени нового."""
    from app.services import security

    bot, _ = await make_bot(
        owner, [(BlockType.welcome, {"text": "привет"})], status=BotStatus.active, provider="yookassa"
    )
    bot.bot_token_encrypted = security.encrypt_token("111:AAA")
    await db.commit()
    monkeypatch.setattr("app.routers.bots.validate_bot_token",
                        AsyncMock(return_value=type("Me", (), {"username": "new_bot"})()))
    monkeypatch.setattr("app.services.bot_registry.register_webhook", AsyncMock())
    removed = []

    async def remember(bot_id, token=None):
        removed.append(token)

    monkeypatch.setattr("app.services.bot_registry.remove", remember)

    await api.post(f"/api/bots/{bot.id}/publish", headers=auth(owner), json={"token": "222:BBB"})

    assert removed == ["111:AAA"], "вебхук старого бота не снят"
