import uuid
from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class PollSend(Base):
    """Один отправленный опрос: чей `poll_id` пришёл в ответе.

    Telegram выдаёт новый `poll_id` на каждый чат, поэтому связь «опрос →
    блок» не помещается в одно поле на блоке: раньше там хранился последний,
    и ответы всех остальных подписчиков молча выбрасывались.
    """

    __tablename__ = "poll_sends"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    bot_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("bots.id", ondelete="CASCADE"), nullable=False
    )
    block_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("bot_blocks.id", ondelete="CASCADE"), nullable=False, index=True
    )
    telegram_poll_id: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    chat_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
