import uuid
from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class BotSubscriber(Base):
    """A person on the other side of a client's bot.

    Until now the only trace of a buyer anywhere was `Payment.telegram_user_id`
    — a bare number, and only if they had paid. That made three things
    impossible at once: the owner could not see *who* bought (the sales log
    showed invoice numbers and amounts), nothing could be sent to a buyer
    later (no chat to send it to, once the webhook that carried it was gone),
    and no subscription could be tied to a person.

    One row per (bot, telegram user), written on every /start and refreshed
    on every payment, so the name and @username follow the person if they
    change them. `chat_id` is what later sends actually need — for a private
    chat it equals the user id, but it is stored rather than assumed.
    """

    __tablename__ = "bot_subscribers"
    __table_args__ = (UniqueConstraint("bot_id", "telegram_user_id", name="uq_bot_subscriber"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    bot_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("bots.id", ondelete="CASCADE"), nullable=False, index=True
    )

    telegram_user_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    chat_id: Mapped[int] = mapped_column(BigInteger, nullable=False)

    first_name: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    last_name: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    username: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    language_code: Mapped[str] = mapped_column(String(16), nullable=False, default="")

    #: Set when Telegram tells us the bot can no longer write to this person
    #: (they blocked it, or deleted the account). Scheduled sends skip these
    #: instead of burning a retry on every run, forever.
    blocked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    #: Set when the person asked to stop (/stop). Deliberately separate from
    #: `blocked_at`: that one is reset the moment they write again — as it
    #: should be, it means "Telegram lets us through once more" — and reusing
    #: it for consent meant a single «привет» silently re-subscribed someone
    #: who had opted out. Only another /start clears this.
    unsubscribed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    @property
    def title(self) -> str:
        """How to name this person to the shop owner."""
        name = " ".join(part for part in (self.first_name, self.last_name) if part).strip()
        if self.username:
            return f"{name} (@{self.username})" if name else f"@{self.username}"
        return name or f"id {self.telegram_user_id}"
