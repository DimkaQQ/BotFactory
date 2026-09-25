"""То, что отделяет работающий прототип от SaaS, за который берут деньги.

Каждый тест здесь — про обещание, которое продукт даёт молча: очередь
подписчика переживёт неоплату, рассылка не придёт дважды, отписка что-то
значит, ключ шифрования можно сменить, не потеряв чужие кассы.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

import pytest
from cryptography.fernet import Fernet
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models.bot import Bot as BotModel
from app.models.bot import BotStatus
from app.models.bot_block import BlockType
from app.models.bot_subscriber import BotSubscriber
from app.models.client import Client
from app.models.scheduled_step import ScheduledStep, StepStatus
from app.services import scheduler, security, subscribers

CHAT_ID = 5150
USER_ID = 900090501


async def _reread(db: AsyncSession, step_id: uuid.UUID) -> ScheduledStep:
    """Перечитать шаг, а не достать его из карты идентичности сессии.

    Планировщик работает в своей сессии; обычный `select` здесь вернул бы
    объект, который эта сессия уже держит, со старыми полями — и тест
    сравнивал бы утверждение с тем, что было до прохода.
    """
    return (
        await db.execute(
            select(ScheduledStep)
            .where(ScheduledStep.id == step_id)
            .execution_options(populate_existing=True)
        )
    ).scalar_one()


# ------------------------- очередь переживает снятие бота с эфира


@pytest.mark.asyncio
async def test_a_suspended_bot_keeps_its_queue(db: AsyncSession, owner: Client, make_bot, monkeypatch):
    """Владелец не заплатил вовремя, бот снят — и ВСЁ, что было обещано его
    подписчикам, помечалось failed за пять часов. Заплатил на следующий день,
    бот вернулся, а уроки, за которые люди отдали деньги, не пришли никогда."""
    bot, blocks = await make_bot(
        owner, [(BlockType.description, {"text": "урок 2"})], status=BotStatus.disabled
    )
    bot.bot_token_encrypted = security.encrypt_token("111:abc")
    await db.commit()

    step = await scheduler.schedule(
        db, bot_id=bot.id, block_id=blocks[0].id, chat_id=CHAT_ID,
        telegram_user_id=USER_ID, delay_seconds=0, reason="delay",
    )

    # Десять проходов — вдвое больше лимита попыток.
    for _ in range(10):
        await db.execute(
            ScheduledStep.__table__.update()
            .where(ScheduledStep.id == step.id)
            .values(run_at=datetime.now(timezone.utc) - timedelta(minutes=1))
        )
        await db.commit()
        await scheduler.run_due()

    fresh = await _reread(db, step.id)
    assert fresh.status == StepStatus.pending, f"очередь потеряна: {fresh.status} / {fresh.last_error}"
    assert fresh.attempts <= 1, "удержание жжёт попытки, лимит кончится за часы"

    # Бот вернулся — шаг обязан уйти.
    bot.status = BotStatus.active
    await db.commit()
    sent = AsyncMock()
    monkeypatch.setattr("app.services.bot_registry.get_or_create", AsyncMock(return_value=sent))
    await db.execute(
        ScheduledStep.__table__.update()
        .where(ScheduledStep.id == step.id)
        .values(run_at=datetime.now(timezone.utc) - timedelta(minutes=1))
    )
    await db.commit()
    await scheduler.run_due()

    fresh = await _reread(db, step.id)
    assert fresh.status == StepStatus.sent


@pytest.mark.asyncio
async def test_a_bot_that_never_comes_back_does_not_hold_forever(
    db: AsyncSession, owner: Client, make_bot
):
    """Но ждать вечно тоже нельзя — иначе очередь мёртвых ботов копится
    бесконечно."""
    bot, blocks = await make_bot(
        owner, [(BlockType.description, {"text": "урок"})], status=BotStatus.disabled
    )
    bot.bot_token_encrypted = security.encrypt_token("111:abc")
    await db.commit()
    step = await scheduler.schedule(
        db, bot_id=bot.id, block_id=blocks[0].id, chat_id=CHAT_ID,
        telegram_user_id=USER_ID, delay_seconds=0, reason="delay",
    )
    await db.execute(
        ScheduledStep.__table__.update()
        .where(ScheduledStep.id == step.id)
        .values(
            created_at=datetime.now(timezone.utc) - scheduler._HOLD_LIMIT - timedelta(days=1),
            run_at=datetime.now(timezone.utc) - timedelta(minutes=1),
        )
    )
    await db.commit()

    await scheduler.run_due()

    fresh = await _reread(db, step.id)
    assert fresh.status == StepStatus.cancelled
    assert "не дождались" in fresh.last_error


# ----------------------------------------- рассылка: один клик — одно письмо


@pytest.mark.asyncio
async def test_a_double_click_does_not_broadcast_twice(api, auth, owner: Client, make_bot, db):
    bot, blocks = await make_bot(
        owner, [(BlockType.description, {"text": "у нас скидка"})], status=BotStatus.active
    )
    db.add(BotSubscriber(
        id=uuid.uuid4(), bot_id=bot.id, telegram_user_id=USER_ID, chat_id=CHAT_ID,
    ))
    await db.commit()

    first = await api.post(
        f"/api/bots/{bot.id}/broadcast", headers=auth(owner),
        json={"block_id": str(blocks[0].id), "audience": "all"},
    )
    second = await api.post(
        f"/api/bots/{bot.id}/broadcast", headers=auth(owner),
        json={"block_id": str(blocks[0].id), "audience": "all"},
    )

    assert first.status_code == 200 and first.json()["queued"] == 1
    assert second.status_code == 409, "второй клик разослал сообщение ещё раз"

    queued = (
        await db.execute(
            select(ScheduledStep).where(ScheduledStep.bot_id == bot.id, ScheduledStep.reason == "broadcast")
        )
    ).scalars().all()
    assert len(queued) == 1


@pytest.mark.asyncio
async def test_an_unsubscribed_person_gets_no_broadcast(api, auth, owner: Client, make_bot, db):
    """Единственным способом отписаться было заблокировать бота, а это
    сбрасывалось первым же его сообщением."""
    bot, blocks = await make_bot(
        owner, [(BlockType.description, {"text": "новости"})], status=BotStatus.active
    )
    db.add_all([
        BotSubscriber(id=uuid.uuid4(), bot_id=bot.id, telegram_user_id=USER_ID, chat_id=CHAT_ID),
        BotSubscriber(
            id=uuid.uuid4(), bot_id=bot.id, telegram_user_id=USER_ID + 1, chat_id=CHAT_ID + 1,
            unsubscribed_at=datetime.now(timezone.utc),
        ),
    ])
    await db.commit()

    response = await api.post(
        f"/api/bots/{bot.id}/broadcast", headers=auth(owner),
        json={"block_id": str(blocks[0].id), "audience": "all"},
    )

    assert response.json()["queued"] == 1, "отписавшийся всё равно получил рассылку"


@pytest.mark.asyncio
async def test_writing_again_does_not_resubscribe_you(db: AsyncSession, owner: Client, make_bot, telegram):
    """Отписка снимается только явным /start. Раньше согласием считалось
    любое сообщение — то есть «спасибо» возвращало человека в рассылку."""
    from app.services import bot_dispatcher

    bot, _ = await make_bot(owner, [(BlockType.welcome, {"text": "привет"})], status=BotStatus.active)
    db.add(BotSubscriber(id=uuid.uuid4(), bot_id=bot.id, telegram_user_id=USER_ID, chat_id=CHAT_ID))
    await db.commit()

    message = {"chat": {"id": CHAT_ID}, "from": {"id": USER_ID}, "text": "/stop"}
    await bot_dispatcher.process_update(telegram, {"message": message}, bot.id, db)
    person = await subscribers.get(db, bot.id, USER_ID)
    await db.refresh(person)
    assert person.unsubscribed_at is not None

    # Просто написал — согласия это не значит.
    await bot_dispatcher.process_update(
        telegram, {"message": {**message, "text": "спасибо"}}, bot.id, db
    )
    await db.refresh(person)
    assert person.unsubscribed_at is not None, "случайное сообщение вернуло человека в рассылку"

    # А /start — значит.
    await bot_dispatcher.process_update(
        telegram, {"message": {**message, "text": "/start"}}, bot.id, db
    )
    await db.refresh(person)
    assert person.unsubscribed_at is None


# ------------------------------------------- выдача: группа И файл, не или


@pytest.mark.asyncio
async def test_a_delivery_with_a_group_and_a_file_sends_both(
    db: AsyncSession, owner: Client, make_bot, telegram, monkeypatch
):
    """Продавец «доступ в клуб + методичка» отдавал только клуб."""
    from app.services import bot_dispatcher

    bot, blocks = await make_bot(
        owner,
        [(BlockType.delivery, {
            "text": "Добро пожаловать", "group_chat_id": "-1001", "media_file_id": "FILEID",
            "media_type": "document",
        })],
        status=BotStatus.active,
    )
    monkeypatch.setattr(
        bot_dispatcher, "_deliver_group_invite", AsyncMock(return_value=True)
    )

    await bot_dispatcher.walk_chain(telegram, CHAT_ID, blocks[0].id, bot.id, db, telegram_user_id=USER_ID)

    assert telegram.send_document.await_count == 1, "методичка не ушла"


# ------------------------------------------------ загрузка: сигнатуры файлов


@pytest.mark.asyncio
async def test_a_disguised_file_is_refused(api, auth, owner: Client, make_bot):
    """`epub` и `x-zip-compressed` не проверялись вовсе — на нашем домене
    можно было разместить что угодно."""
    bot, _ = await make_bot(owner, [])

    html_as_epub = await api.post(
        f"/api/bots/{bot.id}/media/upload", headers=auth(owner),
        files={"file": ("x.epub", b"<html><script>alert(1)</script></html>", "application/epub+zip")},
    )
    elf_as_zip = await api.post(
        f"/api/bots/{bot.id}/media/upload", headers=auth(owner),
        files={"file": ("x.zip", b"\x7fELF" + b"\x00" * 100, "application/x-zip-compressed")},
    )
    text_as_mp3 = await api.post(
        f"/api/bots/{bot.id}/media/upload", headers=auth(owner),
        files={"file": ("x.mp3", b"not an mp3 at all", "audio/mpeg")},
    )
    real_zip = await api.post(
        f"/api/bots/{bot.id}/media/upload", headers=auth(owner),
        files={"file": ("x.zip", b"PK\x03\x04" + b"\x00" * 100, "application/zip")},
    )

    assert html_as_epub.status_code == 400
    assert elf_as_zip.status_code == 400
    assert text_as_mp3.status_code == 400
    assert real_zip.status_code == 201, "настоящий архив перестал загружаться"


# --------------------------------------------------- даты в часовом поясе


def test_a_date_is_shown_in_the_deployment_timezone(monkeypatch):
    """«Доступ до 24.10» в UTC у подписчика в UTC+5 — это уже 25-е."""
    from app.services import dates

    evening = datetime(2026, 10, 24, 20, 30, tzinfo=timezone.utc)

    monkeypatch.setattr(get_settings(), "display_timezone", "UTC", raising=False)
    assert dates.day(evening) == "24.10.2026"

    monkeypatch.setattr(get_settings(), "display_timezone", "Asia/Almaty", raising=False)
    assert dates.day(evening) == "25.10.2026"

    # Опечатка в настройке не должна ронять сообщение о покупке.
    monkeypatch.setattr(get_settings(), "display_timezone", "Нет/Такого", raising=False)
    assert dates.day(evening) == "24.10.2026"


# ------------------------------------------------- смена ключа шифрования


@pytest.mark.asyncio
async def test_the_master_key_can_be_rotated_without_losing_anything(
    db: AsyncSession, owner: Client, make_bot, monkeypatch
):
    """Ответ на «что делать, если ключ утёк». До этого его не было: смена
    ключа разом разлогинивала всех и делала нечитаемыми чужие кассы."""
    from app.services.payment_service import decrypt_credentials, encrypt_credentials

    settings = get_settings()
    old_key = settings.fernet_key
    new_key = Fernet.generate_key().decode()

    bot, _ = await make_bot(owner, [])
    bot.bot_token_encrypted = security.encrypt_token("111:SECRET")
    bot.payment_credentials_encrypted = encrypt_credentials({"secret_key": "sk_live_xyz"})
    await db.commit()

    # Новый ключ впереди, старый — в отставных.
    monkeypatch.setattr(settings, "fernet_key", new_key, raising=False)
    monkeypatch.setattr(settings, "fernet_keys_retired", old_key, raising=False)
    security._fernet.cache_clear()
    try:
        # Старое читается сразу, без перешифровки.
        assert security.decrypt_token(bot.bot_token_encrypted) == "111:SECRET"

        from app.rotate_keys import rotate

        counts = await rotate()
        assert counts["failed"] == 0 and counts["bot_tokens"] >= 1

        # Старый ключ выброшен — всё по-прежнему читается.
        monkeypatch.setattr(settings, "fernet_keys_retired", "", raising=False)
        security._fernet.cache_clear()
        await db.refresh(bot)
        assert security.decrypt_token(bot.bot_token_encrypted) == "111:SECRET"
        assert decrypt_credentials(bot.payment_credentials_encrypted) == {"secret_key": "sk_live_xyz"}
    finally:
        monkeypatch.setattr(settings, "fernet_key", old_key, raising=False)
        monkeypatch.setattr(settings, "fernet_keys_retired", "", raising=False)
        security._fernet.cache_clear()


def test_webhook_secrets_survive_a_key_rotation(monkeypatch):
    """Секрет вебхука выводится из отдельного ключа — иначе ротация меняет
    его у всех ботов разом, и Telegram шлёт старый, пока процесс не
    перезапустится."""
    settings = get_settings()
    bot_id = uuid.uuid4()

    monkeypatch.setattr(settings, "webhook_secret_key", "pinned-webhook-key", raising=False)
    before = security.webhook_secret(bot_id)

    monkeypatch.setattr(settings, "fernet_key", Fernet.generate_key().decode(), raising=False)
    security._fernet.cache_clear()

    assert security.webhook_secret(bot_id) == before
