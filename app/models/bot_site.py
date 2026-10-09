import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class BotSite(Base):
    """Публичная страница продавца для бота: товары, цены, реквизиты, документы.

    Нужна эквайрингу (в Казахстане банки не принимают оплату «внутри Telegram» и
    просят сайт с кнопкой перехода в бота). Содержимое — данные владельца бота;
    товары и цены берутся из блоков оплаты, чтобы не расходились с ботом.
    """

    __tablename__ = "bot_sites"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    bot_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("bots.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    slug: Mapped[str] = mapped_column(String(40), nullable=False, unique=True, index=True)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    title: Mapped[str] = mapped_column(String(120), nullable=False, default="", server_default="")
    about: Mapped[str] = mapped_column(Text, nullable=False, default="", server_default="")
    seller_name: Mapped[str] = mapped_column(String(200), nullable=False, default="", server_default="")
    seller_id: Mapped[str] = mapped_column(String(64), nullable=False, default="", server_default="")
    seller_address: Mapped[str] = mapped_column(String(300), nullable=False, default="", server_default="")
    email: Mapped[str] = mapped_column(String(120), nullable=False, default="", server_default="")
    phone: Mapped[str] = mapped_column(String(40), nullable=False, default="", server_default="")
    refund_text: Mapped[str] = mapped_column(Text, nullable=False, default="", server_default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
