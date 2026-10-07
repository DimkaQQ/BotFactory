import uuid
from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class AbuseReport(Base):
    """Жалоба на бота: кто угодно присылает её со страницы /report или из бота
    командой /report. Бот и его владелец жалобу не видят, а рассматривает её
    оператор сервиса (см. `app.services.moderation`)."""

    __tablename__ = "abuse_reports"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)
    #: Бот найден по имени из жалобы. NULL — имя не нашлось или бот удалён:
    #: жалоба остаётся, её читают и без привязки.
    bot_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("bots.id", ondelete="SET NULL"), nullable=True, index=True
    )
    #: Что написал сам жалобщик (имя или ссылка), как есть.
    bot_ref: Mapped[str] = mapped_column(String(255), nullable=False)
    category: Mapped[str] = mapped_column(String(32), nullable=False)
    details: Mapped[str] = mapped_column(Text, nullable=False)
    contact: Mapped[str | None] = mapped_column(String(255), nullable=True)
    #: new → actioned | dismissed
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="new", server_default="new", index=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ModerationAction(Base):
    """Журнал решений оператора: что, над чем, почему и кто сделал.

    Записи не удаляются вместе с ботом или аккаунтом — для этого журнал и
    нужен: на спор «почему меня заблокировали» должно быть чем ответить.
    """

    __tablename__ = "moderation_actions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)
    report_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("abuse_reports.id", ondelete="SET NULL"), nullable=True
    )
    bot_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("bots.id", ondelete="SET NULL"), nullable=True
    )
    #: Telegram id владельца на момент действия (аккаунт могут удалить).
    client_telegram_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    #: block_bot | restore_bot | ban_client | unban_client | dismiss_report
    action: Mapped[str] = mapped_column(String(24), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False, default="", server_default="")
    #: Кто решил: `tg:<id>` или `cli`.
    actor: Mapped[str] = mapped_column(String(64), nullable=False)
