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


async def test_the_provider_catalogue_is_enough_to_render_the_settings_form(api, auth, owner):
    """The catalogue is the entire contract with the frontend — the settings
    form has no provider-specific code of its own. Comparing it back to
    `PROVIDERS` proved nothing; what matters is that every entry carries what
    the form needs, and that no secret comes along for the ride."""
    response = await api.get("/api/payments/providers", headers=auth(owner))
    body = response.json()
    catalogue = body["providers"]

    assert len(catalogue) >= 15
    for entry in catalogue:
        assert entry["slug"] and entry["title"] and entry["hint"]
        assert entry["currencies"], f"{entry['slug']} без валют — селектор будет пустым"
        assert entry["recurring"] in {"none", "gateway", "token"}, entry["slug"]
        for flag in ("supports_status_check", "uses_callback", "has_test_mode"):
            assert isinstance(entry[flag], bool), f"{entry['slug']}: {flag} должен быть булевым"
        for field in entry["fields"] + entry["block_fields"]:
            # A value here would be a stored secret on its way to a browser.
            assert set(field) == {"key", "label", "hint", "secret"}

    by_slug = {entry["slug"]: entry for entry in catalogue}
    # Two spot checks that would break if the flags were wired to each other
    # again: one provider with no callback that still has a test gateway, and
    # one that has neither.
    assert by_slug["processingkz"] == {**by_slug["processingkz"], "uses_callback": False, "has_test_mode": True}
    assert by_slug["link"] == {**by_slug["link"], "uses_callback": False, "has_test_mode": False}

    # The form draws a section per region and skips empty ones, so every
    # provider has to land in a section the response also describes —
    # otherwise it is configurable over the API and invisible in the UI.
    # Several recurring options, not one: the whole point of the exercise is
    # that a shop does not have to take Telegram Stars to sell a subscription.
    recurring = [e["slug"] for e in catalogue if e["recurring"] != "none"]
    assert len(recurring) >= 3, recurring

    regions = body["regions"]
    assert regions, "без разделов форма отрисует один безымянный список"
    known = {r["slug"] for r in regions}
    assert all(r["title"] for r in regions), "раздел без заголовка"
    for entry in catalogue:
        assert entry["region"] in known, f"{entry['slug']} в неизвестном разделе"


async def test_sales_totals_cover_every_order_and_keep_currencies_apart(api, auth, owner, make_bot, db):
    """Summing only the page of recent orders made a busy shop's revenue
    start silently going down; adding roubles to stars made it meaningless."""
    from app.models.payment import Payment, PaymentKind, PaymentStatus

    bot, _ = await make_bot(owner, [(BlockType.welcome, {"text": "Hi"})])
    for amount, currency, status in [
        (99000, "RUB", PaymentStatus.paid),
        (49000, "RUB", PaymentStatus.paid),
        (25000, "XTR", PaymentStatus.paid),
        (99000, "RUB", PaymentStatus.pending),
    ]:
        db.add(
            Payment(
                kind=PaymentKind.order, status=status, provider="test", amount_minor=amount,
                currency=currency, description="Товар", bot_id=bot.id, meta={},
            )
        )
    await db.commit()

    report = (await api.get(f"/api/bots/{bot.id}/orders", headers=auth(owner))).json()

    totals = {t["currency"]: t for t in report["totals"]}
    assert totals["RUB"]["total_minor"] == 148000 and totals["RUB"]["count"] == 2
    assert totals["XTR"]["total_minor"] == 25000 and totals["XTR"]["count"] == 1
    # The unpaid one is listed but not counted as revenue.
    assert len(report["orders"]) == 4


async def test_a_provider_with_no_callback_can_still_be_switched_off_test_mode(api, auth, owner, make_bot):
    """Processing.kz has no callback but does have its own test gateway, and
    `payment_is_test` defaults to True. While the test switch was tied to
    `uses_callback` the settings form never offered it, so the one provider
    aimed at bank-acquired Kazakh merchants could not take real money at all."""
    bot, _ = await make_bot(owner, [])

    saved = await api.put(
        f"/api/bots/{bot.id}/payment-settings",
        headers=auth(owner),
        json={
            "provider": "processingkz",
            "is_test": False,
            "credentials": {"merchant_id": "000000000000115"},
        },
    )

    assert saved.status_code == 200
    assert saved.json()["is_test"] is False
    # No callback, so no address is offered to paste anywhere.
    assert saved.json()["callback_url"] is None

    from app.services.payments import get_provider

    assert get_provider("processingkz").uses_callback is False
    assert get_provider("processingkz").has_test_mode is True


async def test_the_landing_is_told_the_truth_about_the_acquirers(api):
    """The landing page's «17 касс» comes from here rather than from the
    page, so the claim cannot outlive the adapters behind it. Unauthenticated
    on purpose: nobody has logged in yet when it is read."""
    config = (await api.get("/api/config")).json()

    names = [name for region in config["payment_regions"] for name in region["gateways"]]
    assert config["gateway_count"] == len(names)
    assert "ЮKassa" in names and "Stripe" in names

    # Neither of these is an acquirer, and listing them as one on a sales
    # page is a lie: "Тестовая оплата" hands goods over without money, and
    # "оплата по ссылке" is a human confirming a transfer by hand.
    assert "Тестовая оплата" not in names
    assert not any("ссылк" in name.lower() for name in names)

    # An empty heading rendered as a section title with nothing under it.
    assert all(region["gateways"] for region in config["payment_regions"])


async def test_health_says_ok_only_when_the_database_answers(api, monkeypatch):
    """This endpoint used to return a constant, which meant it reported "ok"
    while Postgres was gone — exactly the moment a health check exists for,
    and exactly when both the watchdog and any uptime service would have
    said nothing."""
    healthy = await api.get("/health")
    assert healthy.status_code == 200
    assert healthy.json() == {"status": "ok", "database": "ok"}

    import app.main

    class DeadPool:
        def __call__(self):
            raise OSError("connection refused")

    monkeypatch.setattr(app.main, "AsyncSessionLocal", DeadPool(), raising=False)
    monkeypatch.setattr("app.database.AsyncSessionLocal", DeadPool())

    sick = await api.get("/health")
    # 503 rather than an exception: an uptime monitor reads the status code,
    # and a traceback would look like an application bug instead of "the
    # database is down".
    assert sick.status_code == 503
    assert sick.json()["database"] == "unreachable"
