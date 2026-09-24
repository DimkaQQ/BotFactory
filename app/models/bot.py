import enum
import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, LargeBinary, SmallInteger, String, func
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class BotStatus(str, enum.Enum):
    draft = "draft"
    active = "active"
    disabled = "disabled"


class Bot(Base):
    """A client bot built through the constructor."""

    __tablename__ = "bots"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    client_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("clients.id", ondelete="CASCADE"), nullable=False, index=True
    )

    # User-chosen label, so several bots (all "Новый бот" until published) can
    # be told apart in the list. Independent of telegram_bot_username.
    name: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Encrypted with Fernet — never exposed decrypted outside bot_registry.
    bot_token_encrypted: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)

    telegram_bot_username: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[BotStatus] = mapped_column(
        SAEnum(BotStatus, name="bot_status", native_enum=False), default=BotStatus.draft, nullable=False
    )

    # Entry point of the dialogue graph — the node the "▶ Старт" pseudo-node
    # points at in the flow editor. ON DELETE SET NULL: if that block is
    # removed the bot just has no entry point until one is picked again
    # (dispatcher treats a bot with no start block as empty).
    start_block_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("bot_blocks.id", ondelete="SET NULL", use_alter=True), nullable=True
    )

    # How this bot takes money from *its* customers. The credentials belong
    # to the bot's owner (their Robokassa shop, their Stripe account) and are
    # encrypted at rest with the same Fernet key as bot tokens — we only ever
    # decrypt them to build a checkout link. Money never passes through us.
    payment_provider: Mapped[str | None] = mapped_column(String(32), nullable=True)
    payment_credentials_encrypted: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    payment_is_test: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    # Set once this bot's publication has been paid for (see PaymentKind.
    # publication) — publishing checks this, not the payment rows.
    publication_paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # End of the paid period, when the deployment charges one (see
    # `renewal_price_minor`). NULL means the bot is not on a clock at all —
    # either nothing is charged monthly here, or this bot predates the
    # monthly and is left alone. A date in the past does *not* mean the bot
    # is off: the grace period is counted from here, and only
    # `platform_billing` decides what that adds up to.
    paid_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # How far the owner has already been warned about the current period
    # (see `platform_billing.NOTICE_*`). Reset to 0 every time `paid_until`
    # moves forward, which is what scopes it to one period and lets the
    # hourly sweep remind once instead of every hour.
    billing_notice_stage: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=0, server_default="0")

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    client: Mapped["Client"] = relationship(back_populates="bots")
    blocks: Mapped[list["BotBlock"]] = relationship(
        back_populates="bot",
        cascade="all, delete-orphan",
        order_by="BotBlock.order_index",
        foreign_keys="BotBlock.bot_id",
    )
