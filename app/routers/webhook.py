import logging
import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.services import bot_dispatcher, bot_registry

logger = logging.getLogger(__name__)

router = APIRouter(tags=["webhook"])


@router.post("/webhook/{bot_id}")
async def handle_update(bot_id: uuid.UUID, update: dict, db: AsyncSession = Depends(get_db)) -> dict:
    bot_instance = await bot_registry.get_or_create(bot_id, db)
    if bot_instance is None:
        return {"ok": False}

    try:
        await bot_dispatcher.process_update(bot_instance, update, bot_id, db)
    except Exception:
        # An error in one bot's dialogue must never take down the shared webhook.
        logger.exception("Error handling update for bot %s", bot_id)

    return {"ok": True}
