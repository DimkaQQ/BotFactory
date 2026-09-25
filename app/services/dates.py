"""Как бот называет дату человеку.

Хранится и считается всё в UTC, и это не обсуждается: `timestamptz` везде,
арифметика только `timedelta`, перевод часов ничего не сдвигает. Но показывать
UTC — отдельный вопрос: «доступ до 24.10» в UTC у подписчика в UTC+6 наступает
вечером 24-го по его часам, а у подписчика в UTC−5 — ещё 23-го. Одна строчка
разницы, зато ровно та, из-за которой пишут в поддержку.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app.config import get_settings

logger = logging.getLogger(__name__)


def _zone() -> ZoneInfo:
    name = get_settings().display_timezone or "UTC"
    try:
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError):
        # Опечатка в настройке не должна ронять отправку сообщения о покупке.
        logger.error("Неизвестный часовой пояс %r — показываю UTC", name)
        return ZoneInfo("UTC")


def day(moment: datetime) -> str:
    """«24.10.2026» в часовом поясе деплоя."""
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return moment.astimezone(_zone()).strftime("%d.%m.%Y")
