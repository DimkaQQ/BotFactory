"""Encryption helpers for bot tokens.

Tokens are encrypted with Fernet before they ever touch the database, and the
only place they are decrypted is inside `bot_registry`, right before handing
them to an `aiogram.Bot` instance. No API response, log line, or schema
should ever carry a decrypted token.
"""

import hashlib
import hmac
from functools import lru_cache

from cryptography.fernet import Fernet, InvalidToken

from app.config import get_settings


@lru_cache
def _fernet() -> Fernet:
    settings = get_settings()
    if not settings.fernet_key:
        raise RuntimeError(
            "FERNET_KEY is not set. Generate one with: "
            "python -c \"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())\""
        )
    return Fernet(settings.fernet_key.encode())


def get_fernet() -> Fernet:
    """Shared Fernet instance, for other modules that need authenticated
    encryption under the same master key (e.g. web session tokens)."""
    return _fernet()


def encrypt_token(token: str) -> bytes:
    return _fernet().encrypt(token.encode())


def decrypt_token(token_encrypted: bytes) -> str:
    try:
        return _fernet().decrypt(token_encrypted).decode()
    except InvalidToken as exc:
        raise ValueError("Could not decrypt bot token — invalid FERNET_KEY or corrupted data") from exc


def webhook_secret(bot_id) -> str:
    """The `secret_token` Telegram echoes back on every update for this bot.

    `POST /webhook/{bot_id}` is otherwise open to anyone who learns the id:
    the URL is the only thing standing between a stranger and a forged
    update — including a `callback_query` claiming to come from the shop
    owner, confirming their own payment.

    Derived from the master key rather than stored, so it needs no column and
    no migration, and it differs per bot so one leaked secret says nothing
    about any other. Telegram allows 1-256 chars of `A-Za-z0-9_-`; hex fits.
    """
    key = get_settings().fernet_key.encode()
    return hmac.new(key, f"webhook:{bot_id}".encode(), hashlib.sha256).hexdigest()
