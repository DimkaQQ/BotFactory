"""Поддержка в мета-боте: человек пишет — владелец отвечает Reply."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from aiogram.exceptions import TelegramForbiddenError
from aiogram.methods import SendMessage
from sqlalchemy import delete

from app.config import get_settings
from app.database import AsyncSessionLocal
from app.models.support_relay import SupportRelay
from meta_bot.handlers import support

ADMIN = 990_700_001
USER = 990_700_002


def _msg(chat_id, message_id, text="привет", *, reply_to=None, username="anna"):
    """Столько от Message, сколько читает обработчик."""
    return SimpleNamespace(
        chat=SimpleNamespace(id=chat_id, type="private"),
        from_user=SimpleNamespace(first_name="Аня", last_name=None, username=username),
        message_id=message_id,
        text=text,
        reply_to_message=SimpleNamespace(message_id=reply_to) if reply_to is not None else None,
    )


def _bot(next_id=500):
    counter = {"n": next_id}

    async def send_message(chat_id, text, **kwargs):
        counter["n"] += 1
        return SimpleNamespace(message_id=counter["n"])

    async def copy_message(chat_id, from_chat_id, message_id, **kwargs):
        counter["n"] += 1
        return SimpleNamespace(message_id=counter["n"])

    bot = SimpleNamespace(send_message=AsyncMock(side_effect=send_message), copy_message=AsyncMock(side_effect=copy_message))
    return bot


@pytest.fixture(autouse=True)
async def _clean(monkeypatch):
    monkeypatch.setenv("SUPPORT_CHAT_ID", str(ADMIN))
    get_settings.cache_clear()
    support._recent.clear()
    support._acknowledged.clear()
    support._warned.clear()
    yield
    async with AsyncSessionLocal() as db:
        await db.execute(delete(SupportRelay).where(SupportRelay.user_chat_id == USER))
        await db.commit()
    get_settings.cache_clear()


@pytest.mark.asyncio
async def test_a_message_reaches_the_owner_and_the_person_is_told_it_was_received():
    bot = _bot()
    await support.relay(_msg(USER, 11), bot)

    sent_to_admin = [c for c in bot.send_message.await_args_list if c.args[0] == ADMIN]
    assert sent_to_admin and "id 990700002" in sent_to_admin[0].args[1] and "@anna" in sent_to_admin[0].args[1]
    bot.copy_message.assert_awaited_with(ADMIN, from_chat_id=USER, message_id=11)
    acks = [c for c in bot.send_message.await_args_list if c.args[0] == USER]
    assert acks and "Принято" in acks[0].args[1]


@pytest.mark.asyncio
async def test_the_owners_reply_goes_to_the_person_who_wrote():
    bot = _bot()
    await support.relay(_msg(USER, 11), bot)
    copy_id = 502  # header=501, copy=502 по счётчику фейка

    await support.relay(_msg(ADMIN, 77, "Здравствуйте! Сейчас посмотрю.", reply_to=copy_id), bot)

    bot.copy_message.assert_awaited_with(USER, from_chat_id=ADMIN, message_id=77)
    confirmations = [c for c in bot.send_message.await_args_list if c.args[0] == ADMIN and "Отправлено" in c.args[1]]
    assert confirmations


@pytest.mark.asyncio
async def test_replying_to_the_header_works_too():
    bot = _bot()
    await support.relay(_msg(USER, 11), bot)
    await support.relay(_msg(ADMIN, 78, "ок", reply_to=501), bot)
    bot.copy_message.assert_awaited_with(USER, from_chat_id=ADMIN, message_id=78)


@pytest.mark.asyncio
async def test_an_owner_message_that_is_not_a_reply_is_explained_not_sent_to_anyone():
    bot = _bot()
    await support.relay(_msg(ADMIN, 90, "просто пишу"), bot)
    assert not any(c.kwargs.get("from_chat_id") == ADMIN for c in bot.copy_message.await_args_list)
    assert "Reply" in bot.send_message.await_args_list[-1].args[1]


@pytest.mark.asyncio
async def test_a_reply_to_something_unknown_is_not_guessed():
    bot = _bot()
    await support.relay(_msg(ADMIN, 91, "ответ", reply_to=424242), bot)
    assert not bot.copy_message.await_args_list
    assert "Не нашёл" in bot.send_message.await_args_list[-1].args[1]


@pytest.mark.asyncio
async def test_a_person_who_blocked_the_bot_is_reported_to_the_owner():
    bot = _bot()
    await support.relay(_msg(USER, 11), bot)

    async def refuse(chat_id, from_chat_id, message_id, **kwargs):
        raise TelegramForbiddenError(method=SendMessage(chat_id=1, text="x"), message="Forbidden: bot was blocked by the user")

    bot.copy_message = AsyncMock(side_effect=refuse)
    await support.relay(_msg(ADMIN, 92, "ответ", reply_to=502), bot)
    assert "заблокировал" in bot.send_message.await_args_list[-1].args[1]


@pytest.mark.asyncio
async def test_without_a_support_chat_the_bot_says_it_is_not_connected(monkeypatch):
    monkeypatch.setenv("SUPPORT_CHAT_ID", "")
    get_settings.cache_clear()
    bot = _bot()
    await support.relay(_msg(USER, 11), bot)
    assert not bot.copy_message.await_args_list
    assert "не подключена" in bot.send_message.await_args_list[-1].args[1]


@pytest.mark.asyncio
async def test_a_flood_from_one_person_does_not_reach_the_owner():
    bot = _bot()
    for i in range(support.LIMIT + 5):
        await support.relay(_msg(USER, 100 + i), bot)
    to_owner = [c for c in bot.copy_message.await_args_list if c.args[0] == ADMIN]
    assert len(to_owner) == support.LIMIT
    warnings = [c for c in bot.send_message.await_args_list if c.args[0] == USER and "Слишком много" in c.args[1]]
    assert len(warnings) == 1, "предупреждение должно быть одно, а не на каждое сообщение"


def test_commands_are_left_to_other_handlers():
    assert support._is_plain(_msg(USER, 1, "привет"))
    assert not support._is_plain(_msg(USER, 1, "/start"))
    assert support._is_plain(_msg(USER, 1, text=None))  # фото и файлы без подписи
