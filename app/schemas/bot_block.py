import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.models.bot_block import BlockType


class BotBlockOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    bot_id: uuid.UUID
    block_type: BlockType
    order_index: int
    content: dict[str, Any]
    created_at: datetime
    updated_at: datetime


class BotBlockCreate(BaseModel):
    block_type: BlockType
    content: dict[str, Any] = Field(default_factory=dict)
    order_index: int | None = None


class BotBlockUpdate(BaseModel):
    content: dict[str, Any] | None = None
    order_index: int | None = None


class BlockOrderItem(BaseModel):
    id: uuid.UUID
    order_index: int


class BlockReorderRequest(BaseModel):
    items: list[BlockOrderItem]
