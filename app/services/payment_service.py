"""Creating payments and acting on what the provider tells us afterwards.

Two flows meet here:

* an **order** — someone paying a client's bot. On "paid" the bot picks its
  dialogue back up at the payment block's next block, which is how the
  buyer receives what they bought.
* a **publication** — a client paying us to publish a bot. On "paid" the
  bot's `publication_paid_at` is stamped and the publish button unlocks.

Money never touches us in the first case: the credentials belong to the bot
owner and the checkout link points straight at their merchant account.
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models.bot import Bot as BotModel
from app.models.bot_block import BotBlock
from app.models.payment import Payment, PaymentKind, PaymentStatus
from app.services import payments as payment_providers
from app.services.payments import CheckoutRequest, ProviderError
from app.services.security import decrypt_token, encrypt_token

logger = logging.getLogger(__name__)


def encrypt_credentials(credentials: dict[str, str]) -> bytes:
    return encrypt_token(json.dumps(credentials, ensure_ascii=False))


def decrypt_credentials(blob: bytes | None) -> dict[str, str]:
    if not blob:
        return {}
    try:
        return json.loads(decrypt_token(blob))
    except (ValueError, json.JSONDecodeError):
        logger.exception("Could not read stored payment credentials")
        return {}


def platform_credentials() -> dict[str, str]:
    """Our own merchant credentials, for publication payments. One env var
    holding JSON, so a new provider needs no new settings field."""
    raw = get_settings().platform_payment_credentials.strip()
    if not raw:
        return {}
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        logger.error("PLATFORM_PAYMENT_CREDENTIALS is not valid JSON — publication payments will fail")
        return {}


def price_to_minor(value) -> int:
    """"990", "990.5", 990.5 -> minor units. Parsed via string, because a
    price is a decimal amount and floats round it wrong."""
    text = str(value).strip().replace(",", ".").replace(" ", "")
    if not text:
        return 0
    if "." not in text:
        return int(text) * 100
    whole, _, frac = text.partition(".")
    frac = (frac + "00")[:2]
    return int(whole or 0) * 100 + int(frac)


async def _create(
    db: AsyncSession,
    *,
    kind: PaymentKind,
    provider_slug: str,
    credentials: dict[str, str],
    is_test: bool,
    amount_minor: int,
    currency: str,
    description: str,
    return_url: str,
    bot_id: uuid.UUID | None = None,
    client_id: uuid.UUID | None = None,
    block_id: uuid.UUID | None = None,
    telegram_user_id: int | None = None,
    chat_id: int | None = None,
) -> tuple[Payment, str]:
    provider = payment_providers.get_provider(provider_slug)

    payment = Payment(
        kind=kind,
        status=PaymentStatus.pending,
        provider=provider.slug,
        amount_minor=amount_minor,
        currency=currency.upper(),
        description=description[:255],
        bot_id=bot_id,
        client_id=client_id,
        block_id=block_id,
        telegram_user_id=telegram_user_id,
        chat_id=chat_id,
        meta={},
    )
    db.add(payment)
    # Flushed, not committed: invoice_no is database-generated and the
    # checkout link can't be signed without it.
    await db.flush()

    checkout = await provider.create_checkout(
        CheckoutRequest(
            payment_id=payment.id,
            invoice_no=payment.invoice_no,
            amount_minor=amount_minor,
            currency=currency.upper(),
            description=description,
            return_url=return_url,
            is_test=is_test,
            credentials=credentials,
        )
    )
    # Several providers mint their own id at creation and then use only
    # that in the callback, so it is stored now, not when the money lands.
    payment.provider_payment_id = checkout.provider_payment_id
    payment.meta = {"checkout_url": checkout.url, **checkout.meta}
    await db.commit()
    await db.refresh(payment)
    return payment, checkout.url


async def create_order_payment(
    db: AsyncSession,
    *,
    bot: BotModel,
    block: BotBlock,
    chat_id: int,
    telegram_user_id: int | None,
) -> tuple[Payment, str]:
    """A customer buying something from a client's bot."""
    content = block.content or {}
    amount_minor = price_to_minor(content.get("price"))
    if amount_minor <= 0:
        raise ProviderError("В блоке оплаты не указана цена")
    if not bot.payment_provider:
        raise ProviderError("У бота не подключён платёжный провайдер")

    settings = get_settings()
    title = (content.get("title") or "").strip() or "Оплата"
    # Send the buyer back where they came from — the bot — rather than to a
    # web page of ours they have no use for.
    return_url = (
        f"https://t.me/{bot.telegram_bot_username}"
        if bot.telegram_bot_username
        else f"{settings.public_base_url.rstrip('/')}/api/pay/done"
    )

    return await _create(
        db,
        kind=PaymentKind.order,
        provider_slug=bot.payment_provider,
        credentials=decrypt_credentials(bot.payment_credentials_encrypted),
        is_test=bot.payment_is_test,
        amount_minor=amount_minor,
        currency=(content.get("currency") or "RUB").upper(),
        description=title,
        return_url=return_url,
        bot_id=bot.id,
        block_id=block.id,
        telegram_user_id=telegram_user_id,
        chat_id=chat_id,
    )


async def create_publication_payment(db: AsyncSession, *, bot: BotModel, client_id: uuid.UUID) -> tuple[Payment, str]:
    """A client paying us to put their bot on the air."""
    settings = get_settings()
    amount_minor = settings.publication_price_minor
    if amount_minor <= 0:
        raise ProviderError("Публикация сейчас бесплатна — оплата не требуется")

    return await _create(
        db,
        kind=PaymentKind.publication,
        provider_slug=settings.platform_payment_provider,
        credentials=platform_credentials(),
        is_test=settings.platform_payment_is_test,
        amount_minor=amount_minor,
        currency=settings.publication_currency,
        description=f"Публикация бота в Telegram · {bot.name or 'Новый бот'}",
        # Back into the constructor, which polls the payment and unlocks
        # the publish button as soon as it turns paid.
        return_url=f"{settings.public_base_url.rstrip('/')}/?paid={bot.id}",
        bot_id=bot.id,
        client_id=client_id,
    )


async def find_payment(db: AsyncSession, ref) -> Payment | None:
    if ref.payment_id is not None:
        result = await db.execute(select(Payment).where(Payment.id == ref.payment_id))
        return result.scalar_one_or_none()
    if ref.invoice_no is not None:
        result = await db.execute(select(Payment).where(Payment.invoice_no == ref.invoice_no))
        return result.scalar_one_or_none()
    if ref.provider_payment_id is not None:
        result = await db.execute(
            select(Payment).where(Payment.provider_payment_id == ref.provider_payment_id)
        )
        return result.scalar_one_or_none()
    return None


async def credentials_for(db: AsyncSession, payment: Payment) -> tuple[dict[str, str], bool]:
    """Whose merchant account this payment belongs to — the bot owner's, or
    ours for a publication."""
    if payment.kind == PaymentKind.publication:
        settings = get_settings()
        return platform_credentials(), settings.platform_payment_is_test

    result = await db.execute(select(BotModel).where(BotModel.id == payment.bot_id))
    bot = result.scalar_one_or_none()
    if bot is None:
        return {}, False
    return decrypt_credentials(bot.payment_credentials_encrypted), bot.payment_is_test


async def resume_after_payment(db: AsyncSession, payment: Payment) -> None:
    """Deliver what was bought: pick the dialogue back up at the payment
    block's next block. Best-effort — the money is already taken, so a
    Telegram hiccup here is logged, never raised back at the provider (which
    would make it retry and re-deliver)."""
    from app.services import bot_dispatcher, bot_registry

    if payment.kind != PaymentKind.order or not payment.bot_id or payment.chat_id is None:
        return

    result = await db.execute(select(BotBlock).where(BotBlock.id == payment.block_id))
    block = result.scalar_one_or_none()

    try:
        bot_instance = await bot_registry.get_or_create(payment.bot_id, db)
        if bot_instance is None:
            logger.warning("Payment %s: bot %s has no token — cannot deliver", payment.id, payment.bot_id)
            return

        await bot_instance.send_message(payment.chat_id, "✅ Оплата получена, спасибо!")
        if block is not None and block.next_block_id is not None:
            await bot_dispatcher._walk_chain(
                bot_instance,
                payment.chat_id,
                block.next_block_id,
                payment.bot_id,
                db,
                telegram_user_id=payment.telegram_user_id,
            )
    except Exception:
        logger.exception("Payment %s: paid but delivery failed", payment.id)


async def mark_paid(db: AsyncSession, payment: Payment, provider_payment_id: str | None) -> bool:
    """Returns True if this call is what flipped it to paid — webhooks get
    redelivered, and delivering the goods twice is worse than not at all."""
    if payment.status == PaymentStatus.paid:
        return False

    payment.status = PaymentStatus.paid
    payment.paid_at = datetime.now(timezone.utc)
    if provider_payment_id:
        payment.provider_payment_id = provider_payment_id

    if payment.kind == PaymentKind.publication and payment.bot_id:
        result = await db.execute(select(BotModel).where(BotModel.id == payment.bot_id))
        bot = result.scalar_one_or_none()
        if bot is not None and bot.publication_paid_at is None:
            bot.publication_paid_at = datetime.now(timezone.utc)

    await db.commit()
    return True
