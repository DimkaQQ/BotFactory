"""The HTTP surface: the journey, and the things that must not work.

Roughly half of this is negative — one client reaching another's bot, a
stored secret coming back out, a callback for a payment that isn't there.
Those are the cases nobody notices breaking until it matters.
"""

from __future__ import annotations

import uuid

import pytest

from app.models.bot_block import BlockType


async def create_bot(api, headers, name="Тест-магазин") -> str:
    response = await api.post("/api/bots", headers=headers)
    assert response.status_code in (200, 201), response.text
    bot_id = response.json()["id"]
    # A bot is created empty and named afterwards, which is what the
    # constructor does too.
    await api.patch(f"/api/bots/{bot_id}", headers=headers, json={"name": name})
    return bot_id


# ------------------------------------------------------------ authentication


@pytest.mark.parametrize("headers", [{}, {"Authorization": "Bearer not-a-real-token"}])
async def test_the_api_is_closed_without_a_valid_session(api, headers):
    assert (await api.get("/api/bots", headers=headers)).status_code == 401


# --------------------------------------------------------------- the journey


async def test_a_bot_and_its_graph_survive_a_round_trip(api, auth, owner):
    headers = auth(owner)
    bot_id = await create_bot(api, headers)

    ids = {}
    for kind, content in [
        ("welcome", {"text": "Привет!"}),
        ("payment", {"text": "Гайд — 990 ₽", "title": "Гайд", "price": "990", "currency": "RUB"}),
        ("delivery", {"text": "Держи файл 🎁"}),
    ]:
        response = await api.post(
            f"/api/bots/{bot_id}/blocks", headers=headers, json={"block_type": kind, "content": content}
        )
        assert response.status_code in (200, 201), response.text
        ids[kind] = response.json()["id"]

    await api.patch(f"/api/bots/{bot_id}/blocks/{ids['welcome']}", headers=headers,
                    json={"next_block_id": ids["payment"]})
    await api.patch(f"/api/bots/{bot_id}/blocks/{ids['payment']}", headers=headers,
                    json={"next_block_id": ids["delivery"]})
    await api.patch(f"/api/bots/{bot_id}", headers=headers, json={"start_block_id": ids["welcome"]})

    fetched = (await api.get(f"/api/bots/{bot_id}", headers=headers)).json()
    assert len(fetched["blocks"]) == 3
    assert fetched["start_block_id"] == ids["welcome"]
    assert fetched["name"] == "Тест-магазин"


async def test_a_block_cannot_point_at_itself(api, auth, owner):
    headers = auth(owner)
    bot_id = await create_bot(api, headers)
    response = await api.post(
        f"/api/bots/{bot_id}/blocks", headers=headers, json={"block_type": "welcome", "content": {"text": "Hi"}}
    )
    block_id = response.json()["id"]

    response = await api.patch(
        f"/api/bots/{bot_id}/blocks/{block_id}", headers=headers, json={"next_block_id": block_id}
    )

    assert response.status_code >= 400


# ------------------------------------------------------- one client, one bot


async def test_another_client_cannot_touch_the_bot(api, auth, owner, stranger):
    mine, theirs = auth(owner), auth(stranger)
    bot_id = await create_bot(api, mine)

    attempts = [
        ("get", f"/api/bots/{bot_id}", {}),
        ("patch", f"/api/bots/{bot_id}", {"json": {"name": "Захвачено"}}),
        ("delete", f"/api/bots/{bot_id}", {}),
        ("get", f"/api/bots/{bot_id}/blocks", {}),
        ("post", f"/api/bots/{bot_id}/blocks", {"json": {"block_type": "welcome", "content": {}}}),
        ("get", f"/api/bots/{bot_id}/payment-settings", {}),
        ("put", f"/api/bots/{bot_id}/payment-settings", {"json": {"provider": "test", "is_test": True}}),
        ("get", f"/api/bots/{bot_id}/orders", {}),
        ("post", f"/api/bots/{bot_id}/publish", {"json": {"token": "1:x"}}),
    ]
    for method, path, kwargs in attempts:
        response = await getattr(api, method)(path, headers=theirs, **kwargs)
        assert response.status_code in (403, 404), f"{method.upper()} {path} → {response.status_code}"

    still_mine = await api.get(f"/api/bots/{bot_id}", headers=mine)
    assert still_mine.status_code == 200 and still_mine.json()["name"] == "Тест-магазин"


# ------------------------------------------------------------------- secrets


async def test_payment_keys_go_in_but_never_come_back(api, auth, owner):
    headers = auth(owner)
    bot_id = await create_bot(api, headers)

    await api.put(
        f"/api/bots/{bot_id}/payment-settings", headers=headers,
        json={"provider": "robokassa", "is_test": True,
              "credentials": {"merchant_login": "demo", "password1": "СЕКРЕТ1", "password2": "СЕКРЕТ2"}},
    )

    settings = await api.get(f"/api/bots/{bot_id}/payment-settings", headers=headers)
    assert "СЕКРЕТ1" not in settings.text and "СЕКРЕТ2" not in settings.text
    # Only *which* fields are filled, never their values.
    assert set(settings.json()["filled_fields"]) == {"merchant_login", "password1", "password2"}

    bot = await api.get(f"/api/bots/{bot_id}", headers=headers)
    assert "password" not in bot.text.lower() and "token_encrypted" not in bot.text


async def test_switching_provider_drops_the_old_keys(api, auth, owner):
    """Live Robokassa passwords must not sit in the database forever because
    the shop moved to ЮKassa, or turned payments off entirely."""
    headers = auth(owner)
    bot_id = await create_bot(api, headers)

    await api.put(
        f"/api/bots/{bot_id}/payment-settings", headers=headers,
        json={"provider": "robokassa", "is_test": True,
              "credentials": {"merchant_login": "demo", "password1": "P1", "password2": "P2"}},
    )
    await api.put(
        f"/api/bots/{bot_id}/payment-settings", headers=headers,
        json={"provider": "yookassa", "is_test": True,
              "credentials": {"shop_id": "123", "secret_key": "live_KEY"}},
    )

    filled = (await api.get(f"/api/bots/{bot_id}/payment-settings", headers=headers)).json()["filled_fields"]
    assert set(filled) == {"shop_id", "secret_key"}, filled

    await api.put(f"/api/bots/{bot_id}/payment-settings", headers=headers,
                  json={"provider": None, "is_test": True})
    filled = (await api.get(f"/api/bots/{bot_id}/payment-settings", headers=headers)).json()["filled_fields"]
    assert filled == [], filled


async def test_editing_settings_without_resending_secrets_keeps_them(api, auth, owner):
    """The form never receives stored secrets back, so an untouched field
    arrives blank — that must not wipe it."""
    headers = auth(owner)
    bot_id = await create_bot(api, headers)

    await api.put(
        f"/api/bots/{bot_id}/payment-settings", headers=headers,
        json={"provider": "robokassa", "is_test": True,
              "credentials": {"merchant_login": "demo", "password1": "P1", "password2": "P2"}},
    )
    await api.put(f"/api/bots/{bot_id}/payment-settings", headers=headers,
                  json={"provider": "robokassa", "is_test": False, "credentials": {}})

    filled = (await api.get(f"/api/bots/{bot_id}/payment-settings", headers=headers)).json()["filled_fields"]
    assert set(filled) == {"merchant_login", "password1", "password2"}


# --------------------------------------------------------------- publication


async def test_a_bot_on_the_test_provider_cannot_be_published(api, auth, owner):
    """Its checkout page pays the order the moment it is opened."""
    headers = auth(owner)
    bot_id = await create_bot(api, headers)
    await api.put(f"/api/bots/{bot_id}/payment-settings", headers=headers,
                  json={"provider": "test", "is_test": True})

    response = await api.post(f"/api/bots/{bot_id}/publish", headers=headers, json={"token": "123456:FAKE"})

    assert response.status_code == 400
    assert "Тестовая оплата" in response.json()["detail"]


async def test_publication_is_gated_until_it_is_paid(api, auth, owner, monkeypatch):
    from app.config import get_settings

    settings = get_settings()
    monkeypatch.setattr(settings, "publication_price_minor", 200000, raising=False)
    monkeypatch.setattr(settings, "publication_currency", "KZT", raising=False)
    monkeypatch.setattr(settings, "platform_payment_provider", "test", raising=False)
    monkeypatch.setattr(settings, "platform_payment_is_test", True, raising=False)

    headers = auth(owner)
    bot_id = await create_bot(api, headers)

    info = (await api.get(f"/api/bots/{bot_id}/publication", headers=headers)).json()
    assert info["required"] is True and info["paid"] is False

    blocked = await api.post(f"/api/bots/{bot_id}/publish", headers=headers, json={"token": "123456:FAKE"})
    assert blocked.status_code == 402

    checkout = (await api.post(f"/api/bots/{bot_id}/publication-checkout", headers=headers)).json()
    assert checkout["amount_minor"] == 200000 and checkout["currency"] == "KZT"

    # Opening the test provider's page is what settles it.
    assert (await api.get(checkout["checkout_url"])).status_code == 200
    assert (await api.get(f"/api/payments/{checkout['id']}", headers=headers)).json()["status"] == "paid"
    assert (await api.get(f"/api/bots/{bot_id}/publication", headers=headers)).json()["paid"] is True

    # The paywall is gone; the fake Telegram token is still refused, so
    # paying does not buy a way past token validation.
    after = await api.post(f"/api/bots/{bot_id}/publish", headers=headers, json={"token": "123456:FAKE"})
    assert after.status_code != 402 and after.status_code >= 400


async def test_another_client_cannot_read_the_payment(api, auth, owner, stranger, monkeypatch):
    from app.config import get_settings

    monkeypatch.setattr(get_settings(), "publication_price_minor", 200000, raising=False)
    monkeypatch.setattr(get_settings(), "platform_payment_provider", "test", raising=False)

    headers = auth(owner)
    bot_id = await create_bot(api, headers)
    checkout = (await api.post(f"/api/bots/{bot_id}/publication-checkout", headers=headers)).json()

    response = await api.get(f"/api/payments/{checkout['id']}", headers=auth(stranger))

    assert response.status_code == 404


# ------------------------------------------------------------------ webhooks


@pytest.mark.parametrize(
    ("path", "kwargs"),
    [
        ("/webhook/pay/no-such-provider", {"content": b"{}"}),
        ("/webhook/pay/robokassa", {"data": {"InvId": "999999999", "OutSum": "1.00"}}),
        ("/webhook/pay/robokassa", {"content": "вообще не форма".encode()}),
    ],
)
async def test_a_junk_callback_never_returns_a_server_error(api, path, kwargs):
    response = await api.post(path, **kwargs)

    assert response.status_code < 500, response.text


async def test_an_update_for_an_unknown_bot_is_shrugged_off(api):
    response = await api.post(
        f"/webhook/{uuid.uuid4()}", json={"message": {"chat": {"id": 1}, "text": "/start"}}
    )

    assert response.status_code < 500


# ------------------------------------------------------------------- catalog


async def test_the_provider_catalogue_lists_every_provider(api, auth, owner):
    from app.services.payments import PROVIDERS

    response = await api.get("/api/payments/providers", headers=auth(owner))

    assert {p["slug"] for p in response.json()["providers"]} == set(PROVIDERS)
