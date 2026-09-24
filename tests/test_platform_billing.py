"""What the bot's owner pays us, period by period.

Two charges and one clock (see `app.services.platform_billing`): the launch,
paid once at the end of building, and a renewal for every period after it.
The rules worth holding onto are all about *not* taking too much and *not*
switching a working shop off too early — those are the ones with money and
somebody else's customers on the other side, so they are what is tested
here.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models.bot import Bot as BotModel
from app.models.bot import BotStatus
from app.models.bot_block import BlockType
from app.models.client import Client
from app.models.payment import Payment, PaymentKind, PaymentStatus
from app.services import payment_service, platform_billing

LAUNCH_AND_MONTHLY = json.dumps(
    [
        {
            "provider": "stripe",
            "price_minor": 9900,
            "renewal_price_minor": 990,
            "currency": "USD",
            "credentials": {"secret_key": "sk_test_x", "webhook_secret": "whsec_x"},
        },
        {
            "provider": "cryptobot",
            "price_minor": 9900,
            "renewal_price_minor": 990,
            "currency": "USDT",
            "credentials": {"token": "crypto-token"},
        },
    ]
)


@pytest.fixture
def priced(monkeypatch):
    """A deployment that charges $99 to launch and $9.90 per 30 days."""
    settings = get_settings()
    monkeypatch.setattr(settings, "platform_payment_methods", LAUNCH_AND_MONTHLY, raising=False)
    monkeypatch.setattr(settings, "renewal_period_days", 30, raising=False)
    monkeypatch.setattr(settings, "renewal_grace_days", 7, raising=False)
    return settings


@pytest_asyncio.fixture
async def live_bot(db: AsyncSession, owner: Client, make_bot) -> BotModel:
    bot, _ = await make_bot(owner, [(BlockType.welcome, {"text": "привет"})], status=BotStatus.active)
    bot.telegram_bot_username = "shop_bot"
    await db.commit()
    return bot


async def _settle(db: AsyncSession, bot: BotModel, kind: PaymentKind, amount: int) -> Payment:
    """A real payment row, settled the way a provider callback settles one."""
    payment = Payment(
        id=uuid.uuid4(),
        kind=kind,
        status=PaymentStatus.pending,
        provider="stripe",
        amount_minor=amount,
        currency="USD",
        description="test",
        bot_id=bot.id,
        client_id=bot.client_id,
        meta={},
    )
    db.add(payment)
    await db.commit()
    await payment_service.mark_paid(db, payment, provider_payment_id=None)
    return payment


# ---------------------------------------------------------------- the prices


def test_the_launch_and_the_renewal_are_separate_prices(priced):
    methods = payment_service.platform_methods()

    assert [(m.price_minor, m.renewal_price_minor) for m in methods] == [(9900, 990), (9900, 990)]
    assert platform_billing.renewal_price() == (990, "USD")


def test_no_renewal_price_means_the_launch_is_all_there_is(monkeypatch):
    """The default, and what every deployment configured before this looked
    like: pay once, the bot runs forever."""
    monkeypatch.setattr(
        get_settings(),
        "platform_payment_methods",
        json.dumps([{"provider": "stripe", "price_minor": 900, "currency": "USD", "credentials": {}}]),
        raising=False,
    )

    assert platform_billing.charges_per_period() is False


# ------------------------------------------------------------------ the clock


@pytest.mark.asyncio
async def test_the_launch_includes_the_first_period(db: AsyncSession, owner: Client, make_bot, priced):
    """Someone who has just paid $99 and is immediately asked for $9.90 has
    been charged twice for the same week, whatever the invoices say."""
    bot, _ = await make_bot(owner, [(BlockType.welcome, {"text": "привет"})], status=BotStatus.draft)

    await _settle(db, bot, PaymentKind.publication, 9900)
    await db.refresh(bot)

    assert bot.publication_paid_at is not None
    assert bot.paid_until is not None
    # 30 days from the moment it was paid, give or take the test's own runtime.
    assert abs((bot.paid_until - datetime.now(timezone.utc)) - timedelta(days=30)) < timedelta(minutes=1)
    assert platform_billing.state_of(bot).state == "active"


@pytest.mark.asyncio
async def test_renewing_early_keeps_the_days_already_paid_for(db: AsyncSession, live_bot: BotModel, priced):
    """Otherwise renewing on the 25th day silently throws five days away, and
    the owner is punished for paying on time."""
    live_bot.paid_until = datetime.now(timezone.utc) + timedelta(days=5)
    await db.commit()

    await _settle(db, live_bot, PaymentKind.renewal, 990)
    await db.refresh(live_bot)

    assert abs((live_bot.paid_until - datetime.now(timezone.utc)) - timedelta(days=35)) < timedelta(minutes=1)


@pytest.mark.asyncio
async def test_renewing_late_does_not_backdate_the_period(db: AsyncSession, live_bot: BotModel, priced):
    """The other direction: three weeks of arrears must not eat three weeks
    of the period just bought — they would be sold days already spent."""
    live_bot.paid_until = datetime.now(timezone.utc) - timedelta(days=21)
    await db.commit()

    await _settle(db, live_bot, PaymentKind.renewal, 990)
    await db.refresh(live_bot)

    assert abs((live_bot.paid_until - datetime.now(timezone.utc)) - timedelta(days=30)) < timedelta(minutes=1)


@pytest.mark.asyncio
async def test_a_bot_from_before_the_monthly_is_never_in_arrears(db: AsyncSession, live_bot: BotModel, priced):
    """Turning a price on must not retroactively put every existing bot into
    its grace period — `paid_until` is NULL for all of them."""
    assert live_bot.paid_until is None

    assert platform_billing.state_of(live_bot).state == "off"

    await platform_billing.sweep(db)
    await db.refresh(live_bot)
    assert live_bot.status == BotStatus.active


# ------------------------------------------------------- running out of money


@pytest.mark.asyncio
async def test_a_period_that_just_ended_does_not_stop_the_bot(db: AsyncSession, live_bot: BotModel, priced, monkeypatch):
    """The grace period is the whole point: the people hurt by switching a
    shop off the hour a card expires are its customers, not its owner."""
    told = []
    monkeypatch.setattr(platform_billing, "_tell_owner", _recorder(told))
    live_bot.paid_until = datetime.now(timezone.utc) - timedelta(hours=1)
    await db.commit()

    assert platform_billing.state_of(live_bot).state == "grace"

    await platform_billing.sweep(db)
    await db.refresh(live_bot)

    assert live_bot.status == BotStatus.active
    mine = _about(told, live_bot)
    assert len(mine) == 1 and "Бот пока работает" in mine[0]


@pytest.mark.asyncio
async def test_the_bot_goes_off_the_air_only_after_the_grace_period(
    db: AsyncSession, live_bot: BotModel, priced, monkeypatch
):
    told = []
    monkeypatch.setattr(platform_billing, "_tell_owner", _recorder(told))
    live_bot.paid_until = datetime.now(timezone.utc) - timedelta(days=8)
    await db.commit()

    await platform_billing.sweep(db)
    await db.refresh(live_bot)

    assert live_bot.status == BotStatus.disabled
    # Told by us, before the webhook went — not by a customer asking why the
    # bot has gone quiet.
    mine = _about(told, live_bot)
    assert len(mine) == 1 and "снят с эфира" in mine[0]


@pytest.mark.asyncio
async def test_suspending_deletes_nothing(db: AsyncSession, live_bot: BotModel, priced, monkeypatch):
    """What the owner is promised on the banner, checked rather than assumed:
    the scenario, the payment setup and the order history survive."""
    monkeypatch.setattr(platform_billing, "_tell_owner", _recorder([]))
    live_bot.paid_until = datetime.now(timezone.utc) - timedelta(days=8)
    await db.commit()
    blocks_before = (await db.execute(select(BotModel).where(BotModel.id == live_bot.id))).scalar_one()
    start_before = blocks_before.start_block_id

    await platform_billing.sweep(db)
    await db.refresh(live_bot)

    assert live_bot.start_block_id == start_before
    assert live_bot.bot_token_encrypted == blocks_before.bot_token_encrypted
    assert live_bot.publication_paid_at == blocks_before.publication_paid_at


@pytest.mark.asyncio
async def test_the_owner_is_nagged_once_per_period_not_once_an_hour(
    db: AsyncSession, live_bot: BotModel, priced, monkeypatch
):
    """The sweep runs hourly; a reminder that runs with it is a bot that
    messages you 120 times before the period ends."""
    told = []
    monkeypatch.setattr(platform_billing, "_tell_owner", _recorder(told))
    live_bot.paid_until = datetime.now(timezone.utc) + timedelta(days=2)
    await db.commit()

    for _ in range(5):
        await platform_billing.sweep(db)

    assert len(_about(told, live_bot)) == 1


@pytest.mark.asyncio
async def test_a_new_period_makes_the_reminders_new_again(
    db: AsyncSession, live_bot: BotModel, priced, monkeypatch
):
    """The counterpart: once renewed, the next period must be able to warn
    again — a stage left at 'already told' would silence it forever."""
    told = []
    monkeypatch.setattr(platform_billing, "_tell_owner", _recorder(told))
    live_bot.paid_until = datetime.now(timezone.utc) + timedelta(days=2)
    await db.commit()
    await platform_billing.sweep(db)

    await _settle(db, live_bot, PaymentKind.renewal, 990)
    await db.refresh(live_bot)
    assert live_bot.billing_notice_stage == platform_billing.NOTICE_NONE

    live_bot.paid_until = datetime.now(timezone.utc) + timedelta(days=2)
    await db.commit()
    await platform_billing.sweep(db)

    assert len(_about(told, live_bot)) == 2


@pytest.mark.asyncio
async def test_paying_brings_a_stopped_bot_back(db: AsyncSession, live_bot: BotModel, priced, monkeypatch):
    """Renewal is the only button a suspended owner should need to find."""
    monkeypatch.setattr(platform_billing, "_tell_owner", _recorder([]))
    registered = []

    async def fake_register(bot_id, token):
        registered.append(bot_id)

    from app.services import bot_registry

    monkeypatch.setattr(bot_registry, "register_webhook", fake_register)
    monkeypatch.setattr(bot_registry, "remove", _noop)
    from app.services import security

    live_bot.bot_token_encrypted = security.encrypt_token("123:abc")
    live_bot.paid_until = datetime.now(timezone.utc) - timedelta(days=8)
    await db.commit()

    await platform_billing.sweep(db)
    await db.refresh(live_bot)
    assert live_bot.status == BotStatus.disabled

    await _settle(db, live_bot, PaymentKind.renewal, 990)
    await db.refresh(live_bot)

    assert live_bot.status == BotStatus.active
    assert registered == [live_bot.id]


@pytest.mark.asyncio
async def test_a_draft_is_not_published_by_a_renewal(db: AsyncSession, owner: Client, make_bot, priced, monkeypatch):
    """`resume` puts a *suspended* bot back; a draft has never been on the
    air and must not arrive there by paying an invoice."""
    monkeypatch.setattr(platform_billing, "_tell_owner", _recorder([]))
    bot, _ = await make_bot(owner, [(BlockType.welcome, {"text": "привет"})], status=BotStatus.draft)
    bot.paid_until = datetime.now(timezone.utc) - timedelta(days=30)
    await db.commit()

    await _settle(db, bot, PaymentKind.renewal, 990)
    await db.refresh(bot)

    assert bot.status == BotStatus.draft


# -------------------------------------------------------------- the endpoints


@pytest.mark.asyncio
async def test_the_paywall_says_what_comes_after_the_launch(api, auth, owner, make_bot, priced):
    """Finding out about a monthly a month after paying is where refund
    requests come from."""
    bot, _ = await make_bot(owner, [(BlockType.welcome, {"text": "привет"})], status=BotStatus.draft)

    info = (await api.get(f"/api/bots/{bot.id}/publication", headers=auth(owner))).json()

    assert info["price_minor"] == 9900
    assert info["renewal_price_minor"] == 990
    assert info["renewal_period_days"] == 30
    assert info["renewal_grace_days"] == 7
    assert all(m["renewal_price_minor"] == 990 for m in info["methods"])


@pytest.mark.asyncio
async def test_billing_state_is_readable_by_the_owner_only(api, auth, owner, stranger, live_bot, db, priced):
    live_bot.paid_until = datetime.now(timezone.utc) + timedelta(days=3)
    await db.commit()

    mine = await api.get(f"/api/bots/{live_bot.id}/billing", headers=auth(owner))
    assert mine.json()["state"] == "active"
    assert mine.json()["days_left"] == 3

    theirs = await api.get(f"/api/bots/{live_bot.id}/billing", headers=auth(stranger))
    assert theirs.status_code == 404


@pytest.mark.asyncio
async def test_there_is_nothing_to_renew_when_nothing_is_charged(api, auth, owner, live_bot, monkeypatch):
    """A deployment that sells the launch only must refuse to invoice for a
    period it does not have."""
    monkeypatch.setattr(
        get_settings(),
        "platform_payment_methods",
        json.dumps([{"provider": "stripe", "price_minor": 900, "currency": "USD", "credentials": {}}]),
        raising=False,
    )

    response = await api.post(f"/api/bots/{live_bot.id}/renewal-checkout", headers=auth(owner), json={})

    assert response.status_code == 400


def _recorder(sink: list[tuple[uuid.UUID, str]]):
    """The sweep scans every bot in the database, and the tests share one —
    so what it said is recorded *with* who it was about, and each test looks
    only at its own bot. Asserting on the raw count made these pass or fail
    on whatever another test (or a leftover row) happened to leave behind.
    """

    async def remember(db, bot, text):
        sink.append((bot.id, text))

    return remember


def _about(told: list[tuple[uuid.UUID, str]], bot: BotModel) -> list[str]:
    return [text for bot_id, text in told if bot_id == bot.id]


async def _noop(*args, **kwargs):
    return None
