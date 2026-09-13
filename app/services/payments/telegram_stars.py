"""Telegram Stars (XTR) — the only way a bot may sell digital goods.

App Store and Google Play rules put digital goods and services sold inside
Telegram on Stars; cards through a payment provider are for physical goods
and offline services. So a bot selling a guide, a course or channel access
belongs here, not on Prodamus.

Nothing about this looks like the other providers, even though it wears the
same interface:

* the "checkout link" is an invoice the *selling bot* mints for itself with
  `createInvoiceLink`, so the adapter needs that bot's token rather than
  merchant credentials — there are no credentials, and nothing to configure;
* the confirmation never reaches `/webhook/pay/...`. It arrives as ordinary
  updates on the bot's own webhook (`pre_checkout_query`, then a message
  carrying `successful_payment`), which the dispatcher handles — see
  `bot_dispatcher._handle_pre_checkout` / `_handle_successful_payment`;
* the amount is a whole number of stars, not minor units of a currency.
"""

from __future__ import annotations

import uuid

from aiogram import Bot
from aiogram.types import LabeledPrice

from app.models.payment import PaymentStatus
from app.services.payments.base import (
    Checkout,
    CheckoutRequest,
    PaymentRef,
    ProviderDefaults,
    ProviderError,
    WebhookResult,
)
from app.services.telegram_session import build_bot_session

# Telegram's own bounds for a Stars invoice.
_MIN_STARS = 1
_MAX_STARS = 100_000

#: Telegram accepts exactly one subscription period today: 30 days. Named
#: rather than inlined so the day it accepts more, there is one place to look.
SUBSCRIPTION_PERIOD_SECONDS = 2592000
#: Subscriptions are capped lower than one-off invoices by Telegram itself.
_MAX_SUBSCRIPTION_STARS = 2500


def stars_from_minor(amount_minor: int) -> int:
    """Prices are stored in minor units throughout, so 250 stars is held as
    250_00. Stars come only in whole units — half a star cannot be charged,
    and silently rounding one away would mis-price the product."""
    if amount_minor % 100 != 0:
        raise ProviderError("Telegram Stars: цена должна быть целым числом звёзд, без копеек")
    stars = amount_minor // 100
    if not _MIN_STARS <= stars <= _MAX_STARS:
        raise ProviderError(f"Telegram Stars: цена должна быть от {_MIN_STARS} до {_MAX_STARS} ⭐")
    return stars


class TelegramStarsProvider(ProviderDefaults):
    slug = "stars"
    title = "Telegram Stars ⭐"
    hint = (
        "Ничего подключать не нужно — оплата идёт внутри Telegram токеном самого бота. Цена указывается "
        "в звёздах (целым числом). По правилам Apple и Google цифровые товары в боте — гайды, курсы, доступ "
        "к каналу — можно продавать только так; карты нужны для физических товаров и офлайн-услуг. "
        "Звёзды выводятся через Fragment примерно через 21 день после оплаты."
    )
    currencies = ("XTR",)
    region = "global"
    credential_fields = ()
    uses_callback = False
    has_test_mode = False

    async def create_checkout(self, request: CheckoutRequest) -> Checkout:
        if not request.bot_token:
            raise ProviderError("Telegram Stars: бот ещё не опубликован — нет токена для выставления счёта")
        stars = stars_from_minor(request.amount_minor)

        title = (request.description or "Покупка").strip()[:32]
        # A subscription invoice differs from a one-off one by a single
        # argument — and that argument is the whole difference between a
        # product that charges once and one that charges every month, with
        # Telegram doing the charging and the subscriber able to cancel from
        # inside Telegram. Of the twenty providers here it is the only one
        # that can take money a second time on its own.
        period = SUBSCRIPTION_PERIOD_SECONDS if request.extra.get("subscription") else None
        if period is not None and stars > _MAX_SUBSCRIPTION_STARS:
            raise ProviderError(
                f"Telegram Stars: подписка не может стоить дороже {_MAX_SUBSCRIPTION_STARS} ⭐ за месяц"
            )

        bot = Bot(token=request.bot_token, session=build_bot_session())
        try:
            url = await bot.create_invoice_link(
                title=title,
                # Telegram requires a non-empty description and shows it on
                # the payment sheet; the title alone is often all the block
                # carries, so it stands in rather than sending a blank.
                description=(request.description or title)[:255],
                # Comes back verbatim in successful_payment — this is how the
                # confirmation finds its way back to our row.
                payload=str(request.payment_id),
                currency="XTR",
                prices=[LabeledPrice(label=title, amount=stars)],
                subscription_period=period,
            )
        except Exception as exc:  # aiogram raises its own family of errors
            raise ProviderError(f"Telegram Stars: {exc}") from exc
        finally:
            await bot.session.close()

        return Checkout(url=url, meta={"stars": stars, "subscription_period": period})

    def locate_payment(self, *, headers: dict[str, str], raw_body: bytes, form: dict[str, str]) -> PaymentRef:
        # Stars never call our payment webhook — the money lands as a
        # Telegram update on the bot's own webhook instead.
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
        currency: str = "",
    ) -> WebhookResult:
        raise ProviderError("Telegram Stars: оплата подтверждается через webhook самого бота, не здесь")


def settled(
    charge_id: str,
    total_amount: int,
    amount_minor: int,
    *,
    is_recurring: bool = False,
    is_first_recurring: bool = False,
    subscription_expiration: int | None = None,
) -> WebhookResult:
    """What the dispatcher turns a `successful_payment` into.

    Telegram vouched for this update by delivering it on the bot's own
    webhook, so there is no signature to check — but the amount is still
    compared, because a stale invoice link for a since-lowered price would
    otherwise unlock the current product.

    The recurrence flags are passed through rather than interpreted here: a
    renewal arrives as an ordinary `successful_payment` on the same payload,
    thirty days later and with nobody having tapped anything, and it is the
    subscription layer's job to decide what that means.
    """
    expected = amount_minor // 100
    if total_amount != expected:
        raise ProviderError(f"Telegram Stars: оплачено {total_amount} ⭐ вместо {expected} ⭐")
    return WebhookResult(
        status=PaymentStatus.paid,
        provider_payment_id=charge_id,
        meta={
            "is_recurring": bool(is_recurring),
            "is_first_recurring": bool(is_first_recurring),
            "subscription_expiration": subscription_expiration,
        },
    )
