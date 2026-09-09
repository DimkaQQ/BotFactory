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
    # Per-block settings, straight from the payment block's content: what
    # varies per product rather than per shop (Lava's offer id, the link a
    # "pay by link" block points at). Credentials are the shop; this is the
    # thing being sold.
    extra: dict = field(default_factory=dict)
    # Only Telegram Stars needs this: its "checkout" is an invoice minted by
    # the selling bot itself, so the adapter has to speak as that bot.
    bot_token: str | None = None
    telegram_user_id: int | None = None


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
    #: True when `check_status` can ask the provider outright whether a
    #: payment went through. Drives the "Я оплатил" button in the bot: with a
    #: status check it re-reads the payment; without one there is nothing to
    #: read, and the buyer's claim goes to the shop owner to confirm.
    supports_status_check: bool
    #: Per-block fields the constructor asks for on the payment block itself
    #: (as opposed to once per shop in the settings form).
    block_fields: tuple[CredentialField, ...]
    #: Whether this provider notifies us over `/webhook/pay/{slug}` at all.
    uses_callback: bool

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

    async def check_status(
        self,
        *,
        credentials: dict[str, str],
        amount_minor: int,
        invoice_no: int,
        payment_id: uuid.UUID,
        provider_payment_id: str | None,
        meta: dict,
    ) -> WebhookResult:
        """Ask the provider where this payment stands, with no callback
        involved — what the buyer's "Я оплатил" tap runs.

        Only meaningful when `supports_status_check` is True; a webhook can
        be lost or delayed, and a buyer who has already paid should not have
        to wait for a retry schedule to get what they bought."""
        ...


class ProviderDefaults:
    """What most providers don't have to think about.

    Adapters inherit this and override only where they differ, so the two
    optional halves of the protocol — an on-demand status check and per-block
    fields — cost nothing to the providers that have neither.
    """

    supports_status_check = False
    #: False for the providers that never call `/webhook/pay/...` — Stars
    #: (Telegram delivers on the bot's own webhook), pay-by-link and the test
    #: provider. Drives whether the settings form shows a callback address to
    #: paste into a merchant dashboard.
    uses_callback = True
    block_fields: tuple[CredentialField, ...] = ()

    async def check_status(
        self,
        *,
        credentials: dict[str, str],
        amount_minor: int,
        invoice_no: int,
        payment_id: uuid.UUID,
        provider_payment_id: str | None,
        meta: dict,
    ) -> WebhookResult:
        raise ProviderError(f"{getattr(self, 'title', 'Провайдер')}: статус платежа так не проверяется")


def minor_to_major(amount_minor: int) -> str:
    """990_00 -> "990.00" — the string form providers expect in a signature,
    where a rounding difference of one kopek means a rejected payment."""
    return f"{amount_minor // 100}.{amount_minor % 100:02d}"
