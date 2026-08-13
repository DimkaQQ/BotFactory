"""Shared FastAPI dependencies."""

from __future__ import annotations

import uuid

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.bot import Bot
from app.models.client import Client
from app.services.telegram_validator import InvalidInitData, parse_init_data_user, validate_init_data


async def get_current_client(
    x_telegram_init_data: str = Header(..., alias="X-Telegram-Init-Data"),
    db: AsyncSession = Depends(get_db),
) -> Client:
    """Validate Telegram Web App initData and resolve/create the Client it belongs to."""

    try:
        parsed = validate_init_data(x_telegram_init_data)
        user = parse_init_data_user(parsed)
    except InvalidInitData as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc

    telegram_user_id = user["id"]
    full_name = " ".join(filter(None, [user.get("first_name"), user.get("last_name")])) or None

    result = await db.execute(select(Client).where(Client.telegram_user_id == telegram_user_id))
    client = result.scalar_one_or_none()

    if client is None:
        client = Client(telegram_user_id=telegram_user_id, full_name=full_name)
        db.add(client)
        await db.commit()
        await db.refresh(client)
    elif full_name and client.full_name != full_name:
        client.full_name = full_name
        await db.commit()

    return client


async def get_owned_bot(
    bot_id: uuid.UUID,
    client: Client = Depends(get_current_client),
    db: AsyncSession = Depends(get_db),
) -> Bot:
    """Resolve a bot by id, scoped to the current client — 404s if it's not theirs."""

    result = await db.execute(select(Bot).where(Bot.id == bot_id, Bot.client_id == client.id))
    bot = result.scalar_one_or_none()
    if bot is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Bot not found")
    return bot
