"""Entry point for the meta-bot — the bot users talk to first, which opens
the Bot Factory constructor Mini App. Runs on long polling (it's the only
bot that does; published client bots are served through the shared FastAPI
webhook, see app/routers/webhook.py).
"""

import asyncio
import logging

from aiogram import Bot, Dispatcher

from app.config import get_settings
from app.services.telegram_session import Ipv4AiohttpSession
from meta_bot.handlers.start import router as start_router

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def main() -> None:
    settings = get_settings()
    if not settings.meta_bot_token:
        raise RuntimeError("META_BOT_TOKEN is not set")

    bot = Bot(token=settings.meta_bot_token, session=Ipv4AiohttpSession())
    dp = Dispatcher()
    dp.include_router(start_router)

    # Make sure we're not stuck on a leftover webhook from a previous deploy.
    await bot.delete_webhook(drop_pending_updates=True)

    logger.info("Meta-bot starting (polling)...")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
