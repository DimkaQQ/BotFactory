"""Conversations that continue later.

The engine used to run a chain to its end inside the update that started it,
which capped "Пауза" at fifteen seconds and made the one thing every
subscription product needs — the next video, next week — unbuildable with
any combination of blocks.

What is pinned here is the seam: where a walk stops and becomes a row, that
the row resumes the *same* chain, that two sweeps cannot both send it, and
that entitlement is re-read at send time rather than trusted from when the
work was queued.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from app.models.bot_block import BlockType, BotBlock
from app.models.scheduled_step import ScheduledStep, StepStatus
from app.models.subscription import BillingMode, Subscription, SubscriptionStatus
from app.services import bot_dispatcher, scheduler

CHAT_ID = 777
USER_ID = 424242


async def steps_of(db, bot_id) -> list[ScheduledStep]:
    # The sweep runs in its own session, so this one still holds whatever it
    # loaded earlier — the app sets `expire_on_commit=False` deliberately,
    # which means a plain re-SELECT hands back the stale identity-mapped copy
    # and reports every step as still pending. `populate_existing` overwrites
    # those instances from the result instead. (Expiring the whole session
    # would do it too, and then blow up on the first lazy load outside a
    # greenlet.)
    result = await db.execute(
        select(ScheduledStep)
        .where(ScheduledStep.bot_id == bot_id)
        .order_by(ScheduledStep.created_at)
        .execution_options(populate_existing=True)
    )
    return list(result.scalars().all())


async def drip_bot(db, owner, make_bot, *, pause_seconds: int):
    """welcome → pause → video. The shape of every "материал придёт позже" bot."""
    bot, blocks = await make_bot(
        owner,
        [
            (BlockType.welcome, {"text": "Добро пожаловать в клуб!"}),
            (BlockType.delay, {"seconds": pause_seconds}),
            (BlockType.description, {"text": "Тренировка №2"}),
        ],
    )
    return bot, blocks


# --------------------------------------------------------------- the seam


async def test_a_short_pause_is_still_just_a_pause(db, owner, make_bot, telegram):
    """Below the inline ceiling nothing is queued — a two-second pause is
    pacing, and a database round trip would cost more than the wait."""
    bot, _ = await drip_bot(db, owner, make_bot, pause_seconds=2)

    await bot_dispatcher.process_update(
        telegram, {"message": {"chat": {"id": CHAT_ID}, "text": "/start"}}, bot.id, db
    )

    assert telegram.sent() == ["Добро пожаловать в клуб!", "Тренировка №2"]
    assert await steps_of(db, bot.id) == []


async def test_a_long_pause_stops_the_walk_and_queues_the_rest(db, owner, make_bot, telegram):
    """The whole point: a week-long pause must not be waited out inside the
    webhook request, and must not be silently clamped to fifteen seconds
    either — the rest of the chain becomes a row with a due date."""
    week = 7 * 24 * 3600
    bot, blocks = await drip_bot(db, owner, make_bot, pause_seconds=week)
    _welcome, _pause, video = blocks

    before = datetime.now(timezone.utc)
    await bot_dispatcher.process_update(
        telegram, {"message": {"chat": {"id": CHAT_ID, "type": "private"}, "text": "/start", "from": {"id": USER_ID}}},
        bot.id, db,
    )

    # The first block went out; the one after the pause did not.
    assert telegram.sent() == ["Добро пожаловать в клуб!"]

    queued = await steps_of(db, bot.id)
    assert len(queued) == 1, "долгая пауза обязана превратиться в отложенный шаг"
    step = queued[0]
    assert step.block_id == video.id, "продолжать надо с блока ПОСЛЕ паузы"
    assert step.chat_id == CHAT_ID
    assert step.telegram_user_id == USER_ID
    assert step.status == StepStatus.pending
    # Due a week out, not now and not in fifteen seconds.
    assert step.run_at - before >= timedelta(days=6, hours=23)


async def test_the_queued_step_sends_exactly_what_the_walk_would_have(db, owner, make_bot, telegram, as_bot):
    bot, blocks = await drip_bot(db, owner, make_bot, pause_seconds=3600)
    await bot_dispatcher.process_update(
        telegram, {"message": {"chat": {"id": CHAT_ID}, "text": "/start"}}, bot.id, db
    )
    telegram.reset_mock()

    step = (await steps_of(db, bot.id))[0]
    step.run_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    await db.commit()

    assert await scheduler.run_due() == 1

    assert telegram.sent() == ["Тренировка №2"]
    await db.refresh(step)
    assert step.status == StepStatus.sent
    assert step.ran_at is not None


async def test_a_chain_of_long_pauses_drips_one_at_a_time(db, owner, make_bot, telegram, as_bot):
    """Four videos over a month is four hops, not one walk — each sweep sends
    one block and re-queues the next, so nothing is ever sent early."""
    bot, blocks = await make_bot(
        owner,
        [
            (BlockType.welcome, {"text": "Оплачено!"}),
            (BlockType.delay, {"seconds": 7 * 24 * 3600}),
            (BlockType.description, {"text": "Видео 1"}),
            (BlockType.delay, {"seconds": 7 * 24 * 3600}),
            (BlockType.description, {"text": "Видео 2"}),
        ],
    )

    await bot_dispatcher.process_update(
        telegram, {"message": {"chat": {"id": CHAT_ID}, "text": "/start"}}, bot.id, db
    )
    assert telegram.sent() == ["Оплачено!"]

    for expected in ("Видео 1", "Видео 2"):
        telegram.reset_mock()
        pending = [s for s in await steps_of(db, bot.id) if s.status == StepStatus.pending]
        assert len(pending) == 1, f"перед «{expected}» в очереди должен быть ровно один шаг"
        pending[0].run_at = datetime.now(timezone.utc) - timedelta(seconds=1)
        await db.commit()
        await scheduler.run_due()
        assert telegram.sent() == [expected]


# ------------------------------------------------------- exactly once


async def test_two_sweeps_racing_on_one_step_send_it_once(db, owner, make_bot, telegram, as_bot):
    """The same guarantee the payment path has, for the same reason: the row
    leaves `pending` in the statement that checks it is still there."""
    bot, _ = await drip_bot(db, owner, make_bot, pause_seconds=3600)
    await bot_dispatcher.process_update(
        telegram, {"message": {"chat": {"id": CHAT_ID}, "text": "/start"}}, bot.id, db
    )
    telegram.reset_mock()

    step = (await steps_of(db, bot.id))[0]
    step.run_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    await db.commit()

    await asyncio.gather(*(scheduler.run_due() for _ in range(8)))

    assert telegram.sent() == ["Тренировка №2"], "восемь одновременных проходов — одна отправка"


async def test_a_deleted_block_cancels_the_step_instead_of_vanishing(db, owner, make_bot, telegram, as_bot):
    """ON DELETE SET NULL means the row survives its target. It must say so,
    not sit pending forever and not look as if it ran."""
    bot, blocks = await drip_bot(db, owner, make_bot, pause_seconds=3600)
    await bot_dispatcher.process_update(
        telegram, {"message": {"chat": {"id": CHAT_ID}, "text": "/start"}}, bot.id, db
    )
    telegram.reset_mock()

    step = (await steps_of(db, bot.id))[0]
    step.run_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    await db.commit()
    await db.delete(blocks[2])
    await db.commit()

    await scheduler.run_due()

    await db.refresh(step)
    assert step.status == StepStatus.cancelled
    assert "удал" in step.last_error
    assert telegram.sent() == []


# ------------------------------------------- entitlement is re-read, not trusted


async def subscription_row(db, bot, *, status=SubscriptionStatus.active, days_left=10) -> Subscription:
    row = Subscription(
        bot_id=bot.id,
        block_id=None,
        telegram_user_id=USER_ID,
        chat_id=CHAT_ID,
        provider="stars",
        billing_mode=BillingMode.auto,
        status=status,
        period_days=30,
        amount_minor=59000,
        currency="RUB",
        title="Закрытый клуб",
        current_period_end=datetime.now(timezone.utc) + timedelta(days=days_left),
    )
    db.add(row)
    await db.commit()
    return row


@pytest.mark.parametrize(
    "status, days_left, why",
    [
        (SubscriptionStatus.cancelled, 10, "отменённая подписка не досылает оплаченное"),
        (SubscriptionStatus.expired, 10, "закончившаяся подписка не досылает"),
        (SubscriptionStatus.active, -1, "период кончился — статус ещё не успели поменять"),
    ],
)
async def test_work_queued_while_healthy_is_dropped_once_it_is_not(
    db, owner, make_bot, telegram, as_bot, status, days_left, why
):
    """Everything in the queue was queued while the subscription was fine.
    Whether it still is gets decided at send time — including by the date
    alone, because a period ending is a moment, not an event somebody has to
    remember to record."""
    bot, blocks = await drip_bot(db, owner, make_bot, pause_seconds=3600)
    subscription = await subscription_row(db, bot, status=status, days_left=days_left)

    step = ScheduledStep(
        bot_id=bot.id,
        block_id=blocks[2].id,
        chat_id=CHAT_ID,
        telegram_user_id=USER_ID,
        subscription_id=subscription.id,
        reason="delay",
        run_at=datetime.now(timezone.utc) - timedelta(seconds=1),
    )
    db.add(step)
    await db.commit()

    await scheduler.run_due()

    await db.refresh(step)
    assert step.status == StepStatus.cancelled, why
    assert telegram.sent() == []


async def test_cancelling_a_subscription_empties_its_queue(db, owner, make_bot, telegram):
    bot, blocks = await drip_bot(db, owner, make_bot, pause_seconds=3600)
    subscription = await subscription_row(db, bot)
    for _ in range(3):
        db.add(
            ScheduledStep(
                bot_id=bot.id,
                block_id=blocks[2].id,
                chat_id=CHAT_ID,
                telegram_user_id=USER_ID,
                subscription_id=subscription.id,
                run_at=datetime.now(timezone.utc) + timedelta(days=7),
            )
        )
    await db.commit()

    assert await scheduler.cancel_for_subscription(db, subscription.id, why="отменено") == 3

    remaining = [s for s in await steps_of(db, bot.id) if s.status == StepStatus.pending]
    assert remaining == []


# --------------------------------------------------- the poll that collected nothing


async def test_a_poll_answer_is_recorded_against_the_block_that_asked(db, owner, make_bot, telegram):
    """The block sent a real poll and the landing page sold it as a way to
    find out what subscribers want. `poll_answer` was not in the bot's
    allowed_updates, so Telegram never delivered an answer — and there was
    nowhere to put one."""
    from app.models.poll_answer import PollAnswer

    bot, blocks = await make_bot(
        owner,
        [(BlockType.poll, {"question": "Что снимать дальше?", "options": ["Ноги", "Спина", "Руки"]})],
    )
    poll_block = blocks[0]

    telegram.send_poll.return_value = type("Sent", (), {"poll": type("P", (), {"id": "tg_poll_77"})()})()

    await bot_dispatcher.process_update(
        telegram, {"message": {"chat": {"id": CHAT_ID}, "from": {"id": USER_ID}, "text": "/start"}}, bot.id, db
    )
    from app.models.poll_send import PollSend

    sent = (
        await db.execute(select(PollSend).where(PollSend.telegram_poll_id == "tg_poll_77"))
    ).scalar_one_or_none()
    assert sent is not None and sent.block_id == poll_block.id, "иначе ответ не привязать к блоку"

    await bot_dispatcher.process_update(
        telegram,
        {"poll_answer": {"poll_id": "tg_poll_77", "user": {"id": USER_ID}, "option_ids": [1]}},
        bot.id,
        db,
    )

    saved = (
        await db.execute(select(PollAnswer).where(PollAnswer.block_id == poll_block.id))
    ).scalars().all()
    assert len(saved) == 1
    assert saved[0].option_ids == [1]
    assert saved[0].telegram_user_id == USER_ID


async def test_changing_your_mind_replaces_the_answer_instead_of_counting_twice(db, owner, make_bot, telegram):
    from app.models.poll_answer import PollAnswer

    bot, blocks = await make_bot(
        owner, [(BlockType.poll, {"question": "Что снимать?", "options": ["Ноги", "Спина"]})]
    )
    telegram.send_poll.return_value = type("Sent", (), {"poll": type("P", (), {"id": "tg_poll_88"})()})()
    await bot_dispatcher.process_update(
        telegram, {"message": {"chat": {"id": CHAT_ID}, "from": {"id": USER_ID}, "text": "/start"}}, bot.id, db
    )

    for picked in ([0], [1]):
        await bot_dispatcher.process_update(
            telegram,
            {"poll_answer": {"poll_id": "tg_poll_88", "user": {"id": USER_ID}, "option_ids": picked}},
            bot.id,
            db,
        )

    saved = (
        await db.execute(
            select(PollAnswer)
            .where(PollAnswer.block_id == blocks[0].id)
            .execution_options(populate_existing=True)
        )
    ).scalars().all()
    assert len(saved) == 1, "один человек — один голос"
    assert saved[0].option_ids == [1]


async def test_a_bot_asks_telegram_for_poll_answers_at_all():
    """Everything above is unreachable if the update type is not subscribed."""
    import inspect

    from app.services import bot_registry

    source = inspect.getsource(bot_registry)
    assert '"poll_answer"' in source, "без poll_answer в allowed_updates Telegram ответы не пришлёт"


# ------------------------------------------------------------ рассылка


async def test_a_broadcast_reaches_everyone_the_bot_knows(db, owner, make_bot, api, auth, telegram, as_bot):
    """The landing page has promised «рассылка» since day one and the
    constructor could not send anything to anybody after the update that
    triggered it."""
    from app.models.bot import BotStatus
    from app.models.bot_subscriber import BotSubscriber

    bot, blocks = await make_bot(
        owner, [(BlockType.description, {"text": "Скидка 20% до воскресенья!"})], status=BotStatus.active
    )
    for index in range(3):
        db.add(
            BotSubscriber(
                bot_id=bot.id,
                telegram_user_id=9000 + index,
                chat_id=9000 + index,
                first_name=f"Клиент {index}",
            )
        )
    # Someone who blocked the bot: writing to them fails forever, so they are
    # not queued at all.
    db.add(
        BotSubscriber(
            bot_id=bot.id,
            telegram_user_id=9100,
            chat_id=9100,
            first_name="Ушёл",
            blocked_at=datetime.now(timezone.utc),
        )
    )
    await db.commit()

    response = await api.post(
        f"/api/bots/{bot.id}/broadcast",
        headers=auth(owner),
        json={"block_id": str(blocks[0].id), "audience": "all"},
    )
    assert response.status_code == 200, response.text
    assert response.json()["queued"] == 3, "заблокировавший бота в очередь не попадает"

    await scheduler.run_due()
    assert sorted(telegram.sent()) == ["Скидка 20% до воскресенья!"] * 3


async def test_a_broadcast_to_subscribers_only_skips_everyone_else(db, owner, make_bot, api, auth, as_bot):
    """«Новый выпуск для подписчиков» and «у нас скидка» go to different
    rooms — sending the first to everyone gives away who is paying."""
    from app.models.bot import BotStatus
    from app.models.bot_subscriber import BotSubscriber

    bot, blocks = await make_bot(
        owner, [(BlockType.description, {"text": "Выпуск 5 уже в канале"})], status=BotStatus.active
    )
    db.add_all(
        [
            BotSubscriber(bot_id=bot.id, telegram_user_id=9200, chat_id=9200, first_name="Платит"),
            BotSubscriber(bot_id=bot.id, telegram_user_id=9201, chat_id=9201, first_name="Просто зашёл"),
        ]
    )
    db.add(
        Subscription(
            bot_id=bot.id,
            telegram_user_id=9200,
            chat_id=9200,
            provider="stars",
            billing_mode=BillingMode.auto,
            status=SubscriptionStatus.active,
            period_days=30,
            amount_minor=59000,
            currency="RUB",
            title="Клуб",
            current_period_end=datetime.now(timezone.utc) + timedelta(days=10),
        )
    )
    await db.commit()

    response = await api.post(
        f"/api/bots/{bot.id}/broadcast",
        headers=auth(owner),
        json={"block_id": str(blocks[0].id), "audience": "subscribers"},
    )
    assert response.json()["queued"] == 1


async def test_a_draft_bot_cannot_broadcast(db, owner, make_bot, api, auth):
    """There is no token yet, so every send would fail — and the owner would
    find out from a queue of failures rather than from a sentence."""
    from app.models.bot import BotStatus

    bot, blocks = await make_bot(
        owner, [(BlockType.description, {"text": "Привет"})], status=BotStatus.draft
    )

    response = await api.post(
        f"/api/bots/{bot.id}/broadcast",
        headers=auth(owner),
        json={"block_id": str(blocks[0].id), "audience": "all"},
    )
    assert response.status_code == 400
    assert "не опубликован" in response.json()["detail"]
