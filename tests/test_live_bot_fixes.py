"""Находки проверки «каждый сантиметр»: что видно уже после запуска.

Общая тема этой партии — продукт зовёт править живого бота («изменения
применяются сразу»), но всё, что помогало не ошибиться, было построено для
черновика: чек-лист, подсказки, проверки. А то, что покупатель получает
в чате, никто не смотрел глазами покупателя: файл с именем из хекса,
опрос, результаты которого физически нельзя узнать.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.bot_block import BlockType
from app.models.client import Client
from app.models.payment import Payment, PaymentKind, PaymentStatus
from app.routers.media import _slug
from app.services.payments import WebhookResult

CHAT_ID = 7711
USER_ID = 900077110

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64
PDF = b"%PDF-1.4\n" + b"\x00" * 64


# ------------------------------------------------- имя файла у покупателя


def test_a_russian_file_name_survives_the_upload():
    """Покупатель платил за гайд, а в чате получал `3f9c…e7.pdf`.

    Имя файла в чате Telegram берёт из адреса, а адрес собирали мы — из
    случайного хекса. Кириллица в пути доехала бы процентными кодами,
    поэтому она переводится в латиницу.
    """
    assert _slug("Гайд по продажам.pdf", ".pdf") == "Gayd-po-prodazham.pdf"
    assert _slug("Чек-лист №3.pdf", ".pdf") == "Chek-list-3.pdf"
    assert _slug("lesson 01.mp4", ".mp4") == "lesson-01.mp4"


def test_the_name_cannot_carry_a_path_or_a_second_extension():
    """Имя приходит от клиента, значит из него остаётся только безопасное."""
    assert _slug("../../etc/passwd", ".pdf") == "passwd.pdf"
    assert _slug("отчёт.pdf.exe", ".pdf") == "otchet-pdf.pdf"
    assert _slug('a"b/c\\d.png', ".png") == "d.png"
    # Ни одной годной буквы — лучше «file», чем пустое имя или точка.
    assert _slug("日本語.png", ".png") == "file.png"
    assert _slug(None, ".png") == "file.png"


def test_a_very_long_name_is_cut_but_stays_a_name():
    slug = _slug("очень " * 40 + "длинное имя.pdf", ".pdf")
    assert slug.endswith(".pdf")
    assert len(slug) <= 65
    assert not slug.startswith("-") and "--" not in slug


@pytest.mark.asyncio
async def test_the_uploaded_file_keeps_its_name_in_the_url(api, auth, owner: Client, make_bot):
    bot, _ = await make_bot(owner, [])

    res = await api.post(
        f"/api/bots/{bot.id}/media/upload",
        headers=auth(owner),
        files={"file": ("Гайд по выпечке.pdf", PDF, "application/pdf")},
    )

    assert res.status_code == 201, res.text
    url = res.json()["url"]
    assert url.endswith("-Gayd-po-vypechke.pdf"), url


@pytest.mark.asyncio
async def test_two_files_with_one_name_do_not_overwrite_each_other(
    api, auth, owner: Client, make_bot
):
    """Читаемое имя не должно стоить уникальности: «photo.png» у всех один."""
    bot, _ = await make_bot(owner, [])

    first = await api.post(
        f"/api/bots/{bot.id}/media/upload",
        headers=auth(owner),
        files={"file": ("photo.png", PNG, "image/png")},
    )
    second = await api.post(
        f"/api/bots/{bot.id}/media/upload",
        headers=auth(owner),
        files={"file": ("photo.png", PNG + b"different", "image/png")},
    )

    assert first.status_code == 201 and second.status_code == 201
    assert first.json()["url"] != second.json()["url"]


# ------------------------------------------- недоставленный заказ: ещё раз


async def _paid_order(db: AsyncSession, bot, block, **meta) -> Payment:
    payment = Payment(
        id=uuid.uuid4(),
        kind=PaymentKind.order,
        status=PaymentStatus.paid,
        provider="test",
        amount_minor=390000,
        currency="RUB",
        description="Пак пресетов",
        bot_id=bot.id,
        block_id=block.id,
        telegram_user_id=USER_ID,
        chat_id=CHAT_ID,
        meta=meta,
        paid_at=datetime.now(timezone.utc),
    )
    db.add(payment)
    await db.commit()
    return payment


@pytest.mark.asyncio
async def test_an_undelivered_order_can_be_sent_again(
    api, auth, owner: Client, make_bot, db: AsyncSession, monkeypatch
):
    """Автоматика сдаётся после шести попыток — и до этого на этом всё и
    заканчивалось: владельцу оставался только возврат."""
    bot, blocks = await make_bot(
        owner, [(BlockType.payment, {"title": "Пак пресетов", "price": "3900"})], provider="test"
    )
    order = await _paid_order(
        db, bot, blocks[0],
        delivery_attempts=6,
        delivery_gave_up_at=datetime.now(timezone.utc).isoformat(),
    )

    queued: list[uuid.UUID] = []
    monkeypatch.setattr(
        "app.services.payment_service.deliver_later", lambda payment_id: queued.append(payment_id)
    )

    res = await api.post(f"/api/bots/{bot.id}/orders/{order.id}/redeliver", headers=auth(owner))

    assert res.status_code == 200, res.text
    assert queued == [order.id], "выдачу не поставили в очередь"

    fresh = (
        await db.execute(
            select(Payment).where(Payment.id == order.id).execution_options(populate_existing=True)
        )
    ).scalar_one()
    # Счётчик сброшен: если и эта отправка не дойдёт, автоматический дозвон
    # должен взяться за заказ заново, а не считать его давно закрытым.
    assert fresh.meta.get("delivery_attempts") == 0
    assert "delivery_gave_up_at" not in fresh.meta


@pytest.mark.asyncio
async def test_an_unpaid_order_is_not_sent_again(
    api, auth, owner: Client, make_bot, db: AsyncSession
):
    """«Отправить ещё раз» по неоплаченному — это отдать товар бесплатно."""
    bot, blocks = await make_bot(
        owner, [(BlockType.payment, {"title": "Пак пресетов", "price": "3900"})], provider="test"
    )
    order = await _paid_order(db, bot, blocks[0])
    order.status = PaymentStatus.pending
    order.paid_at = None
    await db.commit()

    res = await api.post(f"/api/bots/{bot.id}/orders/{order.id}/redeliver", headers=auth(owner))

    assert res.status_code == 400


@pytest.mark.asyncio
async def test_a_stranger_cannot_resend_someone_elses_order(
    api, auth, owner: Client, stranger: Client, make_bot, db: AsyncSession
):
    bot, blocks = await make_bot(
        owner, [(BlockType.payment, {"title": "Пак пресетов", "price": "3900"})], provider="test"
    )
    order = await _paid_order(db, bot, blocks[0])

    res = await api.post(f"/api/bots/{bot.id}/orders/{order.id}/redeliver", headers=auth(stranger))

    assert res.status_code == 404


# ------------------------------------------------- выгрузка: столбец статуса


@pytest.mark.asyncio
async def test_the_export_says_the_status_in_russian(
    api, auth, owner: Client, make_bot, db: AsyncSession
):
    """Таблицу пересылают бухгалтеру, и `refunded` ему не говорит ничего."""
    bot, blocks = await make_bot(
        owner, [(BlockType.payment, {"title": "Пак пресетов", "price": "3900"})], provider="test"
    )
    paid = await _paid_order(db, bot, blocks[0], delivered_at=datetime.now(timezone.utc).isoformat())
    returned = await _paid_order(db, bot, blocks[0])
    returned.status = PaymentStatus.refunded
    await db.commit()

    body = (await api.get(f"/api/bots/{bot.id}/orders.csv", headers=auth(owner))).text

    assert "оплачен" in body and "возврат" in body
    assert "paid" not in body and "refunded" not in body
    assert str(paid.invoice_no) in body and str(returned.invoice_no) in body


# --------------------------------------- подписчик узнаёт, как перестать


@pytest.mark.asyncio
async def test_the_first_charge_says_how_to_stop_the_next_one(
    db: AsyncSession, owner: Client, make_bot, as_bot
):
    """Команда /cancel была с самого начала — и не называлась нигде.

    Списание с сохранённой карты, которое нечем остановить, человек
    останавливает через банк: для продавца это уже не отписка, а спор по
    платежу.
    """
    from app.services import bot_dispatcher, payment_service

    bot, _ = await make_bot(
        owner,
        [
            (BlockType.payment, {
                "title": "Клуб", "price": "990", "currency": "RUB",
                "subscription": True, "period_days": 30,
            }),
            (BlockType.delivery, {"text": "ССЫЛКА НА КЛУБ"}),
        ],
        provider="test",
    )
    await bot_dispatcher.process_update(
        as_bot, {"message": {"chat": {"id": CHAT_ID}, "from": {"id": USER_ID}, "text": "/start"}}, bot.id, db
    )
    payment = (
        await db.execute(select(Payment).where(Payment.bot_id == bot.id))
    ).scalar_one()

    await payment_service.apply_result(
        db, payment, WebhookResult(status=PaymentStatus.paid, provider_payment_id="x")
    )

    receipt = next(m for m in as_bot.sent() if "Оплата получена" in m)
    assert "/cancel" in receipt, "покупателю не сказали, как остановить списания"


@pytest.mark.asyncio
async def test_a_one_off_purchase_is_not_told_about_cancelling(
    db: AsyncSession, owner: Client, make_bot, as_bot
):
    """Разовая покупка — не подписка: «отменить списания» там пугает зря."""
    from app.services import bot_dispatcher, payment_service

    bot, _ = await make_bot(
        owner,
        [
            (BlockType.payment, {"title": "Гайд", "price": "990", "currency": "RUB"}),
            (BlockType.delivery, {"text": "ВОТ ГАЙД"}),
        ],
        provider="test",
    )
    await bot_dispatcher.process_update(
        as_bot, {"message": {"chat": {"id": CHAT_ID}, "from": {"id": USER_ID}, "text": "/start"}}, bot.id, db
    )
    payment = (
        await db.execute(select(Payment).where(Payment.bot_id == bot.id))
    ).scalar_one()

    await payment_service.apply_result(
        db, payment, WebhookResult(status=PaymentStatus.paid, provider_payment_id="x")
    )

    receipt = next(m for m in as_bot.sent() if "Оплата получена" in m)
    assert "/cancel" not in receipt
