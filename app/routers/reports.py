"""Страница «Пожаловаться на бота» — открыта всем, без входа.

Отдельная страница без сборки фронтенда и не зависящая от юридических
реквизитов: пожаловаться должно быть можно всегда, даже если приложение не
поднялось или оферта ещё не опубликована.

Защита от мусора простая: скрытое поле-ловушка для ботов, потолок жалоб с
одного адреса в час и лимиты длины. Жалобы читает оператор (мета-бот,
`/reports`), переписку покупателей эта страница не открывает.
"""

from __future__ import annotations

import html
import logging
import time

from fastapi import APIRouter, Form, Request, Response, status

from app.config import get_settings
from app.database import AsyncSessionLocal
from app.services import moderation

logger = logging.getLogger(__name__)

router = APIRouter(tags=["reports"])

#: Не больше стольких жалоб с одного адреса за окно.
LIMIT = 5
WINDOW_SECONDS = 3600
_recent: dict[str, list[float]] = {}


def _client_ip(request: Request) -> str:
    forwarded = request.headers.get("cf-connecting-ip") or request.headers.get("x-real-ip") or ""
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def _throttled(ip: str) -> bool:
    now = time.monotonic()
    if len(_recent) > 10_000:
        _recent.clear()
    window = [t for t in _recent.get(ip, []) if now - t < WINDOW_SECONDS]
    if len(window) >= LIMIT:
        _recent[ip] = window
        return True
    window.append(now)
    _recent[ip] = window
    return False


def _layout(title: str, body: str) -> Response:
    return Response(
        content=f"""<!doctype html>
<html lang="ru">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(title)}</title>
<style>
  :root {{ color-scheme: light dark; }}
  body {{ margin: 0 auto; padding: 32px 20px 80px; max-width: 640px;
    font: 16px/1.6 -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; }}
  h1 {{ font-size: 24px; margin-top: 0; }}
  label {{ display: block; margin: 18px 0 6px; font-weight: 600; }}
  input, select, textarea {{ width: 100%; box-sizing: border-box; padding: 10px 12px; font: inherit;
    border: 1px solid rgba(127,127,127,.5); border-radius: 8px; background: transparent; color: inherit; }}
  textarea {{ min-height: 140px; }}
  button {{ margin-top: 22px; padding: 12px 20px; font: inherit; font-weight: 700; border: 0;
    border-radius: 10px; background: #4f46e5; color: #fff; cursor: pointer; }}
  .hint {{ opacity: .7; font-size: 14px; }}
  .err {{ padding: 12px 14px; border-radius: 8px; background: rgba(220,38,38,.15); }}
  .trap {{ position: absolute; left: -9999px; }}
  a {{ color: #4f46e5; }}
</style>
</head>
<body>
<p><a href="/">← на сайт</a></p>
{body}
</body>
</html>""",
        media_type="text/html; charset=utf-8",
    )


def _form(bot: str = "", category: str = "", details: str = "", contact: str = "", error: str = "") -> Response:
    options = "".join(
        f'<option value="{k}"{" selected" if k == category else ""}>{html.escape(v)}</option>'
        for k, v in moderation.CATEGORIES.items()
    )
    err = f'<p class="err">{html.escape(error)}</p>' if error else ""
    return _layout(
        "Пожаловаться на бота",
        f"""
<h1>Пожаловаться на бота</h1>
<p>Если бот, созданный в нашем сервисе, обманывает покупателей, нарушает закон или чьи-то права,
расскажите нам. Мы рассмотрим жалобу и при нарушении снимем бота. Переписку покупателей мы не читаем:
смотрим только на настройки бота, на который пожаловались.</p>
{err}
<form method="post" action="/report">
  <label for="bot">Имя бота или ссылка</label>
  <input id="bot" name="bot" value="{html.escape(bot)}" placeholder="@name_bot или t.me/name_bot" required maxlength="255">
  <label for="category">Что не так</label>
  <select id="category" name="category">{options}</select>
  <label for="details">Что произошло</label>
  <textarea id="details" name="details" required minlength="10" maxlength="3000">{html.escape(details)}</textarea>
  <label for="contact">Как с вами связаться (необязательно)</label>
  <input id="contact" name="contact" value="{html.escape(contact)}" placeholder="Telegram или почта" maxlength="255">
  <p class="hint">Контакт нужен, только если нам придётся уточнить детали.</p>
  <input class="trap" type="text" name="website" tabindex="-1" autocomplete="off">
  <button type="submit">Отправить жалобу</button>
</form>
""",
    )


@router.get("/report", response_class=Response)
async def report_form(bot: str = "") -> Response:
    return _form(bot=bot[:255])


async def _notify_operators(report) -> None:
    """Сообщить оператору в мета-боте: жалоба ждёт рассмотрения. Не обязательно:
    без мета-бота или адресатов жалоба просто лежит в базе."""
    import asyncio

    from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

    from app.services import platform_billing

    settings = get_settings()
    chats = set(settings.admin_ids)
    if not chats and settings.support_chat is not None:
        chats.add(settings.support_chat)
    meta = platform_billing._meta_bot()
    if meta is None or not chats:
        return
    category = moderation.CATEGORIES.get(report.category, report.category)
    text = f"🚩 Новая жалоба на бота {html.escape(report.bot_ref)}\n{html.escape(category)}"
    markup = InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="Открыть", callback_data=f"rp:{report.id.hex}")]]
    )
    for chat in chats:
        try:
            await asyncio.wait_for(meta.send_message(chat, text, parse_mode="HTML", reply_markup=markup), timeout=10)
        except Exception:  # noqa: BLE001
            logger.info("Could not notify operator %s about report %s", chat, report.id, exc_info=True)


@router.post("/report", response_class=Response)
async def submit_report(
    request: Request,
    bot: str = Form(""),
    category: str = Form("other"),
    details: str = Form(""),
    contact: str = Form(""),
    website: str = Form(""),
) -> Response:
    thanks = _layout(
        "Жалоба принята",
        "<h1>Спасибо, жалоба принята</h1><p>Мы рассмотрим её и при нарушении снимем бота. "
        'Это может занять некоторое время.</p><p><a href="/">← на сайт</a></p>',
    )
    if website.strip():
        # Ловушка для ботов: человек это поле не видит. Отвечаем так же, как всем.
        return thanks
    if _throttled(_client_ip(request)):
        response = _form(bot, category, details, contact, "Слишком много жалоб с вашего адреса. Попробуйте позже.")
        response.status_code = status.HTTP_429_TOO_MANY_REQUESTS
        return response
    async with AsyncSessionLocal() as db:
        try:
            report = await moderation.submit_report(
                db, bot_ref=bot, category=category, details=details, contact=contact
            )
        except moderation.ModerationError as exc:
            response = _form(bot, category, details, contact, str(exc))
            response.status_code = status.HTTP_400_BAD_REQUEST
            return response
    await _notify_operators(report)
    return thanks
