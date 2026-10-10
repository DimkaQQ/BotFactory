"""Session tokens for the web (non-Telegram-Mini-App) login flow.

The Mini App authenticates every request with a fresh, short-lived
Telegram `initData` signature — there's no concept of a "session" there.
Outside Telegram (a plain browser, via the Telegram Login Widget) there's
no initData to resend, so logging in once issues an opaque bearer token
the frontend stores and replays. The token is just a Fernet-encrypted
`{"client_id": ...}` blob under the same master key already used for bot
tokens — Fernet's own `ttl` on decrypt gives us expiry for free, no JWT
library needed.
"""

from __future__ import annotations

import json
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone

from cryptography.fernet import InvalidToken

from app.services.security import get_fernet

SESSION_TTL_SECONDS = 60 * 60 * 24 * 30  # 30 days


@dataclass(frozen=True)
class Session:
    """Кому принадлежит токен и когда он выдан.

    Время выпуска нужно, чтобы выход из аккаунта что-то значил: токен живёт
    тридцать дней, и до этого отозвать его было нечем — «Выйти» стирало его
    только в браузере.
    """

    client_id: uuid.UUID
    issued_at: datetime | None


def create_session_token(client_id: uuid.UUID) -> str:
    # Дробные секунды не для точности, а чтобы вход сразу после выхода
    # сработал: выход ставит отметку с микросекундами, и токен, выпущенный
    # в ту же секунду, но округлённый вниз, оказывался «старше» её.
    payload = json.dumps({"client_id": str(client_id), "iat": time.time()}).encode()
    return get_fernet().encrypt(payload).decode()


def verify_session_token(token: str) -> Session | None:
    try:
        payload = get_fernet().decrypt(token.encode(), ttl=SESSION_TTL_SECONDS)
        data = json.loads(payload)
        issued = data.get("iat")
        return Session(
            client_id=uuid.UUID(data["client_id"]),
            # Токены, выпущенные до появления этого поля, времени не несут.
            # Такой токен считается выпущенным бесконечно давно: любой выход
            # из аккаунта его закрывает, и это правильная сторона ошибки.
            issued_at=datetime.fromtimestamp(float(issued), tz=timezone.utc) if issued else None,
        )
    except (InvalidToken, ValueError, KeyError, TypeError):
        return None
