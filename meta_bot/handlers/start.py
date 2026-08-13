from aiogram import Router
from aiogram.filters import CommandStart
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message, WebAppInfo

from app.config import get_settings

router = Router(name="start")


@router.message(CommandStart())
async def cmd_start(message: Message) -> None:
    settings = get_settings()

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🛠 Открыть конструктор",
                    web_app=WebAppInfo(url=settings.webapp_url),
                )
            ]
        ]
    )

    await message.answer(
        "Привет! Я Bot Factory 🏭\n\n"
        "Здесь ты можешь собрать своего Telegram-бота без единой строчки кода — "
        "просто перетаскивай блоки в конструкторе.\n\n"
        "Нажми кнопку ниже, чтобы начать 👇",
        reply_markup=keyboard,
    )
