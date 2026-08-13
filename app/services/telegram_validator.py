"""Validation helpers for things coming from Telegram:

- `validate_bot_token`: checks a bot token is real via the `getMe` API call,
  before we ever encrypt/store it.
- `validate_init_data`: verifies the signature of Telegram Web App `initData`
  so a Mini App request can be trusted to really come from the
  `telegram_user_id` it claims.
"""

from __future__ import annotations

import hashlib
import hmac
import json
from dataclasses import dataclass
from urllib.parse import parse_qsl

import httpx

from app.config import get_settings

TELEGRAM_API_BASE = "https://api.telegram.org"


@dataclass
class TelegramMe:
    id: int
    username: str
    first_name: str


class InvalidBotToken(Exception):
    pass


class InvalidInitData(Exception):
    pass


async def validate_bot_token(token: str) -> TelegramMe:
    """Call Telegram's getMe with the given token. Raises InvalidBotToken if it's not valid."""

    token = token.strip()
    if not token or ":" not in token:
        raise InvalidBotToken("Токен пустой или имеет неверный формат")

    url = f"{TELEGRAM_API_BASE}/bot{token}/getMe"
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(url)
    except httpx.HTTPError as exc:
        raise InvalidBotToken(f"Не удалось связаться с Telegram API: {exc}") from exc

    data = response.json()
    if not data.get("ok"):
        description = data.get("description", "Неизвестная ошибка")
        raise InvalidBotToken(f"Telegram отклонил токен: {description}")

    result = data["result"]
    if not result.get("is_bot"):
        raise InvalidBotToken("Указанный токен принадлежит не боту")

    return TelegramMe(id=result["id"], username=result.get("username", ""), first_name=result.get("first_name", ""))


def validate_init_data(init_data: str, *, max_age_seconds: int | None = 86400) -> dict:
    """Verify the HMAC signature of Telegram Web App initData.

    See: https://core.telegram.org/bots/webapps#validating-data-received-via-the-mini-app

    Returns the parsed key/value pairs (as a dict) on success. Raises
    InvalidInitData if the signature doesn't check out.
    """

    settings = get_settings()
    if not settings.meta_bot_token:
        raise InvalidInitData("META_BOT_TOKEN is not configured on the server")

    if not init_data:
        raise InvalidInitData("initData is empty")

    parsed = dict(parse_qsl(init_data, keep_blank_values=True))
    received_hash = parsed.pop("hash", None)
    if not received_hash:
        raise InvalidInitData("initData is missing hash")

    data_check_string = "\n".join(f"{key}={value}" for key, value in sorted(parsed.items()))

    secret_key = hmac.new(b"WebAppData", settings.meta_bot_token.encode(), hashlib.sha256).digest()
    computed_hash = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()

    if not hmac.compare_digest(computed_hash, received_hash):
        raise InvalidInitData("initData signature is invalid")

    if max_age_seconds is not None and "auth_date" in parsed:
        import time

        auth_date = int(parsed["auth_date"])
        if time.time() - auth_date > max_age_seconds:
            raise InvalidInitData("initData is too old")

    return parsed


def parse_init_data_user(parsed: dict) -> dict:
    """Extract the `user` object out of already-validated initData."""

    user_raw = parsed.get("user")
    if not user_raw:
        raise InvalidInitData("initData has no user field")
    try:
        return json.loads(user_raw)
    except (json.JSONDecodeError, TypeError) as exc:
        raise InvalidInitData("initData user field is not valid JSON") from exc
