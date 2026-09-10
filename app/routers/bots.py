import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import get_settings
from app.database import get_db
from app.deps import get_current_client
from app.models.bot import Bot, BotStatus
from app.models.bot_block import BotBlock
from app.models.client import Client
from app.schemas.bot import BotOut, BotUpdate, BotWithBlocksOut, PublishRequest, PublishResponse
from app.schemas.client import ClientOut
from app.services import bot_registry
from app.services.security import decrypt_token, encrypt_token
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
) -> list[BotOut]:
    stmt = (
        select(Bot, func.count(BotBlock.id))
        .outerjoin(BotBlock, BotBlock.bot_id == Bot.id)
        .where(Bot.client_id == client.id)
        .group_by(Bot.id)
        .order_by(Bot.created_at.desc())
    )
    result = await db.execute(stmt)
    return [
        BotOut.model_validate(bot, from_attributes=True).model_copy(update={"block_count": count})
        for bot, count in result.all()
    ]


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


@router.patch("/bots/{bot_id}", response_model=BotOut)
async def update_bot(
    bot_id: uuid.UUID,
    payload: BotUpdate,
    client: Client = Depends(get_current_client),
    db: AsyncSession = Depends(get_db),
) -> Bot:
    bot = await _get_owned_bot(bot_id, client, db)
    if payload.name is not None:
        bot.name = payload.name.strip() or None
    if "start_block_id" in payload.model_fields_set:
        if payload.start_block_id is not None:
            result = await db.execute(
                select(BotBlock.id).where(BotBlock.id == payload.start_block_id, BotBlock.bot_id == bot_id)
            )
            if result.scalar_one_or_none() is None:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Блок не принадлежит этому боту")
        bot.start_block_id = payload.start_block_id
    await db.commit()
    await db.refresh(bot)
    return bot


@router.delete("/bots/{bot_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_bot(
    bot_id: uuid.UUID,
    client: Client = Depends(get_current_client),
    db: AsyncSession = Depends(get_db),
) -> None:
    bot = await _get_owned_bot(bot_id, client, db)

    token = decrypt_token(bot.bot_token_encrypted) if bot.bot_token_encrypted else None
    # Best-effort: detach the webhook and drop the cached Bot instance
    # before the row (and its blocks, via ON DELETE CASCADE) disappear.
    await bot_registry.remove(bot_id, token)

    await db.delete(bot)
    await db.commit()


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

    # The test provider's checkout page marks an order paid the moment it is
    # opened — that is its entire purpose, and it is exactly why a live bot
    # must not carry it: anyone who tapped the button would get the goods.
    if bot.payment_provider == "test":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "У бота выбрана «Тестовая оплата» — она отдаёт товар без денег. "
                "Подключи настоящую платёжную систему перед публикацией."
            ),
        )

    # Building a bot is free; putting it on the air is what's paid for.
    # A price of 0 (the default) leaves publishing open — the paywall only
    # exists once one is configured.
    settings = get_settings()
    if settings.publication_price_minor > 0 and bot.publication_paid_at is None:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail="Публикация бота не оплачена",
        )

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
