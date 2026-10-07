"""Entry point for the meta-bot — the bot users talk to first, which opens
the Bot Factory constructor Mini App. Runs on long polling (it's the only
bot that does; published client bots are served through the shared FastAPI
webhook, see app/routers/webhook.py).
"""

import asyncio
import logging

from aiogram import Bot, Dispatcher

from app.config import get_settings
from app.services.telegram_session import build_bot_session
from meta_bot.handlers.admin import router as admin_router
from meta_bot.handlers.menu import router as menu_router
from meta_bot.handlers.payments import router as payments_router
from meta_bot.handlers.support import router as support_router

logging.basicConfig(level=logging.INFO)
# httpx на INFO пишет полный URL запроса, а в нём токен бота (.../bot<TOKEN>/getMe).
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)


def build_dispatcher() -> Dispatcher:
    """Порядок роутеров важен и потому собран в одном месте (его проверяет тест)."""
    dp = Dispatcher()
    # Платежи первыми: сообщение об оплате не должно попасть в «поддержку».
    dp.include_router(payments_router)
    # Модерация оператора: только свои id и свои команды, остальным не отвечает.
    dp.include_router(admin_router)
    dp.include_router(menu_router)
    # Последним: он ловит всё, что не команда, — команды должны достаться раньше.
    dp.include_router(support_router)
    return dp


async def main() -> None:
    settings = get_settings()
    if not settings.meta_bot_token:
        raise RuntimeError("META_BOT_TOKEN is not set")

    bot = Bot(token=settings.meta_bot_token, session=build_bot_session())
    dp = build_dispatcher()

    # Make sure we're not stuck on a leftover webhook from a previous deploy.
    await bot.delete_webhook(drop_pending_updates=False)

    logger.info("Meta-bot starting (polling)...")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
