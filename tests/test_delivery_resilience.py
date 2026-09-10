"""What happens to the goods when something goes wrong around delivery.

Delivery moved off the request into a background task, which fixed the
webhook timing out — and quietly created a new way to lose a sale: the
provider has already been told "received", so if the process dies in between,
nothing anywhere retries. These pin the recovery.
"""

from __future__ import annotations

import asyncio

from sqlalchemy import select

from app.models.bot_block import BlockType
from app.models.payment import Payment, PaymentStatus
from app.services import background, bot_dispatcher, payment_service

CHAT_ID = 6161


async def sold_bot(make_bot, owner):
    return await make_bot(
        owner,
        [
            (BlockType.payment, {"text": "Гайд", "title": "Гайд", "price": "990", "currency": "RUB"}),
            (BlockType.delivery, {"text": "ВОТ ТОВАР"}),
        ],
        provider="test",
    )


async def order(db, bot, telegram):
    await bot_dispatcher.process_update(
        telegram, {"message": {"chat": {"id": CHAT_ID}, "text": "/start"}}, bot.id, db
    )
    return (await db.execute(select(Payment).where(Payment.bot_id == bot.id))).scalar_one()


async def test_delivery_is_recorded_so_it_is_not_repeated(db, owner, make_bot, as_bot):
    bot, _ = await sold_bot(make_bot, owner)
    payment = await order(db, bot, as_bot)

    await payment_service.mark_paid(db, payment, "x")
    await payment_service.resume_after_payment(db, payment)

    assert "ВОТ ТОВАР" in as_bot.sent()
    assert (payment.meta or {}).get("delivered_at"), "выдача должна отмечаться, иначе её повторят"


async def test_a_paid_order_never_handed_over_is_delivered_on_the_next_start(db, owner, make_bot, as_bot):
    """The exact shape of a restart mid-delivery: paid, but no delivery mark."""
    bot, _ = await sold_bot(make_bot, owner)
    payment = await order(db, bot, as_bot)
    await payment_service.mark_paid(db, payment, "x")
    # Backdate it past the "might still be in flight right now" window.
    await db.execute(
        Payment.__table__.update()
        .where(Payment.id == payment.id)
        .values(paid_at=payment.paid_at.replace(year=payment.paid_at.year - 1))
    )
    await db.commit()
    as_bot.reset_mock()

    await payment_service.redeliver_undelivered()

    assert "ВОТ ТОВАР" in as_bot.sent(), "оплаченный, но не выданный заказ должен доехать"


async def test_a_delivered_order_is_not_delivered_again_on_restart(db, owner, make_bot, as_bot):
    bot, _ = await sold_bot(make_bot, owner)
    payment = await order(db, bot, as_bot)
    await payment_service.mark_paid(db, payment, "x")
    await payment_service.resume_after_payment(db, payment)
    as_bot.reset_mock()

    await payment_service.redeliver_undelivered()

    assert as_bot.sent() == []


async def test_deleting_the_block_after_an_order_does_not_swallow_the_goods(db, owner, make_bot, as_bot):
    """Editing the canvas is a normal thing to do while an order is open, and
    the landing page promises edits apply immediately. Losing the delivery
    target must not mean the buyer pays and hears nothing."""
    bot, blocks = await sold_bot(make_bot, owner)
    payment = await order(db, bot, as_bot)

    # The shop deletes the delivery block; the payment block's next_block_id
    # becomes NULL through ON DELETE SET NULL.
    await db.delete(blocks[1])
    await db.commit()
    as_bot.reset_mock()

    await payment_service.mark_paid(db, payment, "x")
    await payment_service.resume_after_payment(db, payment)

    said = " ".join(as_bot.sent())
    assert "Оплата получена" in said
    # The buyer is told a person is coming, rather than being left with a
    # receipt and silence.
    assert "продавец" in said.lower()


async def test_one_chat_is_processed_in_order(db, owner, make_bot, as_bot):
    """Answering the webhook immediately gave up the ordering Telegram used
    to provide by waiting for each update in turn."""
    order_seen: list[int] = []

    async def slow(index: int) -> None:
        await asyncio.sleep(0.03 if index == 0 else 0)
        order_seen.append(index)

    for index in range(5):
        background.spawn(slow(index), name=f"t{index}", key="chat-1")
    await background.wait_for_all()

    assert order_seen == [0, 1, 2, 3, 4]


async def test_redelivery_finds_an_old_order_behind_newer_delivered_ones(db, owner, make_bot, as_bot):
    """The undelivered one is not necessarily recent.

    Filtering `delivered_at` in Python *after* LIMIT meant a single stranded
    order sitting behind a page of delivered ones was never found at all.
    """
    bot, _ = await sold_bot(make_bot, owner)
    payment = await order(db, bot, as_bot)
    await payment_service.mark_paid(db, payment, "x")
    await db.execute(
        Payment.__table__.update()
        .where(Payment.id == payment.id)
        .values(paid_at=payment.paid_at.replace(year=payment.paid_at.year - 1))
    )
    await db.commit()
    as_bot.reset_mock()

    # A limit of one, with newer *delivered* orders that would otherwise fill
    # the page — only the SQL-side filter can see past them.
    await payment_service.redeliver_undelivered(limit=1)

    assert "ВОТ ТОВАР" in as_bot.sent()


async def test_queued_work_cancelled_before_it_runs_is_closed_cleanly(db):
    """Cancelling a task still waiting for its predecessor used to leave the
    coroutine un-awaited — a bare warning, and the update simply gone."""
    import warnings

    ran: list[int] = []

    async def slow() -> None:
        await asyncio.sleep(5)
        ran.append(0)

    async def queued() -> None:
        ran.append(1)

    with warnings.catch_warnings():
        warnings.simplefilter("error", RuntimeWarning)
        background.spawn(slow(), name="head", key="chat-x")
        background.spawn(queued(), name="tail", key="chat-x")
        await asyncio.sleep(0.05)
        await background.cancel_all()

    assert ran == []
