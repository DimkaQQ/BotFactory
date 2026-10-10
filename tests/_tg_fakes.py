"""Общие подделки для тестов мета-бота: сессия aiogram без сети и сборка апдейтов."""

from __future__ import annotations

from datetime import datetime

from aiogram.client.session.base import BaseSession
from aiogram.methods import AnswerCallbackQuery, CopyMessage
from aiogram.types import CallbackQuery, Chat, Message, MessageEntity, MessageId, Update, User


class FakeSession(BaseSession):
    """Записывает вызовы Bot API и отвечает «успех»."""

    def __init__(self):
        super().__init__()
        self.calls = []

    async def close(self):
        return None

    async def make_request(self, bot, method, timeout=None):
        self.calls.append(method)
        number = 900 + len(self.calls)
        if isinstance(method, CopyMessage):
            return MessageId(message_id=number)
        if isinstance(method, AnswerCallbackQuery):
            return True
        chat_id = getattr(method, "chat_id", 0)
        return Message(message_id=number, date=datetime.now(), chat=Chat(id=chat_id, type="private"))

    async def stream_content(self, *args, **kwargs):  # pragma: no cover
        raise NotImplementedError

    def of(self, kind):
        return [c for c in self.calls if isinstance(c, kind)]


def text_update(update_id, chat_id, message_id, text=None, reply_to=None, first_name="Аня", username="anna"):
    entities = (
        [MessageEntity(type="bot_command", offset=0, length=len(text.split()[0]))]
        if text and text.startswith("/")
        else None
    )
    return Update(
        update_id=update_id,
        message=Message(
            message_id=message_id,
            date=datetime.now(),
            chat=Chat(id=chat_id, type="private"),
            from_user=User(id=chat_id, is_bot=False, first_name=first_name, username=username),
            text=text,
            entities=entities,
            reply_to_message=reply_to,
        ),
    )


def button_update(update_id, user_id, data, message_id=50, first_name="Аня"):
    return Update(
        update_id=update_id,
        callback_query=CallbackQuery(
            id=f"cb{update_id}",
            from_user=User(id=user_id, is_bot=False, first_name=first_name),
            chat_instance="x",
            data=data,
            message=Message(
                message_id=message_id,
                date=datetime.now(),
                chat=Chat(id=user_id, type="private"),
            ),
        ),
    )
