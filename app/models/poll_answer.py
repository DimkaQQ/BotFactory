import uuid
from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class PollAnswer(Base):
    """What someone picked in a bot's poll.

    The block existed, the landing page sold it («Узнай, чего хотят
    подписчики — нативный опрос Telegram, без сторонних форм»), and the
    answers went nowhere: `poll_answer` was not even in the bot's
    `allowed_updates`, so Telegram never sent them and nothing would have
    read them if it had.

    One row per person per poll — a Telegram poll answer can be changed, and
    the latest choice replaces the earlier one rather than counting twice.
    """

    __tablename__ = "poll_answers"
    __table_args__ = (UniqueConstraint("block_id", "telegram_user_id", name="uq_poll_answer"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    bot_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("bots.id", ondelete="CASCADE"), nullable=False, index=True
    )
    block_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("bot_blocks.id", ondelete="CASCADE"), nullable=False, index=True
    )

    telegram_user_id: Mapped[int] = mapped_column(BigInteger, nullable=False)

    #: Telegram's own poll id, which is how an incoming answer is matched
    #: back to the block that asked — the update carries no block of ours.
    telegram_poll_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)

    #: Indices into the block's `options`. A list because Telegram supports
    #: multiple-choice polls; empty means the answer was retracted.
    option_ids: Mapped[list[int]] = mapped_column(ARRAY(BigInteger), nullable=False, default=list)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
