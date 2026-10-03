"""Платёжные записи — это учёт и доказательства для споров: удаление бота или
аккаунта их не стирает, только отвязывает."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.bot_block import BlockType
from app.models.client import Client
from app.models.payment import Payment, PaymentKind, PaymentStatus


@pytest.mark.asyncio
async def test_deleting_a_bot_keeps_its_payments(db: AsyncSession, owner: Client, make_bot):
    bot, _ = await make_bot(owner, [(BlockType.welcome, {"text": "привет"})])
    pid = uuid.uuid4()
    db.add(
        Payment(
            id=pid, kind=PaymentKind.publication, status=PaymentStatus.paid, provider="test",
            amount_minor=990, currency="USD", description="запуск", bot_id=bot.id, client_id=owner.id,
            meta={}, paid_at=datetime.now(timezone.utc),
        )
    )
    await db.commit()

    await db.delete(bot)
    await db.commit()

    kept = (await db.execute(select(Payment).where(Payment.id == pid))).scalar_one()
    assert kept.status == PaymentStatus.paid
    assert kept.amount_minor == 990
    assert kept.bot_id is None
