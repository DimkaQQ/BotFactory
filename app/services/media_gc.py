"""Уборка загруженных файлов, на которые больше никто не ссылается.

Файл переживал и блок, и бота, и клиента: удалить его было нечем, потому что
связь «файл → блок» существует только внутри JSONB (`content.media_file_id`
хранит ссылку, а не идентификатор). Каталог рос монотонно и никем не
чистился — на тысяче клиентов это единственное место, которое гарантированно
кончится раньше остального.

Проход простой и намеренно осторожный: для каждого клиента собираем ссылки
из всех его блоков и удаляем из его каталога то, чего среди них нет и что
старше `media_orphan_ttl_hours`. Возраст обязателен — между загрузкой файла и
сохранением блока проходит время, и уборщик, работающий «сразу», отнимал бы
у человека картинку прямо из-под рук.
"""

from __future__ import annotations

import logging
import time
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models.bot import Bot as BotModel
from app.models.bot_block import BotBlock
from app.models.client import Client

logger = logging.getLogger(__name__)

#: Раз в сутки. Файлы никуда не торопятся, а проход читает все блоки всех
#: ботов клиента — делать это чаще незачем.
SWEEP_SECONDS = 24 * 3600.0


async def sweep(db: AsyncSession) -> int:
    """Один проход по всем клиентам. Возвращает, сколько файлов удалено."""
    settings = get_settings()
    root = Path(settings.media_upload_dir)
    if not root.is_dir():
        return 0

    cutoff = time.time() - settings.media_orphan_ttl_hours * 3600
    removed = 0

    for folder in root.iterdir():
        if not folder.is_dir():
            # Файлы, загруженные до появления каталогов на клиента. Кому они
            # принадлежат, теперь не выяснить, поэтому их не трогаем совсем:
            # удалить чужую картинку из живого бота хуже, чем хранить лишнее.
            continue
        try:
            removed += await _sweep_client(db, folder, cutoff)
        except Exception:
            logger.exception("Media GC failed for %s", folder.name)

    if removed:
        logger.info("Media GC removed %d orphaned file(s)", removed)
    return removed


async def _sweep_client(db: AsyncSession, folder: Path, cutoff: float) -> int:
    import uuid as _uuid

    try:
        client_id = _uuid.UUID(folder.name)
    except ValueError:
        return 0

    exists = (
        await db.execute(select(Client.id).where(Client.id == client_id))
    ).scalar_one_or_none()
    if exists is None:
        # Клиента больше нет — вместе с ним уходят и его файлы. Строки в БД
        # уже удалены каскадом, ссылаться на них некому.
        return _drop_all(folder)

    referenced = await _referenced_files(db, client_id)
    removed = 0
    for path in folder.glob("*"):
        if not path.is_file() or path.name in referenced:
            continue
        try:
            if path.stat().st_mtime > cutoff:
                continue  # только что загружен, блок ещё сохраняется
            path.unlink()
            removed += 1
        except OSError:
            logger.info("Could not remove %s", path, exc_info=True)
    return removed


async def _referenced_files(db: AsyncSession, client_id) -> set[str]:
    """Имена файлов, упомянутые хоть в одном блоке этого клиента.

    Смотрим на всё содержимое блока целиком, а не на одно известное поле:
    ссылка на файл может лежать и в тексте, и в кнопке, и в выдаче, и
    удалять «неиспользуемый» файл из-за того, что мы не знали про ещё одно
    поле, — худший из возможных исходов для уборщика.
    """
    import json

    rows = await db.execute(
        select(BotBlock.content)
        .join(BotModel, BotModel.id == BotBlock.bot_id)
        .where(BotModel.client_id == client_id)
    )
    referenced: set[str] = set()
    for (content,) in rows.all():
        if not content:
            continue
        for chunk in json.dumps(content, ensure_ascii=False).split("/api/media/")[1:]:
            name = chunk.split('"')[0].split("?")[0].split("/")[-1].strip()
            if name:
                referenced.add(name)
    return referenced


def _drop_all(folder: Path) -> int:
    removed = 0
    for path in folder.glob("*"):
        try:
            if path.is_file():
                path.unlink()
                removed += 1
        except OSError:
            logger.info("Could not remove %s", path, exc_info=True)
    try:
        folder.rmdir()
    except OSError:
        pass
    return removed


async def sweep_once() -> None:
    from app.database import AsyncSessionLocal

    async with AsyncSessionLocal() as db:
        await sweep(db)


async def sweep_forever(every_seconds: float = SWEEP_SECONDS) -> None:
    import asyncio

    from app.database import AsyncSessionLocal

    while True:
        await asyncio.sleep(every_seconds)
        try:
            async with AsyncSessionLocal() as db:
                await sweep(db)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Media GC sweep failed; will try again")
