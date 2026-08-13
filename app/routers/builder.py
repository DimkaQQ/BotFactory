import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.deps import get_owned_bot
from app.models.bot import Bot
from app.models.bot_block import BotBlock
from app.schemas.bot_block import BlockReorderRequest, BotBlockCreate, BotBlockOut, BotBlockUpdate

router = APIRouter(prefix="/api/bots/{bot_id}/blocks", tags=["builder"])

# Editing is allowed for both draft and already-published bots — the
# dispatcher (app/services/bot_dispatcher.py) always reads blocks fresh
# from the DB on every /start, so edits to a live bot take effect
# immediately, no republish needed.


async def _get_owned_block(bot_id: uuid.UUID, block_id: uuid.UUID, db: AsyncSession) -> BotBlock:
    result = await db.execute(select(BotBlock).where(BotBlock.id == block_id, BotBlock.bot_id == bot_id))
    block = result.scalar_one_or_none()
    if block is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Block not found")
    return block


@router.get("", response_model=list[BotBlockOut])
async def list_blocks(
    bot_id: uuid.UUID,
    bot: Bot = Depends(get_owned_bot),
    db: AsyncSession = Depends(get_db),
) -> list[BotBlock]:
    result = await db.execute(select(BotBlock).where(BotBlock.bot_id == bot_id).order_by(BotBlock.order_index))
    return list(result.scalars().all())


@router.post("", response_model=BotBlockOut, status_code=status.HTTP_201_CREATED)
async def create_block(
    bot_id: uuid.UUID,
    payload: BotBlockCreate,
    bot: Bot = Depends(get_owned_bot),
    db: AsyncSession = Depends(get_db),
) -> BotBlock:
    if payload.order_index is None:
        result = await db.execute(select(BotBlock.order_index).where(BotBlock.bot_id == bot_id))
        existing = [row[0] for row in result.all()]
        order_index = (max(existing) + 1) if existing else 0
    else:
        order_index = payload.order_index

    block = BotBlock(bot_id=bot_id, block_type=payload.block_type, content=payload.content, order_index=order_index)
    db.add(block)
    await db.commit()
    await db.refresh(block)
    return block


@router.patch("/reorder", response_model=list[BotBlockOut])
async def reorder_blocks(
    bot_id: uuid.UUID,
    payload: BlockReorderRequest,
    bot: Bot = Depends(get_owned_bot),
    db: AsyncSession = Depends(get_db),
) -> list[BotBlock]:
    block_ids = [item.id for item in payload.items]
    result = await db.execute(select(BotBlock).where(BotBlock.bot_id == bot_id, BotBlock.id.in_(block_ids)))
    blocks_by_id = {block.id: block for block in result.scalars().all()}

    if len(blocks_by_id) != len(payload.items):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Some blocks do not belong to this bot")

    for item in payload.items:
        blocks_by_id[item.id].order_index = item.order_index

    await db.commit()

    result = await db.execute(select(BotBlock).where(BotBlock.bot_id == bot_id).order_by(BotBlock.order_index))
    return list(result.scalars().all())


@router.patch("/{block_id}", response_model=BotBlockOut)
async def update_block(
    bot_id: uuid.UUID,
    block_id: uuid.UUID,
    payload: BotBlockUpdate,
    bot: Bot = Depends(get_owned_bot),
    db: AsyncSession = Depends(get_db),
) -> BotBlock:
    block = await _get_owned_block(bot_id, block_id, db)
    if payload.content is not None:
        block.content = payload.content
    if payload.order_index is not None:
        block.order_index = payload.order_index

    await db.commit()
    await db.refresh(block)
    return block


@router.delete("/{block_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_block(
    bot_id: uuid.UUID,
    block_id: uuid.UUID,
    bot: Bot = Depends(get_owned_bot),
    db: AsyncSession = Depends(get_db),
) -> None:
    block = await _get_owned_block(bot_id, block_id, db)
    await db.delete(block)
    await db.commit()
