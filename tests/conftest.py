"""Shared fixtures.

Two things shape this file.

The tests talk to a **real PostgreSQL** — the same one the app uses — rather
than SQLite, because most of what is worth testing here is Postgres-specific:
JSONB block content, the `Identity` sequence behind `invoice_no`, and the
`ON DELETE CASCADE` chain that the `owner` fixture leans on to clean up.

And they reach the API **through the ASGI app in-process**, not over a
socket, so `pytest` needs nothing running but the database.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator, Callable
from contextlib import contextmanager
from unittest.mock import AsyncMock

import httpx
import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import AsyncSessionLocal, engine
from app.main import app
from app.services import background
from app.models.bot import Bot as BotModel
from app.models.bot import BotStatus
from app.models.bot_block import BlockType, BotBlock
from app.models.client import Client
from app.services.session_token import create_session_token

# Telegram ids are unique per client, so tests that run in the same database
# need ids that cannot collide with each other or with real data.
_TEST_TG_ID_BASE = 990_000_000


@pytest.fixture(scope="session")
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture(autouse=True)
def _allow_the_test_till(monkeypatch: pytest.MonkeyPatch) -> None:
    """Почти всё здесь платит платформе «Тестовой оплатой».

    В бою она запрещена как наша касса (отмечает счёт оплаченным по открытию
    ссылки), поэтому тесты включают её явным флагом — а то, что без флага она
    действительно отключается, проверяется отдельно в test_audit_fixes.
    """
    from app.config import get_settings

    monkeypatch.setattr(get_settings(), "platform_allow_test_till", True, raising=False)


@pytest_asyncio.fixture(autouse=True)
async def _fresh_pool() -> AsyncIterator[None]:
    """Drop the engine's pooled connections between tests.

    The app's engine is a module-level singleton, while pytest-asyncio runs
    each test in its own event loop. A connection left in the pool belongs to
    the loop that opened it, and reusing (or even closing) it from the next
    test's loop raises "Event loop is closed" from deep inside asyncpg. The
    pool is not what these tests are measuring, so it is simply emptied.

    Background work is stopped first: a task the request only scheduled may
    still be holding a session, and it has to be gone before the pool is.
    """
    yield
    await background.cancel_all()
    await engine.dispose()


@pytest_asyncio.fixture
async def db() -> AsyncIterator[AsyncSession]:
    async with AsyncSessionLocal() as session:
        yield session


@pytest_asyncio.fixture
async def owner(db: AsyncSession) -> AsyncIterator[Client]:
    """A client, removed afterwards along with everything they own.

    Bots, blocks and payments all cascade from `clients`, so deleting the one
    row is enough — and it stays enough as the schema grows, which a
    hand-written teardown list would not.
    """
    client = Client(
        id=uuid.uuid4(),
        telegram_user_id=_TEST_TG_ID_BASE + uuid.uuid4().int % 1_000_000,
        full_name="Тестовый владелец",
    )
    # Held as a plain value: the rollback below expires every ORM object in
    # the session, and reading `client.id` after that would try to reload it
    # from a transaction that is already gone.
    client_id = client.id
    db.add(client)
    await db.commit()
    try:
        yield client
    finally:
        await db.rollback()
        await db.execute(Client.__table__.delete().where(Client.id == client_id))
        await db.commit()


@pytest_asyncio.fixture
async def stranger(db: AsyncSession) -> AsyncIterator[Client]:
    """A second client, for proving one account cannot reach another's bots."""
    client = Client(
        id=uuid.uuid4(),
        telegram_user_id=_TEST_TG_ID_BASE + uuid.uuid4().int % 1_000_000,
        full_name="Чужой",
    )
    client_id = client.id
    db.add(client)
    await db.commit()
    try:
        yield client
    finally:
        await db.rollback()
        await db.execute(Client.__table__.delete().where(Client.id == client_id))
        await db.commit()


@pytest_asyncio.fixture
async def api() -> AsyncIterator[httpx.AsyncClient]:
    """The real app, in-process. No server to start, no port to pick."""
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver", timeout=30) as client:
        yield client


@pytest.fixture
def auth() -> Callable[[Client], dict[str, str]]:
    """Authorization header for a client, minted the way a login would.

    Going through `/api/auth/telegram-login` would mean forging a signed
    Telegram widget payload in every test; the token is the same either way.
    """

    def make(client: Client) -> dict[str, str]:
        return {"Authorization": f"Bearer {create_session_token(client.id)}"}

    return make


@pytest_asyncio.fixture
async def make_bot(db: AsyncSession) -> Callable:
    """Build a bot with a chain of blocks already wired up.

    `blocks` is a list of (type, content); each block's `next_block_id` points
    at the following one and the first is the start block, which is the shape
    almost every dispatcher test wants.
    """

    async def build(
        owner: Client,
        blocks: list[tuple[BlockType, dict]],
        *,
        provider: str | None = None,
        is_test: bool = True,
        status: BotStatus = BotStatus.active,
        credentials: dict[str, str] | None = None,
    ) -> tuple[BotModel, list[BotBlock]]:
        bot = BotModel(
            id=uuid.uuid4(),
            client_id=owner.id,
            status=status,
            name="Тестовый бот",
            payment_provider=provider,
            payment_is_test=is_test,
        )
        if credentials:
            from app.services.payment_service import encrypt_credentials

            bot.payment_credentials_encrypted = encrypt_credentials(credentials)
        db.add(bot)
        await db.flush()

        rows = [
            BotBlock(bot_id=bot.id, block_type=kind, content=content, order_index=index)
            for index, (kind, content) in enumerate(blocks)
        ]
        db.add_all(rows)
        await db.flush()

        for current, following in zip(rows, rows[1:]):
            current.next_block_id = following.id
        if rows:
            bot.start_block_id = rows[0].id
        await db.commit()
        return bot, rows

    return build


@pytest.fixture
def telegram() -> AsyncMock:
    """Stand-in for the aiogram Bot, with a `sent` helper.

    Every dispatcher test asks the same question — "what did the bot actually
    say?" — so that lives here instead of being re-derived from
    `method_calls` in each test.
    """
    bot = AsyncMock()
    bot.sent = lambda: [call.args[1] for call in bot.method_calls if call[0] == "send_message"]
    bot.keyboards = lambda: [
        call.kwargs["reply_markup"]
        for call in bot.method_calls
        if call[0] == "send_message" and call.kwargs.get("reply_markup") is not None
    ]
    return bot


@pytest.fixture
def as_bot(telegram: AsyncMock, monkeypatch: pytest.MonkeyPatch) -> AsyncMock:
    """Make `bot_registry.get_or_create` hand back the mock.

    Delivery after payment re-fetches the bot from the registry, which would
    otherwise need a real Telegram token.
    """
    from app.services import bot_registry

    async def fake_get_or_create(bot_id, session):
        return telegram

    monkeypatch.setattr(bot_registry, "get_or_create", fake_get_or_create)
    return telegram


@contextmanager
def _mock_http(handler: Callable[[httpx.Request], httpx.Response]):
    """Point every adapter's httpx client at a mock transport.

    Always wraps the *real* class rather than whatever is currently installed,
    so nesting or re-entering this never leaves an earlier handler in place
    answering calls a later test meant to control.
    """
    real = httpx.AsyncClient

    def factory(*args, **kwargs):
        kwargs["transport"] = httpx.MockTransport(handler)
        return real(*args, **kwargs)

    httpx.AsyncClient = factory
    try:
        yield
    finally:
        httpx.AsyncClient = real


@pytest.fixture
def mock_http():
    """`with mock_http(handler):` — every adapter's HTTP calls answered locally."""
    return _mock_http
