"""Команды владельца: блокировка закрывает вход и глушит ботов, выгрузка не содержит секретов."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app import admin
from app.models.bot_block import BlockType
from app.models.client import Client
from app.models.payment import Payment, PaymentKind, PaymentStatus
from app.services import owner_panel


@pytest.mark.asyncio
async def test_a_banned_account_is_shut_out_and_its_bots_go_quiet(db: AsyncSession, owner: Client, make_bot, api, auth):
    bot, _ = await make_bot(owner, [(BlockType.welcome, {"text": "привет"})])
    assert (await api.get("/api/bots", headers=auth(owner))).status_code == 200

    message = await admin.ban(db, owner.telegram_user_id, "спам")
    assert "на паузе — 1" in message

    await db.refresh(bot)
    assert bot.paused is True
    response = await api.get("/api/bots", headers=auth(owner))
    assert response.status_code == 403

    # а паузу снять самому нельзя
    await db.refresh(owner)
    with pytest.raises(owner_panel.PauseError):
        await owner_panel.set_paused(db, owner, bot.id, False)

    await admin.unban(db, owner.telegram_user_id)
    await db.refresh(owner)
    assert owner.banned_at is None


@pytest.mark.asyncio
async def test_the_export_has_the_payments_and_none_of_the_secrets(db: AsyncSession, owner: Client, make_bot):
    bot, _ = await make_bot(owner, [(BlockType.welcome, {"text": "привет"})])
    db.add(
        Payment(
            id=uuid.uuid4(), kind=PaymentKind.order, status=PaymentStatus.paid, provider="test",
            amount_minor=500, currency="RUB", description="товар", bot_id=bot.id, meta={},
            paid_at=datetime.now(timezone.utc),
        )
    )
    await db.commit()

    data = await admin.export(db, owner.telegram_user_id)
    assert data["client"]["telegram_user_id"] == owner.telegram_user_id
    assert len(data["bots"]) == 1 and data["bots"][0]["blocks"]
    assert len(data["payments"]) == 1
    flat = str(data)
    assert "bot_token_encrypted" not in flat and "payment_credentials_encrypted" not in flat
