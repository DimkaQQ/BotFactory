"""Перешифровать всё хранимое текущим ключом.

Запускать после смены `FERNET_KEY` — когда прежний ключ ещё лежит в
`FERNET_KEYS_RETIRED`, иначе расшифровать старые записи будет нечем:

    # 1. новый ключ первым, старый — в отставные
    FERNET_KEY=<новый>
    FERNET_KEYS_RETIRED=<старый>
    # 2. перезапустить сервис (он уже читает оба)
    # 3. перешифровать
    python -m app.rotate_keys
    # 4. и только теперь убрать старый из FERNET_KEYS_RETIRED

Шаг 3 не обязателен для работы — `MultiFernet` расшифрует старые записи и
без него. Он обязателен для того, чтобы старый ключ можно было наконец
выбросить: пока хоть одна строка зашифрована им, он остаётся действующим
ключом от всех касс всех клиентов.

Идемпотентен: перешифровать уже перешифрованное безвредно. Ничего не
удаляет и не меняет по смыслу — только переупаковывает.
"""

from __future__ import annotations

import asyncio
import logging

from sqlalchemy import select

from app.models.bot import Bot as BotModel
from app.models.subscription import Subscription
from app.services.security import decrypt_token, encrypt_token

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger("rotate")


def _redo(blob: bytes | None) -> bytes | None:
    if not blob:
        return None
    return encrypt_token(decrypt_token(blob))


async def rotate() -> dict[str, int]:
    from app.database import AsyncSessionLocal

    counts = {"bot_tokens": 0, "payment_credentials": 0, "recurring_tokens": 0, "failed": 0}

    async with AsyncSessionLocal() as db:
        bots = (await db.execute(select(BotModel))).scalars().all()
        for bot in bots:
            try:
                if bot.bot_token_encrypted:
                    bot.bot_token_encrypted = _redo(bot.bot_token_encrypted)
                    counts["bot_tokens"] += 1
                if bot.payment_credentials_encrypted:
                    bot.payment_credentials_encrypted = _redo(bot.payment_credentials_encrypted)
                    counts["payment_credentials"] += 1
            except Exception:
                # Одна нерасшифровываемая строка не должна останавливать
                # ротацию: сообщаем и идём дальше, иначе половина базы
                # останется на старом ключе из-за одной порченой записи.
                counts["failed"] += 1
                logger.exception("Не смог перешифровать бота %s", bot.id)
        await db.commit()

        subs = (await db.execute(select(Subscription))).scalars().all()
        for sub in subs:
            blob = (sub.meta or {}).get("recurring_token")
            if not blob:
                continue
            try:
                sub.meta = {
                    **(sub.meta or {}),
                    "recurring_token": _redo(blob.encode("ascii")).decode("ascii"),
                }
                counts["recurring_tokens"] += 1
            except Exception:
                counts["failed"] += 1
                logger.exception("Не смог перешифровать подписку %s", sub.id)
        await db.commit()

    return counts


def main() -> None:
    counts = asyncio.run(rotate())
    logger.info(
        "Перешифровано: токенов ботов %d, ключей касс %d, сохранённых способов оплаты %d; ошибок %d",
        counts["bot_tokens"], counts["payment_credentials"], counts["recurring_tokens"], counts["failed"],
    )
    if counts["failed"]:
        logger.warning(
            "Старый ключ убирать НЕЛЬЗЯ, пока есть ошибки: этими записями он всё ещё пользуется."
        )
    else:
        logger.info("Ошибок нет — старый ключ можно убрать из FERNET_KEYS_RETIRED.")


if __name__ == "__main__":
    main()
