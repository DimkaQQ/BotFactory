import asyncio
import contextlib
import logging
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

logger = logging.getLogger(__name__)

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


@router.get("/meta-bot/status")
async def meta_bot_status(client: Client = Depends(get_current_client)) -> dict:
    """Нажал ли владелец Start у мета-бота: туда приходят уведомления о продажах и
    сообщения о запуске. Запуск бота без этого закрыт (см. `publish_bot`)."""
    from app.services import platform_billing

    username = get_settings().meta_bot_username.lstrip("@").strip()
    reachable = await platform_billing.can_reach_owner(client.telegram_user_id)
    return {
        "configured": reachable is not None or bool(get_settings().meta_bot_token),
        "reachable": reachable is not False,
        "username": username,
        "url": f"https://t.me/{username}" if username else "",
    }


@router.get("/bots/{bot_id}/button-stats")
async def button_stats(
    bot_id: uuid.UUID,
    days: int = 30,
    client: Client = Depends(get_current_client),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Какие кнопки нажимают: число нажатий и сколько разных людей нажало."""
    from datetime import timedelta

    from app.models.button_click import ButtonClick

    bot = await _get_owned_bot(bot_id, client, db)
    since = datetime.now(timezone.utc) - timedelta(days=max(1, min(days, 365)))
    rows = (
        await db.execute(
            select(
                ButtonClick.block_id,
                ButtonClick.label,
                func.count(ButtonClick.id),
                func.count(func.distinct(ButtonClick.telegram_user_id)),
                func.max(ButtonClick.created_at),
            )
            .where(ButtonClick.bot_id == bot.id, ButtonClick.created_at >= since)
            .group_by(ButtonClick.block_id, ButtonClick.label)
            .order_by(func.count(ButtonClick.id).desc())
            .limit(200)
        )
    ).all()
    blocks = {
        b.id: b
        for b in (await db.execute(select(BotBlock).where(BotBlock.bot_id == bot.id))).scalars().all()
    }

    def title(block_id) -> str:
        block = blocks.get(block_id)
        text = str((block.content or {}).get("text") or "").strip() if block else ""
        return text[:60] if text else ("Блок удалён" if block is None else "Кнопки")

    return {
        "days": days,
        "buttons": [
            {
                "block_id": str(block_id) if block_id else None,
                "block": title(block_id),
                "label": label,
                "clicks": int(clicks),
                "people": int(people),
                "last_at": last,
            }
            for block_id, label, clicks, people, last in rows
        ],
    }


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
    settings = get_settings()
    mine = await db.execute(select(func.count(Bot.id)).where(Bot.client_id == client.id))
    if mine.scalar_one() >= settings.max_bots_per_client:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"Больше {settings.max_bots_per_client} ботов на аккаунт пока нельзя. "
                f"Удали ненужного или напиши нам — поднимем."
            ),
        )

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
    if payload.paused is not None:
        from app.services import owner_panel

        try:
            await owner_panel.set_paused(db, client, bot_id, payload.paused)
        except owner_panel.PauseError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
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

    # An already-live bot may publish again, and that is the repair button.
    # Setting the webhook is a call to Telegram and can fail — a 5xx on their
    # side, a rate limit — and when it did, the bot was already marked active
    # and this check refused every retry. The client had paid for a launch and
    # owned a corpse they could not revive. Only `disabled` is refused: that
    # one is ours to lift, by paying for the next period.
    if bot.status == BotStatus.disabled:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Бот остановлен — продли оплату, и он вернётся в строй сам.",
        )

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
    # With no payment method configured (the default) publishing stays open —
    # the paywall exists only once there is somewhere for the money to go.
    from app.services import payment_service

    if payment_service.platform_methods() and bot.publication_paid_at is None:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail="Публикация бота не оплачена",
        )

    # Сначала мета-бот: уведомления о продажах и сообщения о запуске идут через
    # него, поэтому владелец должен был его запустить до включения бота.
    # False — Telegram сказал «писать нельзя»; None (не настроен, сбой сети)
    # не блокирует.
    from app.services import platform_billing

    if await platform_billing.can_reach_owner(client.telegram_user_id) is False:
        username = get_settings().meta_bot_username.lstrip("@").strip()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"Сначала открой @{username or 'мета-бота'} в Telegram и нажми Start — "
                "туда придут уведомления о продажах и сообщение о запуске. Потом вернись и включи бота."
            ),
        )

    try:
        me = await validate_bot_token(payload.token)
    except InvalidBotToken as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    # Telegram first, database second. The other way round — which is how
    # this read until a failing setWebhook was actually tried — commits
    # "active" and then makes a network call that may not come back: the row
    # says the bot is on the air while Telegram has no webhook for it, so the
    # bot is silent and nothing in the product will ever retry.
    # Перевыпуск на другой токен: снять вебхук со старого бота, иначе он
    # продолжает слать апдейты на тот же /webhook/{bot_id} — секрет выводится
    # из id бота, а не из токена, — и диспетчер отвечает на них от имени
    # нового. Пользователи первого бота получают ответы второго.
    previous = decrypt_token(bot.bot_token_encrypted) if bot.bot_token_encrypted else None
    if previous and previous != payload.token.strip():
        await bot_registry.remove(bot.id, previous)

    try:
        await bot_registry.register_webhook(bot.id, payload.token.strip())
    except Exception as exc:
        logger.exception("Bot %s: Telegram refused the webhook", bot_id)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=(
                "Telegram сейчас не принял бота — это бывает при сбое на их стороне. "
                "Нажми «Опубликовать» ещё раз через минуту, оплата уже сохранена."
            ),
        ) from exc

    bot.bot_token_encrypted = encrypt_token(payload.token.strip())
    bot.telegram_bot_username = me.username
    bot.status = BotStatus.active
    bot.published_at = bot.published_at or datetime.now(timezone.utc)
    await db.commit()

    # Подтверждение запуска в мета-боте — владелец видит, что уведомления работают.
    with contextlib.suppress(Exception):
        meta = platform_billing._meta_bot()
        if meta is not None:
            await asyncio.wait_for(
                meta.send_message(
                    client.telegram_user_id,
                    f"✅ Бот @{me.username} запущен. Сюда будут приходить уведомления о продажах.",
                ),
                timeout=8,
            )

    return PublishResponse(status=bot.status, telegram_bot_username=bot.telegram_bot_username)
