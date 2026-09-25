"""Находки клиента — владельца онлайн-школы, который прошёл продукт целиком.

Не «код сломан», а «продукт молча врёт»: зелёная галочка при пустой кассе,
несостоявшаяся продажа, о которой продавец не узнаёт, и кнопка «Удалить» под
вопросом «отправить всем?».
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.bot_block import BlockType
from app.models.client import Client
from app.models.payment import Payment, PaymentKind, PaymentStatus
from app.services import bot_dispatcher, payment_service

CHAT_ID = 7007
USER_ID = 900110001


# ------------------------------- «Касса подключена» при пустых ключах


@pytest.mark.asyncio
async def test_a_till_without_keys_is_not_reported_as_connected(api, auth, owner: Client, make_bot):
    """Самое дорогое из найденного клиентом: выбрал ЮKassa, оставил поля
    пустыми, получил «✓ Сохранено», красное предупреждение погасло, в шапке
    загорелось зелёное «Касса подключена». Заплатил 99 $ за бота, который не
    примет ни рубля."""
    bot, _ = await make_bot(owner, [])

    saved = await api.put(
        f"/api/bots/{bot.id}/payment-settings",
        headers=auth(owner),
        json={"provider": "yookassa", "is_test": True, "credentials": {}},
    )

    assert saved.status_code == 200
    body = saved.json()
    assert body["ready"] is False, "пустая касса объявлена готовой"
    assert body["missing_fields"], "не сказано, чего не хватает"

    # А заполненная — готова.
    filled = await api.put(
        f"/api/bots/{bot.id}/payment-settings",
        headers=auth(owner),
        json={
            "provider": "yookassa", "is_test": True,
            "credentials": {"shop_id": "123", "secret_key": "test_key"},
        },
    )
    assert filled.json()["ready"] is True
    assert filled.json()["missing_fields"] == []


# --------------------------- несостоявшаяся продажа доходит до продавца


@pytest.mark.asyncio
async def test_a_sale_that_could_not_start_reaches_the_owner(
    db: AsyncSession, owner: Client, make_bot, telegram, monkeypatch
):
    """Покупатель жал «Купить», получал извинение, а продавец не узнавал
    ничего: ошибка уходила в лог. Под это попадало всё — пустые ключи,
    упавший шлюз, цена «0»."""
    bot, blocks = await make_bot(
        owner,
        [(BlockType.payment, {"title": "Курс по фотографии", "price": "1990"})],
        provider="yookassa",
        credentials={},  # ключей нет — счёт не выставится
    )
    told: list[str] = []

    async def remember(db_, bot_id, message):
        told.append(message)

    monkeypatch.setattr(bot_dispatcher, "_tell_owner", remember)

    await bot_dispatcher._send_payment_block(telegram, CHAT_ID, blocks[0], bot.id, db, USER_ID)

    # Покупателю — извинение.
    said = " ".join(str(c) for c in telegram.send_message.call_args_list)
    assert "Не получилось открыть оплату" in said
    # Продавцу — причина.
    assert len(told) == 1, "продавец не узнал о несостоявшейся продаже"
    assert "не состоялась" in told[0]
    assert "Курс по фотографии" in told[0]
    assert "shopId" in told[0] or "ключ" in told[0].lower(), f"причина не названа: {told[0]}"


# --------------------------------------------------------- возврат денег


@pytest.mark.asyncio
async def test_a_refund_closes_access_and_tells_the_buyer(
    db: AsyncSession, owner: Client, make_bot, monkeypatch
):
    """Возврата не было вовсе: продавец возвращал деньги в кабинете кассы, а
    покупатель оставался в закрытом канале навсегда."""
    bot, blocks = await make_bot(
        owner,
        [(BlockType.payment, {"title": "Курс", "price": "1990"}),
         (BlockType.delivery, {"text": "добро пожаловать", "group_chat_id": "-1001234"})],
        provider="test",
    )
    payment = Payment(
        id=uuid.uuid4(), kind=PaymentKind.order, status=PaymentStatus.paid,
        provider="test", amount_minor=199000, currency="RUB", description="Курс",
        bot_id=bot.id, block_id=blocks[0].id, telegram_user_id=USER_ID, chat_id=CHAT_ID,
        meta={"deliver_from": str(blocks[1].id)}, paid_at=datetime.now(timezone.utc),
    )
    db.add(payment)
    await db.commit()

    instance = AsyncMock()
    monkeypatch.setattr("app.services.bot_registry.get_or_create", AsyncMock(return_value=instance))

    removed = await payment_service.refund_by_owner(db, payment)
    await db.refresh(payment)

    assert payment.status == PaymentStatus.refunded
    assert removed is True, "доступ в закрытый чат не закрыт"
    instance.ban_chat_member.assert_awaited()
    # И разбанен сразу же — это возврат, а не «ты больше не наш покупатель».
    instance.unban_chat_member.assert_awaited()
    told = " ".join(str(c) for c in instance.send_message.call_args_list)
    assert "возврат" in told.lower(), "покупателю не сказали, почему пропал доступ"


@pytest.mark.asyncio
async def test_only_a_paid_order_can_be_refunded(api, auth, owner: Client, make_bot, db):
    bot, _ = await make_bot(owner, [], provider="test")
    pending = Payment(
        id=uuid.uuid4(), kind=PaymentKind.order, status=PaymentStatus.pending,
        provider="test", amount_minor=199000, currency="RUB", description="Курс",
        bot_id=bot.id, telegram_user_id=USER_ID, chat_id=CHAT_ID, meta={},
    )
    db.add(pending)
    await db.commit()

    response = await api.post(
        f"/api/bots/{bot.id}/orders/{pending.id}/refund", headers=auth(owner)
    )

    assert response.status_code == 400


# ------------------------------------------------ мелочи, которые стоили денег


def test_the_test_checkout_page_does_not_double_the_currency():
    """«— 99 USD USD»: `money()` уже включает валюту, её добавляли второй раз."""
    from app.services.payments import money

    assert money(9900, "USD") == "99 USD"

    import pathlib

    page = pathlib.Path("app/routers/payments.py").read_text()
    assert "{amount} {escape(payment.currency)}" not in page
