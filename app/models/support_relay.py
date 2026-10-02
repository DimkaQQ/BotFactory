from datetime import datetime

from sqlalchemy import BigInteger, DateTime, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class SupportRelay(Base):
    """Какому человеку принадлежит сообщение в чате поддержки.

    Мета-бот пересылает обращения владельцу, а ответ владельца должен уйти
    тому, кто написал. Telegram не говорит, кому адресован «ответ» на копию
    сообщения (автор скрыт настройками приватности), поэтому соответствие
    «сообщение в чате поддержки → человек» хранится здесь, а не угадывается.
    """

    __tablename__ = "support_relay"

    admin_message_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=False)
    user_chat_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
