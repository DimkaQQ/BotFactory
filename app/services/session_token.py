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
import uuid

from cryptography.fernet import InvalidToken

from app.services.security import get_fernet

SESSION_TTL_SECONDS = 60 * 60 * 24 * 30  # 30 days


def create_session_token(client_id: uuid.UUID) -> str:
    payload = json.dumps({"client_id": str(client_id)}).encode()
    return get_fernet().encrypt(payload).decode()


def verify_session_token(token: str) -> uuid.UUID | None:
    try:
        payload = get_fernet().decrypt(token.encode(), ttl=SESSION_TTL_SECONDS)
        data = json.loads(payload)
        return uuid.UUID(data["client_id"])
    except (InvalidToken, ValueError, KeyError, TypeError):
        return None
