"""Payment provider registry.

Adding a provider (CKassa is the one still missing) means
writing one module against `base.PaymentProvider` and registering it here —
the settings form, the webhook route and the constructor's payment block all
read this registry and need no changes of their own.

Order matters: it is the order the shop owner sees in the settings form.
"""

from __future__ import annotations

from app.services.payments.base import (
    Checkout,
    CheckoutRequest,
    CredentialField,
    PaymentProvider,
    PaymentRef,
    ProviderDefaults,
    ProviderError,
    WebhookResult,
    minor_to_major,
)
from app.services.payments.cryptobot import CryptoBotProvider
from app.services.payments.lavatop import LavaTopProvider
from app.services.payments.lifepay import LifePayProvider
from app.services.payments.link import LinkProvider
from app.services.payments.paymaster import PayMasterProvider
from app.services.payments.prodamus import ProdamusProvider
from app.services.payments.robokassa import RobokassaProvider
from app.services.payments.stripe import StripeProvider
from app.services.payments.telegram_stars import TelegramStarsProvider
from app.services.payments.test_provider import TestProvider
from app.services.payments.yookassa import YooKassaProvider

PROVIDERS: dict[str, PaymentProvider] = {
    provider.slug: provider
    for provider in (
        TelegramStarsProvider(),
        YooKassaProvider(),
        ProdamusProvider(),
        RobokassaProvider(),
        PayMasterProvider(),
        LifePayProvider(),
        LavaTopProvider(),
        StripeProvider(),
        CryptoBotProvider(),
        LinkProvider(),
        TestProvider(),
    )
}


def get_provider(slug: str) -> PaymentProvider:
    provider = PROVIDERS.get((slug or "").strip().lower())
    if provider is None:
        raise ProviderError(f"Неизвестный платёжный провайдер: {slug!r}")
    return provider


def describe_providers() -> list[dict]:
    """The provider catalogue the constructor renders its settings form
    from — no provider-specific code on the frontend."""
    return [
        {
            "slug": provider.slug,
            "title": provider.title,
            "hint": provider.hint,
            "currencies": list(provider.currencies),
            "fields": [
                {"key": f.key, "label": f.label, "hint": f.hint, "secret": f.secret}
                for f in provider.credential_fields
            ],
            # Asked once per product, on the payment block itself, rather
            # than once per shop in the settings form.
            "block_fields": [
                {"key": f.key, "label": f.label, "hint": f.hint, "secret": f.secret}
                for f in provider.block_fields
            ],
            # Whether the bot can answer "я оплатил" by asking the provider,
            # or has to ask the shop owner to confirm.
            "supports_status_check": bool(provider.supports_status_check),
            "uses_callback": bool(provider.uses_callback),
        }
        for provider in PROVIDERS.values()
    ]


__all__ = [
    "Checkout",
    "CheckoutRequest",
    "ProviderDefaults",
    "CredentialField",
    "PaymentProvider",
    "PaymentRef",
    "PROVIDERS",
    "ProviderError",
    "WebhookResult",
    "describe_providers",
    "get_provider",
    "minor_to_major",
]
