"""Encryption helpers for bot tokens.

Tokens are encrypted with Fernet before they ever touch the database, and the
only place they are decrypted is inside `bot_registry`, right before handing
them to an `aiogram.Bot` instance. No API response, log line, or schema
should ever carry a decrypted token.
"""

import hashlib
import hmac
from functools import lru_cache

from cryptography.fernet import Fernet, InvalidToken, MultiFernet

from app.config import get_settings


@lru_cache
def _fernet() -> MultiFernet:
    """Encrypt with the current key, decrypt with any key we still hold.

    A single key was the one thing here with no way out: it protects bot
    tokens, the shops' own acquirer credentials, webhook secrets and web
    sessions at once, so the standard answer to a leak — change the key —
    logged everyone out, made every bot token unreadable and destroyed every
    client's payment credentials, irreversibly. There was no rotation path
    at all, which is a poor thing to discover on the day you need one.

    `MultiFernet` encrypts with the first key and tries all of them when
    decrypting, so a rotation is: put the new key first, keep the old one in
    `FERNET_KEYS_RETIRED`, re-encrypt at leisure (`python -m app.rotate_keys`),
    then drop the old one.
    """
    settings = get_settings()
    if not settings.fernet_key:
        raise RuntimeError(
            "FERNET_KEY is not set. Generate one with: "
            "python -c \"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())\""
        )
    keys = [Fernet(settings.fernet_key.encode())]
    keys += [Fernet(old.encode()) for old in settings.retired_key_list]
    return MultiFernet(keys)


def get_fernet() -> MultiFernet:
    """Shared instance, for other modules that need authenticated encryption
    under the same master key (e.g. web session tokens)."""
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
    # `webhook_key`, а не сам FERNET_KEY: иначе ротация ключа меняет секреты
    # всех вебхуков разом, Telegram продолжает слать старые, и каждый бот
    # молчит до следующего запуска процесса. Пока WEBHOOK_SECRET_KEY не
    # задан, это тот же ключ — то есть для существующих деплоев не меняется
    # ничего.
    key = get_settings().webhook_key.encode()
    return hmac.new(key, f"webhook:{bot_id}".encode(), hashlib.sha256).hexdigest()
