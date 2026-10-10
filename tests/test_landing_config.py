"""Что лендинг узнаёт о цене: те же цифры, что у кнопки публикации, и ни одного ключа."""

from __future__ import annotations

import json

import pytest

from app.config import get_settings


@pytest.mark.asyncio
async def test_pricing_comes_from_the_same_setting_as_the_paywall(api, monkeypatch):
    methods = [
        {
            "provider": "stripe",
            "price_minor": 900,
            "renewal_price_minor": 90,
            "currency": "USD",
            "credentials": {"secret_key": "sk_live_SUPERSECRET", "webhook_secret": "whsec_SUPERSECRET"},
        },
        {"provider": "cryptobot", "price_minor": 900, "currency": "USDT", "credentials": {"token": "TOKEN-SECRET"}},
    ]
    monkeypatch.setattr(get_settings(), "platform_payment_methods", json.dumps(methods), raising=False)

    response = await api.get("/api/config")
    assert response.status_code == 200
    body = response.json()

    assert [p["method"] for p in body["pricing"]] == ["Stripe", "Crypto Bot (USDT, TON)"]
    assert body["pricing"][0]["launch"] != "" and body["pricing"][0]["renewal"] != ""
    assert body["pricing"][1]["renewal"] == ""  # у второго способа продления нет
    assert body["renewal_period_days"] > 0

    raw = response.text
    assert "SUPERSECRET" not in raw and "TOKEN-SECRET" not in raw, "ключи платформы утекли в публичный конфиг"


@pytest.mark.asyncio
async def test_no_methods_means_no_prices(api, monkeypatch):
    monkeypatch.setattr(get_settings(), "platform_payment_methods", "", raising=False)
    monkeypatch.setattr(get_settings(), "publication_price_minor", 0, raising=False)

    body = (await api.get("/api/config")).json()
    assert body["pricing"] == []
    assert body["renewal_period_days"] == 0
