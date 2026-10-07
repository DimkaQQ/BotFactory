from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Text, func
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
    # В базе колонка допускает NULL (миграция 0014); модель приведена к ней, без разрушающей миграции.
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=True)
    #: Текст сообщения человека (подпись или пометка о вложении) — чтобы ответ поддержки
    #: уходил одним сообщением вместе с вопросами. Только у копий его сообщений.
    question_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    #: Когда на этот вопрос ответили; пока пусто — вопрос входит в следующий ответ.
    answered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
