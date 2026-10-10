"""Отдельный процесс фоновых задач: планировщик, продления, повторная выдача.

    python -m app.worker

Вынесен из api, чтобы api можно было запускать в нескольких экземплярах и
обновлять по одному: пока api перезапускается, отложенные сообщения и
напоминания об оплате продолжают идти.
"""

from __future__ import annotations

import asyncio
import logging
import signal

from app.services import background, bot_registry, platform_billing
from app.tasks import start_background_tasks

logging.basicConfig(level=logging.INFO)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
logger = logging.getLogger("worker")


async def main() -> None:
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, stop.set)

    start_background_tasks()
    logger.info("Worker started")
    await stop.wait()

    logger.info("Worker stopping")
    await background.wait_for_all(timeout=25.0)
    await background.cancel_all()
    await bot_registry.close_all()
    await platform_billing.close_meta_bot()


if __name__ == "__main__":
    asyncio.run(main())
