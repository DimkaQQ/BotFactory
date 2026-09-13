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
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import select, update
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


@dataclass(frozen=True)
class PlatformMethod:
    """One way a client can pay us for publishing a bot."""

    provider: str
    price_minor: int
    currency: str
    credentials: dict[str, str]
    is_test: bool

    @property
    def title(self) -> str:
        return payment_providers.get_provider(self.provider).title


def platform_methods() -> list[PlatformMethod]:
    """Every method offered at the publication checkout.

    Read fresh rather than cached: these carry live credentials, and a
    deployment changing them should not need a restart to take effect.
    """
    settings = get_settings()
    raw = settings.platform_payment_methods.strip()

    if raw:
        try:
            entries = json.loads(raw)
        except json.JSONDecodeError:
            logger.error("PLATFORM_PAYMENT_METHODS is not valid JSON — publication payments will fail")
            return []
        methods = []
        for entry in entries:
            try:
                provider = str(entry["provider"]).strip().lower()
                payment_providers.get_provider(provider)  # rejects a typo here, not at checkout
                methods.append(
                    PlatformMethod(
                        provider=provider,
                        price_minor=int(entry["price_minor"]),
                        currency=str(entry["currency"]).upper(),
                        credentials=dict(entry.get("credentials") or {}),
                        is_test=bool(entry.get("is_test", False)),
                    )
                )
            except (KeyError, TypeError, ValueError, ProviderError):
                logger.error("Skipping a malformed entry in PLATFORM_PAYMENT_METHODS: %r", entry)
        return methods

    # Nothing configured as a list — fall back to the single-provider
    # settings, so a deployment set up before this keeps working.
    if settings.publication_price_minor <= 0:
        return []
    credentials: dict[str, str] = {}
    if settings.platform_payment_credentials.strip():
        try:
            credentials = json.loads(settings.platform_payment_credentials)
        except json.JSONDecodeError:
            logger.error("PLATFORM_PAYMENT_CREDENTIALS is not valid JSON — publication payments will fail")
    return [
        PlatformMethod(
            provider=settings.platform_payment_provider,
            price_minor=settings.publication_price_minor,
            currency=settings.publication_currency.upper(),
            credentials=credentials,
            is_test=settings.platform_payment_is_test,
        )
    ]


def platform_method(provider: str | None) -> PlatformMethod:
    """The method the client picked, or the first one offered."""
    methods = platform_methods()
    if not methods:
        raise ProviderError("Публикация сейчас бесплатна — оплата не требуется")
    if provider:
        for method in methods:
            if method.provider == provider.strip().lower():
                return method
        raise ProviderError(f"Такой способ оплаты не подключён: {provider}")
    return methods[0]


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


def currency_for(provider_slug: str, requested: str | None) -> str:
    """The currency this provider will actually charge in.

    The block carries a currency and the provider supports a fixed list, and
    the two drift apart easily: a block created before a provider was chosen
    defaults to one currency, and the `<select>` in the editor happily shows
    the provider's list while leaving the old value in the data. The buyer
    would then be told "250 RUB" and charged 250 ⭐. The provider decides.

    But only where the block never said. Substituting silently in *both*
    cases meant a shop that had deliberately priced something at 990 ₸ and
    then switched to a rouble-only provider started charging 990 ₽ — five
    times the money, with nothing anywhere saying so. An explicit currency
    the provider cannot charge is now a refusal the owner can read.
    """
    provider = payment_providers.get_provider(provider_slug)
    wanted = (requested or "").strip().upper()
    if not wanted:
        return provider.currencies[0]
    if wanted in provider.currencies:
        return wanted
    raise ProviderError(
        f"{provider.title} не принимает {wanted}. Поменяй валюту в блоке оплаты "
        f"(доступно: {', '.join(provider.currencies)}) или выбери другого провайдера."
    )


# How long a checkout link is offered again instead of a new one being made.
# Long enough for someone to go and pay, short enough that a link the
# provider has since expired is not handed out.
_REUSE_WINDOW = timedelta(minutes=30)


def block_fingerprint(content: dict, next_block_id=None) -> str:
    """What the buyer would be sent to, boiled down.

    An open order is offered again rather than re-created, but only while it
    is still an order for the same thing: if the shop has since edited the
    link a "pay by link" block points at, or swapped the Lava offer, the
    stored checkout URL now leads somewhere else entirely.

    `next_block_id` is in here because the delivery target is pinned onto the
    payment when it is created. Rewiring the arrow while an order is open
    used to keep handing over the *old* goods for the rest of the reuse
    window — the owner changed what they sell and the bot went on selling
    the previous thing for half an hour.
    """
    watched = {k: content.get(k) for k in ("title", "link_url", "offer_id", "button_label")}
    watched["deliver_from"] = str(next_block_id) if next_block_id else None
    return json.dumps(watched, ensure_ascii=False, sort_keys=True)


async def _open_payment(
    db: AsyncSession,
    *,
    bot_id: uuid.UUID,
    block_id: uuid.UUID,
    chat_id: int,
    amount_minor: int,
    currency: str,
    fingerprint: str,
) -> Payment | None:
    """This buyer's still-open order for this exact product, if there is one."""
    result = await db.execute(
        select(Payment)
        .where(
            Payment.bot_id == bot_id,
            Payment.block_id == block_id,
            Payment.chat_id == chat_id,
            Payment.kind == PaymentKind.order,
            Payment.status == PaymentStatus.pending,
            Payment.amount_minor == amount_minor,
            Payment.currency == currency,
            Payment.created_at > datetime.now(timezone.utc) - _REUSE_WINDOW,
        )
        .order_by(Payment.created_at.desc())
        .limit(1)
    )
    payment = result.scalar_one_or_none()
    # Without a stored link there is nothing to offer again.
    if payment is None or not (payment.meta or {}).get("checkout_url"):
        return None
    if (payment.meta or {}).get("fingerprint") != fingerprint:
        return None
    return payment


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
    extra: dict | None = None,
    bot_token: str | None = None,
    meta: dict | None = None,
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
    # Committed before the provider is called, not after. `invoice_no` is
    # database-generated and the checkout link can't be signed without it, so
    # the row has to exist first either way — but holding the transaction
    # open across an outbound HTTP call with a 30-second timeout means one
    # pooled connection per checkout in flight, and the pool is fifteen.
    # Fifteen people opening checkout at once would stall every other request
    # in the process, the constructor's own API included. This is the same
    # trap `_pause` in the dispatcher was written to avoid.
    #
    # Committing first also closes a worse hole: the provider can no longer
    # mint an invoice for an order that was never written down.
    await db.commit()

    try:
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
                extra=extra or {},
                bot_token=bot_token,
                telegram_user_id=telegram_user_id,
            )
        )
    except Exception:
        # No checkout means no way for anyone to pay this row, and
        # `_open_payment` skips anything without a `checkout_url` — but an
        # inert stub would still show up in the owner's order list as a sale
        # that never happened. Take it back out.
        await db.delete(payment)
        await db.commit()
        raise

    # Several providers mint their own id at creation and then use only
    # that in the callback, so it is stored now, not when the money lands.
    payment.provider_payment_id = checkout.provider_payment_id
    payment.meta = {"checkout_url": checkout.url, **checkout.meta, **(meta or {})}
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
    currency = currency_for(bot.payment_provider, content.get("currency"))

    # Someone who taps /start three times is looking at one product, not
    # three orders. Reusing the open one keeps the shop's order list honest
    # and, for pay-by-link, stops every tap of «Я оплатил» from pinging the
    # owner about a different row.
    fingerprint = block_fingerprint(content, block.next_block_id)
    existing = await _open_payment(
        db, bot_id=bot.id, block_id=block.id, chat_id=chat_id, amount_minor=amount_minor,
        currency=currency, fingerprint=fingerprint,
    )
    if existing is not None:
        return existing, (existing.meta or {})["checkout_url"]
    # Send the buyer back where they came from — the bot — rather than to a
    # web page of ours they have no use for.
    return_url = (
        f"https://t.me/{bot.telegram_bot_username}"
        if bot.telegram_bot_username
        else f"{settings.public_base_url.rstrip('/')}/api/pay/done"
    )

    # Telegram Stars invoices are minted by the selling bot itself, so that
    # one provider — and only it — is handed the bot's token.
    bot_token = None
    if bot.payment_provider == "stars" and bot.bot_token_encrypted:
        bot_token = decrypt_token(bot.bot_token_encrypted)

    return await _create(
        db,
        kind=PaymentKind.order,
        provider_slug=bot.payment_provider,
        credentials=decrypt_credentials(bot.payment_credentials_encrypted),
        is_test=bot.payment_is_test,
        amount_minor=amount_minor,
        currency=currency,
        description=title,
        return_url=return_url,
        bot_id=bot.id,
        block_id=block.id,
        telegram_user_id=telegram_user_id,
        chat_id=chat_id,
        # The block is the product: whatever the chosen provider needs per
        # item (Lava's offerId, the link a "pay by link" block points at)
        # lives in its content.
        extra=content,
        bot_token=bot_token,
        # Pinned now, not looked up at delivery time: the shop can edit the
        # canvas while an order is open ("правки применяются сразу"), and a
        # deleted block must not turn into money taken with nothing sent.
        meta={
            "deliver_from": str(block.next_block_id) if block.next_block_id else None,
            "fingerprint": fingerprint,
        },
    )


async def create_publication_payment(
    db: AsyncSession, *, bot: BotModel, client_id: uuid.UUID, provider: str | None = None
) -> tuple[Payment, str]:
    """A client paying us to put their bot on the air, by whichever of the
    offered methods they picked."""
    settings = get_settings()
    method = platform_method(provider)

    return await _create(
        db,
        kind=PaymentKind.publication,
        provider_slug=method.provider,
        credentials=method.credentials,
        is_test=method.is_test,
        amount_minor=method.price_minor,
        currency=method.currency,
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
        # Keyed on the payment's own provider: several methods are offered at
        # once, and a callback about a Stripe payment must not be verified
        # with the crypto app's token.
        for method in platform_methods():
            if method.provider == payment.provider:
                return method.credentials, method.is_test
        logger.error("Payment %s used provider %r, which is no longer configured", payment.id, payment.provider)
        return {}, False

    result = await db.execute(select(BotModel).where(BotModel.id == payment.bot_id))
    bot = result.scalar_one_or_none()
    if bot is None:
        return {}, False
    return decrypt_credentials(bot.payment_credentials_encrypted), bot.payment_is_test


async def resume_after_payment(db: AsyncSession, payment: Payment) -> None:
    """Deliver what was bought: pick the dialogue back up at the payment
    block's next block.

    Failures are logged, never raised back at the provider — the money is
    already taken and an error here would only make it retry and re-deliver.
    But the attempt is recorded either way: `meta.delivered_at` is stamped
    only once the goods have actually gone out, which is what lets
    `redeliver_undelivered` pick up anything a restart cut in half.
    """
    from app.services import bot_dispatcher, bot_registry

    if payment.kind != PaymentKind.order or not payment.bot_id or payment.chat_id is None:
        return

    # Where delivery goes was captured when the order was created. Looking it
    # up through the block now would find nothing if the shop has since
    # edited the canvas — and "the block was deleted" must not silently mean
    # "money taken, nothing sent".
    target = (payment.meta or {}).get("deliver_from")
    if target is None:
        result = await db.execute(select(BotBlock).where(BotBlock.id == payment.block_id))
        block = result.scalar_one_or_none()
        target = str(block.next_block_id) if block is not None and block.next_block_id else None

    # The pinned target can itself have been deleted since — pinning survives
    # the payment block going away, not the delivery block. Either way the
    # answer is the same: do not quietly send a receipt and nothing else.
    if target is not None:
        exists = await db.execute(
            select(BotBlock.id).where(BotBlock.id == uuid.UUID(str(target)), BotBlock.bot_id == payment.bot_id)
        )
        if exists.scalar_one_or_none() is None:
            target = None

    try:
        bot_instance = await bot_registry.get_or_create(payment.bot_id, db)
        if bot_instance is None:
            logger.warning("Payment %s: bot %s has no token — cannot deliver", payment.id, payment.bot_id)
            return

        await bot_instance.send_message(payment.chat_id, "✅ Оплата получена, спасибо!")
        if target:
            await bot_dispatcher.walk_chain(
                bot_instance,
                payment.chat_id,
                uuid.UUID(str(target)),
                payment.bot_id,
                db,
                telegram_user_id=payment.telegram_user_id,
            )
        else:
            # Paid, but the scenario no longer says what to hand over. Tell
            # the buyer someone is coming rather than leaving them with a
            # receipt and nothing else, and make it loud in the log.
            logger.error("Payment %s: paid but there is nothing to deliver — the block is gone", payment.id)
            await bot_instance.send_message(
                payment.chat_id,
                "Оплата получена, но товар пока не пришёл — продавец уже знает и свяжется с тобой.",
            )
            await _notify_owner_of_stuck_delivery(db, payment)

        await _stamp_delivered(db, payment)
    except Exception:
        logger.exception("Payment %s: paid but delivery failed", payment.id)


async def _stamp_delivered(db: AsyncSession, payment: Payment) -> None:
    payment.meta = {**(payment.meta or {}), "delivered_at": datetime.now(timezone.utc).isoformat()}
    await db.commit()


async def _notify_owner_of_stuck_delivery(db: AsyncSession, payment: Payment) -> None:
    from app.models.client import Client
    from app.services import bot_registry

    try:
        result = await db.execute(select(BotModel).where(BotModel.id == payment.bot_id))
        bot_row = result.scalar_one_or_none()
        if bot_row is None or bot_row.client_id is None:
            return
        result = await db.execute(select(Client).where(Client.id == bot_row.client_id))
        owner = result.scalar_one_or_none()
        instance = await bot_registry.get_or_create(payment.bot_id, db)
        if owner is None or not owner.telegram_user_id or instance is None:
            return
        await instance.send_message(
            owner.telegram_user_id,
            f"⚠️ Заказ №{payment.invoice_no} оплачен, но выдавать нечего — блок после оплаты удалён. "
            f"Свяжись с покупателем и восстанови блок «Выдача».",
        )
    except Exception:
        logger.info("Could not warn the owner about stuck payment %s", payment.id, exc_info=True)


async def redeliver_undelivered(limit: int = 100) -> None:
    """Hand over anything that was paid for but never delivered.

    Delivery happens in a background task now, and the provider was already
    told "received" — so a restart in between used to lose the goods for
    good, with no retry from anywhere and nothing in the database to say so.
    Run at startup, this closes that window.
    """
    from app.database import AsyncSessionLocal

    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(Payment)
            .where(
                Payment.kind == PaymentKind.order,
                Payment.status == PaymentStatus.paid,
                # Anything settled a while ago and still unmarked was cut off
                # mid-flight; a payment from the last minute may simply be
                # in progress right now.
                Payment.paid_at < datetime.now(timezone.utc) - timedelta(minutes=1),
                # Filtered in SQL, not afterwards in Python: applying LIMIT
                # first and then dropping the delivered ones meant a single
                # undelivered order sitting behind a hundred delivered ones
                # was never found at all.
                ~Payment.meta.has_key("delivered_at"),  # noqa: W601 — JSONB ? operator
            )
            .order_by(Payment.paid_at.desc())
            .limit(limit)
        )
        pending = list(result.scalars().all())

    if not pending:
        return
    logger.warning("Re-delivering %d payment(s) that were paid but never handed over", len(pending))
    for payment in pending:
        async with AsyncSessionLocal() as db:
            fresh = (await db.execute(select(Payment).where(Payment.id == payment.id))).scalar_one_or_none()
            if fresh is not None and not (fresh.meta or {}).get("delivered_at"):
                await resume_after_payment(db, fresh)


async def redeliver_forever(every_seconds: float = 600.0) -> None:
    """Keep sweeping for paid-but-undelivered orders while the process runs.

    One pass at startup only covered a restart. It left the other way of
    losing a sale wide open: `resume_after_payment` swallows a failed send —
    a Telegram 5xx, a rate limit, a network blip — without stamping
    `delivered_at`, so the buyer's goods sat there until the next deploy.
    Now the same sweep that fixes a restart also retries a bad minute.
    """
    import asyncio

    while True:
        await asyncio.sleep(every_seconds)
        try:
            await redeliver_undelivered()
        except asyncio.CancelledError:
            raise
        except Exception:
            # A sweep that dies takes every later sweep with it, which is the
            # failure this loop exists to prevent.
            logger.exception("Redelivery sweep failed; will try again")


async def apply_result(db: AsyncSession, payment: Payment, result, *, deliver: bool = True) -> bool:
    """Turn a provider's verdict into what actually happens to the order.

    The single place a payment becomes paid, whatever prompted the news — a
    callback, the buyer's "Я оплатил", a Stars update, or the shop owner
    confirming by hand. Returns True if this call is what settled it.

    `deliver=False` settles the payment without sending anything, for callers
    that want to acknowledge the provider first and hand the goods over from
    a background task — see `deliver_later`.
    """
    await _remember(db, payment, result)

    if result.status == PaymentStatus.paid:
        if await mark_paid(db, payment, result.provider_payment_id):
            # Before delivery, not after: a Stars renewal arrives as an
            # ordinary successful_payment on the original invoice, and the
            # period has to be pushed out even if the goods themselves fail
            # to send. Losing a month of paid access to a Telegram hiccup is
            # not a trade worth making.
            from app.services import subscription_service

            try:
                await subscription_service.start_or_extend(db, payment)
            except Exception:
                logger.exception("Payment %s settled but the subscription could not be updated", payment.id)
            if deliver:
                await resume_after_payment(db, payment)
            await _notify_owner_of_sale(db, payment)
            return True
        return False

    if result.status == PaymentStatus.refunded:
        # A refund arrives *after* the payment succeeded, so testing for
        # "still pending" meant every refund notification did nothing at all
        # and the order kept counting as a sale.
        if payment.status != PaymentStatus.refunded:
            payment.status = PaymentStatus.refunded
            payment.meta = {**(payment.meta or {}), "refunded_at": datetime.now(timezone.utc).isoformat()}
            await db.commit()
            logger.info("Payment %s refunded", payment.id)
        return False

    if result.status == PaymentStatus.failed and payment.status == PaymentStatus.pending:
        payment.status = PaymentStatus.failed
        await db.commit()
    return False


async def _remember(db: AsyncSession, payment: Payment, result) -> None:
    """Write down what the adapter learned, before deciding what it means.

    Most providers hand us one notification and are done. Payme instead
    holds a conversation about the same transaction and expects every answer
    to match the last, so an adapter can return notes in
    `WebhookResult.meta` and read them back on the next call.

    Committed on its own, ahead of the status handling: `mark_paid` rolls
    back when it loses the race to settle, and these notes must survive
    that.
    """
    notes = dict(getattr(result, "meta", None) or {})
    remote_id = getattr(result, "provider_payment_id", None)
    changed = False

    if remote_id and payment.provider_payment_id != remote_id:
        payment.provider_payment_id = remote_id
        changed = True
    if notes:
        payment.meta = {**(payment.meta or {}), **notes}
        changed = True

    if changed:
        await db.commit()


def deliver_later(payment_id: uuid.UUID) -> None:
    """Hand the goods over after the current request has answered.

    Delivery walks the dialogue with real typing pauses, and a provider that
    doesn't get its acknowledgement quickly retries the callback — which is
    exactly the duplicate confirmation `mark_paid` then has to fend off.
    Better not to provoke it.
    """
    from app.services import background

    async def run() -> None:
        from app.database import AsyncSessionLocal

        async with AsyncSessionLocal() as session:
            result = await session.execute(select(Payment).where(Payment.id == payment_id))
            payment = result.scalar_one_or_none()
            if payment is not None:
                await resume_after_payment(session, payment)

    background.spawn(run(), name=f"deliver:{payment_id}")


async def check_and_settle(db: AsyncSession, payment: Payment) -> PaymentStatus:
    """Ask the provider where a payment stands right now, and deliver if it
    turns out to be paid. What the buyer's "Я оплатил" runs for a provider
    that has an API to ask — a webhook can be late, lost, or misconfigured in
    the shop's dashboard, and the buyer shouldn't pay for that."""
    provider = payment_providers.get_provider(payment.provider)
    if not provider.supports_status_check:
        raise ProviderError(f"{provider.title}: статус платежа так не проверяется")
    if payment.status in (PaymentStatus.paid, PaymentStatus.refunded):
        return payment.status

    credentials, _is_test = await credentials_for(db, payment)
    # Same reason as the callback route: the read below is an outbound HTTP
    # call, and a buyer tapping «Я оплатил» must not hold a pooled connection
    # for its duration.
    await db.commit()
    result = await provider.check_status(
        credentials=credentials,
        amount_minor=payment.amount_minor,
        invoice_no=payment.invoice_no,
        payment_id=payment.id,
        provider_payment_id=payment.provider_payment_id,
        meta=payment.meta or {},
        currency=payment.currency,
    )
    await apply_result(db, payment, result)
    return result.status


async def claim_payment(db: AsyncSession, payment: Payment) -> None:
    """The buyer says they paid, on a provider with nothing to ask.

    Recorded rather than believed: the order shows up as claimed in the
    owner's list and — if the owner has ever opened their own bot — as a
    message with confirm/reject buttons. Only the owner's confirmation
    releases the goods.
    """
    payment.meta = {**(payment.meta or {}), "claimed_at": datetime.now(timezone.utc).isoformat()}
    await db.commit()
    await _notify_owner_of_claim(db, payment)


async def _notify_owner_of_claim(db: AsyncSession, payment: Payment) -> None:
    """Best-effort ping to the shop owner. A bot may only message people who
    have written to it first, so this quietly does nothing when the owner has
    never opened their own bot — the claim is in the constructor's order list
    either way, which is why nothing here is allowed to raise."""
    from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

    from app.models.client import Client
    from app.services import bot_registry

    try:
        result = await db.execute(select(BotModel).where(BotModel.id == payment.bot_id))
        bot_row = result.scalar_one_or_none()
        if bot_row is None or bot_row.client_id is None:
            return
        result = await db.execute(select(Client).where(Client.id == bot_row.client_id))
        owner = result.scalar_one_or_none()
        if owner is None or not owner.telegram_user_id:
            return

        instance = await bot_registry.get_or_create(payment.bot_id, db)
        if instance is None:
            return

        amount = payment_providers.money(payment.amount_minor, payment.currency)
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(text="✅ Подтвердить", callback_data=f"payok:{payment.id.hex}"),
                    InlineKeyboardButton(text="✖️ Отклонить", callback_data=f"payno:{payment.id.hex}"),
                ]
            ]
        )
        await instance.send_message(
            owner.telegram_user_id,
            f"💰 Заказ №{payment.invoice_no}: «{payment.description}» на {amount}.\n"
            f"Покупатель говорит, что оплатил. Деньги пришли?",
            reply_markup=keyboard,
        )
    except Exception:
        logger.info("Could not notify the owner about claimed payment %s", payment.id, exc_info=True)


async def _owner_of(db: AsyncSession, bot_id) -> tuple[int, object] | None:
    """(owner's telegram id, bot instance) for pinging the shop owner."""
    from app.models.client import Client
    from app.services import bot_registry

    bot_row = (await db.execute(select(BotModel).where(BotModel.id == bot_id))).scalar_one_or_none()
    if bot_row is None or bot_row.client_id is None:
        return None
    owner = (await db.execute(select(Client).where(Client.id == bot_row.client_id))).scalar_one_or_none()
    if owner is None or not owner.telegram_user_id:
        return None
    instance = await bot_registry.get_or_create(bot_id, db)
    if instance is None:
        return None
    return owner.telegram_user_id, instance


async def _notify_owner_of_sale(db: AsyncSession, payment: Payment) -> None:
    """Tell the shop owner that someone bought something, and who.

    There was no such message: a card payment settled, the goods went out,
    and the owner learned about it only by reloading a panel inside the
    constructor. For a coach taking bookings that meant refreshing a web page
    to find out somebody had booked a slot — which is exactly the job a bot
    is supposed to be doing for them.

    Best-effort by construction: a bot may only message people who have
    written to it first, so this quietly does nothing when the owner has
    never opened their own bot, and nothing here is allowed to raise into the
    payment path.
    """
    from app.services import subscribers, subscription_service

    if payment.kind != PaymentKind.order:
        return
    try:
        found = await _owner_of(db, payment.bot_id)
        if found is None:
            return
        owner_id, instance = found

        buyer = await subscribers.get(db, payment.bot_id, payment.telegram_user_id)
        who = buyer.title if buyer is not None else f"id {payment.telegram_user_id}"
        amount = payment_providers.money(payment.amount_minor, payment.currency)

        subscription = await subscription_service.find_for_payment(db, payment)
        if subscription is not None and subscription.periods_paid > 1:
            headline = f"🔁 Продление №{subscription.periods_paid}"
        elif subscription is not None:
            headline = "🎉 Новая подписка"
        else:
            headline = "💰 Оплачен заказ"

        lines = [
            f"{headline} №{payment.invoice_no}",
            f"«{payment.description}» — {amount}",
            f"Покупатель: {who}",
        ]
        if subscription is not None:
            until = subscription.current_period_end.strftime("%d.%m.%Y")
            lines.append(f"Доступ оплачен до {until}")
        await instance.send_message(owner_id, "\n".join(lines))
    except Exception:
        logger.info("Could not notify the owner about paid order %s", payment.id, exc_info=True)


async def confirm_by_owner(db: AsyncSession, payment: Payment, *, deliver: bool = True) -> bool:
    """The shop owner vouches for a payment we cannot verify ourselves."""
    from app.services.payments import WebhookResult

    return await apply_result(
        db,
        payment,
        WebhookResult(status=PaymentStatus.paid, provider_payment_id=payment.provider_payment_id),
        deliver=deliver,
    )


async def reject_by_owner(db: AsyncSession, payment: Payment) -> None:
    if payment.status != PaymentStatus.pending:
        return
    payment.status = PaymentStatus.failed
    await db.commit()

    from app.services import bot_registry

    if payment.chat_id is None:
        return
    try:
        instance = await bot_registry.get_or_create(payment.bot_id, db)
        if instance is not None:
            await instance.send_message(
                payment.chat_id,
                "Пока не видим оплату по этому заказу. Если платёж прошёл — напиши продавцу, разберёмся.",
            )
    except Exception:
        logger.info("Could not tell the buyer that payment %s was rejected", payment.id, exc_info=True)


async def mark_paid(db: AsyncSession, payment: Payment, provider_payment_id: str | None) -> bool:
    """Flip a payment to paid, exactly once. True means *this* call did it.

    The caller delivers the goods on True, so "exactly once" has to survive
    concurrency, and it genuinely happens: Robokassa re-posts its ResultURL
    until it gets `OK{InvId}`, ЮKassa retries on a slow response, and the
    buyer can tap «Я оплатил» twice. Reading the status and then writing it
    would let every one of those racers observe `pending` and deliver.

    So the check and the write are one statement — `UPDATE … WHERE status
    <> 'paid'` — and Postgres decides the winner. Exactly one caller sees a
    row updated; the rest get zero and stay quiet.
    """
    now = datetime.now(timezone.utc)
    values = {"status": PaymentStatus.paid, "paid_at": now}
    if provider_payment_id:
        values["provider_payment_id"] = provider_payment_id

    result = await db.execute(
        update(Payment)
        .where(
            Payment.id == payment.id,
            # Only an open payment may become paid. `status != paid` also
            # matched a *refunded* one, so a stale "я оплатил" tap after a
            # refund re-settled the order and shipped the goods again — and
            # put the money back into the revenue figure.
            Payment.status.in_((PaymentStatus.pending, PaymentStatus.failed)),
        )
        .values(**values)
    )
    if result.rowcount == 0:
        # Someone else got there first. Roll back rather than commit, so this
        # call leaves no trace — but a rollback expires every ORM object in
        # the session, and the caller goes on to read this payment (the router
        # returns its status; the bot names its invoice_no in a message). Left
        # expired, that read is lazy IO outside a greenlet and blows up, which
        # turned a redelivered callback into a 500 and made the owner's
        # confirm button silently do nothing the second time.
        await db.rollback()
        await db.refresh(payment)
        return False

    if payment.kind == PaymentKind.publication and payment.bot_id:
        await db.execute(
            update(BotModel)
            .where(BotModel.id == payment.bot_id, BotModel.publication_paid_at.is_(None))
            .values(publication_paid_at=now)
        )

    await db.commit()
    # The in-memory object was not touched by the UPDATE; refresh it so the
    # caller (and anything it hands the payment to) sees the new state.
    await db.refresh(payment)
    return True
