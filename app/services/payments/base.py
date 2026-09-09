"""The shape every payment provider adapter has to fit.

Adding a provider is one module implementing `PaymentProvider` plus a line
in `registry.py` — deliberately, because the list of providers people ask
for is long (Robokassa, ЮKassa, Prodamus, Lava, LifePay, CKassa, PayMaster,
Stripe…) and they all do the same three things: build a checkout link,
call us back, and be verifiable.

`credential_fields` doubles as the UI contract: the constructor renders the
provider's settings form straight from it, so a new provider needs no
frontend work at all.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Protocol

from app.models.payment import PaymentStatus


@dataclass(frozen=True)
class CredentialField:
    key: str
    label: str
    hint: str = ""
    #  Secret values are write-only in the API: never sent back to the
    #  browser, only replaced.
    secret: bool = True


@dataclass(frozen=True)
class CheckoutRequest:
    payment_id: uuid.UUID
    invoice_no: int
    amount_minor: int
    currency: str
    description: str
    # Where the payer lands after paying (a page of ours, not the provider's).
    return_url: str
    is_test: bool
    credentials: dict[str, str]


@dataclass(frozen=True)
class PaymentRef:
    """Which payment a webhook is about, before anything is trusted."""

    payment_id: uuid.UUID | None = None
    invoice_no: int | None = None
    # For providers that carry no order id of their own (LIFE PAY), the only
    # handle is the id they gave us when the invoice was created.
    provider_payment_id: str | None = None


@dataclass(frozen=True)
class Checkout:
    """Where to send the payer, plus whatever the provider called this
    payment — several of them mint an id at creation time and then use it,
    not our order id, as the only reference in the callback."""

    url: str
    provider_payment_id: str | None = None
    meta: dict = field(default_factory=dict)


@dataclass(frozen=True)
class WebhookResult:
    status: PaymentStatus
    provider_payment_id: str | None = None
    # Some providers demand an exact acknowledgement body (Robokassa wants
    # "OK{InvId}"), and treat anything else as a failed delivery worth
    # retrying — so the adapter, not the router, decides what we answer.
    response_body: str = "OK"
    response_content_type: str = "text/plain"
    meta: dict = field(default_factory=dict)


class ProviderError(Exception):
    """The provider refused us — bad credentials, malformed request, or a
    signature that doesn't check out."""


class PaymentProvider(Protocol):
    slug: str
    title: str
    #: Human note shown under the provider's settings form.
    hint: str
    #: Currencies the adapter is known to handle, uppercase ISO codes.
    currencies: tuple[str, ...]
    credential_fields: tuple[CredentialField, ...]

    async def create_checkout(self, request: CheckoutRequest) -> Checkout:
        """Create the payment on the provider's side and return where to
        send the payer."""
        ...

    def locate_payment(self, *, headers: dict[str, str], raw_body: bytes, form: dict[str, str]) -> PaymentRef:
        """Identify which payment a callback refers to — parsing only, no
        trust: the payment is loaded by this reference and only then are its
        credentials used to verify the callback really came from the
        provider."""
        ...

    async def verify_webhook(
        self,
        *,
        headers: dict[str, str],
        raw_body: bytes,
        form: dict[str, str],
        credentials: dict[str, str],
        amount_minor: int,
        invoice_no: int,
        payment_id: uuid.UUID,
        provider_payment_id: str | None,
    ) -> WebhookResult:
        """Check the callback's authenticity and say what it means.

        Where the provider signs its callbacks (Prodamus), that signature is
        the proof. Where it doesn't (ЮKassa, PayMaster, LIFE PAY), the
        callback is only a hint: the adapter calls the provider's API back
        and believes the answer, not the request body."""
        ...


def minor_to_major(amount_minor: int) -> str:
    """990_00 -> "990.00" — the string form providers expect in a signature,
    where a rounding difference of one kopek means a rejected payment."""
    return f"{amount_minor // 100}.{amount_minor % 100:02d}"
