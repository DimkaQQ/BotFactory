"""How the platform itself gets paid.

Publishing can be charged for through several methods at once, because no
single one reaches everybody: Stripe does not operate in Russia or
Kazakhstan, a local acquirer does not take foreign cards, and crypto needs
no company at all. They are priced in different currencies, and a callback
about one must never be verified with another's credentials.
"""

from __future__ import annotations

import json

import pytest

from app.config import get_settings
from app.services import payment_service
from app.services.payments import ProviderError

THREE_METHODS = json.dumps(
    [
        {"provider": "stripe", "price_minor": 900, "currency": "USD",
         "credentials": {"secret_key": "sk_test_x", "webhook_secret": "whsec_x"}},
        {"provider": "robokassa", "price_minor": 450000, "currency": "KZT",
         "credentials": {"merchant_login": "shop", "password1": "p1", "password2": "p2"}},
        {"provider": "cryptobot", "price_minor": 900, "currency": "USDT",
         "credentials": {"token": "crypto-token"}},
    ]
)


@pytest.fixture
def three_methods(monkeypatch):
    monkeypatch.setattr(get_settings(), "platform_payment_methods", THREE_METHODS, raising=False)


def test_every_configured_method_is_offered(three_methods):
    methods = payment_service.platform_methods()

    assert [m.provider for m in methods] == ["stripe", "robokassa", "cryptobot"]
    # Each carries its own price: one number in one currency cannot say that
    # the same publication is $9, ₸4500 and 9 USDT.
    assert [(m.price_minor, m.currency) for m in methods] == [(900, "USD"), (450000, "KZT"), (900, "USDT")]
    assert methods[0].title == "Stripe"


def test_a_method_is_chosen_by_name(three_methods):
    assert payment_service.platform_method("cryptobot").currency == "USDT"
    # No choice means the first one, which is what a single-method
    # deployment always wants.
    assert payment_service.platform_method(None).provider == "stripe"


def test_an_unoffered_method_is_refused(three_methods):
    """Otherwise a crafted request could pick a provider with no credentials,
    or one the shop deliberately turned off."""
    with pytest.raises(ProviderError):
        payment_service.platform_method("yookassa")


def test_a_malformed_entry_is_skipped_not_fatal(monkeypatch):
    """One bad line in the config must not take the whole paywall down."""
    monkeypatch.setattr(
        get_settings(),
        "platform_payment_methods",
        json.dumps(
            [
                {"provider": "nonexistent", "price_minor": 100, "currency": "USD"},
                {"provider": "stripe", "price_minor": 900, "currency": "USD", "credentials": {}},
            ]
        ),
        raising=False,
    )

    assert [m.provider for m in payment_service.platform_methods()] == ["stripe"]


def test_nothing_configured_means_publishing_is_free(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "platform_payment_methods", "", raising=False)
    monkeypatch.setattr(settings, "publication_price_minor", 0, raising=False)

    assert payment_service.platform_methods() == []


def test_the_old_single_provider_settings_still_work(monkeypatch):
    """A deployment configured before the list existed keeps running."""
    settings = get_settings()
    monkeypatch.setattr(settings, "platform_payment_methods", "", raising=False)
    monkeypatch.setattr(settings, "publication_price_minor", 200000, raising=False)
    monkeypatch.setattr(settings, "publication_currency", "KZT", raising=False)
    monkeypatch.setattr(settings, "platform_payment_provider", "test", raising=False)

    methods = payment_service.platform_methods()

    assert len(methods) == 1
    assert (methods[0].provider, methods[0].price_minor, methods[0].currency) == ("test", 200000, "KZT")


async def test_the_paywall_offers_all_three_and_charges_the_chosen_one(api, auth, owner, three_methods):
    headers = auth(owner)
    bot_id = (await api.post("/api/bots", headers=headers)).json()["id"]

    info = (await api.get(f"/api/bots/{bot_id}/publication", headers=headers)).json()
    assert info["required"] is True
    assert [(m["provider"], m["currency"]) for m in info["methods"]] == [
        ("stripe", "USD"), ("robokassa", "KZT"), ("cryptobot", "USDT")
    ]

    # Robokassa builds its link locally, so this reaches no network.
    checkout = await api.post(
        f"/api/bots/{bot_id}/publication-checkout", headers=headers, json={"provider": "robokassa"}
    )
    assert checkout.status_code == 200, checkout.text
    assert (checkout.json()["amount_minor"], checkout.json()["currency"]) == (450000, "KZT")

    refused = await api.post(
        f"/api/bots/{bot_id}/publication-checkout", headers=headers, json={"provider": "yookassa"}
    )
    assert refused.status_code == 400


async def test_a_callback_is_verified_with_its_own_method_credentials(db, owner, three_methods):
    """Three methods are live at once; verifying a Robokassa callback with
    the crypto app's token would either fail or, worse, succeed by accident."""
    from app.models.payment import Payment, PaymentKind, PaymentStatus

    payment = Payment(
        kind=PaymentKind.publication, status=PaymentStatus.pending, provider="robokassa",
        amount_minor=450000, currency="KZT", description="Публикация", meta={},
    )
    db.add(payment)
    await db.commit()

    credentials, is_test = await payment_service.credentials_for(db, payment)

    assert credentials["password2"] == "p2"
    assert is_test is False

    await db.execute(Payment.__table__.delete().where(Payment.id == payment.id))
    await db.commit()
