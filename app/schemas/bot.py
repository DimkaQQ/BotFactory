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
    start_block_id: uuid.UUID | None = None
    # End of the paid period, when this deployment charges one. None means
    # the bot is not on a clock — see `Bot.paid_until`.
    paid_until: datetime | None = None


class BotWithBlocksOut(BotOut):
    blocks: list[BotBlockOut] = []


class BotUpdate(BaseModel):
    name: str | None = None
    # Explicit clear (dragging the "▶ Старт" arrow away) vs. "not sent"
    # matters here too — see BotBlockUpdate.next_block_id.
    start_block_id: uuid.UUID | None = None


class PublishRequest(BaseModel):
    token: str


class PublishResponse(BaseModel):
    status: BotStatus
    telegram_bot_username: str
