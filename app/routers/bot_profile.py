"""Оформление бота в Telegram: имя, «Что умеет этот бот» (описание до /start),
короткое описание для профиля и фото.

Всё это настройки самого бота у Telegram, а не наши данные: читаем и пишем их
через Bot API токеном бота, ничего у себя не храним. Раньше для этого нужно
было идти в @BotFather.
"""

from __future__ import annotations

import logging
import uuid

from aiogram import Bot as AiogramBot
from aiogram.types import BufferedInputFile, InputProfilePhotoStatic
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.deps import get_current_client
from app.models.bot import Bot
from app.models.client import Client
from app.services.security import decrypt_token
from app.services.telegram_session import build_bot_session

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/bots/{bot_id}/profile", tags=["bot-profile"])

MAX_PHOTO_BYTES = 5 * 1024 * 1024


class ProfileOut(BaseModel):
    name: str = ""
    short_description: str = ""
    description: str = ""


class ProfileIn(BaseModel):
    name: str | None = Field(default=None, max_length=64)
    short_description: str | None = Field(default=None, max_length=120)
    description: str | None = Field(default=None, max_length=512)


async def _owned_bot_token(bot_id: uuid.UUID, client: Client, db: AsyncSession) -> str:
    bot = (
        await db.execute(select(Bot).where(Bot.id == bot_id, Bot.client_id == client.id))
    ).scalar_one_or_none()
    if bot is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Bot not found")
    if not bot.bot_token_encrypted:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Оформление доступно после запуска: сначала вставь токен бота и опубликуй его.",
        )
    return decrypt_token(bot.bot_token_encrypted)


def _telegram_error(exc: Exception, token: str = "") -> HTTPException:
    """Ошибка Bot API человеческими словами. Сырой английский ответ Telegram владельцу ни к чему,
    а токен в тексте исключения не должен ни попасть в журнал, ни уйти в браузер."""
    raw = str(exc)
    if token:
        raw = raw.replace(token, "***")
    logger.info("Bot profile call failed: %s", raw)
    low = raw.lower()
    if "too many requests" in low or "retry after" in low:
        text = "Telegram просит подождать: оформление можно менять не чаще, чем раз в несколько минут."
    elif "photo" in low or "image" in low or "file" in low:
        text = "Telegram не принял фото. Попробуй другую картинку (JPG или PNG, без анимации)."
    elif "unauthorized" in low or "token" in low:
        text = "Telegram не принял токен бота. Если ты его перевыпускал в @BotFather, вставь новый при публикации."
    elif "not found" in low or "network" in low or "timeout" in low or "connect" in low:
        text = "Не получилось связаться с Telegram. Попробуй ещё раз чуть позже."
    else:
        text = "Telegram не принял изменение. Проверь значения и попробуй ещё раз."
    return HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=text)


@router.get("", response_model=ProfileOut)
async def get_profile(
    bot_id: uuid.UUID, client: Client = Depends(get_current_client), db: AsyncSession = Depends(get_db)
) -> ProfileOut:
    token = await _owned_bot_token(bot_id, client, db)
    bot = AiogramBot(token=token, session=build_bot_session())
    try:
        name = await bot.get_my_name()
        short = await bot.get_my_short_description()
        long = await bot.get_my_description()
    except Exception as exc:  # noqa: BLE001
        raise _telegram_error(exc, token) from exc
    finally:
        await bot.session.close()
    return ProfileOut(name=name.name, short_description=short.short_description, description=long.description)


@router.put("", response_model=ProfileOut)
async def update_profile(
    bot_id: uuid.UUID,
    payload: ProfileIn,
    client: Client = Depends(get_current_client),
    db: AsyncSession = Depends(get_db),
) -> ProfileOut:
    token = await _owned_bot_token(bot_id, client, db)
    bot = AiogramBot(token=token, session=build_bot_session())
    try:
        if payload.name is not None:
            await bot.set_my_name(name=payload.name.strip())
        if payload.short_description is not None:
            await bot.set_my_short_description(short_description=payload.short_description.strip())
        if payload.description is not None:
            await bot.set_my_description(description=payload.description.strip())
        name = await bot.get_my_name()
        short = await bot.get_my_short_description()
        long = await bot.get_my_description()
    except Exception as exc:  # noqa: BLE001
        raise _telegram_error(exc, token) from exc
    finally:
        await bot.session.close()
    return ProfileOut(name=name.name, short_description=short.short_description, description=long.description)


@router.post("/photo", status_code=status.HTTP_204_NO_CONTENT)
async def set_photo(
    bot_id: uuid.UUID,
    file: UploadFile = File(...),
    client: Client = Depends(get_current_client),
    db: AsyncSession = Depends(get_db),
) -> None:
    token = await _owned_bot_token(bot_id, client, db)
    data = await file.read(MAX_PHOTO_BYTES + 1)
    if len(data) > MAX_PHOTO_BYTES:
        raise HTTPException(status_code=status.HTTP_413_CONTENT_TOO_LARGE, detail="Фото больше 5 МБ")
    # Telegram принимает для аватара только JPEG (конвертацию делает редактор).
    if not data.startswith(b"\xff\xd8\xff"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Нужна фотография в формате JPG")
    bot = AiogramBot(token=token, session=build_bot_session())
    try:
        await bot.set_my_profile_photo(
            photo=InputProfilePhotoStatic(photo=BufferedInputFile(data, filename="avatar.jpg"))
        )
    except Exception as exc:  # noqa: BLE001
        raise _telegram_error(exc, token) from exc
    finally:
        await bot.session.close()


@router.delete("/photo", status_code=status.HTTP_204_NO_CONTENT)
async def remove_photo(
    bot_id: uuid.UUID, client: Client = Depends(get_current_client), db: AsyncSession = Depends(get_db)
) -> None:
    token = await _owned_bot_token(bot_id, client, db)
    bot = AiogramBot(token=token, session=build_bot_session())
    try:
        await bot.remove_my_profile_photo()
    except Exception as exc:  # noqa: BLE001
        raise _telegram_error(exc, token) from exc
    finally:
        await bot.session.close()
