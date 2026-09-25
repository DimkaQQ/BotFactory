"""Payment callbacks (provider → us) and the payment endpoints the
constructor talks to.

The callback route is deliberately provider-agnostic: identify the payment,
load *its* credentials, let the adapter verify the signature, then act. A
callback that fails verification changes nothing and is answered with 400.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta, timezone
from html import escape
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import HTMLResponse, PlainTextResponse, Response
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.database import get_db
from app.deps import get_current_client, get_owned_bot
from app.models.bot import Bot as BotModel
from app.models.bot import BotStatus
from app.models.bot_block import BlockType, BotBlock
from app.models.bot_subscriber import BotSubscriber
from app.models.client import Client
from app.models.scheduled_step import ScheduledStep
from app.models.subscription import Subscription, SubscriptionStatus
from app.models.payment import Payment, PaymentKind, PaymentStatus
from app.schemas.payment import (
    BillingStateOut,
    PaymentOut,
    PaymentSettingsIn,
    PaymentSettingsOut,
    PublicationCheckoutIn,
    PublicationInfoOut,
    PublicationMethodOut,
)
from app.services import payment_service, platform_billing
from app.services import payments as payment_providers
from app.services.payments import ProviderError

logger = logging.getLogger(__name__)

router = APIRouter(tags=["payments"])


# ---------------------------------------------------------------- callbacks


async def _apply(db: AsyncSession, payment: Payment, result) -> None:
    """Settle now, deliver after answering.

    Providers retry a callback they don't see acknowledged quickly, and
    delivery is slow by design — so the payment is recorded inside the
    request (which is what makes the retry harmless) and the goods go out
    from a background task.
    """
    # Only orders have something to hand over; a publication payment just
    # unlocks the publish button.
    if await payment_service.apply_result(db, payment, result, deliver=False):
        if payment.kind == PaymentKind.order:
            payment_service.deliver_later(payment.id)


def _refusal(provider, *, form: dict, raw_body: bytes, found: bool, exc: Exception | None = None):
    """How to say no to this particular provider.

    Almost all of them read an HTTP error as "delivery failed, try again",
    which is what we want. Click and Payme are built the other way round:
    they answer everything with 200 and put the verdict in the body, and an
    HTTP error tells them the integration is broken rather than that the
    payment was rejected. Those two supply their own refusal.
    """
    body = getattr(exc, "body", None)
    if body is not None:
        return Response(content=body, media_type="application/json")
    supplied = provider.error_body(form=form, raw_body=raw_body, found=found)
    if supplied is None:
        return None
    content, media_type = supplied
    return Response(content=content, media_type=media_type)


@router.post("/webhook/pay/{provider_slug}")
async def payment_callback(provider_slug: str, request: Request, db: AsyncSession = Depends(get_db)) -> Response:
    try:
        provider = payment_providers.get_provider(provider_slug)
    except ProviderError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    raw_body = await request.body()
    try:
        form = {key: str(value) for key, value in (await request.form()).items()}
    except Exception:
        form = {}
    headers = {key.lower(): value for key, value in request.headers.items()}

    ref = provider.locate_payment(headers=headers, raw_body=raw_body, form=form)
    payment = await payment_service.find_payment(db, ref)
    if payment is not None and payment.provider != provider.slug:
        # Someone else's payment, addressed to this provider's route.
        payment = None
    if payment is None:
        logger.warning("Payment callback from %s did not match any payment", provider_slug)
        refusal = _refusal(provider, form=form, raw_body=raw_body, found=False)
        if refusal is not None:
            return refusal
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unknown payment")

    credentials, _is_test = await payment_service.credentials_for(db, payment)
    # Half the adapters answer a callback by calling the provider's own API,
    # which can take tens of seconds. Let go of the pooled connection first —
    # a retry storm from one slow provider would otherwise take the whole
    # process down with it. Safe to commit rather than roll back:
    # `expire_on_commit=False` keeps `payment` usable afterwards.
    await db.commit()
    try:
        result = await provider.verify_webhook(
            headers=headers,
            raw_body=raw_body,
            form=form,
            credentials=credentials,
            amount_minor=payment.amount_minor,
            invoice_no=payment.invoice_no,
            payment_id=payment.id,
            provider_payment_id=payment.provider_payment_id,
            meta=payment.meta or {},
            currency=payment.currency,
        )
    except ProviderError as exc:
        logger.warning("Rejected %s callback for payment %s: %s", provider_slug, payment.id, exc)
        refusal = _refusal(provider, form=form, raw_body=raw_body, found=True, exc=exc)
        if refusal is not None:
            return refusal
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    await _apply(db, payment, result)
    return Response(content=result.response_body, media_type=result.response_content_type)


@router.get("/api/pay/redirect/{payment_id}", response_class=HTMLResponse)
async def payment_redirect(payment_id: uuid.UUID, db: AsyncSession = Depends(get_db)) -> HTMLResponse:
    """A link for a checkout that is only reachable by POST.

    LiqPay's checkout is an HTML form, not a URL, and a bot button can only
    carry a link — so the link points here and this page submits the form.
    The fields were built when the payment was created and contain nothing
    secret: they are exactly what the browser would have sent anyway.
    """
    result = await db.execute(select(Payment).where(Payment.id == payment_id))
    payment = result.scalar_one_or_none()
    meta = (payment.meta or {}) if payment else {}
    action = meta.get("form_action")
    fields = meta.get("form_fields") or {}
    if payment is None or not action:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Платёж не найден")

    inputs = "".join(
        f'<input type="hidden" name="{escape(str(key), quote=True)}" '
        f'value="{escape(str(value), quote=True)}">'
        for key, value in fields.items()
    )
    return HTMLResponse(
        f"""<!doctype html><html lang="ru"><head><meta charset="utf-8">
        <meta name="viewport" content="width=device-width,initial-scale=1">
        <title>Переход к оплате</title></head>
        <body style="font-family:system-ui,sans-serif;display:flex;min-height:100vh;margin:0;
                     align-items:center;justify-content:center;background:#fdfcfe;color:#14121f">
          <form id="pay" method="post" action="{escape(str(action), quote=True)}" accept-charset="utf-8">
            {inputs}
            <noscript><button type="submit">Перейти к оплате</button></noscript>
          </form>
          <p style="color:#83829a;font-size:14px">Открываем страницу оплаты…</p>
          <script>document.getElementById('pay').submit();</script>
        </body></html>"""
    )


@router.get("/webhook/pay/test/{payment_id}", response_class=HTMLResponse)
async def test_payment_page(payment_id: uuid.UUID, db: AsyncSession = Depends(get_db)) -> HTMLResponse:
    """The whole of the "test" provider: opening its checkout link marks the
    payment paid. Guarded so it can only ever settle a test-mode payment."""
    result = await db.execute(select(Payment).where(Payment.id == payment_id))
    payment = result.scalar_one_or_none()
    if payment is None or payment.provider != "test":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unknown payment")

    _credentials, is_test = await payment_service.credentials_for(db, payment)
    if not is_test:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Тестовая оплата выключена")

    provider = payment_providers.get_provider("test")
    verified = await provider.verify_webhook(
        headers={},
        raw_body=b"",
        form={},
        credentials={},
        amount_minor=payment.amount_minor,
        invoice_no=payment.invoice_no,
        payment_id=payment.id,
        provider_payment_id=payment.provider_payment_id,
    )
    await _apply(db, payment, verified)

    amount = payment_providers.money(payment.amount_minor, payment.currency)
    return HTMLResponse(
        f"""<!doctype html><html lang="ru"><head><meta charset="utf-8">
        <meta name="viewport" content="width=device-width,initial-scale=1">
        <title>Тестовая оплата</title></head>
        <body style="font-family:system-ui,sans-serif;display:flex;min-height:100vh;margin:0;
                     align-items:center;justify-content:center;background:#fdfcfe;color:#14121f">
          <div style="text-align:center;max-width:320px">
            <div style="font-size:44px">✅</div>
            <h1 style="font-size:20px;margin:12px 0 6px">Тестовая оплата прошла</h1>
            <p style="color:#83829a;font-size:14px;margin:0">
              {escape(payment.description or '')} — {amount} {escape(payment.currency)}.<br>Возвращайся в Telegram, бот уже всё прислал.
            </p>
          </div>
        </body></html>"""
    )


@router.get("/api/pay/done", response_class=HTMLResponse)
async def payment_done() -> HTMLResponse:
    """Fallback landing page for a provider's "return to merchant" link.
    Under /api/ so it rides the same proxy rule as the rest of the backend on
    every deployment flavour (the SPA owns every other path).

    Deliberately says nothing about status: what settles a payment is the
    provider's callback, not a browser redirect anyone could open by hand."""
    return HTMLResponse(
        """<!doctype html><html lang="ru"><head><meta charset="utf-8">
        <meta name="viewport" content="width=device-width,initial-scale=1">
        <title>Оплата</title></head>
        <body style="font-family:system-ui,sans-serif;display:flex;min-height:100vh;margin:0;
                     align-items:center;justify-content:center;background:#fdfcfe;color:#14121f">
          <div style="text-align:center;max-width:320px">
            <div style="font-size:44px">💳</div>
            <h1 style="font-size:20px;margin:12px 0 6px">Готово</h1>
            <p style="color:#83829a;font-size:14px;margin:0">
              Как только банк подтвердит платёж, бот пришлёт всё сам. Можно закрывать эту страницу.
            </p>
          </div>
        </body></html>"""
    )


# ------------------------------------------------------------------ the API


@router.get("/api/payments/providers")
async def list_providers(_client: Client = Depends(get_current_client)) -> dict:
    return {
        "providers": payment_providers.describe_providers(),
        # Subscriptions are built but switched off while the one-off sale is
        # being shaken out; the constructor hides the control rather than
        # showing one that does nothing.
        "subscriptions_enabled": get_settings().subscriptions_enabled,
        # The section headings, in display order. Sent alongside rather than
        # hardcoded in the constructor so adding a gateway is a backend-only
        # change — see payments/__init__.py.
        "regions": [{"slug": slug, "title": title} for slug, title in payment_providers.REGIONS],
    }


@router.get("/api/bots/{bot_id}/payment-settings", response_model=PaymentSettingsOut)
async def get_payment_settings(
    bot_id: uuid.UUID,
    bot: BotModel = Depends(get_owned_bot),
) -> PaymentSettingsOut:
    credentials = payment_service.decrypt_credentials(bot.payment_credentials_encrypted)
    return PaymentSettingsOut(
        provider=bot.payment_provider,
        is_test=bot.payment_is_test,
        # Which keys are filled in, never the keys themselves.
        filled_fields=sorted(k for k, v in credentials.items() if str(v).strip()),
        # Only for providers that actually notify us. Stars, pay-by-link and
        # Processing.kz never call this address, and offering it invited a
        # shop owner to paste something into a dashboard that does nothing.
        callback_url=(
            f"{get_settings().public_base_url.rstrip('/')}/webhook/pay/{bot.payment_provider}"
            if bot.payment_provider and payment_providers.get_provider(bot.payment_provider).uses_callback
            else None
        ),
    )


@router.put("/api/bots/{bot_id}/payment-settings", response_model=PaymentSettingsOut)
async def set_payment_settings(
    bot_id: uuid.UUID,
    payload: PaymentSettingsIn,
    bot: BotModel = Depends(get_owned_bot),
    db: AsyncSession = Depends(get_db),
) -> PaymentSettingsOut:
    if payload.provider:
        try:
            payment_providers.get_provider(payload.provider)
        except ProviderError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    # Publishing refuses the test provider, but that check alone is a door
    # with a window beside it: publish with a real one, then switch. Its
    # checkout page marks an order paid the moment it is opened, so a live
    # bot carrying it hands goods to anyone who taps the button.
    if payload.provider == "test" and bot.status != BotStatus.draft:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "«Тестовая оплата» отдаёт товар без денег, поэтому её нельзя включить "
                "на опубликованном боте."
            ),
        )

    switching = (payload.provider or None) != bot.payment_provider
    bot.payment_provider = payload.provider or None
    bot.payment_is_test = payload.is_test

    # Keys belong to the provider they were issued for. Left merged, turning
    # payments off or moving to another provider would keep live Robokassa
    # passwords sitting in the database forever, and the settings API would
    # go on listing them as filled.
    existing = {} if switching else payment_service.decrypt_credentials(bot.payment_credentials_encrypted)

    if payload.credentials is not None or switching:
        supplied = {k: v for k, v in (payload.credentials or {}).items() if v.strip()}
        # Blank means "leave what's stored" — the form never receives the
        # saved secrets back, so an untouched field arrives empty.
        merged = {**existing, **supplied}
        if bot.payment_provider:
            # Drop anything the chosen provider has no field for, so a stale
            # key from a previous provider cannot linger.
            allowed = {f.key for f in payment_providers.get_provider(bot.payment_provider).credential_fields}
            merged = {k: v for k, v in merged.items() if k in allowed}
        else:
            merged = {}
        bot.payment_credentials_encrypted = payment_service.encrypt_credentials(merged) if merged else None

    await db.commit()
    await db.refresh(bot)
    return await get_payment_settings(bot_id, bot)


@router.get("/api/bots/{bot_id}/publication", response_model=PublicationInfoOut)
async def publication_info(bot_id: uuid.UUID, bot: BotModel = Depends(get_owned_bot)) -> PublicationInfoOut:
    methods = payment_service.platform_methods()
    return PublicationInfoOut(
        # No configured method means publishing is free — a fresh deployment
        # is never locked behind a paywall nobody set up.
        required=bool(methods),
        paid=bot.publication_paid_at is not None,
        price_minor=methods[0].price_minor if methods else 0,
        currency=methods[0].currency if methods else "",
        methods=[
            PublicationMethodOut(
                provider=m.provider,
                title=m.title,
                price_minor=m.price_minor,
                currency=m.currency,
                renewal_price_minor=m.renewal_price_minor,
            )
            for m in methods
        ],
        renewal_price_minor=platform_billing.renewal_price()[0],
        renewal_period_days=platform_billing.period_days(),
        renewal_grace_days=platform_billing.grace_days(),
    )


@router.get("/api/bots/{bot_id}/polls")
async def poll_results(
    bot_id: uuid.UUID,
    bot: BotModel = Depends(get_owned_bot),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Что ответили в опросах этого бота.

    До этого ответы записывались в таблицу, которую никто не читал: ни
    эндпоинта, ни экрана. Блок продавался как способ «узнать, чего хотят
    подписчики», а узнать было негде.
    """
    from app.models.poll_answer import PollAnswer

    blocks = (
        await db.execute(
            select(BotBlock).where(BotBlock.bot_id == bot_id, BotBlock.block_type == BlockType.poll)
        )
    ).scalars().all()

    counts = dict(
        (row[0], row[1])
        for row in (
            await db.execute(
                select(PollAnswer.block_id, func.count(PollAnswer.id))
                .where(PollAnswer.bot_id == bot_id)
                .group_by(PollAnswer.block_id)
            )
        ).all()
    )

    answers = (
        await db.execute(select(PollAnswer.block_id, PollAnswer.option_ids).where(PollAnswer.bot_id == bot_id))
    ).all()

    polls = []
    for block in blocks:
        content = block.content or {}
        options = [str(o) for o in (content.get("options") or [])]
        tally = [0] * len(options)
        for block_id, option_ids in answers:
            if block_id != block.id:
                continue
            for index in option_ids or []:
                if 0 <= index < len(tally):
                    tally[index] += 1
        polls.append({
            "block_id": str(block.id),
            "question": content.get("question") or "",
            "answered": counts.get(block.id, 0),
            # Анонимный опрос Telegram присылает без пользователя, то есть
            # ответов не будет вовсе — это надо сказать, а не показывать ноль.
            "anonymous": bool(content.get("anonymous")),
            "options": [{"label": label, "votes": tally[i]} for i, label in enumerate(options)],
        })
    return {"polls": polls}


@router.get("/api/bots/{bot_id}/billing", response_model=BillingStateOut)
async def billing_state(bot_id: uuid.UUID, bot: BotModel = Depends(get_owned_bot)) -> BillingStateOut:
    state = platform_billing.state_of(bot)
    return BillingStateOut(
        state=state.state,
        paid_until=state.paid_until,
        grace_until=state.grace_until,
        days_left=state.days_left,
        price_minor=state.price_minor,
        currency=state.currency,
        period_days=platform_billing.period_days(),
    )


@router.post("/api/bots/{bot_id}/renewal-checkout", response_model=PaymentOut)
async def renewal_checkout(
    bot_id: uuid.UUID,
    payload: PublicationCheckoutIn | None = None,
    bot: BotModel = Depends(get_owned_bot),
    client: Client = Depends(get_current_client),
    db: AsyncSession = Depends(get_db),
) -> PaymentOut:
    """Buy the bot another period.

    Allowed early as well as late: an owner going on holiday should be able
    to pay three periods ahead, and `extend_period` counts them from the end
    of the paid one rather than from today.
    """
    try:
        payment, url = await payment_service.create_renewal_payment(
            db, bot=bot, client_id=client.id, provider=payload.provider if payload else None
        )
    except ProviderError as exc:
        logger.error("Renewal checkout failed for bot %s: %s", bot_id, exc)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Этот способ оплаты сейчас недоступен. Попробуй другой или напиши нам.",
        ) from exc

    return PaymentOut(
        id=payment.id,
        status=payment.status,
        amount_minor=payment.amount_minor,
        currency=payment.currency,
        checkout_url=url,
    )


@router.post("/api/bots/{bot_id}/publication-checkout", response_model=PaymentOut)
async def publication_checkout(
    bot_id: uuid.UUID,
    payload: PublicationCheckoutIn | None = None,
    bot: BotModel = Depends(get_owned_bot),
    client: Client = Depends(get_current_client),
    db: AsyncSession = Depends(get_db),
) -> PaymentOut:
    if bot.publication_paid_at is not None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Публикация этого бота уже оплачена")

    try:
        payment, url = await payment_service.create_publication_payment(
            db, bot=bot, client_id=client.id, provider=payload.provider if payload else None
        )
    except ProviderError as exc:
        # The detail names our own misconfiguration ("не заполнен secret
        # key") — useful in the log, not something to show the person trying
        # to pay us.
        logger.error("Publication checkout failed for bot %s: %s", bot_id, exc)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Этот способ оплаты сейчас недоступен. Попробуй другой или напиши нам.",
        ) from exc

    return PaymentOut(
        id=payment.id,
        status=payment.status,
        amount_minor=payment.amount_minor,
        currency=payment.currency,
        checkout_url=url,
    )


@router.get("/api/payments/{payment_id}", response_model=PaymentOut)
async def payment_status(
    payment_id: uuid.UUID,
    client: Client = Depends(get_current_client),
    db: AsyncSession = Depends(get_db),
) -> PaymentOut:
    """Polled by the constructor while the payer is off on the provider's
    page — scoped to the caller's own payments."""
    result = await db.execute(select(Payment).where(Payment.id == payment_id, Payment.client_id == client.id))
    payment = result.scalar_one_or_none()
    if payment is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Платёж не найден")

    return PaymentOut(
        id=payment.id,
        status=payment.status,
        amount_minor=payment.amount_minor,
        currency=payment.currency,
        checkout_url=(payment.meta or {}).get("checkout_url"),
    )


@router.get("/api/bots/{bot_id}/orders")
async def list_orders(
    bot_id: uuid.UUID,
    bot: BotModel = Depends(get_owned_bot),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """What this bot has sold — the owner's own sales log.

    The totals are computed in the database over *every* order, not over the
    page of recent ones: summing only the last hundred made a busy shop's
    reported revenue start silently going down. They are also grouped by
    currency, because a shop selling for 990 ₽ and 250 ⭐ has not earned
    "1240" of anything.
    """
    totals = await db.execute(
        select(Payment.currency, func.count(Payment.id), func.sum(Payment.amount_minor))
        .where(
            Payment.bot_id == bot_id,
            Payment.kind == PaymentKind.order,
            Payment.status == PaymentStatus.paid,
        )
        .group_by(Payment.currency)
        .order_by(func.sum(Payment.amount_minor).desc())
    )
    by_currency = [
        {"currency": currency, "count": count, "total_minor": int(total or 0)}
        for currency, count, total in totals.all()
    ]

    result = await db.execute(
        select(Payment)
        .where(Payment.bot_id == bot_id, Payment.kind == PaymentKind.order)
        .order_by(Payment.created_at.desc())
        .limit(100)
    )
    orders = result.scalars().all()

    # Who bought. The id was already in this response and the panel never
    # showed it, so a coach taking bookings could see that *someone* had paid
    # 3000 ₽ for «Пн 15 сентября, 19:00» and had no way to find out who, or
    # to write to them. One query for the whole page rather than one per row.
    buyer_ids = {o.telegram_user_id for o in orders if o.telegram_user_id is not None}
    buyers: dict[int, BotSubscriber] = {}
    if buyer_ids:
        found = await db.execute(
            select(BotSubscriber).where(
                BotSubscriber.bot_id == bot_id, BotSubscriber.telegram_user_id.in_(buyer_ids)
            )
        )
        buyers = {row.telegram_user_id: row for row in found.scalars().all()}

    return {
        "orders": [
            {
                "id": str(o.id),
                "invoice_no": o.invoice_no,
                "status": o.status,
                "amount_minor": o.amount_minor,
                "currency": o.currency,
                "description": o.description,
                "telegram_user_id": o.telegram_user_id,
                "buyer": _buyer_of(buyers.get(o.telegram_user_id)),
                "created_at": o.created_at,
                "paid_at": o.paid_at,
                # Set when the buyer tapped «Я оплатил» on a provider we
                # can't ask — these are the ones waiting on the owner.
                "claimed_at": (o.meta or {}).get("claimed_at"),
                "needs_confirmation": o.status == PaymentStatus.pending and bool((o.meta or {}).get("claimed_at")),
            }
            for o in orders
        ],
        "totals": by_currency,
        # Kept for an older frontend; meaningful only for a single-currency
        # shop, which is why `totals` exists.
        "paid_count": sum(t["count"] for t in by_currency),
        "paid_total_minor": by_currency[0]["total_minor"] if len(by_currency) == 1 else 0,
    }


@router.get("/api/bots/{bot_id}/subscribers")
async def list_subscribers(
    bot_id: uuid.UUID,
    bot: BotModel = Depends(get_owned_bot),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Everyone the bot is selling to, and where each subscription stands.

    There was nothing like this: a shop owner could not answer "кто у меня
    платит" or "у кого заканчивается доступ" from inside the product at all.
    Subscriptions first, because those are the rows with a date on them;
    then everyone else who ever wrote to the bot.
    """
    subs = await db.execute(
        select(Subscription)
        .where(Subscription.bot_id == bot_id)
        .order_by(Subscription.status, Subscription.current_period_end.desc())
        .limit(200)
    )
    subscriptions = list(subs.scalars().all())

    people = await db.execute(
        select(BotSubscriber)
        .where(BotSubscriber.bot_id == bot_id)
        .order_by(BotSubscriber.last_seen_at.desc())
        .limit(200)
    )
    everyone = list(people.scalars().all())
    by_id = {person.telegram_user_id: person for person in everyone}

    return {
        "subscriptions": [
            {
                "id": str(s.id),
                "title": s.title,
                "status": s.status,
                "billing_mode": s.billing_mode,
                "provider": s.provider,
                "period_days": s.period_days,
                "periods_paid": s.periods_paid,
                "amount_minor": s.amount_minor,
                "currency": s.currency,
                "current_period_end": s.current_period_end,
                "created_at": s.created_at,
                "buyer": _buyer_of(by_id.get(s.telegram_user_id)),
                "telegram_user_id": s.telegram_user_id,
            }
            for s in subscriptions
        ],
        "people": [
            {
                "telegram_user_id": person.telegram_user_id,
                "title": person.title,
                "username": person.username or None,
                "first_seen_at": person.first_seen_at,
                "last_seen_at": person.last_seen_at,
                "blocked": person.blocked_at is not None,
            }
            for person in everyone
        ],
        "active_count": sum(1 for s in subscriptions if s.status == SubscriptionStatus.active),
    }


class BroadcastIn(BaseModel):
    """Which block to send, and to whom."""

    block_id: uuid.UUID
    #: "all" — everyone who ever wrote to the bot; "subscribers" — only
    #: people with a live subscription. The second exists because "новый
    #: выпуск для подписчиков" and "у нас скидка" are different messages to
    #: different rooms, and sending the first to the second room gives away
    #: what somebody is paying for.
    audience: Literal["all", "subscribers"] = "all"


#: Окно, в которое повторная рассылка того же блока считается случайной.
#: Достаточно длинное, чтобы покрыть «нажал ещё раз, потому что не понял,
#: сработало ли», и достаточно короткое, чтобы не мешать исправить опечатку
#: и отправить заново осознанно.
_BROADCAST_COOLDOWN = timedelta(minutes=10)


@router.post("/api/bots/{bot_id}/broadcast")
async def broadcast(
    bot_id: uuid.UUID,
    payload: BroadcastIn,
    bot: BotModel = Depends(get_owned_bot),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Send one block to everyone the bot knows.

    The landing page has always promised «рассылка» and the constructor had
    no way to send anything to anybody after the conversation that triggered
    it. It is cheap now only because the two hard parts already exist: a
    list of people, and a queue that resumes a chain at a given time.

    Queued rather than sent inline: a shop with two thousand subscribers
    would otherwise hold this request open through two thousand Telegram
    calls and hit the rate limit halfway, with no record of where it stopped.
    Each person becomes a scheduled step, so the sweep paces them and a
    failure retries only that one.
    """
    from app.services import scheduler

    block = (
        await db.execute(select(BotBlock).where(BotBlock.id == payload.block_id, BotBlock.bot_id == bot_id))
    ).scalar_one_or_none()
    if block is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Блок не найден")

    if bot.status != BotStatus.active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Бот не опубликован — рассылать пока некому и нечем.",
        )

    # Двойной клик, повторная отправка формы, вкладка, которую переоткрыли —
    # и каждый подписчик получает сообщение дважды. Рассылка необратима, её
    # нельзя «отменить после отправки», поэтому защита стоит до постановки в
    # очередь, а не после.
    recent = await db.execute(
        select(func.count(ScheduledStep.id)).where(
            ScheduledStep.bot_id == bot_id,
            ScheduledStep.block_id == block.id,
            ScheduledStep.reason == "broadcast",
            ScheduledStep.created_at > datetime.now(timezone.utc) - _BROADCAST_COOLDOWN,
        )
    )
    if recent.scalar_one():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"Эта рассылка уже отправлена — повтор возможен через "
                f"{int(_BROADCAST_COOLDOWN.total_seconds() // 60)} мин. "
                f"Так двойной клик не дублирует сообщение подписчикам."
            ),
        )

    query = select(BotSubscriber).where(
        BotSubscriber.bot_id == bot_id,
        # Someone who blocked the bot cannot be written to, and trying would
        # burn a retry on every sweep from now on.
        BotSubscriber.blocked_at.is_(None),
        # И тот, кто попросил не писать. Отписка — это не «заблокировал»:
        # человек остаётся покупателем и сохраняет доступы, он лишь не хочет
        # рассылки.
        BotSubscriber.unsubscribed_at.is_(None),
    )
    if payload.audience == "subscribers":
        query = query.where(
            BotSubscriber.telegram_user_id.in_(
                select(Subscription.telegram_user_id).where(
                    Subscription.bot_id == bot_id,
                    Subscription.status == SubscriptionStatus.active,
                )
            )
        )
    people = list((await db.execute(query)).scalars().all())

    for person in people:
        await scheduler.schedule(
            db,
            bot_id=bot_id,
            block_id=block.id,
            chat_id=person.chat_id,
            telegram_user_id=person.telegram_user_id,
            delay_seconds=0,
            reason="broadcast",
        )

    logger.info("Broadcast of block %s queued for %d people of bot %s", block.id, len(people), bot_id)
    return {"queued": len(people)}


def _buyer_of(subscriber: BotSubscriber | None) -> dict | None:
    """What the sales log shows about a person.

    Deliberately not the raw row: the panel needs a name and a way to reach
    them, and nothing else about a bot's customers belongs in a response the
    shop owner's browser holds.
    """
    if subscriber is None:
        return None
    return {
        "title": subscriber.title,
        "username": subscriber.username or None,
        "telegram_user_id": subscriber.telegram_user_id,
    }


async def _owned_order(bot_id: uuid.UUID, payment_id: uuid.UUID, db: AsyncSession) -> Payment:
    result = await db.execute(
        select(Payment).where(
            Payment.id == payment_id, Payment.bot_id == bot_id, Payment.kind == PaymentKind.order
        )
    )
    payment = result.scalar_one_or_none()
    if payment is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Заказ не найден")
    return payment


@router.post("/api/bots/{bot_id}/orders/{payment_id}/confirm")
async def confirm_order(
    bot_id: uuid.UUID,
    payment_id: uuid.UUID,
    _bot: BotModel = Depends(get_owned_bot),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """The owner confirms a payment nobody's API can vouch for — and the bot
    delivers on the spot, exactly as it would on a provider's callback."""
    payment = await _owned_order(bot_id, payment_id, db)
    # Settled here, handed over in the background — like every other path.
    # Delivering inline meant this request hung for as long as the dialogue
    # takes, which for a scenario with pauses is minutes.
    delivered = await payment_service.confirm_by_owner(db, payment, deliver=False)
    if delivered:
        payment_service.deliver_later(payment.id)
    return {"status": payment.status, "delivered": delivered}


@router.post("/api/bots/{bot_id}/orders/{payment_id}/reject")
async def reject_order(
    bot_id: uuid.UUID,
    payment_id: uuid.UUID,
    _bot: BotModel = Depends(get_owned_bot),
    db: AsyncSession = Depends(get_db),
) -> dict:
    payment = await _owned_order(bot_id, payment_id, db)
    await payment_service.reject_by_owner(db, payment)
    return {"status": payment.status}
