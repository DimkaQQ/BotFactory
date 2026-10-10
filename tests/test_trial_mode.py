"""Пробный режим: бот подключён к Telegram до оплаты, но отвечает только владельцу."""

from __future__ import annotations

import json
import uuid
from types import SimpleNamespace

import pytest

from app.config import get_settings
from app.models.bot import BotStatus
from app.models.bot_block import BlockType
from app.models.payment import Payment, PaymentKind, PaymentStatus
from app.services import bot_dispatcher, payment_service, platform_billing

PRICED = json.dumps(
    [{
        "provider": "stripe", "price_minor": 4900, "renewal_price_minor": 1500, "currency": "USD",
        "credentials": {"secret_key": "sk_test_x", "webhook_secret": "whsec_x"},
    }]
)


@pytest.fixture
def priced(monkeypatch):
    monkeypatch.setattr(get_settings(), "platform_payment_methods", PRICED, raising=False)


@pytest.fixture
def telegram_ok(monkeypatch):
    """Telegram «принимает» любой токен и вебхук; мета-бот не блокирует."""
    async def validate(token):
        return SimpleNamespace(username=f"bot_{uuid.uuid4().hex[:6]}")

    async def register(bot_id, token):
        return None

    async def reachable(_tg):
        return None

    monkeypatch.setattr("app.routers.bots.validate_bot_token", validate)
    monkeypatch.setattr("app.routers.bots.bot_registry.register_webhook", register)
    monkeypatch.setattr(platform_billing, "can_reach_owner", reachable)


async def _bot(api, headers):
    created = await api.post("/api/bots", headers=headers, json={"name": "Проба"})
    assert created.status_code in (200, 201), created.text
    bot_id = created.json()["id"]
    await api.post(f"/api/bots/{bot_id}/blocks", headers=headers, json={"block_type": "welcome", "content": {"text": "Привет"}})
    return bot_id


async def test_unpaid_publish_is_refused_but_a_trial_is_allowed(api, auth, owner, priced, telegram_ok):
    headers = auth(owner)
    bot_id = await _bot(api, headers)

    refused = await api.post(f"/api/bots/{bot_id}/publish", headers=headers, json={"token": "1:AA"})
    assert refused.status_code == 402

    trial = await api.post(f"/api/bots/{bot_id}/publish", headers=headers, json={"token": "1:AA", "trial": True})
    assert trial.status_code == 200, trial.text
    assert trial.json()["status"] == "active" and trial.json()["trial_mode"] is True

    shown = (await api.get(f"/api/bots/{bot_id}", headers=headers)).json()
    assert shown["trial_mode"] is True


async def test_trial_is_ignored_when_launch_is_free(api, auth, owner, telegram_ok, monkeypatch):
    monkeypatch.setattr(get_settings(), "platform_payment_methods", "", raising=False)
    headers = auth(owner)
    bot_id = await _bot(api, headers)

    published = await api.post(f"/api/bots/{bot_id}/publish", headers=headers, json={"token": "1:AA", "trial": True})

    assert published.status_code == 200
    assert published.json()["trial_mode"] is False


async def test_only_a_few_trial_bots_per_client(api, auth, owner, priced, telegram_ok, monkeypatch):
    monkeypatch.setattr(get_settings(), "max_trial_bots_per_client", 2, raising=False)
    headers = auth(owner)
    for _ in range(2):
        bot_id = await _bot(api, headers)
        ok = await api.post(f"/api/bots/{bot_id}/publish", headers=headers, json={"token": "1:AA", "trial": True})
        assert ok.status_code == 200
    third = await _bot(api, headers)

    blocked = await api.post(f"/api/bots/{third}/publish", headers=headers, json={"token": "1:AA", "trial": True})

    assert blocked.status_code == 409
    assert "Пробных ботов" in blocked.json()["detail"]


async def test_a_stranger_gets_a_polite_refusal_and_the_owner_is_served(db, owner, make_bot, telegram):
    bot, _blocks = await make_bot(owner, [(BlockType.welcome, {"text": "Привет, владелец"})])
    bot.trial_mode = True
    await db.commit()

    await bot_dispatcher.process_update(
        telegram, {"message": {"chat": {"id": 777}, "from": {"id": 777, "first_name": "Чужой"}, "text": "/start"}},
        bot.id, db,
    )
    assert any("пробном режиме" in text for text in telegram.sent())
    assert not any("владелец" in text for text in telegram.sent())

    telegram.reset_mock()
    await bot_dispatcher.process_update(
        telegram,
        {"message": {"chat": {"id": owner.telegram_user_id}, "from": {"id": owner.telegram_user_id}, "text": "/start"}},
        bot.id, db,
    )
    assert any("Привет, владелец" in text for text in telegram.sent())


async def test_paying_for_the_launch_opens_the_trial_bot_to_everyone(db, owner, make_bot, priced):
    bot, _ = await make_bot(owner, [(BlockType.welcome, {"text": "привет"})], status=BotStatus.active)
    bot.trial_mode = True
    await db.commit()
    payment = Payment(
        id=uuid.uuid4(), kind=PaymentKind.publication, status=PaymentStatus.pending, provider="stripe",
        amount_minor=4900, currency="USD", description="launch", bot_id=bot.id, client_id=bot.client_id, meta={},
    )
    db.add(payment)
    await db.commit()

    await payment_service.mark_paid(db, payment, provider_payment_id=None)
    await db.refresh(bot)

    assert bot.trial_mode is False
