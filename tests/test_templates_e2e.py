"""Каждый шаблон конструктора проходится как настоящий покупатель.

Шаблоны лежат во фронтенде (`frontend/src/templates.ts`); `tests/fixtures/templates.json`
выгружен из них (см. README, «Разработка»), поэтому ломать шаблон и не заметить
этого нельзя: блок, кнопка, оплата и выдача каждого шаблона проходят через
настоящий диспетчер, а оплата подтверждается так же, как в бою.
"""

from __future__ import annotations

import json
import uuid
from pathlib import Path

import pytest
from sqlalchemy import select

from app.models.bot_block import BlockType
from app.models.payment import Payment, PaymentStatus
from app.services import background, bot_dispatcher

TEMPLATES = json.loads((Path(__file__).parent / "fixtures" / "templates.json").read_text())
CHAT_ID = 4242
OWNER_NOTICE = "Оплачен заказ"


def _wire(blocks, template=None):
    """Как BotList: кнопка-ветка первой не-URL кнопки ведёт в следующий блок.
    Если у шаблона своя разводка (`nexts`/`links`) — применяем её."""
    if template and template.get("nexts"):
        for frm, to in template["nexts"]:
            blocks[frm].next_block_id = blocks[to].id
        for link in template.get("links") or []:
            source = blocks[link["from"]]
            buttons = list(source.content.get("buttons") or [])
            buttons[link["button"]] = {**buttons[link["button"]], "target_block_id": str(blocks[link["to"]].id)}
            source.content = {**source.content, "buttons": buttons}
        return
    for index, block in enumerate(blocks[:-1]):
        buttons = block.content.get("buttons") or []
        if block.block_type == BlockType.buttons:
            for i, b in enumerate(buttons):
                if b.get("action_type") != "url":
                    buttons[i] = {**b, "target_block_id": str(blocks[index + 1].id)}
                    break
            block.content = {**block.content, "buttons": buttons}


@pytest.mark.parametrize("template", [t for t in TEMPLATES if t["blocks"]], ids=lambda t: t["id"])
async def test_a_buyer_can_walk_every_template(template, api, db, owner, make_bot, as_bot):
    spec = [(BlockType(b["block_type"]), dict(b["content"])) for b in template["blocks"]]
    bot, blocks = await make_bot(owner, spec, provider="test", is_test=True)
    _wire(blocks, template)
    await db.commit()

    # Настоящий Telegram возвращает у каждого опроса свой id (в таблице он уникален).
    counter = iter(range(1, 1000))

    async def fake_send_poll(chat_id, **kwargs):
        n = next(counter)
        return type("Sent", (), {"poll": type("P", (), {"id": f"poll-{n}"})(), "chat": type("C", (), {"id": chat_id})(), "message_id": n})()

    as_bot.send_poll.side_effect = fake_send_poll

    await bot_dispatcher.process_update(
        as_bot, {"message": {"chat": {"id": CHAT_ID}, "from": {"id": CHAT_ID}, "text": "/start"}}, bot.id, db
    )
    await background.wait_for_all()
    assert as_bot.sent() or any(c[0] == "send_poll" for c in as_bot.method_calls), "бот молчит на /start"

    # дальше — нажать первую кнопку, если она есть
    buttons_block = next((b for b in blocks if b.block_type == BlockType.buttons), None)
    if buttons_block is not None and buttons_block.content.get("keyboard") == "reply":
        # быстрые кнопки: покупатель нажимает каждую — приходит текст с подписью
        for button in buttons_block.content["buttons"]:
            before = len(as_bot.sent())
            await bot_dispatcher.process_update(
                as_bot,
                {"message": {"chat": {"id": CHAT_ID}, "from": {"id": CHAT_ID}, "text": button["label"]}},
                bot.id, db,
            )
            await background.wait_for_all()
            assert len(as_bot.sent()) > before, f"кнопка {button['label']!r} ничего не ответила"
    # дальше — нажать первую кнопку каждого блока кнопок под сообщением (по порядку)
    for inline in blocks:
        if inline.block_type != BlockType.buttons or inline.content.get("keyboard") == "reply":
            continue
        buttons = inline.content.get("buttons") or []
        if not buttons or buttons[0].get("action_type") == "url":
            continue
        await bot_dispatcher.process_update(
            as_bot,
            {"callback_query": {"id": "cb", "data": f"b:{inline.id.hex}:0",
                                "from": {"id": CHAT_ID}, "message": {"chat": {"id": CHAT_ID}}}},
            bot.id, db,
        )
        await background.wait_for_all()

    payment_block = next((b for b in blocks if b.block_type == BlockType.payment), None)
    if payment_block is None:
        return  # шаблон без оплаты: дошли до конца без падений

    payment = (await db.execute(select(Payment).where(Payment.bot_id == bot.id))).scalar_one()
    assert payment.status == PaymentStatus.pending
    assert payment.amount_minor > 0, "цена блока оплаты не распознана"

    # покупатель платит: тестовая касса подтверждает при открытии ссылки
    response = await api.get(f"/webhook/pay/test/{payment.id}")
    assert response.status_code < 400
    await background.wait_for_all()

    await db.refresh(payment)
    assert payment.status == PaymentStatus.paid

    delivery = next(b for b in blocks if b.block_type == BlockType.delivery)
    expected = delivery.content["text"]
    assert as_bot.sent().count(expected) == 1, "выдача должна прийти ровно один раз"
    assert any(OWNER_NOTICE in text or "Новая подписка" in text for text in as_bot.sent()), "владелец не получил уведомление о продаже"


async def test_the_booking_template_notifies_the_owner_with_the_buyer_name(api, db, owner, make_bot, as_bot):
    """«Запись на сессию»: после оплаты владелец видит, КТО записался."""
    template = next(t for t in TEMPLATES if t["id"] == "one-on-one")
    spec = [(BlockType(b["block_type"]), dict(b["content"])) for b in template["blocks"]]
    bot, blocks = await make_bot(owner, spec, provider="test", is_test=True)
    _wire(blocks)
    await db.commit()
    start = {"message": {"chat": {"id": CHAT_ID}, "from": {"id": CHAT_ID, "first_name": "Анна"}, "text": "/start"}}
    await bot_dispatcher.process_update(as_bot, start, bot.id, db)
    await background.wait_for_all()
    buttons_block = next(b for b in blocks if b.block_type == BlockType.buttons)
    await bot_dispatcher.process_update(
        as_bot,
        {"callback_query": {"id": "c", "data": f"b:{buttons_block.id.hex}:0", "from": {"id": CHAT_ID},
                            "message": {"chat": {"id": CHAT_ID}}}},
        bot.id, db,
    )
    await background.wait_for_all()
    payment = (await db.execute(select(Payment).where(Payment.bot_id == bot.id))).scalar_one()
    await api.get(f"/webhook/pay/test/{payment.id}")
    await background.wait_for_all()
    notices = [t for t in as_bot.sent() if OWNER_NOTICE in t]
    assert notices and "Анна" in notices[0], notices
    assert uuid.UUID(str(payment.id))
