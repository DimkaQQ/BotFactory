"""Оплата запуска и продления звёздами Telegram — для клиентов, которым не
подходят карты и крипта (прежде всего из РФ).

Счёт выставляет мета-бот (см. `payment_service._platform_bot_token`), поэтому и
подтверждение приходит ему: сначала `pre_checkout_query` (ответить надо за 10
секунд), затем сообщение с `successful_payment`. Подписи тут нет — подлинность
гарантирует то, что Telegram доставил это в нашего бота; проверяем, что счёт наш,
ещё не оплачен и сумма совпадает.
"""

from __future__ import annotations

import logging
import uuid

from aiogram import Bot, F, Router
from aiogram.types import Message, PreCheckoutQuery
from sqlalchemy import select

from app.database import AsyncSessionLocal
from app.models.payment import Payment, PaymentKind, PaymentStatus
from app.services import payment_service
from app.services.payments import ProviderError
from app.services.payments.telegram_stars import settled

logger = logging.getLogger(__name__)

router = Router(name="platform-payments")

_PLATFORM_KINDS = (PaymentKind.publication, PaymentKind.renewal)


async def _platform_payment(db, raw_payload: str | None) -> Payment | None:
    try:
        payment_id = uuid.UUID(str(raw_payload or ""))
    except (ValueError, TypeError):
        return None
    return (
        await db.execute(
            select(Payment).where(
                Payment.id == payment_id, Payment.kind.in_(_PLATFORM_KINDS), Payment.provider == "stars"
            )
        )
    ).scalar_one_or_none()


@router.pre_checkout_query()
async def on_pre_checkout(query: PreCheckoutQuery, bot: Bot) -> None:
    ok, message = False, "Этот счёт больше не действителен"
    async with AsyncSessionLocal() as db:
        payment = await _platform_payment(db, query.invoice_payload)
        if payment is None:
            message = "Счёт не найден"
        elif payment.status == PaymentStatus.paid:
            message = "Этот счёт уже оплачен"
        elif query.total_amount != payment.amount_minor // 100:
            message = "Цена изменилась — открой оплату заново"
        else:
            ok = True
    await bot.answer_pre_checkout_query(query.id, ok=ok, error_message=None if ok else message)


@router.message(F.successful_payment)
async def on_successful_payment(message: Message, bot: Bot) -> None:
    paid = message.successful_payment
    if paid is None:
        return
    async with AsyncSessionLocal() as db:
        payment = await _platform_payment(db, paid.invoice_payload)
        if payment is None:
            logger.warning("Мета-бот: оплата звёздами за неизвестный счёт %r", paid.invoice_payload)
            return
        try:
            verdict = settled(
                charge_id=paid.telegram_payment_charge_id,
                total_amount=paid.total_amount,
                amount_minor=payment.amount_minor,
            )
        except ProviderError as exc:
            logger.error("Мета-бот: отклоняю оплату звёздами %s — %s", payment.id, exc)
            return
        await payment_service.apply_result(db, payment, verdict)
