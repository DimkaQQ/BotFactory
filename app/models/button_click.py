import uuid
from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class ButtonClick(Base):
    """Одно нажатие покупателя на кнопку сценария (инлайн или быстрая).

    Нужна для статистики «какие кнопки нажимают» и для выбора покупателя
    (дата, время, вариант), который показывается в заказе. Хранится только
    подпись кнопки и id человека в Telegram — переписка не сохраняется.
    """

    __tablename__ = "button_clicks"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    bot_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("bots.id", ondelete="CASCADE"), nullable=False, index=True
    )
    block_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    button_index: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    label: Mapped[str] = mapped_column(String(64), nullable=False)
    #: Выбор покупателя нужно показать в заказе (блок помечен `collect_choice`).
    collect_choice: Mapped[bool] = mapped_column(nullable=False, default=False, server_default="false")
    telegram_user_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)
