import enum
import uuid
from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, Identity, String, func
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class PaymentKind(str, enum.Enum):
    # Someone paying a *client's* bot — the bot owner's money, we only route it.
    order = "order"
    # A client paying *us* to publish a bot.
    publication = "publication"
    # A client paying *us* for the bot's next period. Separate from
    # `publication` because the two carry different prices and settle
    # differently — one unlocks the publish button once, the other moves
    # `paid_until` forward every time.
    renewal = "renewal"


class PaymentStatus(str, enum.Enum):
    pending = "pending"
    paid = "paid"
    failed = "failed"
    refunded = "refunded"


class Payment(Base):
    """One payment attempt, of either kind (see PaymentKind).

    Both kinds share a table because they share everything that matters:
    the same provider adapters create them, the same webhook marks them
    paid, and the same status machine applies. What differs is only what
    happens *after* "paid" — an order resumes the bot's dialogue at the
    payment block's next block, a publication unlocks the publish button.

    Amounts are integer minor units (kopeks/cents/tiyn), never floats: a
    price that arrives back from a provider as 990.0000001 is not a price.
    """

    __tablename__ = "payments"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # A short numeric id, because several providers (Robokassa's InvId among
    # them) will only carry an integer invoice number back to us.
    invoice_no: Mapped[int] = mapped_column(BigInteger, Identity(start=1000), unique=True, nullable=False)

    kind: Mapped[PaymentKind] = mapped_column(SAEnum(PaymentKind, name="payment_kind", native_enum=False), nullable=False)
    status: Mapped[PaymentStatus] = mapped_column(
        SAEnum(PaymentStatus, name="payment_status", native_enum=False), nullable=False, default=PaymentStatus.pending
    )

    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    # The provider's own id for this payment, once it tells us one — kept for
    # support requests and to make webhook replays idempotent.
    provider_payment_id: Mapped[str | None] = mapped_column(String(255), nullable=True)

    amount_minor: Mapped[int] = mapped_column(BigInteger, nullable=False)
    currency: Mapped[str] = mapped_column(String(8), nullable=False)
    description: Mapped[str] = mapped_column(String(255), nullable=False, default="")

    bot_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("bots.id", ondelete="CASCADE"), nullable=True, index=True
    )
    client_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("clients.id", ondelete="CASCADE"), nullable=True, index=True
    )
    # The payment block this order came from — its next_block_id is what the
    # buyer gets once the money lands.
    block_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("bot_blocks.id", ondelete="SET NULL"), nullable=True
    )

    # Who to deliver to, in Telegram terms. Kept on the payment itself because
    # the webhook arrives from the payment provider, with no Telegram context
    # of its own to reconstruct this from.
    telegram_user_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    chat_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)

    meta: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
