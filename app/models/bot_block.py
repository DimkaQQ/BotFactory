import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, func
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class BlockType(str, enum.Enum):
    welcome = "welcome"
    description = "description"
    image = "image"
    video = "video"
    buttons = "buttons"
    poll = "poll"
    delivery = "delivery"
    delay = "delay"


class BotBlock(Base):
    """One node in a bot's dialogue graph, built in the visual flow constructor.

    Execution order is a graph, not the list `order_index` implies (that
    column now only orders the block library / any place blocks are listed
    flatly — it plays no role in dispatch). A block's default continuation
    is `next_block_id`; a "buttons" block can *additionally* send the
    dispatcher down a different path per button via that button's
    `target_block_id` in `content["buttons"][i]` — see
    app/services/bot_dispatcher.py for the traversal itself.
    """

    __tablename__ = "bot_blocks"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    bot_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("bots.id", ondelete="CASCADE"), nullable=False, index=True
    )
    block_type: Mapped[BlockType] = mapped_column(SAEnum(BlockType, name="block_type", native_enum=False), nullable=False)
    order_index: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    content: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)

    # The default "what happens after this block" edge — drawn as the plain
    # (non-button) arrow out of a node on the canvas. Null = end of that
    # branch. ON DELETE SET NULL so removing the target block just makes
    # this a dead end instead of leaving a dangling reference.
    next_block_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("bot_blocks.id", ondelete="SET NULL"), nullable=True, index=True
    )

    # Canvas position (px) in the flow editor.
    position_x: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    position_y: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    bot: Mapped["Bot"] = relationship(back_populates="blocks", foreign_keys="BotBlock.bot_id")
