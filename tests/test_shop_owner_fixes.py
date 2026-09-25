"""Вторая партия находок клиента — владелицы платного канала про выпечку.

Общая тема: продукт выглядел правдоподобно там, где был неправ. Касса в
тестовом режиме считалась подключённой, «1.500» становилось полутора рублями,
заказ без доставки выглядел как успешный, а отписаться было нельзя.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models.bot_block import BlockType
from app.models.bot_subscriber import BotSubscriber
from app.models.client import Client
from app.models.payment import Payment, PaymentKind, PaymentStatus
from app.models.scheduled_step import ScheduledStep, StepStatus

CHAT_ID = 8080
USER_ID = 900140001


# ------------------------------------ подписки снова доступны владельцу


def test_subscriptions_are_available_again():
    """Клиент пришёл за закрытым каналом за 1500 ₽/мес и собрать его не мог:
    переключатель был спрятан, а помеченный подпиской блок продавался как
    разовая покупка."""
    from app.services import subscription_service

    assert get_settings().subscriptions_enabled is True
    assert subscription_service.is_subscription_block({"subscription": True}) is True


@pytest.mark.asyncio
async def test_the_subscription_toggle_is_offered_to_the_constructor(api, auth, owner: Client):
    catalogue = (await api.get("/api/payments/providers", headers=auth(owner))).json()

    assert catalogue["subscriptions_enabled"] is True


# ------------------------------- тестовый режим ≠ подключённая касса


@pytest.mark.asyncio
async def test_a_till_in_test_mode_is_not_reported_as_live(api, auth, owner: Client, make_bot):
    """Галочка «тестовый режим» стоит по умолчанию. Касса с заполненными
    ключами объявлялась подключённой, шапка зеленела, чек-лист очищался — а
    платежи были ненастоящими. Владелец объявил бы бота 900 подписчикам."""
    bot, _ = await make_bot(owner, [])

    test_mode = await api.put(
        f"/api/bots/{bot.id}/payment-settings",
        headers=auth(owner),
        json={
            "provider": "yookassa", "is_test": True,
            "credentials": {"shop_id": "123", "secret_key": "test_key"},
        },
    )
    assert test_mode.json()["ready"] is True, "ключи заполнены — касса настроена"
    assert test_mode.json()["live"] is False, "тестовый режим объявлен боевым"

    live = await api.put(
        f"/api/bots/{bot.id}/payment-settings",
        headers=auth(owner),
        json={
            "provider": "yookassa", "is_test": False,
            "credentials": {"shop_id": "123", "secret_key": "live_key"},
        },
    )
    assert live.json()["live"] is True


# ---------------------------- адрес уведомлений: одна инструкция, не две


@pytest.mark.asyncio
async def test_the_callback_address_is_offered_only_where_it_is_needed(api, auth, owner: Client, make_bot):
    """На одном экране стояло «urlNotification мы подставляем сами» и тут же
    «этот адрес нужно указать в кабинете». Вторая инструкция была ложью."""
    from app.services.payments import get_provider

    bot, _ = await make_bot(owner, [])

    await api.put(
        f"/api/bots/{bot.id}/payment-settings",
        headers=auth(owner),
        json={"provider": "prodamus", "is_test": True, "credentials": {}},
    )
    prodamus = (await api.get(f"/api/bots/{bot.id}/payment-settings", headers=auth(owner))).json()
    assert prodamus["callback_url"] is None, "просим вписать адрес, который отправляем сами"

    await api.put(
        f"/api/bots/{bot.id}/payment-settings",
        headers=auth(owner),
        json={"provider": "yookassa", "is_test": True, "credentials": {}},
    )
    yookassa = (await api.get(f"/api/bots/{bot.id}/payment-settings", headers=auth(owner))).json()
    assert yookassa["callback_url"], "ЮKassa адрес вписывают руками — его надо показать"
    # И база адресов есть всегда, чтобы показать его для кассы, которую
    # настраивают прямо сейчас, а не только для уже сохранённой.
    assert yookassa["callback_base"]

    assert get_provider("prodamus").sends_own_callback_url is True
    assert get_provider("yookassa").sends_own_callback_url is False


# ----------------------------------- заказ без доставки виден продавцу


@pytest.mark.asyncio
async def test_an_undelivered_order_says_so(api, auth, owner: Client, make_bot, db: AsyncSession):
    """Заказ, по которому товар не дошёл, выглядел ровно как успешный:
    «оплачен · Марина · 990 RUB»."""
    bot, blocks = await make_bot(
        owner, [(BlockType.payment, {"title": "Набор рецептов", "price": "990"})], provider="test"
    )
    db.add_all([
        Payment(
            id=uuid.uuid4(), kind=PaymentKind.order, status=PaymentStatus.paid,
            provider="test", amount_minor=99000, currency="RUB", description="дошёл",
            bot_id=bot.id, block_id=blocks[0].id, telegram_user_id=USER_ID, chat_id=CHAT_ID,
            meta={"delivered_at": datetime.now(timezone.utc).isoformat()},
            paid_at=datetime.now(timezone.utc),
        ),
        Payment(
            id=uuid.uuid4(), kind=PaymentKind.order, status=PaymentStatus.paid,
            provider="test", amount_minor=99000, currency="RUB", description="не дошёл",
            bot_id=bot.id, block_id=blocks[0].id, telegram_user_id=USER_ID + 1, chat_id=CHAT_ID + 1,
            meta={}, paid_at=datetime.now(timezone.utc),
        ),
    ])
    await db.commit()

    report = (await api.get(f"/api/bots/{bot.id}/orders", headers=auth(owner))).json()
    by_description = {o["description"]: o for o in report["orders"]}

    assert by_description["дошёл"]["delivered"] is True
    assert by_description["не дошёл"]["delivered"] is False


# --------------------------------------------- отчёт по рассылке


@pytest.mark.asyncio
async def test_a_broadcast_reports_what_actually_happened(
    api, auth, owner: Client, make_bot, db: AsyncSession
):
    """Интерфейс говорил «Отправляем 12 чел.» — и на этом всё. Шаги могли
    упасть все до одного, и при 900 подписчиках этого не заметить никак."""
    bot, blocks = await make_bot(owner, [(BlockType.description, {"text": "новый рецепт"})])
    db.add_all([
        ScheduledStep(
            id=uuid.uuid4(), bot_id=bot.id, block_id=blocks[0].id, chat_id=CHAT_ID + i,
            telegram_user_id=USER_ID + i, reason="broadcast", status=status,
            run_at=datetime.now(timezone.utc),
        )
        for i, status in enumerate([StepStatus.sent, StepStatus.sent, StepStatus.failed, StepStatus.pending])
    ])
    await db.commit()

    report = (await api.get(f"/api/bots/{bot.id}/broadcasts", headers=auth(owner))).json()

    assert len(report["broadcasts"]) == 1
    row = report["broadcasts"][0]
    assert (row["total"], row["sent"], row["failed"], row["waiting"]) == (4, 2, 1, 1)


# --------------------------------------- отписка: и работает, и находится


@pytest.mark.asyncio
async def test_a_broadcast_says_how_to_stop_it(db: AsyncSession, owner: Client, make_bot, telegram):
    """Команда /stop существовала и отвечала хорошо, но узнать о ней было
    неоткуда. Человеку оставалось заблокировать бота — и потерять вместе с
    ним купленный доступ."""
    from app.models.bot import BotStatus
    from app.services import scheduler

    bot, blocks = await make_bot(
        owner, [(BlockType.description, {"text": "Новый рецепт на канале"})], status=BotStatus.active
    )
    db.add(BotSubscriber(id=uuid.uuid4(), bot_id=bot.id, telegram_user_id=USER_ID, chat_id=CHAT_ID))
    await db.commit()
    await scheduler.schedule(
        db, bot_id=bot.id, block_id=blocks[0].id, chat_id=CHAT_ID,
        telegram_user_id=USER_ID, delay_seconds=0, reason="broadcast",
    )

    import unittest.mock as mock

    with mock.patch("app.services.bot_registry.get_or_create", mock.AsyncMock(return_value=telegram)):
        await scheduler.run_due()

    sent = telegram.sent()
    assert sent and "/stop" in sent[0], f"в рассылке не сказано, как отписаться: {sent}"
    # И обычная беседа подписью не обрастает.
    assert "Новый рецепт на канале" in sent[0]
