"""Walking a bot's dialogue graph.

The rules being pinned: the walk stops at a real branch point and nowhere
else, a buttons block with nothing wired to it is just another message, and a
loop in the graph cannot hold a webhook request open.
"""

from __future__ import annotations

import asyncio

import pytest

from app.models.bot_block import BlockType, BotBlock
from app.services import bot_dispatcher

CHAT_ID = 555


def button(label: str, target=None) -> dict:
    return {"label": label, "action_type": "text", "action_value": "", "target_block_id": target}


async def branching_bot(db, owner, make_bot):
    """welcome → description → buttons, with the two buttons going to their
    own branches; the second branch runs on into an unwired buttons block."""
    bot, blocks = await make_bot(
        owner,
        [
            (BlockType.welcome, {"text": "Привет!"}),
            (BlockType.description, {"text": "Мы делаем штуки."}),
            (BlockType.buttons, {"text": "Выбери путь", "buttons": [button("Путь A"), button("Путь B")]}),
        ],
    )
    welcome, desc, buttons = blocks

    branch_a = BotBlock(bot_id=bot.id, block_type=BlockType.description, content={"text": "Ветка A"}, order_index=3)
    branch_b = BotBlock(bot_id=bot.id, block_type=BlockType.description, content={"text": "Ветка B"}, order_index=4)
    inert = BotBlock(
        bot_id=bot.id,
        block_type=BlockType.buttons,
        content={"text": "Просто кнопка", "buttons": [button("ОК")]},
        order_index=5,
    )
    db.add_all([branch_a, branch_b, inert])
    await db.flush()

    buttons.content = {
        **buttons.content,
        "buttons": [button("Путь A", str(branch_a.id)), button("Путь B", str(branch_b.id))],
    }
    branch_a.next_block_id = None
    branch_b.next_block_id = inert.id
    await db.commit()
    return bot, buttons, inert


async def test_start_walks_to_the_branch_point_and_stops(db, owner, make_bot, telegram):
    bot, _buttons, _inert = await branching_bot(db, owner, make_bot)

    await bot_dispatcher.process_update(
        telegram, {"message": {"chat": {"id": CHAT_ID}, "text": "/start"}}, bot.id, db
    )

    assert telegram.sent() == ["Привет!", "Мы делаем штуки.", "Выбери путь"]


async def test_tapping_a_button_follows_only_its_branch(db, owner, make_bot, telegram):
    bot, buttons, _inert = await branching_bot(db, owner, make_bot)

    await bot_dispatcher.process_update(
        telegram,
        {"callback_query": {"id": "cb1", "data": f"b:{buttons.id.hex}:0", "message": {"chat": {"id": CHAT_ID}}}},
        bot.id,
        db,
    )

    assert telegram.sent() == ["Ветка A"]
    assert [c for c in telegram.method_calls if c[0] == "answer_callback_query"], "тап обязан быть отвечен"


async def test_buttons_block_without_branches_does_not_halt_the_chain(db, owner, make_bot, telegram):
    bot, buttons, _inert = await branching_bot(db, owner, make_bot)

    await bot_dispatcher.process_update(
        telegram,
        {"callback_query": {"id": "cb2", "data": f"b:{buttons.id.hex}:1", "message": {"chat": {"id": CHAT_ID}}}},
        bot.id,
        db,
    )

    # Branch B runs into a buttons block with nothing wired to it, which
    # behaves like any other message rather than a decision point.
    assert telegram.sent() == ["Ветка B", "Просто кнопка"]


async def test_tapping_an_unwired_button_answers_but_sends_nothing(db, owner, make_bot, telegram):
    bot, _buttons, inert = await branching_bot(db, owner, make_bot)

    await bot_dispatcher.process_update(
        telegram,
        {"callback_query": {"id": "cb3", "data": f"b:{inert.id.hex}:0", "message": {"chat": {"id": CHAT_ID}}}},
        bot.id,
        db,
    )

    assert [c for c in telegram.method_calls if c[0] == "answer_callback_query"]
    assert telegram.sent() == []


async def test_a_cycle_in_the_graph_stops_itself(db, owner, make_bot, telegram):
    """Each step is paced with a real typing delay, so an unbroken loop would
    otherwise hold the webhook request open for as long as it kept going."""
    bot, blocks = await make_bot(
        owner,
        [(BlockType.description, {"text": "Loop A"}), (BlockType.description, {"text": "Loop B"})],
    )
    loop_a, loop_b = blocks
    loop_b.next_block_id = loop_a.id  # close the ring
    await db.commit()

    await asyncio.wait_for(
        bot_dispatcher._walk_chain(telegram, CHAT_ID, loop_a.id, bot.id, db), timeout=10
    )

    assert len(telegram.sent()) <= bot_dispatcher._MAX_CHAIN_STEPS


async def test_start_on_an_empty_bot_says_so(db, owner, make_bot, telegram):
    bot, _ = await make_bot(owner, [])

    await bot_dispatcher.process_update(
        telegram, {"message": {"chat": {"id": CHAT_ID}, "text": "/start"}}, bot.id, db
    )

    assert telegram.sent() == ["Этот бот пока пуст 🤷"]


async def test_a_blank_button_row_does_not_take_the_whole_block_down(db, owner, make_bot, telegram):
    """A row added in the editor and never filled in used to build an invalid
    button, which made Telegram reject the entire message — caption and all."""
    bot, _ = await make_bot(
        owner,
        [(BlockType.buttons, {"text": "Есть текст", "buttons": [{"label": "", "action_value": ""}]})],
    )

    await bot_dispatcher.process_update(
        telegram, {"message": {"chat": {"id": CHAT_ID}, "text": "/start"}}, bot.id, db
    )

    assert telegram.sent() == ["Есть текст"]


async def test_a_failed_payment_never_releases_the_goods(db, owner, make_bot, telegram):
    """The block after a payment block is the thing being sold.

    So if the payment cannot even be created — no provider configured, a
    blank price, the provider's API down — the walk has to stop. Carrying on
    to `next_block_id` hands over the goods for free.
    """
    bot, _ = await make_bot(
        owner,
        [
            (BlockType.payment, {"text": "Гайд — 990 ₽", "title": "Гайд", "price": "990"}),
            (BlockType.delivery, {"text": "ВОТ ПЛАТНЫЙ ГАЙД"}),
        ],
        provider=None,  # nothing configured — the default for a fresh block
    )

    await bot_dispatcher.process_update(
        telegram, {"message": {"chat": {"id": CHAT_ID}, "text": "/start"}}, bot.id, db
    )

    assert "ВОТ ПЛАТНЫЙ ГАЙД" not in telegram.sent(), "товар выдан без оплаты"
    # And the buyer is told, rather than left looking at a dialogue that
    # simply stopped.
    assert telegram.sent(), "покупателю ничего не сказали"
