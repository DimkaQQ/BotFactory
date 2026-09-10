"""The rules that decide whether money and goods change hands correctly.

Each of these was a real bug found in review, so each test names the way it
went wrong rather than just the behaviour it wants.
"""

from __future__ import annotations

import asyncio
import uuid
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import select

from app.database import AsyncSessionLocal
from app.models.bot_block import BlockType
from app.models.payment import Payment, PaymentStatus
from app.services import bot_dispatcher, payment_service
from app.services.payments import get_provider

CHAT_ID = 4343


async def paid_bot(make_bot, owner, provider="test", **content):
    base = {"text": "Гайд", "title": "Гайд", "price": "990", "currency": "RUB"}
    return await make_bot(
        owner,
        [
            (BlockType.payment, {**base, **content}),
            (BlockType.delivery, {"text": "ВОТ ТОВАР"}),
        ],
        provider=provider,
    )


# ------------------------------------------------- delivering exactly once


async def test_a_redelivered_webhook_does_not_deliver_twice(db, owner, make_bot, as_bot):
    bot, blocks = await paid_bot(make_bot, owner)
    await bot_dispatcher.process_update(
        as_bot, {"message": {"chat": {"id": CHAT_ID}, "text": "/start"}}, bot.id, db
    )
    payment = (await db.execute(select(Payment).where(Payment.bot_id == bot.id))).scalar_one()

    assert await payment_service.mark_paid(db, payment, "chg") is True
    assert await payment_service.mark_paid(db, payment, "chg") is False


async def test_simultaneous_webhooks_deliver_the_goods_once(db, owner, make_bot, as_bot):
    """Robokassa re-posts until it is acknowledged and ЮKassa retries a slow
    response, so several confirmations really do land at the same instant.

    Each `mark_paid` returning True is one delivery, so more than one True
    across concurrent callers means the buyer is sent the goods twice.
    """
    bot, _ = await paid_bot(make_bot, owner)
    await bot_dispatcher.process_update(
        as_bot, {"message": {"chat": {"id": CHAT_ID}, "text": "/start"}}, bot.id, db
    )
    payment_id = (await db.execute(select(Payment).where(Payment.bot_id == bot.id))).scalar_one().id

    racers = 6
    start = asyncio.Barrier(racers)

    async def settle() -> bool:
        # A separate session each, the way separate webhook requests arrive.
        async with AsyncSessionLocal() as session:
            row = (await session.execute(select(Payment).where(Payment.id == payment_id))).scalar_one()
            await start.wait()
            return await payment_service.mark_paid(session, row, "chg")

    results = await asyncio.gather(*(settle() for _ in range(racers)))

    assert sum(results) == 1, f"выдача сработала {sum(results)} раз вместо одного"


# ------------------------------------------------ never ship without paying


async def test_a_provider_outage_does_not_release_the_goods(db, owner, make_bot, telegram, monkeypatch):
    """A live shop whose provider is down must stop selling, not start giving
    things away."""
    bot, _ = await paid_bot(make_bot, owner, price="990")

    async def explode(*args, **kwargs):
        raise RuntimeError("провайдер недоступен")

    monkeypatch.setattr(get_provider("test"), "create_checkout", explode)

    await bot_dispatcher.process_update(
        telegram, {"message": {"chat": {"id": CHAT_ID}, "text": "/start"}}, bot.id, db
    )

    assert "ВОТ ТОВАР" not in telegram.sent()


async def test_a_blank_price_does_not_release_the_goods(db, owner, make_bot, telegram):
    """The state a payment block is in the moment it is dragged onto canvas."""
    bot, _ = await paid_bot(make_bot, owner, price="")

    await bot_dispatcher.process_update(
        telegram, {"message": {"chat": {"id": CHAT_ID}, "text": "/start"}}, bot.id, db
    )

    assert "ВОТ ТОВАР" not in telegram.sent()


# --------------------------------------------------- what the buyer is told


async def test_the_button_shows_the_amount_that_will_be_charged(db, owner, make_bot, telegram):
    """Integer division turned 990.50 into a button reading "990"."""
    bot, _ = await paid_bot(make_bot, owner, price="990.50")

    await bot_dispatcher.process_update(
        telegram, {"message": {"chat": {"id": CHAT_ID}, "text": "/start"}}, bot.id, db
    )

    labels = [b.text for kb in telegram.keyboards() for row in kb.inline_keyboard for b in row]
    assert "Оплатить 990.50 RUB" in labels, labels


async def test_the_currency_comes_from_the_provider_not_the_stale_block(db, owner, make_bot):
    """A block still holding RUB while the provider charges stars would say
    "250 RUB" and take 250 ⭐."""
    assert payment_service.currency_for("stars", "RUB") == "XTR"
    assert payment_service.currency_for("yookassa", "KZT") == "RUB"
    # A currency the provider does support is left alone.
    assert payment_service.currency_for("robokassa", "USD") == "USD"


# ------------------------------------------------------- one order per buyer


async def test_tapping_start_again_reuses_the_open_order(db, owner, make_bot, telegram):
    """Three taps of /start is one person looking at one product."""
    bot, _ = await paid_bot(make_bot, owner)

    for _ in range(3):
        await bot_dispatcher.process_update(
            telegram, {"message": {"chat": {"id": CHAT_ID}, "text": "/start"}}, bot.id, db
        )

    orders = (await db.execute(select(Payment).where(Payment.bot_id == bot.id))).scalars().all()
    assert len(orders) == 1, f"создано {len(orders)} заказов вместо одного"


async def test_a_different_price_starts_a_new_order(db, owner, make_bot, telegram):
    """Reuse must not outlive the thing being sold: once the shop edits the
    price, the open order is for a different product."""
    bot, blocks = await paid_bot(make_bot, owner)
    await bot_dispatcher.process_update(
        telegram, {"message": {"chat": {"id": CHAT_ID}, "text": "/start"}}, bot.id, db
    )

    blocks[0].content = {**blocks[0].content, "price": "1490"}
    await db.commit()
    await bot_dispatcher.process_update(
        telegram, {"message": {"chat": {"id": CHAT_ID}, "text": "/start"}}, bot.id, db
    )

    orders = (await db.execute(select(Payment).where(Payment.bot_id == bot.id))).scalars().all()
    assert {o.amount_minor for o in orders} == {99000, 149000}


# ------------------------------------------------------------------- Stripe


async def test_stripe_refuses_a_session_charged_the_wrong_amount():
    import hashlib
    import hmac
    import json
    import time

    from app.services.payments.base import ProviderError

    secret = "whsec_test"
    body = json.dumps({
        "type": "checkout.session.completed",
        "data": {"object": {"id": "cs_1", "payment_status": "paid",
                            "amount_total": 100, "currency": "usd",
                            "client_reference_id": str(uuid.uuid4())}},
    }).encode()
    ts = str(int(time.time()))
    signature = hmac.new(secret.encode(), f"{ts}.".encode() + body, hashlib.sha256).hexdigest()

    with pytest.raises(ProviderError, match="сумма"):
        await get_provider("stripe").verify_webhook(
            headers={"stripe-signature": f"t={ts},v1={signature}"},
            raw_body=body, form={}, credentials={"webhook_secret": secret},
            amount_minor=99000, invoice_no=1, payment_id=uuid.uuid4(), provider_payment_id=None,
        )


async def test_stripe_accepts_a_delivery_signed_during_a_secret_rotation():
    """Stripe signs one delivery with every active secret while a rotation is
    in progress, so the header carries several `v1=` values."""
    import hashlib
    import hmac
    import json
    import time

    secret = "whsec_new"
    payment_id = uuid.uuid4()
    body = json.dumps({
        "type": "checkout.session.completed",
        "data": {"object": {"id": "cs_1", "payment_status": "paid",
                            "amount_total": 99000, "currency": "usd",
                            "client_reference_id": str(payment_id)}},
    }).encode()
    ts = str(int(time.time()))
    ours = hmac.new(secret.encode(), f"{ts}.".encode() + body, hashlib.sha256).hexdigest()

    result = await get_provider("stripe").verify_webhook(
        headers={"stripe-signature": f"t={ts},v1=0000deadbeef,v1={ours}"},
        raw_body=body, form={}, credentials={"webhook_secret": secret},
        amount_minor=99000, invoice_no=1, payment_id=payment_id, provider_payment_id=None,
    )

    assert result.status == PaymentStatus.paid
