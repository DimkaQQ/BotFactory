import enum
import uuid
from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, Index, Integer, String, func
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class SubscriptionStatus(str, enum.Enum):
    #: Paid, inside the period we were paid for.
    active = "active"
    #: The period ran out and the next payment has not arrived. Access is
    #: withdrawn here, not at `cancelled` — someone who simply let the card
    #: fail should stop receiving, and can come back by paying again.
    expired = "expired"
    #: Deliberately ended — by the subscriber (Telegram's own "отменить
    #: подписку" for Stars) or by the shop owner.
    cancelled = "cancelled"


class BillingMode(str, enum.Enum):
    """How the next period's money is supposed to arrive.

    The distinction is the whole reason this enum exists, and it must reach
    the shop owner in those words, because it decides whether they have a
    subscription business or a reminder business:

    * `auto` — the next period's money arrives without the buyer doing
      anything. Two mechanisms sit under this one word, and which applies is
      a property of the adapter (`payments.base.RecurringMode`): Telegram
      Stars and Stripe run the subscription themselves, while ЮKassa and
      CloudPayments hand back a saved payment method that *we* charge on
      schedule. The distinction matters to the code — only the second kind
      queues a charge of its own — but not to the owner's mental model, which
      is why it collapses to one value here.
    * `renewal` — everyone else. Nothing in those integrations can take money
      again, so the bot sends a fresh invoice when the period ends and access
      continues only if the buyer pays it. Honest recurring *billing*, not
      recurring *collection*.
    """

    auto = "auto"
    renewal = "renewal"


class Subscription(Base):
    """One person's standing access to one thing, for a period at a time.

    Created when a payment block marked as a subscription is first paid, and
    then the row every later charge, reminder, expiry and group-kick hangs
    off. `current_period_end` is the single source of truth for "does this
    person still get things" — the scheduler re-reads it rather than trusting
    whatever was queued earlier, so a cancellation takes effect even for work
    that was scheduled while the subscription was healthy.
    """

    __tablename__ = "subscriptions"
    __table_args__ = (
        # The expiry sweep's query.
        Index("ix_subscriptions_period_end", "current_period_end"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    bot_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("bots.id", ondelete="CASCADE"), nullable=False, index=True
    )
    #: The payment block that sells this subscription. SET NULL so a deleted
    #: block leaves the subscription visible (and refundable) rather than
    #: silently dropping a paying customer out of the owner's list.
    block_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("bot_blocks.id", ondelete="SET NULL"), nullable=True
    )

    telegram_user_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    chat_id: Mapped[int] = mapped_column(BigInteger, nullable=False)

    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    billing_mode: Mapped[BillingMode] = mapped_column(
        SAEnum(BillingMode, name="subscription_billing_mode", native_enum=False), nullable=False
    )
    status: Mapped[SubscriptionStatus] = mapped_column(
        SAEnum(SubscriptionStatus, name="subscription_status", native_enum=False),
        nullable=False,
        default=SubscriptionStatus.active,
    )

    period_days: Mapped[int] = mapped_column(Integer, nullable=False, default=30)
    amount_minor: Mapped[int] = mapped_column(BigInteger, nullable=False)
    currency: Mapped[str] = mapped_column(String(8), nullable=False)

    #: What the subscriber is paying for, as the owner named it — copied at
    #: creation so the list still reads correctly after the block is edited.
    title: Mapped[str] = mapped_column(String(255), nullable=False, default="")

    current_period_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    #: How many periods have actually been paid for. 1 from the first
    #: payment; the owner's list shows it, because "пятый месяц" and "первый
    #: месяц" are different customers.
    periods_paid: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    #: Telegram's `subscription_expiration_date` flow gives us no id of its
    #: own; what identifies the recurrence is the invoice payload, kept here
    #: so a later `successful_payment` can be matched to this row.
    provider_subscription_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)

    #: Chat the subscriber was let into, if this subscription grants group
    #: access — needed to remove them again when it lapses.
    granted_chat_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)

    meta: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    @property
    def is_live(self) -> bool:
        return self.status == SubscriptionStatus.active
