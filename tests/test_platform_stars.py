"""Оплата запуска звёздами Telegram: счёт и подтверждение идут через мета-бота."""

from __future__ import annotations

import json
import uuid
from datetime import datetime

import pytest
from _tg_fakes import FakeSession
from aiogram import Bot
from aiogram.methods import AnswerPreCheckoutQuery
from aiogram.types import Chat, Message, PreCheckoutQuery, SuccessfulPayment, Update, User
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models.bot import BotStatus
from app.models.bot_block import BlockType
from app.models.client import Client
from app.models.payment import Payment, PaymentKind, PaymentStatus


async def _feed(dp, tg, update):
    await dp.feed_update(tg, update)


def _stars_payment(bot, owner, stars=300) -> Payment:
    return Payment(
        id=uuid.uuid4(), kind=PaymentKind.publication, status=PaymentStatus.pending, provider="stars",
        amount_minor=stars * 100, currency="XTR", description="запуск", bot_id=bot.id, client_id=owner.id, meta={},
    )


@pytest.mark.asyncio
async def test_stars_for_launch_are_accepted_by_the_meta_bot(db: AsyncSession, owner: Client, make_bot, meta_dp):
    bot, _ = await make_bot(owner, [(BlockType.welcome, {"text": "привет"})], status=BotStatus.draft)
    payment = _stars_payment(bot, owner)
    db.add(payment)
    await db.commit()

    session = FakeSession()
    tg = Bot("123456:AAAA-testtoken", session=session)
    uid = owner.telegram_user_id
    user = User(id=uid, is_bot=False, first_name="Аня")

    await _feed(meta_dp, tg, Update(update_id=1, pre_checkout_query=PreCheckoutQuery(
        id="pc1", from_user=user, currency="XTR", total_amount=300, invoice_payload=str(payment.id))))
    assert session.of(AnswerPreCheckoutQuery)[-1].ok is True

    # чужая цена — отказ
    await _feed(meta_dp, tg, Update(update_id=2, pre_checkout_query=PreCheckoutQuery(
        id="pc2", from_user=user, currency="XTR", total_amount=1, invoice_payload=str(payment.id))))
    assert session.of(AnswerPreCheckoutQuery)[-1].ok is False

    await _feed(meta_dp, tg, Update(update_id=3, message=Message(
        message_id=7, date=datetime.now(), chat=Chat(id=uid, type="private"), from_user=user,
        successful_payment=SuccessfulPayment(
            currency="XTR", total_amount=300, invoice_payload=str(payment.id),
            telegram_payment_charge_id="chg_1", provider_payment_charge_id="p1"))))

    await db.refresh(payment)
    await db.refresh(bot)
    assert payment.status == PaymentStatus.paid
    assert bot.publication_paid_at is not None
    # подтверждение человеку отправляет общий код оплаты платформе (_confirm_to_client)

    # повтор доставки ничего не меняет и не падает
    await _feed(meta_dp, tg, Update(update_id=4, message=Message(
        message_id=8, date=datetime.now(), chat=Chat(id=uid, type="private"), from_user=user,
        successful_payment=SuccessfulPayment(
            currency="XTR", total_amount=300, invoice_payload=str(payment.id),
            telegram_payment_charge_id="chg_1", provider_payment_charge_id="p1"))))
    await tg.session.close()


@pytest.mark.asyncio
async def test_a_wrong_amount_in_stars_is_not_taken_for_a_launch(db: AsyncSession, owner: Client, make_bot, meta_dp):
    bot, _ = await make_bot(owner, [(BlockType.welcome, {"text": "привет"})], status=BotStatus.draft)
    payment = _stars_payment(bot, owner)
    db.add(payment)
    await db.commit()
    session = FakeSession()
    tg = Bot("123456:AAAA-testtoken", session=session)
    uid = owner.telegram_user_id
    await _feed(meta_dp, tg, Update(update_id=5, message=Message(
        message_id=9, date=datetime.now(), chat=Chat(id=uid, type="private"),
        from_user=User(id=uid, is_bot=False, first_name="Аня"),
        successful_payment=SuccessfulPayment(
            currency="XTR", total_amount=5, invoice_payload=str(payment.id),
            telegram_payment_charge_id="chg_2", provider_payment_charge_id="p2"))))
    await db.refresh(payment)
    assert payment.status == PaymentStatus.pending
    await tg.session.close()


def test_stars_are_listed_as_a_launch_method(monkeypatch):
    from app.services import payment_service

    monkeypatch.setattr(
        get_settings(), "platform_payment_methods",
        json.dumps([{"provider": "stars", "price_minor": 30000, "renewal_price_minor": 10000, "currency": "XTR"}]),
        raising=False,
    )
    methods = payment_service.platform_methods()
    assert [m.provider for m in methods] == ["stars"]


@pytest.mark.asyncio
async def test_a_stripe_refund_event_is_acknowledged_not_retried_forever(api):
    response = await api.post(
        "/webhook/pay/stripe", content=json.dumps({"type": "charge.refunded", "data": {"object": {}}}),
        headers={"content-type": "application/json"},
    )
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_the_client_is_told_that_the_money_arrived(db: AsyncSession, owner: Client, make_bot, monkeypatch):
    """Подтверждение приходит в Telegram при ЛЮБОЙ оплате платформе — не только звёздами."""
    from app.services import payment_service, platform_billing

    bot, _ = await make_bot(owner, [(BlockType.welcome, {"text": "привет"})], status=BotStatus.draft)
    payment = _stars_payment(bot, owner)
    db.add(payment)
    await db.commit()

    told = []

    async def remember(db_, bot_, text, **_):
        told.append(text)

    monkeypatch.setattr(platform_billing, "_tell_owner", remember)
    assert await payment_service.mark_paid(db, payment, "chg_x") is True
    from app.services import background

    await background.wait_for_all()
    assert told and "Оплата получена" in told[0] and "Опубликовать" in told[0]

    # повтор не шлёт второй раз
    told.clear()
    assert await payment_service.mark_paid(db, payment, "chg_x") is False
    await background.wait_for_all()
    assert told == []
