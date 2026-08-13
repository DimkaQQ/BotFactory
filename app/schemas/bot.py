import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.models.bot import BotStatus
from app.schemas.bot_block import BotBlockOut


class BotOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    client_id: uuid.UUID
    name: str | None
    telegram_bot_username: str | None
    status: BotStatus
    created_at: datetime
    published_at: datetime | None
    block_count: int = 0


class BotWithBlocksOut(BotOut):
    blocks: list[BotBlockOut] = []


class BotUpdate(BaseModel):
    name: str | None = None


class PublishRequest(BaseModel):
    token: str


class PublishResponse(BaseModel):
    status: BotStatus
    telegram_bot_username: str
