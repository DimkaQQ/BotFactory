"""Модерация: жалобы, снятие бота, блокировка, журнал и права оператора."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import delete, select

from app.config import get_settings
from app.models.bot_block import BlockType
from app.models.moderation import AbuseReport, ModerationAction
from app.models.scheduled_step import ScheduledStep, StepStatus
from app.routers import reports as reports_router
from app.services import bot_dispatcher, moderation, owner_panel


@pytest.fixture(autouse=True)
async def _clean(db):
    reports_router._recent.clear()
    yield
    await db.rollback()
    await db.execute(delete(ModerationAction))
    await db.execute(delete(AbuseReport))
    await db.commit()


async def _named_bot(db, owner, make_bot, username: str):
    bot, blocks = await make_bot(owner, [(BlockType.welcome, {"text": "Привет"})])
    bot.telegram_bot_username = username
    await db.commit()
    return bot, blocks


# ------------------------------------------------------------------ форма жалобы


async def test_the_report_page_opens_without_login(api):
    response = await api.get("/report?bot=shady_bot")
    assert response.status_code == 200
    assert "shady_bot" in response.text and "Пожаловаться на бота" in response.text


async def test_a_report_is_saved_and_matched_to_the_bot(api, db, owner, make_bot):
    await _named_bot(db, owner, make_bot, "scam_shop_bot")

    response = await api.post(
        "/report",
        data={"bot": "https://t.me/Scam_Shop_Bot?start=x", "category": "fraud", "details": "Берут деньги и не выдают"},
    )

    assert response.status_code == 200 and "жалоба принята" in response.text
    report = (await db.execute(select(AbuseReport))).scalars().one()
    assert report.category == "fraud" and report.status == "new" and report.bot_id is not None


async def test_a_report_about_an_unknown_bot_is_still_kept(api, db):
    await api.post("/report", data={"bot": "@no_such_bot", "category": "other", "details": "Что-то подозрительное"})
    report = (await db.execute(select(AbuseReport))).scalars().one()
    assert report.bot_id is None and report.bot_ref == "@no_such_bot"


async def test_an_empty_or_too_short_report_is_refused_with_the_form_back(api, db):
    response = await api.post("/report", data={"bot": "@x_bot", "details": "коротко"})
    assert response.status_code == 400 and "Опишите" in response.text
    assert (await db.execute(select(AbuseReport))).scalars().first() is None


async def test_the_bot_trap_field_drops_the_report_silently(api, db):
    response = await api.post(
        "/report", data={"bot": "@x_bot", "details": "спам спам спам спам", "website": "http://spam"}
    )
    assert response.status_code == 200
    assert (await db.execute(select(AbuseReport))).scalars().first() is None


async def test_too_many_reports_from_one_address_are_throttled(api):
    for _ in range(reports_router.LIMIT):
        assert (await api.post("/report", data={"bot": "@x_bot", "details": "достаточно длинный текст"})).status_code == 200
    blocked = await api.post("/report", data={"bot": "@x_bot", "details": "достаточно длинный текст"})
    assert blocked.status_code == 429


async def test_a_client_bot_answers_the_report_command_with_the_link(db, owner, make_bot, telegram):
    bot, _ = await _named_bot(db, owner, make_bot, "shop_bot")
    await bot_dispatcher.process_update(
        telegram, {"message": {"chat": {"id": 5}, "from": {"id": 5}, "text": "/report"}}, bot.id, db
    )
    assert any("/report?bot=shop_bot" in text for text in telegram.sent())


# ------------------------------------------------------------ снятие бота и журнал


async def test_blocking_a_bot_pauses_it_cancels_steps_and_writes_the_journal(db, owner, make_bot):
    bot, _ = await _named_bot(db, owner, make_bot, "bad_bot")
    step = ScheduledStep(
        bot_id=bot.id, chat_id=1, telegram_user_id=1, run_at=datetime.now(timezone.utc), status=StepStatus.pending
    )
    db.add(step)
    report = await moderation.submit_report(
        db, bot_ref="@bad_bot", category="illegal", details="Продают запрещённое"
    )
    await db.commit()

    await moderation.block_bot(db, bot.id, actor="tg:1", reason="жалоба", report_id=report.id)

    await db.refresh(bot)
    await db.refresh(step)
    await db.refresh(report)
    assert bot.paused and bot.moderation_blocked_at is not None
    assert step.status == StepStatus.cancelled
    assert report.status == "actioned" and report.resolved_at is not None
    entry = (await db.execute(select(ModerationAction))).scalars().one()
    assert entry.action == "block_bot" and entry.actor == "tg:1" and entry.client_telegram_id == owner.telegram_user_id


async def test_the_owner_cannot_unpause_a_bot_the_operator_took_down(db, owner, make_bot):
    bot, _ = await _named_bot(db, owner, make_bot, "bad_bot")
    await moderation.block_bot(db, bot.id, actor="tg:1", reason="жалоба")

    with pytest.raises(owner_panel.PauseError, match="снят платформой"):
        await owner_panel.set_paused(db, owner, bot.id, False)

    await moderation.restore_bot(db, bot.id, actor="tg:1")
    await db.refresh(bot)
    assert not bot.paused and bot.moderation_blocked_at is None
    actions = [a.action for a in (await db.execute(select(ModerationAction))).scalars()]
    assert sorted(actions) == ["block_bot", "restore_bot"]


async def test_restoring_a_bot_that_was_never_blocked_is_refused(db, owner, make_bot):
    bot, _ = await _named_bot(db, owner, make_bot, "fine_bot")
    with pytest.raises(moderation.ModerationError):
        await moderation.restore_bot(db, bot.id, actor="tg:1")


async def test_banning_a_client_is_logged_and_closes_the_account(db, owner, make_bot):
    bot, _ = await _named_bot(db, owner, make_bot, "x_bot")
    await moderation.ban_client(db, owner.telegram_user_id, actor="cli", reason="мошенничество")
    await db.refresh(owner)
    await db.refresh(bot)
    assert owner.banned_at is not None and bot.paused
    entry = (await db.execute(select(ModerationAction))).scalars().one()
    assert entry.action == "ban_client" and entry.actor == "cli" and entry.reason == "мошенничество"

    await moderation.unban_client(db, owner.telegram_user_id, actor="cli")
    await db.refresh(owner)
    assert owner.banned_at is None


async def test_dismissing_a_report_closes_it_and_is_logged(db):
    report = await moderation.submit_report(db, bot_ref="@a_bot", category="spam", details="Это не нарушение вовсе")
    await moderation.dismiss_report(db, report.id, actor="tg:1", reason="не нарушение")
    await db.refresh(report)
    assert report.status == "dismissed"
    assert await moderation.open_reports(db) == []
    assert (await moderation.journal(db))[0].action == "dismiss_report"


# ------------------------------------------------------ панель оператора в мета-боте


async def test_only_listed_operators_pass_the_admin_filter(monkeypatch):
    from meta_bot.handlers import admin

    monkeypatch.setattr(get_settings(), "admin_telegram_ids", "111, 222", raising=False)
    assert admin._is_admin(111) and admin._is_admin(222)
    assert not admin._is_admin(333) and not admin._is_admin(None)

    monkeypatch.setattr(get_settings(), "admin_telegram_ids", "", raising=False)
    assert not admin._is_admin(111)


async def test_the_block_button_takes_the_bot_down_and_closes_the_report(db, owner, make_bot, monkeypatch):
    from meta_bot.handlers import admin

    monkeypatch.setattr(get_settings(), "admin_telegram_ids", "777", raising=False)
    bot, _ = await _named_bot(db, owner, make_bot, "bad_bot")
    report = await moderation.submit_report(db, bot_ref="@bad_bot", category="fraud", details="Обманывают покупателей")

    query = AsyncMock()
    query.from_user.id = 777
    query.data = f"rbc:{report.id.hex}"
    await admin.do_action(query)

    await db.refresh(bot)
    await db.refresh(report)
    assert bot.moderation_blocked_at is not None and report.status == "actioned"
    entry = (await db.execute(select(ModerationAction))).scalars().one()
    assert entry.actor == "tg:777" and entry.report_id == report.id


async def test_the_report_card_offers_actions_and_hides_nothing_private(db, owner, make_bot):
    from meta_bot.handlers import admin

    bot, _ = await _named_bot(db, owner, make_bot, "bad_bot")
    report = await moderation.submit_report(
        db, bot_ref="@bad_bot", category="fraud", details="Обманывают <b>покупателей</b>", contact="@victim"
    )
    text, markup = await admin._card(db, report)

    assert "&lt;b&gt;" in text, "текст жалобы экранируется"
    assert str(owner.telegram_user_id) in text
    callbacks = [b.callback_data for row in markup.inline_keyboard for b in row]
    assert {f"rb:{report.id.hex}", f"rn:{report.id.hex}", f"rd:{report.id.hex}"} <= set(callbacks)
    assert bot.id is not None and uuid.UUID(callbacks[0].split(":")[1])
