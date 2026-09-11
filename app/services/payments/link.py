"""Оплата по ссылке — a payment page we know nothing about.

For every method with no API worth integrating, or none at all: a lava.top
product page, Boosty, a Telegram Wallet invoice, a bank's payment link, a
QR page. The shop owner pastes the link, the bot sends it, the buyer pays
there.

Since there is no API to ask, "did it go through?" is answered by a person.
The buyer taps «Я оплатил», the shop owner gets that claim — in the bot and
in the constructor's order list — and confirms or rejects it; confirming is
what releases the goods, exactly as a provider's callback would. That keeps
one rule intact across every provider here: nothing is delivered until
something outside the buyer's control says the money arrived.
"""

from __future__ import annotations

import uuid
from urllib.parse import urlparse

from app.services.payments.base import (
    Checkout,
    CheckoutRequest,
    CredentialField,
    PaymentRef,
    ProviderDefaults,
    ProviderError,
    WebhookResult,
)


class LinkProvider(ProviderDefaults):
    slug = "link"
    title = "Оплата по ссылке"
    hint = (
        "Подойдёт для любой оплаты, у которой есть просто страница: витрина lava.top, Boosty, счёт в "
        "Telegram Wallet, ссылка от банка, QR. Ссылка вставляется в сам блок оплаты. Автоматически "
        "проверить такую оплату невозможно, поэтому покупатель жмёт «Я оплатил», а ты подтверждаешь "
        "заказ — в боте или в списке заказов — и бот сразу выдаёт товар."
    )
    currencies = ("RUB", "KZT", "USD", "EUR", "UAH", "BYN")
    credential_fields = ()
    uses_callback = False
    has_test_mode = False
    block_fields = (
        CredentialField(
            "link_url",
            "Ссылка на оплату",
            "страница, где покупатель платит: https://…",
            secret=False,
        ),
    )

    async def create_checkout(self, request: CheckoutRequest) -> Checkout:
        url = (request.extra.get("link_url") or "").strip()
        if not url:
            raise ProviderError("Оплата по ссылке: в блоке не указана ссылка на оплату")
        parsed = urlparse(url)
        # Telegram refuses a button whose url isn't a real absolute link, and
        # a typo here would otherwise surface as a silent send failure.
        if parsed.scheme not in {"http", "https", "tg"} or not parsed.netloc:
            raise ProviderError("Оплата по ссылке: ссылка должна начинаться с https://")
        return Checkout(url=url)

    def locate_payment(self, *, headers: dict[str, str], raw_body: bytes, form: dict[str, str]) -> PaymentRef:
        return PaymentRef()

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
        meta: dict | None = None,
    ) -> WebhookResult:
        raise ProviderError("Оплата по ссылке подтверждается владельцем бота, а не уведомлением")
