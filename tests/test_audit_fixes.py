"""Дыры, найденные независимым аудитом, и то, что их закрывает.

Каждый тест здесь падал до исправления — это и есть причина, по которой он
написан. Все они про одно и то же семейство ошибок: внешний сервис (Telegram,
платёжный шлюз, браузер клиента) ведёт себя не идеально, а продукт считает,
что всё прошло.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models.bot import Bot as BotModel
from app.models.bot import BotStatus
from app.models.bot_block import BlockType
from app.models.client import Client
from app.models.payment import Payment, PaymentKind, PaymentStatus
from app.services import bot_dispatcher, payment_service, platform_billing

PRICED = json.dumps(
    [{
        "provider": "stripe", "price_minor": 9900, "renewal_price_minor": 990,
        "currency": "USD", "credentials": {"secret_key": "sk_test_x", "webhook_secret": "whsec_x"},
    }]
)


@pytest.fixture
def priced(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "platform_payment_methods", PRICED, raising=False)
    monkeypatch.setattr(settings, "renewal_period_days", 30, raising=False)
    monkeypatch.setattr(settings, "renewal_grace_days", 7, raising=False)
    return settings


# ------------------------------------------------- Б4: молчаливая недоставка


@pytest.mark.asyncio
async def test_a_refused_delivery_is_not_recorded_as_delivered(
    db: AsyncSession, owner: Client, make_bot, telegram, monkeypatch
):
    """Самое дорогое из найденного: Telegram отказал, а заказ помечен
    выданным — и подметальщик такой заказ больше никогда не увидит."""
    bot, blocks = await make_bot(
        owner,
        [(BlockType.payment, {"title": "Гайд", "price": "990"}),
         (BlockType.delivery, {"text": "вот твой файл"})],
        provider="test",
    )
    payment = Payment(
        id=uuid.uuid4(), kind=PaymentKind.order, status=PaymentStatus.paid,
        provider="test", amount_minor=99000, currency="RUB", description="Гайд",
        bot_id=bot.id, chat_id=555, telegram_user_id=555,
        meta={"deliver_from": str(blocks[1].id)}, paid_at=datetime.now(timezone.utc),
    )
    db.add(payment)
    await db.commit()

    # Ровно то, что делает Telegram с текстом длиннее 4096.
    telegram.send_message = AsyncMock(
        side_effect=[None, Exception("Bad Request: message is too long")]
    )
    monkeypatch.setattr(
        "app.services.bot_registry.get_or_create", AsyncMock(return_value=telegram)
    )

    await payment_service.resume_after_payment(db, payment)
    await db.refresh(payment)

    assert "delivered_at" not in (payment.meta or {}), (
        "заказ помечен выданным, хотя выдача не ушла — подметальщик его больше не найдёт"
    )


@pytest.mark.asyncio
async def test_a_delivered_order_is_still_stamped(
    db: AsyncSession, owner: Client, make_bot, telegram, monkeypatch
):
    """Обратная сторона: удачная выдача обязана штамповаться, иначе
    подметальщик будет выдавать товар по кругу."""
    bot, blocks = await make_bot(
        owner,
        [(BlockType.payment, {"title": "Гайд", "price": "990"}),
         (BlockType.delivery, {"text": "вот твой файл"})],
        provider="test",
    )
    payment = Payment(
        id=uuid.uuid4(), kind=PaymentKind.order, status=PaymentStatus.paid,
        provider="test", amount_minor=99000, currency="RUB", description="Гайд",
        bot_id=bot.id, chat_id=556, telegram_user_id=556,
        meta={"deliver_from": str(blocks[1].id)}, paid_at=datetime.now(timezone.utc),
    )
    db.add(payment)
    await db.commit()
    monkeypatch.setattr(
        "app.services.bot_registry.get_or_create", AsyncMock(return_value=telegram)
    )

    await payment_service.resume_after_payment(db, payment)
    await db.refresh(payment)

    assert "delivered_at" in (payment.meta or {})


def test_a_long_message_is_split_rather_than_refused():
    """Причина №1 отказа Telegram на блоке выдачи — текст длиннее 4096."""
    text = "\n\n".join("Абзац про сборку ПК. " * 40 for _ in range(8))
    assert len(text) > 4096

    pieces = bot_dispatcher._split_for_telegram(text)

    assert len(pieces) > 1
    assert all(len(p) <= 4096 for p in pieces)
    # Ничего не потеряно и порядок сохранён.
    assert "".join(p.replace("\n", "") for p in pieces).replace(" ", "") == text.replace("\n", "").replace(" ", "")
    # Короткое не трогаем.
    assert bot_dispatcher._split_for_telegram("привет") == ["привет"]


# ------------------------------------------ Б2: сбой Telegram при публикации


@pytest.mark.asyncio
async def test_a_failed_webhook_leaves_the_bot_republishable(
    api, auth, owner: Client, make_bot, monkeypatch
):
    """Клиент заплатил за запуск, Telegram икнул — и бот оставался «в эфире»
    без вебхука, а повторная публикация отбивалась «уже опубликован»."""
    bot, _ = await make_bot(
        owner, [(BlockType.welcome, {"text": "привет"})], status=BotStatus.draft, provider="yookassa"
    )
    monkeypatch.setattr(
        "app.services.telegram_validator.validate_bot_token",
        AsyncMock(return_value=type("Me", (), {"username": "shop_bot"})()),
    )
    monkeypatch.setattr("app.routers.bots.validate_bot_token",
                        AsyncMock(return_value=type("Me", (), {"username": "shop_bot"})()))
    monkeypatch.setattr(
        "app.services.bot_registry.register_webhook",
        AsyncMock(side_effect=Exception("Telegram 500")),
    )

    first = await api.post(
        f"/api/bots/{bot.id}/publish", headers=auth(owner), json={"token": "123:abc"}
    )
    assert first.status_code == 502
    assert "ещё раз" in first.json()["detail"]

    # Статус не тронут — значит, попытка повторима.
    fresh = await api.get(f"/api/bots/{bot.id}", headers=auth(owner))
    assert fresh.json()["status"] == "draft"

    monkeypatch.setattr("app.services.bot_registry.register_webhook", AsyncMock(return_value=None))
    second = await api.post(
        f"/api/bots/{bot.id}/publish", headers=auth(owner), json={"token": "123:abc"}
    )
    assert second.status_code == 200
    assert second.json()["status"] == "active"


@pytest.mark.asyncio
async def test_a_live_bot_can_republish_to_repair_its_webhook(
    api, auth, owner: Client, make_bot, monkeypatch
):
    """Вторая половина Б2. Если вебхук всё-таки потерялся на уже живом боте —
    а это ровно то, что оставляла старая последовательность, — «Опубликовать»
    обязана работать как кнопка «переподключить». Раньше отбивалось «Бот уже
    опубликован», и владелец не мог сделать ничего."""
    bot, _ = await make_bot(
        owner, [(BlockType.welcome, {"text": "привет"})], status=BotStatus.active, provider="yookassa"
    )
    monkeypatch.setattr("app.routers.bots.validate_bot_token",
                        AsyncMock(return_value=type("Me", (), {"username": "shop_bot"})()))
    registered = []

    async def remember(bot_id, token):
        registered.append(bot_id)

    monkeypatch.setattr("app.services.bot_registry.register_webhook", remember)

    again = await api.post(
        f"/api/bots/{bot.id}/publish", headers=auth(owner), json={"token": "123:abc"}
    )

    assert again.status_code == 200
    assert registered == [bot.id], "повторная публикация не переставила вебхук"


@pytest.mark.asyncio
async def test_a_suspended_bot_is_not_republished_behind_the_paywall(
    api, auth, owner: Client, make_bot, monkeypatch
):
    """Но разрешение публиковать живого бота не должно стать лазейкой: снятый
    за неоплату возвращается только оплатой, а не кнопкой «Опубликовать»."""
    bot, _ = await make_bot(
        owner, [(BlockType.welcome, {"text": "привет"})], status=BotStatus.disabled, provider="yookassa"
    )
    monkeypatch.setattr("app.routers.bots.validate_bot_token",
                        AsyncMock(return_value=type("Me", (), {"username": "shop_bot"})()))
    monkeypatch.setattr("app.services.bot_registry.register_webhook", AsyncMock())

    refused = await api.post(
        f"/api/bots/{bot.id}/publish", headers=auth(owner), json={"token": "123:abc"}
    )

    assert refused.status_code == 400
    assert "продли" in refused.json()["detail"].lower()


# --------------------------------- Б3: сбой Telegram при возврате в эфир


@pytest.mark.asyncio
async def test_a_renewal_whose_webhook_failed_is_retried_by_the_sweep(
    db: AsyncSession, owner: Client, make_bot, priced, monkeypatch
):
    """Оплата прошла, Telegram отказал — бот обязан вернуться сам, а не ждать
    деплоя. И колбэк провайдера при этом не должен падать."""
    from app.services import security

    bot, _ = await make_bot(
        owner, [(BlockType.welcome, {"text": "привет"})], status=BotStatus.disabled
    )
    bot.bot_token_encrypted = security.encrypt_token("123:abc")
    bot.paid_until = datetime.now(timezone.utc) - timedelta(days=8)
    await db.commit()
    monkeypatch.setattr(platform_billing, "_tell_owner", AsyncMock())

    monkeypatch.setattr(
        "app.services.bot_registry.register_webhook", AsyncMock(side_effect=Exception("Telegram 500"))
    )
    payment = Payment(
        id=uuid.uuid4(), kind=PaymentKind.renewal, status=PaymentStatus.pending,
        provider="stripe", amount_minor=990, currency="USD", description="период",
        bot_id=bot.id, client_id=owner.id, meta={},
    )
    db.add(payment)
    await db.commit()

    # Колбэк провайдера отрабатывает штатно, несмотря на отказ Telegram.
    assert await payment_service.mark_paid(db, payment, provider_payment_id=None) is True
    await db.refresh(bot)
    assert bot.status == BotStatus.disabled
    assert bot.paid_until > datetime.now(timezone.utc)  # период оплачен

    # Telegram пришёл в себя — подметальщик поднимает бота сам.
    registered = []
    async def ok(bot_id, token):
        registered.append(bot_id)
    monkeypatch.setattr("app.services.bot_registry.register_webhook", ok)

    await platform_billing.sweep(db)
    await db.refresh(bot)

    assert bot.status == BotStatus.active
    assert registered == [bot.id]


# --------------------------------------- С1: двойная оплата публикации


@pytest.mark.asyncio
async def test_two_taps_do_not_open_two_launch_invoices(
    api, auth, owner: Client, make_bot, monkeypatch
):
    """Две вкладки — 198 $ за один запуск, и второй платёж не покупал ничего."""
    # Провайдер «test» — единственный, чей чекаут не ходит наружу; этот тест
    # проверяет переиспользование счёта, а не работу конкретного шлюза.
    monkeypatch.setattr(
        get_settings(),
        "platform_payment_methods",
        json.dumps([{"provider": "test", "price_minor": 9900, "renewal_price_minor": 990,
                     "currency": "USD", "credentials": {}, "is_test": True}]),
        raising=False,
    )
    bot, _ = await make_bot(owner, [(BlockType.welcome, {"text": "привет"})], status=BotStatus.draft)

    first = await api.post(f"/api/bots/{bot.id}/publication-checkout", headers=auth(owner), json={})
    second = await api.post(f"/api/bots/{bot.id}/publication-checkout", headers=auth(owner), json={})

    assert first.status_code == second.status_code == 200
    assert first.json()["id"] == second.json()["id"], "открылось два счёта на один запуск"


@pytest.mark.asyncio
async def test_a_second_launch_fee_at_least_buys_a_period(
    db: AsyncSession, owner: Client, make_bot, priced
):
    """Если два счёта всё же разошлись по времени и оба оплачены — деньги
    обязаны хоть что-то купить, а не пропасть молча."""
    bot, _ = await make_bot(owner, [(BlockType.welcome, {"text": "привет"})], status=BotStatus.draft)

    async def settle():
        payment = Payment(
            id=uuid.uuid4(), kind=PaymentKind.publication, status=PaymentStatus.pending,
            provider="stripe", amount_minor=9900, currency="USD", description="запуск",
            bot_id=bot.id, client_id=owner.id, meta={},
        )
        db.add(payment)
        await db.commit()
        await payment_service.mark_paid(db, payment, provider_payment_id=None)

    await settle()
    await db.refresh(bot)
    after_first = bot.paid_until

    await settle()
    await db.refresh(bot)

    assert bot.paid_until > after_first, "второй платёж не купил вообще ничего"


# ------------------------------------------------- С5: непарсящаяся цена


def test_a_malformed_price_names_itself():
    """`1.2.3` реально набирается в редакторе. Раньше это был ValueError,
    который вылетал раньше понятной проверки — покупатель видел «попробуй
    позже», владелец не узнавал ничего."""
    from app.services.payments import ProviderError

    assert payment_service.price_to_minor(None) == 0
    assert payment_service.price_to_minor("990,50") == 99050

    for bad in ("1.2.3", "990..50", "abc"):
        with pytest.raises(ProviderError) as exc:
            payment_service.price_to_minor(bad)
        assert bad in str(exc.value)


# ----------------------------------------------------- С3: пределы аккаунта


@pytest.mark.asyncio
async def test_one_account_cannot_fill_the_database(api, auth, owner: Client, monkeypatch):
    monkeypatch.setattr(get_settings(), "max_bots_per_client", 3, raising=False)

    codes = [(await api.post("/api/bots", headers=auth(owner))).status_code for _ in range(5)]

    assert codes[:3] == [201, 201, 201]
    assert codes[3:] == [409, 409]


@pytest.mark.asyncio
async def test_a_block_cannot_hold_megabytes(api, auth, owner: Client, make_bot):
    bot, _ = await make_bot(owner, [])

    huge = await api.post(
        f"/api/bots/{bot.id}/blocks",
        headers=auth(owner),
        json={"block_type": "description", "content": {"text": "я" * 200_000}},
    )

    assert huge.status_code == 413
