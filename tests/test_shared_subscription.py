"""Запуск — разово за каждого бота, подписка — одна на все боты клиента."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta, timezone

import pytest

from app.config import get_settings
from app.models.bot import BotStatus
from app.models.bot_block import BlockType
from app.models.payment import Payment, PaymentKind, PaymentStatus
from app.services import payment_service, platform_billing
from app.services.security import encrypt_token

METHODS = json.dumps(
    [{"provider": "stripe", "price_minor": 4900, "renewal_price_minor": 1500, "currency": "USD",
      "credentials": {"secret_key": "sk_test_x", "webhook_secret": "whsec_x"}}]
)


@pytest.fixture
def priced(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "platform_payment_methods", METHODS, raising=False)
    monkeypatch.setattr(settings, "renewal_period_days", 30, raising=False)
    monkeypatch.setattr(settings, "renewal_grace_days", 7, raising=False)
    return settings


async def _pay(db, bot, kind, amount):
    payment = Payment(
        id=uuid.uuid4(), kind=kind, status=PaymentStatus.pending, provider="stripe", amount_minor=amount,
        currency="USD", description="test", bot_id=bot.id, client_id=bot.client_id, meta={},
    )
    db.add(payment)
    await db.commit()
    await payment_service.mark_paid(db, payment, provider_payment_id=None)


async def _three_bots(db, owner, make_bot, status=BotStatus.draft):
    bots = []
    for _ in range(3):
        bot, _blocks = await make_bot(owner, [(BlockType.welcome, {"text": "hi"})], status=status)
        bots.append(bot)
    return bots


@pytest.mark.asyncio
async def test_each_launch_costs_the_launch_fee_but_the_subscription_is_shared(db, owner, make_bot, priced):
    first, second, third = await _three_bots(db, owner, make_bot)
    ids = [b.id for b in (first, second, third)]

    await _pay(db, first, PaymentKind.publication, 4900)
    db.expire_all()
    first = await db.get(type(first), ids[0])
    assert first.paid_until is not None
    until = first.paid_until

    # второй и третий запуск: платят 49 $ за бота, но подписка не продлевается и не дублируется
    for bot_id in ids[1:]:
        bot = await db.get(type(first), bot_id)
        await _pay(db, bot, PaymentKind.publication, 4900)
    db.expire_all()
    paid = [await db.get(type(first), i) for i in ids]
    assert all(b.publication_paid_at is not None for b in paid)
    assert {b.paid_until for b in paid} == {until}  # одна дата у всех: подписка одна


@pytest.mark.asyncio
async def test_one_renewal_extends_every_bot_once(db, owner, make_bot, priced):
    bots = await _three_bots(db, owner, make_bot, status=BotStatus.active)
    ids = [b.id for b in bots]
    start = datetime.now(timezone.utc) + timedelta(days=5)
    for bot in bots:
        bot.paid_until = start
    await db.commit()

    await _pay(db, bots[1], PaymentKind.renewal, 1500)  # 15 $ — один платёж на все
    db.expire_all()
    paid = [await db.get(type(bots[0]), i) for i in ids]
    expected = start + timedelta(days=30)
    assert all(abs(b.paid_until - expected) < timedelta(minutes=1) for b in paid)


@pytest.mark.asyncio
async def test_expiry_warns_once_per_client_and_one_renewal_brings_all_bots_back(db, owner, make_bot, priced, monkeypatch):
    told = []

    async def remember(db, bot, text, **_):
        told.append((bot.id, text))

    monkeypatch.setattr(platform_billing, "_tell_owner", remember)
    bots = await _three_bots(db, owner, make_bot, status=BotStatus.active)
    ids = [b.id for b in bots]
    soon = datetime.now(timezone.utc) + timedelta(days=2)
    for bot in bots:
        bot.paid_until = soon
    await db.commit()

    mine = set(ids)
    await platform_billing.sweep(db)
    assert len([1 for bot_id, _text in told if bot_id in mine]) == 1  # одно напоминание, а не три

    # период кончился и грейс тоже: все три бота снимаются с эфира
    async def noop(*a, **k):
        return None

    from app.services import bot_registry

    monkeypatch.setattr(bot_registry, "remove", noop)
    monkeypatch.setattr(bot_registry, "register_webhook", noop)
    for i in ids:
        bot = await db.get(type(bots[0]), i)
        bot.paid_until = datetime.now(timezone.utc) - timedelta(days=8)
        bot.bot_token_encrypted = encrypt_token("123:abc")
    await db.commit()
    await platform_billing.sweep(db)
    db.expire_all()
    assert [(await db.get(type(bots[0]), i)).status for i in ids] == [BotStatus.disabled] * 3

    await _pay(db, await db.get(type(bots[0]), ids[0]), PaymentKind.renewal, 1500)
    db.expire_all()
    assert [(await db.get(type(bots[0]), i)).status for i in ids] == [BotStatus.active] * 3
