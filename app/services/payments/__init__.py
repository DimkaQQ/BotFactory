"""Payment provider registry.

Adding one of the providers still on the list (ЮKassa, Prodamus, Lava,
LifePay, CKassa, PayMaster …) means writing one module against
`base.PaymentProvider` and registering it here — the settings form, the
webhook route and the constructor's payment block all read this registry
and need no changes of their own.
"""

from __future__ import annotations

from app.services.payments.base import (
    CheckoutRequest,
    CredentialField,
    PaymentProvider,
    PaymentRef,
    ProviderError,
    WebhookResult,
    minor_to_major,
)
from app.services.payments.robokassa import RobokassaProvider
from app.services.payments.stripe import StripeProvider
from app.services.payments.test_provider import TestProvider

PROVIDERS: dict[str, PaymentProvider] = {
    provider.slug: provider
    for provider in (RobokassaProvider(), StripeProvider(), TestProvider())
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
        }
        for provider in PROVIDERS.values()
    ]


__all__ = [
    "CheckoutRequest",
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
