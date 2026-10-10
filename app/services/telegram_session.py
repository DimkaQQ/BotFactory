"""aiohttp session for aiogram, forced to IPv4 and optionally routed
through a reverse proxy in front of the Telegram Bot API.

Two independent problems this works around:

1. Docker's default bridge network has no IPv6 route inside the
   container's network namespace. `api.telegram.org` resolves to both an
   A and an AAAA record, and aiohttp's happy-eyeballs connector tries the
   IPv6 address — which fails instantly with "Network is unreachable"
   instead of falling back cleanly, taking the whole request down with it.
   Forcing the connector to AF_INET sidesteps that entirely.

2. api.telegram.org is blocked/throttled outright from some networks
   (RU-hosted servers in particular). `TELEGRAM_API_BASE_URL` lets a
   reverse proxy (e.g. a Cloudflare Worker that forwards 1:1 to Telegram)
   stand in for the real endpoint.
"""

import socket
from typing import Any

from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.client.telegram import TelegramAPIServer

from app.config import get_settings


class Ipv4AiohttpSession(AiohttpSession):
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._connector_init["family"] = socket.AF_INET


def build_bot_session() -> Ipv4AiohttpSession:
    """Session to use for every aiogram Bot instance in this project."""

    settings = get_settings()
    if settings.telegram_api_base_url:
        api = TelegramAPIServer.from_base(settings.telegram_api_base_url)
        return Ipv4AiohttpSession(api=api)
    return Ipv4AiohttpSession()
