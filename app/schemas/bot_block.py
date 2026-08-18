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
    next_block_id: uuid.UUID | None = None
    position_x: float = 0.0
    position_y: float = 0.0
    created_at: datetime
    updated_at: datetime


class BotBlockCreate(BaseModel):
    block_type: BlockType
    content: dict[str, Any] = Field(default_factory=dict)
    order_index: int | None = None
    position_x: float | None = None
    position_y: float | None = None


class BotBlockUpdate(BaseModel):
    content: dict[str, Any] | None = None
    order_index: int | None = None
    # Graph edges. A sentinel-free "not provided vs. explicitly cleared"
    # distinction matters here (clearing next_block_id — deleting an arrow —
    # is a real, common action, not the absence of one), so these use
    # model_fields_set in the router rather than "not None" checks.
    next_block_id: uuid.UUID | None = None
    position_x: float | None = None
    position_y: float | None = None


class BlockOrderItem(BaseModel):
    id: uuid.UUID
    order_index: int


class BlockReorderRequest(BaseModel):
    items: list[BlockOrderItem]
