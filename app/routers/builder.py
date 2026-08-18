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

    block = BotBlock(
        bot_id=bot_id,
        block_type=payload.block_type,
        content=payload.content,
        order_index=order_index,
        position_x=payload.position_x if payload.position_x is not None else 80.0,
        position_y=payload.position_y if payload.position_y is not None else 80.0 + order_index * 160.0,
    )
    db.add(block)

    # The very first block a bot ever gets automatically becomes the entry
    # point — otherwise a brand-new bot would have no start node at all
    # until someone explicitly drags the "▶ Старт" arrow onto something.
    if bot.start_block_id is None:
        await db.flush()  # block.id needs to exist before we can point at it
        bot.start_block_id = block.id

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
    fields = payload.model_fields_set
    if payload.content is not None:
        block.content = payload.content
    if payload.order_index is not None:
        block.order_index = payload.order_index
    # These three use "was the field sent at all" rather than "is it not
    # None" — dragging an arrow away or dropping a node back to (0, 0) are
    # real edits that set the value to null/0, not omissions.
    if "next_block_id" in fields:
        if payload.next_block_id is not None:
            target = await _get_owned_block(bot_id, payload.next_block_id, db)
            if target.id == block.id:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Блок не может вести сам в себя")
        block.next_block_id = payload.next_block_id
    if "position_x" in fields and payload.position_x is not None:
        block.position_x = payload.position_x
    if "position_y" in fields and payload.position_y is not None:
        block.position_y = payload.position_y

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
