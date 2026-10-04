"""Поддержка в мета-боте: человек пишет — владелец отвечает Reply."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from _tg_fakes import FakeSession, text_update
from aiogram import Bot
from aiogram.exceptions import TelegramForbiddenError
from aiogram.methods import CopyMessage, SendMessage
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
    support._dialogs.clear()
    support.open_dialog(USER)
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
    assert acks and "отправлено в поддержку" in acks[0].args[1] and "24 часов" in acks[0].args[1]


@pytest.mark.asyncio
async def test_the_owners_reply_goes_to_the_person_who_wrote():
    bot = _bot()
    await support.relay(_msg(USER, 11), bot)
    copy_id = 502  # header=501, copy=502 по счётчику фейка

    await support.relay(_msg(ADMIN, 77, "Здравствуйте! Сейчас посмотрю.", reply_to=copy_id), bot)

    answers = [c for c in bot.send_message.await_args_list if c.args[0] == USER and "Пришёл ответ" in c.args[1]]
    assert answers and "Здравствуйте! Сейчас посмотрю." in answers[0].args[1]
    confirmations = [c for c in bot.send_message.await_args_list if c.args[0] == ADMIN and "Отправлено" in c.args[1]]
    assert confirmations


@pytest.mark.asyncio
async def test_replying_to_the_header_works_too():
    bot = _bot()
    await support.relay(_msg(USER, 11), bot)
    await support.relay(_msg(ADMIN, 78, "ок", reply_to=501), bot)
    assert any(c.args[0] == USER and "Пришёл ответ" in c.args[1] for c in bot.send_message.await_args_list)


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

    async def refuse(chat_id, text, **kwargs):
        if chat_id == USER:
            raise TelegramForbiddenError(method=SendMessage(chat_id=1, text="x"), message="Forbidden: bot was blocked by the user")
        return SimpleNamespace(message_id=999)

    bot.send_message = AsyncMock(side_effect=refuse)
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


# ----------------------------------- сквозная проверка на настоящем диспетчере


@pytest.mark.asyncio
async def test_the_meta_bot_still_opens_the_constructor_and_relays_everything_else(meta_dp):
    """Главное, что нельзя сломать: /start по-прежнему даёт кнопку конструктора
    (так клиент попадает с бота на сайт), а поддержка ловит только обычные
    сообщения."""

    session = FakeSession()
    bot = Bot("123456:AAAA-testtoken", session=session)
    dp = meta_dp

    await dp.feed_update(bot, text_update(1, USER, 1, "/start"))
    starts = [c for c in session.calls if isinstance(c, SendMessage) and c.chat_id == USER]
    assert starts, "/start остался без ответа"
    button = starts[0].reply_markup.inline_keyboard[0][0]
    assert button.web_app is not None and "конструктор" in button.text.lower()
    assert not [c for c in session.calls if isinstance(c, CopyMessage)], "команда /start ушла в поддержку"

    session.calls.clear()
    await dp.feed_update(bot, text_update(2, USER, 2, "У меня не открывается конструктор"))
    copies = [c for c in session.calls if isinstance(c, CopyMessage)]
    assert copies and copies[0].chat_id == ADMIN and copies[0].from_chat_id == USER

    await bot.session.close()


@pytest.mark.asyncio
async def test_a_plain_message_without_pressing_support_is_not_relayed_to_the_owner():
    """Бот не лезет в личную переписку владельца случайными словами: пока человек
    не нажал «Поддержка» (и не писал нам за сутки), он получает подсказку."""
    support._dialogs.clear()
    bot = _bot()
    await support.relay(_msg(USER, 11), bot)
    assert not bot.copy_message.await_args_list
    assert "Поддержка" in bot.send_message.await_args_list[-1].args[1]


@pytest.mark.asyncio
async def test_the_owners_reply_keeps_the_conversation_open_both_ways():
    bot = _bot()
    await support.relay(_msg(USER, 11), bot)
    await support.relay(_msg(ADMIN, 77, "Здравствуйте!", reply_to=502), bot)
    support._dialogs.clear()  # перезапуск бота: память пуста, но в базе разговор есть
    await support.relay(_msg(USER, 12, "спасибо, а ещё вопрос"), bot)
    assert bot.copy_message.await_args_list[-1].kwargs["from_chat_id"] == USER

    # и ответ на ответ владельца тоже находит человека
    await support.relay(_msg(ADMIN, 79, "Конечно", reply_to=77), bot)
    assert bot.send_message.await_args_list[-3].args[0] == USER or any(
        c.args[0] == USER and "Конечно" in c.args[1] for c in bot.send_message.await_args_list
    )


# ------------------------------------------- ответ одним сообщением: вопросы + ответ


@pytest.mark.asyncio
async def test_the_answer_comes_as_one_message_with_all_unanswered_questions():
    bot = _bot()
    await support.relay(_msg(USER, 11, "Не открывается конструктор"), bot)
    await support.relay(_msg(USER, 12, "И ещё <b>не</b> приходит оплата"), bot)

    await support.relay(_msg(ADMIN, 77, "Обновите страницу & попробуйте снова.", reply_to=502), bot)

    to_user = [c for c in bot.send_message.await_args_list if c.args[0] == USER and "Пришёл ответ" in c.args[1]]
    assert len(to_user) == 1, "ответ — одним сообщением"
    text = to_user[0].args[1]
    assert "Ваши вопросы:" in text
    assert "Не открывается конструктор" in text and "И ещё &lt;b&gt;не&lt;/b&gt; приходит оплата" in text, "HTML человека экранируется"
    assert text.index("Ваши вопросы:") < text.index("Ответ от поддержки:")
    assert "Обновите страницу &amp; попробуйте снова." in text
    assert "«💬 Поддержка»" in text
    assert to_user[0].kwargs["parse_mode"] == "HTML"


@pytest.mark.asyncio
async def test_answered_questions_are_not_repeated_in_the_next_answer():
    bot = _bot()
    await support.relay(_msg(USER, 11, "Первый вопрос"), bot)
    await support.relay(_msg(ADMIN, 77, "Ответ 1", reply_to=502), bot)
    await support.relay(_msg(USER, 12, "Второй вопрос"), bot)
    await support.relay(_msg(ADMIN, 78, "Ответ 2", reply_to=506), bot)

    answers = [c.args[1] for c in bot.send_message.await_args_list if c.args[0] == USER and "Пришёл ответ" in c.args[1]]
    assert len(answers) == 2
    assert "Первый вопрос" in answers[0]
    assert "Второй вопрос" in answers[1] and "Первый вопрос" not in answers[1]
    assert "Ваш вопрос:" in answers[1], "один вопрос — единственное число"


@pytest.mark.asyncio
async def test_an_attachment_answer_goes_after_the_questions_not_instead_of_them():
    bot = _bot()
    await support.relay(_msg(USER, 11, "Вот скрин"), bot)
    await support.relay(_msg(ADMIN, 77, None, reply_to=502), bot)  # владелец отвечает вложением

    intro = [c for c in bot.send_message.await_args_list if c.args[0] == USER and "Пришёл ответ" in c.args[1]]
    assert intro and "Вот скрин" in intro[0].args[1] and "следующее сообщение" in intro[0].args[1]
    bot.copy_message.assert_awaited_with(USER, from_chat_id=ADMIN, message_id=77)


@pytest.mark.asyncio
async def test_a_very_long_answer_is_sent_whole_after_the_questions():
    bot = _bot()
    await support.relay(_msg(USER, 11, "Вопрос"), bot)
    await support.relay(_msg(ADMIN, 77, "я" * 4500, reply_to=502), bot)
    intro = [c for c in bot.send_message.await_args_list if c.args[0] == USER and "Пришёл ответ" in c.args[1]]
    assert intro and len(intro[0].args[1]) < 4096 and "следующее сообщение" in intro[0].args[1]
    bot.copy_message.assert_awaited_with(USER, from_chat_id=ADMIN, message_id=77)


def test_the_message_is_short_and_legible_when_there_is_nothing_to_quote():
    text = support.compose_answer([], "Готово")
    assert "Ваш" not in text and "Готово" in text and "Пришёл ответ от поддержки!" in text
