"""Executes a client bot's dialogue graph.

Each bot has a `start_block_id` and every block has a `next_block_id` — the
default "what happens after this" edge, drawn as the plain arrow out of a
node in the visual flow editor. A "buttons" block can *additionally* carry
a `target_block_id` on individual buttons (content["buttons"][i]) — the
branch arrows dragged from a specific button to another node. On /start,
the dispatcher walks the chain from start_block_id, sending each block with
a short "typing…" pause in between, until it runs off the end (next_block_id
is null) *or* reaches a buttons block that actually has at least one branch
configured — at that point it stops and waits for the tap. A buttons block
with no branches configured behaves exactly like every other block (sent,
then straight through to next_block_id) — that's what makes this backward
compatible with every bot built before branching existed (see migration
0003, which backfills next_block_id from the old order_index sequence).

A "payment" block halts the walk the same way: it sends a checkout link
and stops, and the chain resumes from its next_block_id only once the
payment provider confirms the money (payment_service.resume_after_payment).

Three kinds of update besides /start and a button tap end up here, all of
them about money:

* «Я оплатил» — the buyer nudging a payment along. Where the provider has an
  API, that re-reads the payment; where it hasn't, the claim goes to the shop
  owner, who confirms or rejects it from a message of their own.
* `pre_checkout_query` / `successful_payment` — Telegram Stars. Stars never
  touch our payment webhook: Telegram delivers the outcome as ordinary
  updates on the selling bot's own webhook, which is also what vouches for
  them.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import re
import uuid

from aiogram import Bot
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.bot import Bot as BotModel
from app.models.bot_block import BlockType, BotBlock
from app.services import scheduler, subscribers

logger = logging.getLogger(__name__)

# Blocks are sent with a short "typing…" pause in between instead of all at
# once, so a multi-block reply reads like a conversation rather than a wall
# of text dumped in a single instant.
_TYPING_DELAY_MIN = 0.5
_TYPING_DELAY_MAX = 1.8
_CHARS_PER_SECOND = 45

# A visual graph lets someone wire a block's "next" straight back to an
# earlier block — a deliberate loop is a legitimate pattern (repeat a
# question, etc.) if a buttons block breaks it up, but a loop of *plain*
# blocks with no branch point would otherwise hang this webhook request
# forever. This is the circuit breaker.
_MAX_CHAIN_STEPS = 50

_CALLBACK_PREFIX = "b"
# Money-related taps, kept apart from the graph's own "b:<block>:<index>".
_PAY_CHECK = "paychk"  # buyer: "я оплатил"
_PAY_OK = "payok"  # owner: confirm a claimed payment
_PAY_NO = "payno"  # owner: reject it
_SELF_SETTLING = {"stars", "test"}


async def _pause(db: AsyncSession, seconds: float) -> None:
    """Wait, without sitting on a database connection while doing it.

    A dialogue is paced deliberately — typing delays between blocks, and a
    "Пауза" block that can hold for fifteen seconds — and the session keeps
    its connection checked out for as long as a transaction is open. Twelve
    simultaneous conversations therefore held twelve of the fifteen
    connections the deployment has, doing nothing, and the constructor's own
    API queued behind them. Ending the transaction first hands the
    connection back; the next query takes a fresh one.

    Committed rather than rolled back: the sessionmaker sets
    `expire_on_commit=False`, so the blocks the walk is holding stay usable,
    while a rollback would expire them and the very next `block.content`
    read would be lazy IO outside a greenlet.
    """
    await db.commit()
    await asyncio.sleep(seconds)


def _typing_delay(text: str) -> float:
    seconds = len(text) / _CHARS_PER_SECOND
    return max(_TYPING_DELAY_MIN, min(seconds, _TYPING_DELAY_MAX))


def _money(payment) -> str:
    """"990 RUB", "990.50 RUB", "250 ⭐".

    Integer division used to build this, which turned a 990.50 ₽ product into
    a button reading "Оплатить 990 RUB" while the card was charged 990.50 —
    the one number in the whole dialogue the buyer is entitled to trust.
    """
    whole, kopecks = divmod(payment.amount_minor, 100)
    amount = str(whole) if kopecks == 0 else f"{whole}.{kopecks:02d}"
    return f"{amount} ⭐" if payment.currency == "XTR" else f"{amount} {payment.currency}"


_URL_SCHEME_RE = re.compile(r"^[a-zA-Z][a-zA-Z0-9+.-]*://")


def _is_url_button(button: dict) -> bool:
    return button.get("action_type") == "url" and bool((button.get("action_value") or "").strip())


def _button_has_branches(content: dict) -> bool:
    """Whether this block is a real decision point — one the dialogue can
    actually continue from.

    A URL button opens a link; Telegram sends us nothing when it is tapped,
    so it carries no callback_data and can never advance the walk. Counting
    one as a branch stopped the chain at a block nothing could ever move it
    past, and the node it was wired to became unreachable — while the canvas
    happily drew the arrow.
    """
    return any(
        (button.get("target_block_id") or "").strip() and not _is_url_button(button)
        for button in content.get("buttons") or []
    )


def _build_keyboard(block_id: uuid.UUID, content: dict) -> InlineKeyboardMarkup | None:
    buttons = content.get("buttons") or []
    rows = []
    for index, button in enumerate(buttons):
        label = (button.get("label") or "").strip()
        action_value = (button.get("action_value") or "").strip()

        # A fully blank row (added via "+ Добавить кнопку" and never filled
        # in) used to still build a "..." button whose callback_data could
        # end up empty — Telegram then rejects the whole sendMessage call,
        # which our per-block try/except swallows, so the *entire* block
        # (caption text included) would silently vanish. Skip blank rows
        # instead of ever building an invalid button from them.
        if not label and not action_value and not (button.get("target_block_id") or "").strip():
            continue
        label = label or "…"

        if _is_url_button(button):
            url = action_value
            # The single most common way a URL button breaks a block: the
            # user typed "example.com" instead of "https://example.com".
            # Telegram rejects a schemeless URL outright — assume https
            # rather than let one typo take the whole message down.
            if not _URL_SCHEME_RE.match(url):
                url = f"https://{url}"
            rows.append([InlineKeyboardButton(text=label, url=url)])
        else:
            # Every non-URL button's callback_data is just a pointer back to
            # "which button on which block" — process_update looks up the
            # actual target_block_id fresh from the DB when it's tapped,
            # rather than baking a target into the callback_data itself, so
            # editing a button's connection later doesn't require anything
            # already sent to the user to change.
            rows.append([InlineKeyboardButton(text=label, callback_data=f"{_CALLBACK_PREFIX}:{block_id.hex}:{index}")])

    return InlineKeyboardMarkup(inline_keyboard=rows) if rows else None


async def _send_payment_block(
    bot: Bot, chat_id: int, block: BotBlock, bot_id: uuid.UUID, db: AsyncSession, telegram_user_id: int | None
) -> bool:
    """Send the invoice message for a payment block.

    Always returns True — the chain stops here no matter what happens.

    What follows a payment block is the thing being sold, so continuing past
    it means handing that over. That has to hold for the failure path too: an
    unconfigured provider, a blank price or a provider outage must leave the
    buyer without the goods, not without the paywall. The customer is told
    something went wrong instead of being left staring at silence.
    """
    from app.services import payment_service  # local import: avoids a cycle

    content = block.content or {}
    result = await db.execute(select(BotModel).where(BotModel.id == bot_id))
    bot_row = result.scalar_one_or_none()
    if bot_row is None:
        return True

    text = (content.get("text") or content.get("title") or "").strip()
    try:
        payment, url = await payment_service.create_order_payment(
            db, bot=bot_row, block=block, chat_id=chat_id, telegram_user_id=telegram_user_id
        )
    except Exception:
        logger.exception("Could not create a payment for block %s (bot %s)", block.id, bot_id)
        with contextlib.suppress(Exception):
            await bot.send_message(
                chat_id,
                "Не получилось открыть оплату — попробуй ещё раз чуть позже. "
                "Если не заработает, напиши продавцу.",
            )
        return True

    label = (content.get("button_label") or "").strip() or f"Оплатить {_money(payment)}"
    rows = [[InlineKeyboardButton(text=label[:64], url=url)]]

    # For most providers the buyer may need to nudge a payment along, but not
    # these two: the Stars sheet reports its own outcome the moment it closes,
    # and the test provider's checkout page settles on open. Offering "Я
    # оплатил" there would only invite a tap that can do nothing.
    if payment.provider not in _SELF_SETTLING:
        rows.append([InlineKeyboardButton(text="Я оплатил", callback_data=f"{_PAY_CHECK}:{payment.id.hex}")])

    await bot.send_message(chat_id, text or "Оплата", reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))
    return True


async def _handle_payment_callback(
    bot: Bot, callback_query: dict, bot_id: uuid.UUID, db: AsyncSession, action: str, payment_hex: str
) -> None:
    """«Я оплатил» from a buyer, or «Подтвердить»/«Отклонить» from the owner."""
    from app.models.payment import Payment, PaymentKind, PaymentStatus
    from app.services import payment_service
    from app.services.payments import ProviderError, get_provider

    chat_id = ((callback_query.get("message") or {}).get("chat") or {}).get("id")
    try:
        payment_id = uuid.UUID(hex=payment_hex)
    except ValueError:
        return

    result = await db.execute(
        select(Payment).where(
            Payment.id == payment_id, Payment.bot_id == bot_id, Payment.kind == PaymentKind.order
        )
    )
    payment = result.scalar_one_or_none()
    if payment is None or chat_id is None:
        return

    if action in (_PAY_OK, _PAY_NO):
        # Owner-only: these buttons are sent to the owner's private chat, and
        # this check is what stops the callback_data being replayed from the
        # buyer's side.
        if not await _is_owner(db, bot_id, (callback_query.get("from") or {}).get("id")):
            return
        if action == _PAY_OK:
            await payment_service.confirm_by_owner(db, payment)
            await bot.send_message(chat_id, f"Заказ №{payment.invoice_no} подтверждён — товар отправлен покупателю.")
        else:
            await payment_service.reject_by_owner(db, payment)
            await bot.send_message(chat_id, f"Заказ №{payment.invoice_no} отклонён.")
        return

    # «Я оплатил» belongs to the person who was offered the payment. The id is
    # unguessable, but callback_data is visible to whoever holds the message,
    # and a claim from anyone else would ping the shop owner about an order
    # that is not theirs.
    if payment.chat_id is not None and chat_id != payment.chat_id:
        return

    if payment.status == PaymentStatus.paid:
        await bot.send_message(chat_id, "Эта покупка уже оплачена ✅")
        return

    provider = get_provider(payment.provider)
    if not provider.supports_status_check:
        # Nothing to ask: the shop owner is the only one who can see whether
        # the money arrived.
        await payment_service.claim_payment(db, payment)
        await bot.send_message(chat_id, "Спасибо! Передали продавцу — как только он подтвердит оплату, всё придёт сюда.")
        return

    try:
        status_now = await payment_service.check_and_settle(db, payment)
    except ProviderError as exc:
        logger.warning("Status check failed for payment %s: %s", payment.id, exc)
        await bot.send_message(chat_id, "Не получилось проверить оплату прямо сейчас. Попробуй ещё раз через минуту.")
        return

    if status_now == PaymentStatus.paid:
        return  # resume_after_payment already said everything and delivered
    if status_now == PaymentStatus.failed:
        await bot.send_message(chat_id, "Платёж не прошёл. Попробуй оплатить ещё раз.")
    else:
        await bot.send_message(chat_id, "Оплата пока не дошла. Если ты только что заплатил — подожди минуту и нажми ещё раз.")


async def _is_owner(db: AsyncSession, bot_id: uuid.UUID, telegram_user_id: int | None) -> bool:
    from app.models.client import Client

    if telegram_user_id is None:
        return False
    result = await db.execute(
        select(Client.telegram_user_id).join(BotModel, BotModel.client_id == Client.id).where(BotModel.id == bot_id)
    )
    owner_id = result.scalar_one_or_none()
    return owner_id is not None and int(owner_id) == int(telegram_user_id)


async def _send_block(bot: Bot, chat_id: int, block: BotBlock) -> None:
    content = block.content or {}

    if block.block_type == BlockType.poll:
        question = (content.get("question") or "").strip()
        options = [opt.strip() for opt in content.get("options") or [] if opt and opt.strip()]
        if not question or len(options) < 2:
            # Telegram refuses a poll with fewer than two options. Rather than
            # letting the block vanish from the conversation with no trace,
            # say so — the shop owner testing their own bot is the one who
            # needs to find out.
            logger.warning("Bot: poll block %s needs a question and at least two options — skipped", block.id)
            return
        await bot.send_poll(chat_id, question=question, options=options, is_anonymous=content.get("anonymous", True))
        return

    # Whitespace is not content: a block holding only spaces used to pass the
    # emptiness check and send a bubble containing "   ".
    text = (content.get("text") or "").strip()
    media_file_id = content.get("media_file_id")
    media_type = content.get("media_type")
    keyboard = _build_keyboard(block.id, content) if block.block_type == BlockType.buttons else None

    if not text and not media_file_id and not keyboard:
        return

    if media_file_id:
        caption = text or None
        if media_type == "photo":
            await bot.send_photo(chat_id, media_file_id, caption=caption, reply_markup=keyboard)
        elif media_type == "video":
            await bot.send_video(chat_id, media_file_id, caption=caption, reply_markup=keyboard)
        else:
            await bot.send_document(chat_id, media_file_id, caption=caption, reply_markup=keyboard)
    else:
        await bot.send_message(chat_id, text or "…", reply_markup=keyboard)


async def walk_chain(
    bot: Bot,
    chat_id: int,
    start_block_id: uuid.UUID,
    bot_id: uuid.UUID,
    db: AsyncSession,
    telegram_user_id: int | None = None,
    subscription_id: uuid.UUID | None = None,
) -> None:
    """Send `start_block_id` and keep following next_block_id, pausing for
    typing/delay between steps, until the chain ends or hits a branch
    point (a buttons block with at least one connected button).

    A long "Пауза" ends the walk too — the rest of the chain is handed to
    the scheduler and resumes from here, in a later process, whenever the
    pause is up. `subscription_id` rides along so that everything queued
    downstream stays attached to the subscription that started it and can
    be withdrawn in one go when it lapses."""

    next_id: uuid.UUID | None = start_block_id
    visited: set[uuid.UUID] = set()
    steps = 0
    first = True

    while next_id is not None:
        steps += 1
        if steps > _MAX_CHAIN_STEPS:
            logger.warning("Bot %s dialogue chain exceeded %d steps — stopping.", bot_id, _MAX_CHAIN_STEPS)
            return
        if next_id in visited:
            # A revisit means a cycle (a real, deliberate pattern in a
            # visual flow graph) with no branch point to break it up — each
            # step in this loop is paced with a real typing delay, so
            # waiting for _MAX_CHAIN_STEPS to catch this could hold a
            # webhook request open for tens of seconds. Catch it the
            # instant it's actually detected instead.
            logger.warning("Bot %s dialogue hit a loop at block %s — stopping.", bot_id, next_id)
            return
        visited.add(next_id)

        result = await db.execute(select(BotBlock).where(BotBlock.id == next_id, BotBlock.bot_id == bot_id))
        block = result.scalar_one_or_none()
        if block is None:
            return  # dangling/removed target — nothing left to do

        try:
            if block.block_type == BlockType.payment:
                if not first:
                    await bot.send_chat_action(chat_id, "typing")
                    await _pause(db, _TYPING_DELAY_MIN)
                if await _send_payment_block(bot, chat_id, block, bot_id, db, telegram_user_id):
                    # Paid delivery waits for the provider's callback — see
                    # payment_service.resume_after_payment.
                    return
            elif block.block_type == BlockType.delay:
                # A bare pause — no message of its own, just stretches the
                # gap before the next block.
                #
                # Short pauses are simply waited out here: they are pacing,
                # and a round trip to the scheduler would cost more than the
                # pause itself. Anything longer hands the rest of the chain
                # to the scheduler and ends this walk — the webhook request
                # is held open for an inline pause, and neither Telegram nor
                # a reverse proxy will wait a week. That single branch is
                # what turns "Пауза" from a typing-rhythm effect into the
                # thing a subscription needs: the next video, next Tuesday.
                seconds = max(0.0, float((block.content or {}).get("seconds", 2) or 0))
                if seconds > scheduler.INLINE_PAUSE_SECONDS:
                    await scheduler.schedule(
                        db,
                        bot_id=bot_id,
                        block_id=block.next_block_id,
                        chat_id=chat_id,
                        telegram_user_id=telegram_user_id,
                        delay_seconds=seconds,
                        reason="delay",
                        subscription_id=subscription_id,
                    )
                    return
                await _pause(db, seconds)
            else:
                if not first:
                    text = (block.content or {}).get("text") or ""
                    await bot.send_chat_action(chat_id, "typing")
                    await _pause(db, _typing_delay(text))
                await _send_block(bot, chat_id, block)
        except Exception:
            logger.exception("Failed to send block %s for bot %s", block.id, bot_id)

        first = False

        # A buttons block with any branch configured is a real decision
        # point — stop and wait for the tap instead of barrelling through
        # to next_block_id regardless of what the user picks. Without any
        # branch configured it's just another block in the chain (matches
        # every bot built before branching existed).
        if block.block_type == BlockType.buttons and _button_has_branches(block.content or {}):
            return

        next_id = block.next_block_id


async def _handle_callback_query(bot: Bot, callback_query: dict, bot_id: uuid.UUID, db: AsyncSession) -> None:
    # Phase-1-style buttons (no branch configured) still exist and are
    # valid — the tap just has nowhere to go, so acknowledging it (stopping
    # Telegram's loading spinner) is all there is to do.
    try:
        await bot.answer_callback_query(callback_query["id"])
    except Exception:
        logger.exception("Failed to answer callback query for bot %s", bot_id)

    data = callback_query.get("data") or ""
    parts = data.split(":")

    if len(parts) == 2 and parts[0] in (_PAY_CHECK, _PAY_OK, _PAY_NO):
        try:
            await _handle_payment_callback(bot, callback_query, bot_id, db, parts[0], parts[1])
        except Exception:
            logger.exception("Payment callback %s failed for bot %s", data, bot_id)
        return

    if len(parts) != 3 or parts[0] != _CALLBACK_PREFIX:
        return
    _, block_hex, index_str = parts
    try:
        source_block_id = uuid.UUID(hex=block_hex)
        index = int(index_str)
    except ValueError:
        return

    chat = (callback_query.get("message") or {}).get("chat") or {}
    chat_id = chat.get("id")
    if chat_id is None:
        return

    result = await db.execute(select(BotBlock).where(BotBlock.id == source_block_id, BotBlock.bot_id == bot_id))
    source_block = result.scalar_one_or_none()
    if source_block is None:
        return
    buttons = (source_block.content or {}).get("buttons") or []
    if index >= len(buttons):
        return
    target_raw = (buttons[index].get("target_block_id") or "").strip()
    if not target_raw:
        return  # this particular button isn't wired to anything

    try:
        target_id = uuid.UUID(target_raw)
    except ValueError:
        return

    tapped_by = (callback_query.get("from") or {}).get("id")
    await walk_chain(bot, chat_id, target_id, bot_id, db, telegram_user_id=tapped_by)


async def _handle_pre_checkout(bot: Bot, query: dict, bot_id: uuid.UUID, db: AsyncSession) -> None:
    """Telegram's last check before charging Stars: answer within 10 seconds
    or the payment is cancelled. We approve only an order that is ours, still
    unpaid, and for the amount we asked — this is the last point at which a
    stale invoice link can be turned away rather than refunded."""
    from app.models.payment import Payment, PaymentKind, PaymentStatus

    query_id = query.get("id")
    if not query_id:
        return

    ok, message = False, "Этот счёт больше не действителен"
    try:
        payment_id = uuid.UUID(str(query.get("invoice_payload") or ""))
        result = await db.execute(
            select(Payment).where(
                Payment.id == payment_id, Payment.bot_id == bot_id, Payment.kind == PaymentKind.order
            )
        )
        payment = result.scalar_one_or_none()
        if payment is None:
            message = "Заказ не найден"
        elif payment.status == PaymentStatus.paid:
            message = "Этот заказ уже оплачен"
        elif int(query.get("total_amount") or 0) != payment.amount_minor // 100:
            message = "Цена изменилась — открой оплату заново"
        else:
            ok = True
    except (ValueError, TypeError):
        message = "Заказ не найден"

    try:
        await bot.answer_pre_checkout_query(query_id, ok=ok, error_message=None if ok else message)
    except Exception:
        logger.exception("Failed to answer pre_checkout_query for bot %s", bot_id)


async def _handle_successful_payment(bot: Bot, message: dict, bot_id: uuid.UUID, db: AsyncSession) -> None:
    """Stars have landed. Telegram delivered this on the bot's own webhook,
    which is what vouches for it — there is no signature and no API to
    re-read, so the check that remains is that the order is ours and the
    amount matches."""
    from app.models.payment import Payment, PaymentKind
    from app.services import payment_service
    from app.services.payments import ProviderError
    from app.services.payments.telegram_stars import settled

    payload = message["successful_payment"]
    try:
        payment_id = uuid.UUID(str(payload.get("invoice_payload") or ""))
    except (ValueError, TypeError):
        return

    result = await db.execute(
        select(Payment).where(
            Payment.id == payment_id, Payment.bot_id == bot_id, Payment.kind == PaymentKind.order
        )
    )
    payment = result.scalar_one_or_none()
    if payment is None:
        logger.warning("Bot %s: successful_payment for unknown order %s", bot_id, payment_id)
        return

    try:
        verdict = settled(
            charge_id=str(payload.get("telegram_payment_charge_id") or ""),
            total_amount=int(payload.get("total_amount") or 0),
            amount_minor=payment.amount_minor,
            # A monthly Stars renewal arrives here: same invoice payload,
            # thirty days later, with nobody having tapped anything. These
            # flags are how it is told apart from the first charge.
            is_recurring=bool(payload.get("is_recurring")),
            is_first_recurring=bool(payload.get("is_first_recurring")),
            subscription_expiration=payload.get("subscription_expiration_date"),
        )
    except ProviderError as exc:
        logger.error("Bot %s: refusing Stars payment %s — %s", bot_id, payment_id, exc)
        return

    if payload.get("is_recurring") and not payload.get("is_first_recurring"):
        # A renewal, not a purchase. `apply_result` would find the payment
        # already `paid` and do nothing at all — including not extending the
        # period, which is the only thing this update exists to do.
        from app.services import subscription_service

        await payment_service._remember(db, payment, verdict)
        subscription = await subscription_service.start_or_extend(db, payment)
        if subscription is None:
            logger.warning("Bot %s: Stars renewal for payment %s has no subscription", bot_id, payment_id)
        else:
            await _tell_them_renewed(bot, subscription)
        return

    await payment_service.apply_result(db, payment, verdict)


async def _tell_them_renewed(bot: Bot, subscription) -> None:
    """A charge nobody initiated should still be announced — silence after
    money leaves an account is how a subscription becomes a complaint."""
    until = subscription.current_period_end.strftime("%d.%m.%Y")
    with contextlib.suppress(Exception):
        await bot.send_message(
            subscription.chat_id,
            f"🔁 Подписка «{subscription.title}» продлена — доступ открыт до {until}.",
        )


def _sender_and_chat(update: dict) -> tuple[dict | None, int | None]:
    """The person and the chat behind any of the update shapes we handle."""
    for key in ("message", "callback_query", "pre_checkout_query", "poll_answer"):
        payload = update.get(key)
        if not payload:
            continue
        user = payload.get("from") or payload.get("user")
        chat = payload.get("chat") or (payload.get("message") or {}).get("chat") or {}
        chat_id = chat.get("id")
        # A pre-checkout query carries no chat of its own; in a private
        # conversation the user id is the chat id, which is the only case
        # a bot's own updates can be in.
        if chat_id is None and user:
            chat_id = user.get("id")
        return user, chat_id
    return None, None


async def process_update(bot: Bot, update: dict, bot_id: uuid.UUID, db: AsyncSession) -> None:
    # Before anything is answered: record who this is. Every later capability
    # — naming the buyer in the sales log, sending next week's video, kicking
    # a lapsed subscriber out of a group — needs a person to attach to, and
    # the update is the only place that information ever appears.
    user, sender_chat_id = _sender_and_chat(update)
    if user is not None:
        await subscribers.remember(
            db,
            bot_id=bot_id,
            telegram_user_id=user.get("id"),
            chat_id=sender_chat_id,
            user=user,
        )

    callback_query = update.get("callback_query")
    if callback_query:
        await _handle_callback_query(bot, callback_query, bot_id, db)
        return

    pre_checkout = update.get("pre_checkout_query")
    if pre_checkout:
        await _handle_pre_checkout(bot, pre_checkout, bot_id, db)
        return

    message = update.get("message")
    if not message:
        return

    if message.get("successful_payment"):
        await _handle_successful_payment(bot, message, bot_id, db)
        return

    chat_id = message.get("chat", {}).get("id")
    text = message.get("text", "") or ""
    sender_id = (message.get("from") or {}).get("id")
    if chat_id is None:
        return

    result = await db.execute(select(BotModel.start_block_id).where(BotModel.id == bot_id))
    start_block_id = result.scalar_one_or_none()

    if not text.startswith("/start"):
        # These bots answer taps, not typing. Saying nothing at all reads as
        # broken to someone who just wrote a question into the chat, so point
        # them back at the buttons instead of leaving them guessing.
        if start_block_id is not None:
            await bot.send_message(
                chat_id,
                "Я отвечаю на кнопки под сообщениями 🙂\nНапиши /start, чтобы начать сначала.",
            )
        return

    if start_block_id is None:
        await bot.send_message(chat_id, "Этот бот пока пуст 🤷")
        return

    await walk_chain(bot, chat_id, start_block_id, bot_id, db, telegram_user_id=sender_id)
