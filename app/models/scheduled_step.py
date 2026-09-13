import enum
import uuid
from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, Index, Integer, String, func, text
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class StepStatus(str, enum.Enum):
    pending = "pending"
    sent = "sent"
    failed = "failed"
    #: Withdrawn before it ran — the subscription it belonged to lapsed, the
    #: block was deleted, or the person blocked the bot.
    cancelled = "cancelled"


class ScheduledStep(Base):
    """"Continue this conversation at this time."

    The dialogue engine is synchronous: a walk starts on an update and runs
    to the end of the chain inside that request. That put a hard ceiling on
    what a bot could express — the "Пауза" block was clamped to fifteen
    seconds, because the webhook request is held open for it — and so a bot
    could not do the single most common thing a subscription product needs:
    send the second video next week.

    A row here is a walk that has not started yet: at `run_at`, resume the
    bot's chain from `block_id` in `chat_id`. That makes "Пауза" mean what
    it looks like it means for any duration, and it is also what a renewal
    reminder and a monthly re-invoice are built from.

    Deliberately a table and not an in-process timer: a month is longer than
    any deployment, and a sleeping task is lost at the next restart.
    """

    __tablename__ = "scheduled_steps"
    __table_args__ = (
        # The sweep's only query: what is due. Partial, because everything
        # already sent stays in the table as history and would otherwise
        # dominate the index within a week of real use.
        Index("ix_scheduled_steps_due", "run_at", postgresql_where=text("status = 'pending'")),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    bot_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("bots.id", ondelete="CASCADE"), nullable=False, index=True
    )
    #: Where the walk picks up. SET NULL rather than CASCADE so a step whose
    #: block the owner deleted is *seen* and cancelled with a reason, instead
    #: of vanishing from the queue as if it had run.
    block_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("bot_blocks.id", ondelete="SET NULL"), nullable=True
    )

    telegram_user_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    chat_id: Mapped[int] = mapped_column(BigInteger, nullable=False)

    #: Set when this step belongs to a subscription, so cancelling the
    #: subscription can withdraw everything still queued for it in one go.
    subscription_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("subscriptions.id", ondelete="CASCADE"), nullable=True, index=True
    )

    #: "delay" (a Пауза block in the middle of a chain), "renewal" (ask for
    #: the next period's money), "expiry" (the period ran out). Kept as a
    #: plain string rather than an enum: the sweep treats them identically,
    #: and this is for the log and for support.
    reason: Mapped[str] = mapped_column(String(32), nullable=False, default="delay")

    run_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    status: Mapped[StepStatus] = mapped_column(
        SAEnum(StepStatus, name="scheduled_step_status", native_enum=False),
        nullable=False,
        default=StepStatus.pending,
    )
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_error: Mapped[str] = mapped_column(String(500), nullable=False, default="")

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    ran_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
