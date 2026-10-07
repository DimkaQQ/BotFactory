"""Команды для владельца сервиса: блокировка нарушителя, выгрузка и удаление данных.

Запуск на сервере:

    docker compose exec api python -m app.admin ban 123456789 --reason "спам"
    docker compose exec api python -m app.admin unban 123456789
    docker compose exec api python -m app.admin export 123456789 > export.json
    docker compose exec api python -m app.admin delete 123456789 --yes

Человек задаётся числовым Telegram id (его видно в обращении в поддержку и в
таблице clients). Подробности и порядок действий — в deploy/runbook.md.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.database import AsyncSessionLocal
from app.models.bot import Bot
from app.models.bot_block import BotBlock
from app.models.client import Client
from app.models.payment import Payment
from app.models.scheduled_step import ScheduledStep, StepStatus
from app.services.security import decrypt_token


async def _client(db: AsyncSession, telegram_id: int) -> Client:
    client = (await db.execute(select(Client).where(Client.telegram_user_id == telegram_id))).scalar_one_or_none()
    if client is None:
        raise SystemExit(f"Клиент с Telegram id {telegram_id} не найден")
    return client


async def ban(db: AsyncSession, telegram_id: int, reason: str = "") -> str:
    """Закрыть вход, заглушить всех ботов и отменить отложенные сообщения."""
    client = await _client(db, telegram_id)
    now = datetime.now(timezone.utc)
    client.banned_at = now
    client.sessions_valid_from = now  # выбросить из всех открытых сессий
    bots = list((await db.execute(select(Bot).where(Bot.client_id == client.id))).scalars())
    for bot in bots:
        bot.paused = True
    bot_ids = [bot.id for bot in bots]
    cancelled = 0
    if bot_ids:
        result = await db.execute(
            update(ScheduledStep)
            .where(ScheduledStep.bot_id.in_(bot_ids), ScheduledStep.status == StepStatus.pending)
            .values(status=StepStatus.cancelled, last_error=f"аккаунт заблокирован: {reason}"[:500])
        )
        cancelled = result.rowcount or 0
    await db.commit()
    return f"Заблокирован {telegram_id}: ботов на паузе — {len(bots)}, отменено отложенных сообщений — {cancelled}"


async def unban(db: AsyncSession, telegram_id: int) -> str:
    client = await _client(db, telegram_id)
    client.banned_at = None
    await db.commit()
    return (
        f"Разблокирован {telegram_id}. Боты остались на паузе — владелец включит их сам "
        "в меню @DragDropBot (отменённые отложенные сообщения не возвращаются)."
    )


def _plain(value):
    if value is None or isinstance(value, (bool, int, float, str, dict, list)):
        return value
    if isinstance(value, datetime):
        return value.isoformat()
    return str(getattr(value, "value", value))


def _row(obj, skip: set[str] | None = None) -> dict:
    return {c.name: _plain(getattr(obj, c.name)) for c in obj.__table__.columns if c.name not in (skip or set())}


async def export(db: AsyncSession, telegram_id: int) -> dict:
    """Всё, что мы храним о человеке как о владельце: профиль, боты, блоки, платежи.

    Токены и ключи касс не выгружаются — это секреты, а не данные человека.
    """
    client = await _client(db, telegram_id)
    bots = list((await db.execute(select(Bot).where(Bot.client_id == client.id))).scalars())
    secret = {"bot_token_encrypted", "payment_credentials_encrypted"}
    result = {"client": _row(client, {"sessions_valid_from"}), "bots": []}
    for bot in bots:
        blocks = list((await db.execute(select(BotBlock).where(BotBlock.bot_id == bot.id))).scalars())
        result["bots"].append({**_row(bot, secret), "blocks": [_row(block) for block in blocks]})
    payments = list(
        (
            await db.execute(
                select(Payment).where(
                    (Payment.client_id == client.id) | (Payment.bot_id.in_([bot.id for bot in bots]))
                )
            )
        ).scalars()
    )
    result["payments"] = [_row(payment) for payment in payments]
    return result


async def delete(db: AsyncSession, telegram_id: int) -> str:
    """Удалить аккаунт: боты (с отключением вебхуков), блоки, подписчики, файлы.

    Платёжные записи остаются обезличенными по связи с аккаунтом — это учёт, и
    его срок хранения задаёт закон, а не просьба об удалении.
    """
    from app.services import bot_registry

    client = await _client(db, telegram_id)
    bots = list((await db.execute(select(Bot).where(Bot.client_id == client.id))).scalars())
    for bot in bots:
        token = decrypt_token(bot.bot_token_encrypted) if bot.bot_token_encrypted else None
        await bot_registry.remove(bot.id, token)
    client_id = client.id
    await db.delete(client)
    await db.commit()
    media = Path(get_settings().media_upload_dir) / str(client_id)
    removed_files = media.exists()
    shutil.rmtree(media, ignore_errors=True)
    return (
        f"Удалён {telegram_id}: ботов — {len(bots)}, каталог файлов {'удалён' if removed_files else 'не найден'}. "
        "Из резервных копий данные уйдут по мере ротации (см. deploy/runbook.md)."
    )


async def _run(args: argparse.Namespace) -> int:
    async with AsyncSessionLocal() as db:
        if args.command == "ban":
            from app.services import moderation

            print(await moderation.ban_client(db, args.telegram_id, actor="cli", reason=args.reason))
        elif args.command == "unban":
            from app.services import moderation

            print(await moderation.unban_client(db, args.telegram_id, actor="cli"))
        elif args.command == "export":
            print(json.dumps(await export(db, args.telegram_id), ensure_ascii=False, indent=2))
        elif args.command == "delete":
            if not args.yes:
                print("Удаление необратимо. Повтори команду с --yes, если уверен.", file=sys.stderr)
                return 2
            print(await delete(db, args.telegram_id))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.admin", description=__doc__.split("\n\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("ban", "unban", "export", "delete"):
        p = sub.add_parser(name)
        p.add_argument("telegram_id", type=int)
        if name == "ban":
            p.add_argument("--reason", default="", help="причина — попадёт в журнал отменённых сообщений")
        if name == "delete":
            p.add_argument("--yes", action="store_true", help="подтвердить необратимое удаление")
    return asyncio.run(_run(parser.parse_args(argv)))


if __name__ == "__main__":
    raise SystemExit(main())
