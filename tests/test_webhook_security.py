"""Who is allowed to post an update, and what the request does with it.

`POST /webhook/{bot_id}` is a public URL. Before secret tokens, the only
thing standing between a stranger and a forged update was guessing a UUID —
and a forged `callback_query` can claim to come from the shop owner and
confirm their own payment.
"""

from __future__ import annotations

import uuid

from app.models.bot_block import BlockType
from app.services import background
from app.services.security import webhook_secret

START = {"message": {"chat": {"id": 555}, "from": {"id": 42}, "text": "/start"}}


async def test_an_update_with_the_wrong_secret_is_refused(api, owner, make_bot):
    bot, _ = await make_bot(owner, [(BlockType.welcome, {"text": "Привет!"})])

    response = await api.post(
        f"/webhook/{bot.id}", json=START, headers={"X-Telegram-Bot-Api-Secret-Token": "wrong-secret"}
    )

    assert response.status_code == 403


async def test_an_update_with_no_secret_at_all_is_refused(api, owner, make_bot):
    """The gap the first version of this check left open.

    Rejecting a *wrong* secret while accepting a *missing* one is not a
    smaller hole than having no check: an attacker simply omits the header.
    A forged callback_query can then claim to be the shop owner and confirm
    an unpaid order.
    """
    bot, _ = await make_bot(owner, [(BlockType.welcome, {"text": "Привет!"})])

    response = await api.post(f"/webhook/{bot.id}", json=START)

    assert response.status_code == 403


async def test_an_update_with_the_right_secret_is_accepted(api, owner, make_bot, as_bot):
    bot, _ = await make_bot(owner, [(BlockType.welcome, {"text": "Привет!"})])

    response = await api.post(
        f"/webhook/{bot.id}", json=START, headers={"X-Telegram-Bot-Api-Secret-Token": webhook_secret(bot.id)}
    )

    assert response.status_code == 200
    await background.wait_for_all()
    assert as_bot.sent() == ["Привет!"]


async def test_the_secret_differs_per_bot():
    """One leaked secret must say nothing about any other bot's."""
    a, b = uuid.uuid4(), uuid.uuid4()

    assert webhook_secret(a) != webhook_secret(b)
    assert webhook_secret(a) == webhook_secret(a)


async def test_the_request_answers_without_waiting_for_the_dialogue(api, owner, make_bot, as_bot):
    """A "Пауза" block holds for as long as it is set to, which is far longer
    than Telegram waits before redelivering the update — and a redelivered
    update replays the whole conversation."""
    import asyncio

    bot, _ = await make_bot(
        owner,
        [
            (BlockType.welcome, {"text": "Привет!"}),
            (BlockType.delay, {"seconds": 10}),
            (BlockType.description, {"text": "Спустя паузу"}),
        ],
    )

    started = asyncio.get_running_loop().time()
    response = await api.post(
        f"/webhook/{bot.id}", json=START, headers={"X-Telegram-Bot-Api-Secret-Token": webhook_secret(bot.id)}
    )
    elapsed = asyncio.get_running_loop().time() - started

    assert response.status_code == 200
    assert elapsed < 2, f"запрос держали {elapsed:.1f}с — Telegram успеет переотправить апдейт"

    # The dialogue is still running in the background; the fixtures stop it.


async def test_one_unreadable_token_does_not_stop_the_other_bots(db, owner, make_bot, monkeypatch):
    """Every live bot's webhook is re-registered at startup, and that is how
    they get their secret — so an exception escaping the loop takes the whole
    fleet off the air, since unsigned updates are now refused."""
    from app.models.bot import BotStatus
    from app.services import bot_registry

    broken, _ = await make_bot(owner, [], status=BotStatus.active)
    healthy, _ = await make_bot(owner, [], status=BotStatus.active)
    broken.bot_token_encrypted = b"not-a-fernet-token"
    healthy.bot_token_encrypted = __import__(
        "app.services.security", fromlist=["encrypt_token"]
    ).encrypt_token("123:ok")
    await db.commit()

    registered: list = []

    async def fake_register(bot_id, token):
        registered.append(bot_id)

    monkeypatch.setattr(bot_registry, "register_webhook", fake_register)

    await bot_registry.refresh_all_webhooks()

    assert healthy.id in registered
    assert broken.id not in registered
