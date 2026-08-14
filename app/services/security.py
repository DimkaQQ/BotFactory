"""Encryption helpers for bot tokens.

Tokens are encrypted with Fernet before they ever touch the database, and the
only place they are decrypted is inside `bot_registry`, right before handing
them to an `aiogram.Bot` instance. No API response, log line, or schema
should ever carry a decrypted token.
"""

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
