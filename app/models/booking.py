import uuid
from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, Index, String, Text, func, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base

#: Статусы, которые занимают время в календаре.
ACTIVE = ("held", "confirmed", "blocked")


class Booking(Base):
    """Запись клиента на время (или время, закрытое владельцем).

    held — время придержано, пока клиент платит (до `held_until`); confirmed —
    запись подтверждена; blocked — владелец закрыл время вручную; cancelled —
    отменена (время свободно). Одно время на бота занимает только одна
    активная запись: это держит частичный уникальный индекс, поэтому два
    клиента не запишутся на один слот даже при одновременных нажатиях.
    """

    __tablename__ = "bookings"
    __table_args__ = (
        Index(
            "uq_booking_active_slot",
            "bot_id",
            "starts_at",
            unique=True,
            postgresql_where=text("status IN ('held','confirmed','blocked')"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    bot_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("bots.id", ondelete="CASCADE"), nullable=False, index=True
    )
    block_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    telegram_user_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, index=True)
    chat_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="held", index=True)
    held_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    note: Mapped[str] = mapped_column(Text, nullable=False, default="", server_default="")
    #: Когда клиенту ушло напоминание за сутки / за 2 часа (NULL — ещё нет).
    reminded_day_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    reminded_hours_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ChatState(Base):
    """Бот ждёт от человека ответа текстом (имя, телефон). Одна запись на
    человека в боте; устаревшие игнорируются."""

    __tablename__ = "chat_states"

    bot_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("bots.id", ondelete="CASCADE"), primary_key=True
    )
    telegram_user_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
