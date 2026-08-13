import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.deps import get_current_client
from app.models.bot import Bot, BotStatus
from app.models.client import Client
from app.schemas.bot import BotOut, BotWithBlocksOut, PublishRequest, PublishResponse
from app.schemas.client import ClientOut
from app.services import bot_registry
from app.services.security import encrypt_token
from app.services.telegram_validator import InvalidBotToken, validate_bot_token

router = APIRouter(prefix="/api", tags=["bots"])


async def _get_owned_bot(bot_id: uuid.UUID, client: Client, db: AsyncSession, *, with_blocks: bool = False) -> Bot:
    stmt = select(Bot).where(Bot.id == bot_id, Bot.client_id == client.id)
    if with_blocks:
        stmt = stmt.options(selectinload(Bot.blocks))
    result = await db.execute(stmt)
    bot = result.scalar_one_or_none()
    if bot is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Bot not found")
    return bot


@router.get("/me", response_model=ClientOut)
async def get_me(client: Client = Depends(get_current_client)) -> Client:
    return client


@router.get("/bots", response_model=list[BotOut])
async def list_bots(
    client: Client = Depends(get_current_client),
    db: AsyncSession = Depends(get_db),
) -> list[Bot]:
    result = await db.execute(select(Bot).where(Bot.client_id == client.id).order_by(Bot.created_at.desc()))
    return list(result.scalars().all())


@router.post("/bots", response_model=BotOut, status_code=status.HTTP_201_CREATED)
async def create_bot(
    client: Client = Depends(get_current_client),
    db: AsyncSession = Depends(get_db),
) -> Bot:
    bot = Bot(client_id=client.id, status=BotStatus.draft)
    db.add(bot)
    await db.commit()
    await db.refresh(bot)
    return bot


@router.get("/bots/{bot_id}", response_model=BotWithBlocksOut)
async def get_bot(
    bot_id: uuid.UUID,
    client: Client = Depends(get_current_client),
    db: AsyncSession = Depends(get_db),
) -> Bot:
    return await _get_owned_bot(bot_id, client, db, with_blocks=True)


@router.post("/bots/{bot_id}/publish", response_model=PublishResponse)
async def publish_bot(
    bot_id: uuid.UUID,
    payload: PublishRequest,
    client: Client = Depends(get_current_client),
    db: AsyncSession = Depends(get_db),
) -> PublishResponse:
    bot = await _get_owned_bot(bot_id, client, db)

    if bot.status != BotStatus.draft:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Бот уже опубликован")

    try:
        me = await validate_bot_token(payload.token)
    except InvalidBotToken as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    bot.bot_token_encrypted = encrypt_token(payload.token.strip())
    bot.telegram_bot_username = me.username
    bot.status = BotStatus.active
    bot.published_at = datetime.now(timezone.utc)
    await db.commit()

    # Register the webhook with Telegram, and warm the in-memory registry.
    await bot_registry.register_webhook(bot.id, payload.token.strip())

    return PublishResponse(status=bot.status, telegram_bot_username=bot.telegram_bot_username)
