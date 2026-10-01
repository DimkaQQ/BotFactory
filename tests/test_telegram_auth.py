"""Подпись входа через Telegram: самое важное место авторизации.

Раньше проверялась только косвенно, через готовые токены сессии. Здесь —
сами функции: что принимают, и главное — что отвергают.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import time
from urllib.parse import parse_qsl, urlencode

import pytest

from app.config import get_settings
from app.services.telegram_validator import (
    InvalidInitData,
    parse_init_data_user,
    validate_init_data,
    validate_login_widget_data,
)


@pytest.fixture(autouse=True)
def _token(monkeypatch):
    monkeypatch.setattr(get_settings(), "meta_bot_token", "123456:TEST-TOKEN", raising=False)


def _check_string(fields: dict) -> str:
    return "\n".join(f"{k}={v}" for k, v in sorted(fields.items()))


def _init_data(fields: dict, *, token: str = "123456:TEST-TOKEN") -> str:
    secret = hmac.new(b"WebAppData", token.encode(), hashlib.sha256).digest()
    digest = hmac.new(secret, _check_string(fields).encode(), hashlib.sha256).hexdigest()
    return urlencode({**fields, "hash": digest})


def _widget(fields: dict, *, token: str = "123456:TEST-TOKEN") -> dict:
    secret = hashlib.sha256(token.encode()).digest()
    digest = hmac.new(secret, _check_string(fields).encode(), hashlib.sha256).hexdigest()
    return {**fields, "hash": digest}


def _fresh(**extra) -> dict:
    return {"auth_date": str(int(time.time())), "user": json.dumps({"id": 42, "first_name": "Аня"}), **extra}


def test_valid_init_data_is_accepted_and_user_parsed():
    parsed = validate_init_data(_init_data(_fresh()))
    assert parse_init_data_user(parsed)["id"] == 42


def test_tampered_init_data_is_refused():
    fields = _fresh()
    signed = dict(parse_qsl(_init_data(fields)))
    signed["user"] = json.dumps({"id": 1, "first_name": "Аня"})  # подмена id, хеш прежний
    with pytest.raises(InvalidInitData):
        validate_init_data(urlencode(signed))


def test_init_data_signed_with_another_token_is_refused():
    with pytest.raises(InvalidInitData):
        validate_init_data(_init_data(_fresh(), token="999:OTHER"))


def test_init_data_without_hash_or_empty_is_refused():
    with pytest.raises(InvalidInitData):
        validate_init_data("")
    with pytest.raises(InvalidInitData):
        validate_init_data(urlencode(_fresh()))


def test_stale_init_data_is_refused():
    old = _fresh()
    old["auth_date"] = str(int(time.time()) - 3 * 86400)
    with pytest.raises(InvalidInitData):
        validate_init_data(_init_data(old))


def test_init_data_cannot_be_checked_without_a_configured_token(monkeypatch):
    monkeypatch.setattr(get_settings(), "meta_bot_token", "", raising=False)
    with pytest.raises(InvalidInitData):
        validate_init_data(_init_data(_fresh()))


def test_init_data_without_user_is_refused():
    fields = {"auth_date": str(int(time.time()))}
    parsed = validate_init_data(_init_data(fields))
    with pytest.raises(InvalidInitData):
        parse_init_data_user(parsed)


def test_valid_login_widget_payload_is_accepted():
    fields = {"id": 42, "first_name": "Аня", "auth_date": int(time.time())}
    assert validate_login_widget_data(_widget(fields))["id"] == 42


def test_login_widget_payload_with_forged_id_is_refused():
    payload = _widget({"id": 42, "first_name": "Аня", "auth_date": int(time.time())})
    payload["id"] = 1
    with pytest.raises(InvalidInitData):
        validate_login_widget_data(payload)


def test_the_two_signing_schemes_are_not_interchangeable():
    """Подпись Mini App не годится для виджета: это разные секреты, и путаница
    молча принимала бы поддельные входы."""
    fields = {"id": 42, "first_name": "Аня", "auth_date": int(time.time())}
    secret = hmac.new(b"WebAppData", b"123456:TEST-TOKEN", hashlib.sha256).digest()
    digest = hmac.new(secret, _check_string(fields).encode(), hashlib.sha256).hexdigest()
    with pytest.raises(InvalidInitData):
        validate_login_widget_data({**fields, "hash": digest})


def test_stale_login_widget_payload_is_refused():
    payload = _widget({"id": 42, "first_name": "Аня", "auth_date": int(time.time()) - 3 * 86400})
    with pytest.raises(InvalidInitData):
        validate_login_widget_data(payload)
