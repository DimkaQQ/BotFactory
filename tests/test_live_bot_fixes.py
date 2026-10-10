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
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models.bot import Bot as BotModel
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


# ---------------------------------------- с кем человек вообще имеет дело


@pytest.fixture
def with_requisites(monkeypatch):
    """Реквизиты заполнены — как у развёрнутого сервиса, который продаёт."""

    monkeypatch.setenv("LEGAL_NAME", 'ИП «Ромашка» & Co')
    monkeypatch.setenv("LEGAL_ID", "ИИН 123456789012")
    monkeypatch.setenv("SUPPORT_TELEGRAM", "@bf_support")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.mark.asyncio
async def test_the_offer_and_the_privacy_policy_are_published(api, with_requisites):
    """Сервис берёт деньги — значит должно быть написано, с кем человек
    договаривается и как вернуть оплату."""
    offer = await api.get("/legal/offer")
    privacy = await api.get("/legal/privacy")

    assert offer.status_code == 200 and privacy.status_code == 200
    assert "text/html" in offer.headers["content-type"]
    for body in (offer.text, privacy.text):
        # Название с кавычками и амперсандом не должно разъехаться в HTML.
        assert "ИП «Ромашка» &amp; Co" in body
        # И ни одного места, где то же название попало в HTML сырым.
        assert "«Ромашка» & Co" not in body
        assert "ИИН 123456789012" in body
        assert "bf_support" in body
    assert "Возврат" in offer.text
    assert "/cancel" in privacy.text


@pytest.mark.asyncio
async def test_an_unsigned_offer_is_not_published_at_all(api, monkeypatch):
    """Оферта, подписанная никем, хуже отсутствующей: первый же спор по
    платежу упирается в то, с кем человек договаривался."""

    monkeypatch.setenv("LEGAL_NAME", "")
    monkeypatch.setenv("LEGAL_ID", "")
    get_settings.cache_clear()
    try:
        assert (await api.get("/legal/offer")).status_code == 404
        assert (await api.get("/legal/privacy")).status_code == 404

        config = (await api.get("/api/config")).json()
        # И ссылок на них на сайте тогда тоже нет.
        assert config["legal_documents"] is False
        assert config["legal_name"] == ""
    finally:
        get_settings.cache_clear()


@pytest.mark.asyncio
async def test_support_always_has_an_address(api, monkeypatch):
    """Не завели своей поддержки — остаётся наш собственный бот. Экрана без
    единого способа написать живому человеку быть не должно."""

    monkeypatch.setenv("SUPPORT_TELEGRAM", "")
    monkeypatch.setenv("META_BOT_USERNAME", "bot_factory_bot")
    get_settings.cache_clear()
    try:
        config = (await api.get("/api/config")).json()
        assert config["support_telegram"] == "bot_factory_bot"
    finally:
        get_settings.cache_clear()


# --------------------------------------- выгрузка, которую опасно открыть


@pytest.mark.asyncio
async def test_a_buyer_name_cannot_become_a_formula_in_the_export(
    api, auth, owner: Client, make_bot, db: AsyncSession
):
    """Имя покупателя приходит из Telegram как есть, а файл мы собираем для
    Excel — BOM стоит именно ради него. Имя с «=» в начале Excel открывает
    как формулу и предлагает выполнить."""
    from app.models.bot_subscriber import BotSubscriber

    bot, blocks = await make_bot(
        owner, [(BlockType.payment, {"title": "Гайд", "price": "990"})], provider="test"
    )
    db.add(BotSubscriber(
        bot_id=bot.id, telegram_user_id=USER_ID, chat_id=CHAT_ID,
        first_name="=cmd|' /C calc'!A0", username="ok",
    ))
    order = await _paid_order(db, bot, blocks[0])
    order.description = "@SUM(1+1)"
    await db.commit()

    body = (await api.get(f"/api/bots/{bot.id}/orders.csv", headers=auth(owner))).text

    assert "'=cmd|" in body, "имя ушло в таблицу как формула"
    assert "'@SUM(1+1)" in body, "название товара ушло как формула"
    # Обычное имя апострофом не уродуем.
    assert ";Гайд;" not in body or "'Гайд" not in body


# ------------------------------------------- подтверждение без доставки


@pytest.mark.asyncio
async def test_confirming_an_order_does_not_claim_a_delivery_that_failed(
    db: AsyncSession, owner: Client, make_bot, as_bot, monkeypatch
):
    """Покупатель заблокировал бота — владельцу всё равно приходило
    «товар отправлен покупателю»."""
    from app.services import bot_dispatcher

    bot, blocks = await make_bot(
        owner,
        [
            (BlockType.payment, {"title": "Гайд", "price": "990"}),
            (BlockType.delivery, {"text": "ВОТ ГАЙД"}),
        ],
        provider="link",
    )
    order = await _paid_order(db, bot, blocks[0])
    order.status = PaymentStatus.pending
    order.paid_at = None
    await db.commit()

    async def blocked(chat_id, text, **kwargs):
        # Покупателю — нельзя, владельцу — можно.
        if chat_id == CHAT_ID:
            raise RuntimeError("Forbidden: bot was blocked by the user")

    as_bot.send_message.side_effect = blocked
    monkeypatch.setattr(bot_dispatcher, "_is_owner", AsyncMock(return_value=True))

    await bot_dispatcher.process_update(
        as_bot,
        {"callback_query": {
            "id": "1",
            "from": {"id": owner.telegram_user_id},
            "message": {"chat": {"id": owner.telegram_user_id}},
            "data": f"payok:{order.id.hex}",
        }},
        bot.id,
        db,
    )

    said = " ".join(str(c) for c in as_bot.send_message.call_args_list)
    assert "товар отправлен покупателю" not in said, "владельцу пообещали доставку, которой не было"
    assert "не дошёл" in said


# ------------------------------- бот, снятый с эфира, больше не отвечает


@pytest.mark.asyncio
async def test_a_suspended_bot_stops_answering_even_if_it_is_cached(
    db: AsyncSession, owner: Client, make_bot
):
    """Кеш живёт в памяти процесса, а снять бота с эфира может другой.

    Так делает `platform_billing.sweep` за неоплаченный период: владельцу
    написали «бот ушёл с эфира», а бот продолжал отвечать из тех процессов,
    где он был закеширован, — то есть работал бесплатно.
    """

    from app.models.bot import BotStatus
    from app.services import bot_registry, security

    bot, _ = await make_bot(owner, [], status=BotStatus.active)
    bot.bot_token_encrypted = security.encrypt_token("111111:AA-token")
    await db.commit()

    first = await bot_registry.get_or_create(bot.id, db)
    assert first is not None, "живой бот должен отвечать"
    # Тот же экземпляр, пока ничего не изменилось: лишних сессий не плодим.
    assert await bot_registry.get_or_create(bot.id, db) is first

    # Другой процесс снял бота с эфира.
    await db.execute(
        BotModel.__table__.update().where(BotModel.id == bot.id).values(status=BotStatus.disabled)
    )
    await db.commit()

    assert await bot_registry.get_or_create(bot.id, db) is None, "снятый бот всё ещё отвечает"
    assert bot.id not in bot_registry._registry, "экземпляр остался в кеше"


@pytest.mark.asyncio
async def test_a_reissued_token_replaces_the_cached_bot(db: AsyncSession, owner: Client, make_bot):
    """Токен перевыпущен у @BotFather — кешированный экземпляр говорит со
    старым и получает от Telegram отказ на каждое сообщение."""
    from app.models.bot import BotStatus
    from app.services import bot_registry, security

    bot, _ = await make_bot(owner, [], status=BotStatus.active)
    bot.bot_token_encrypted = security.encrypt_token("111111:AA-old")
    await db.commit()

    first = await bot_registry.get_or_create(bot.id, db)

    await db.execute(
        BotModel.__table__.update()
        .where(BotModel.id == bot.id)
        .values(bot_token_encrypted=security.encrypt_token("222222:BB-new"))
    )
    await db.commit()

    second = await bot_registry.get_or_create(bot.id, db)
    assert second is not first, "бот отвечает со старым токеном"
    assert second is not None and second.token == "222222:BB-new"


# --------------------------------------------- выход, который закрывает


@pytest.mark.asyncio
async def test_logging_out_closes_the_token_everywhere(api, auth, owner: Client):
    """Стереть токен в браузере — не то же самое, что выйти.

    Токен живёт тридцать дней, и до этого отозвать его было нечем: на общем
    компьютере «Выйти» не закрывало ни кассу, ни список покупателей, ни
    кнопку снятия бота с эфира.
    """
    stolen = auth(owner)

    assert (await api.get("/api/bots", headers=stolen)).status_code == 200

    assert (await api.post("/api/auth/logout", headers=stolen)).status_code == 204

    refused = await api.get("/api/bots", headers=stolen)
    assert refused.status_code == 401, "старый токен всё ещё работает"
    # И на других эндпоинтах тоже, а не только на том, где проверили.
    assert (await api.get("/api/me", headers=stolen)).status_code == 401


@pytest.mark.asyncio
async def test_logging_in_again_works_right_after_logging_out(api, auth, owner: Client):
    """Выход не должен запирать аккаунт: следующий вход выдаёт новый токен,
    и он обязан приниматься."""
    from app.services.session_token import create_session_token

    await api.post("/api/auth/logout", headers=auth(owner))

    fresh = {"Authorization": f"Bearer {create_session_token(owner.id)}"}
    assert (await api.get("/api/bots", headers=fresh)).status_code == 200


@pytest.mark.asyncio
async def test_a_logout_does_not_reach_someone_else(api, auth, owner: Client, stranger: Client):
    """Выход закрывает свои токены, а не чужие."""
    others = auth(stranger)

    await api.post("/api/auth/logout", headers=auth(owner))

    assert (await api.get("/api/bots", headers=others)).status_code == 200
