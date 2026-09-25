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
from datetime import datetime, timezone

from aiogram import Bot
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.bot import Bot as BotModel
from app.models.bot_block import BlockType, BotBlock
from app.services import dates
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
    """The amount as the buyer reads it — the one number in the whole
    dialogue they are entitled to trust. Shared with the owner's
    notifications so the two can never disagree."""
    from app.services.payments import money

    return money(payment.amount_minor, payment.currency)


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
    from app.services import payment_service, subscription_service  # local import: avoids a cycle

    content = block.content or {}
    result = await db.execute(select(BotModel).where(BotModel.id == bot_id))
    bot_row = result.scalar_one_or_none()
    if bot_row is None:
        return True

    # Already bought, and still entitled: hand it over instead of selling it
    # again. A guide sold by the volume is the obvious case — a returning
    # buyer pressing /start used to be offered том 1 a second time, with
    # nothing anywhere to stop them paying for it — and a live subscriber
    # coming back mid-period is the same question with the same answer.
    #
    # But only for things that are bought once. This used to apply to every
    # payment block, and that quietly broke every repeatable sale there is:
    # a coach selling a second consultation to the same client got no money
    # and the client got the session, because the chain falls through into
    # the delivery block. Anything sold again and again — a consultation, a
    # donation, a re-order — says so on the block (`repeatable`), and then
    # a returning buyer is simply sold to again.
    one_off = not content.get("repeatable")
    if (
        one_off
        and telegram_user_id is not None
        and await subscription_service.has_paid_for(db, bot_id, telegram_user_id, block.id)
    ):
        what = (content.get("title") or "").strip()
        with contextlib.suppress(Exception):
            await bot.send_message(
                chat_id,
                f"У тебя уже есть доступ — «{what}» оплачено ✅" if what else "Это уже оплачено ✅",
            )
        # Not `True`: the chain continues into what was bought, which is
        # exactly what "уже оплачено" has to mean.
        return False

    text = (content.get("text") or content.get("title") or "").strip()
    try:
        payment, url = await payment_service.create_order_payment(
            db, bot=bot_row, block=block, chat_id=chat_id, telegram_user_id=telegram_user_id
        )
    except Exception as exc:
        logger.exception("Could not create a payment for block %s (bot %s)", block.id, bot_id)
        with contextlib.suppress(Exception):
            await bot.send_message(
                chat_id,
                "Не получилось открыть оплату — попробуй ещё раз чуть позже. "
                "Если не заработает, напиши продавцу.",
            )
        # И — обязательно — продавцу. Это единственная ветка в файле, где
        # покупатель уходит без товара, а владелец не узнавал ничего:
        # ошибка падала в лог, покупателю приносили извинения от его имени,
        # и он выяснял всё от учеников через неделю. Сюда попадает всё, что
        # ломает продажу: пустые ключи кассы, упавший шлюз, цена «0».
        await _tell_owner(
            db, bot_id,
            f"🔴 Покупатель нажал «{(content.get('title') or 'Оплата').strip()}», "
            f"но счёт не выставился — продажа не состоялась.\n\n"
            f"Причина: {_human_reason(exc)}\n\n"
            f"Проверь настройки кассы и цену в блоке оплаты.",
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


async def _deliver_group_invite(
    bot: Bot,
    chat_id: int,
    block: BotBlock,
    bot_id: uuid.UUID,
    db: AsyncSession,
    telegram_user_id: int | None,
) -> bool:
    """Let this one buyer into the private chat the block points at.

    Returns True when it handled the block entirely. The invite is minted per
    buyer and single-use, which is the difference between selling access and
    giving away a link that works forever for anyone it is forwarded to.
    """
    from app.services import group_access, subscription_service

    content = block.content or {}
    chat_ref = group_access.chat_ref(content)
    if not chat_ref:
        return False

    subscription = None
    if telegram_user_id is not None:
        live = await subscription_service.active_for(db, bot_id, telegram_user_id)
        # Attach the invite to the subscription this delivery belongs to, so
        # expiry knows which chat to remove them from.
        subscription = live[-1] if live else None

    try:
        invite = await group_access.grant(
            db,
            bot_id=bot_id,
            chat_ref_raw=chat_ref,
            subscription=subscription,
            valid_days=subscription.period_days if subscription is not None else None,
        )
    except group_access.GroupAccessError as exc:
        # The buyer paid. They must not be left with silence, and the owner
        # must be told in words they can act on rather than a log line.
        logger.error("Bot %s: could not grant group access — %s", bot_id, exc)
        await bot.send_message(
            chat_id,
            "Оплата прошла, но выдать доступ в группу прямо сейчас не получилось — продавец уже знает и всё пришлёт.",
        )
        await _tell_owner(db, bot_id, f"⚠️ Бот не смог выдать доступ в группу.\n{exc}")
        return True

    text = (content.get("text") or "").strip()
    await bot.send_message(
        chat_id,
        f"{text}\n\n{invite}".strip() if text else invite,
    )
    return True


def _human_reason(exc: Exception) -> str:
    """Причина отказа словами, которые владелец может прочитать.

    `ProviderError` мы формулируем сами и по-русски («ЮKassa: не заполнены
    shopId или секретный ключ») — её видно как есть. Всё прочее — это сбой
    на чужой стороне или наш, и владельцу от его текста пользы нет.
    """
    from app.services.payments import ProviderError

    if isinstance(exc, ProviderError):
        return str(exc)
    return "касса не ответила или вернула ошибку"


async def _tell_owner(db: AsyncSession, bot_id: uuid.UUID, message: str) -> None:
    from app.services import payment_service

    with contextlib.suppress(Exception):
        found = await payment_service._owner_of(db, bot_id)
        if found is not None:
            owner_id, instance = found
            await instance.send_message(owner_id, message)


async def _remember_poll(db: AsyncSession | None, block: BotBlock, sent) -> None:
    """Tie Telegram's poll id to the block that asked.

    An incoming `poll_answer` names Telegram's poll and the person, and
    nothing of ours — so without this the answer cannot be attributed to a
    block, a question, or a bot.
    """
    from app.models.poll_send import PollSend

    poll = getattr(sent, "poll", None)
    poll_id = getattr(poll, "id", None)
    if db is None or not poll_id:
        return
    # A row per send, not a field on the block. Telegram mints a new poll id
    # for every chat, so one field held only the most recent one — and every
    # other subscriber's answer was dropped on the floor, silently, in a
    # block the constructor sells as a way to find out what they want.
    with contextlib.suppress(Exception):
        db.add(
            PollSend(
                id=uuid.uuid4(),
                bot_id=block.bot_id,
                block_id=block.id,
                telegram_poll_id=str(poll_id),
                chat_id=getattr(getattr(sent, "chat", None), "id", None),
            )
        )
        await db.commit()


async def _handle_poll_answer(answer: dict, bot_id: uuid.UUID, db: AsyncSession) -> None:
    """Record what somebody picked.

    Upserted on (block, person): a Telegram poll answer can be changed, and
    the later choice replaces the earlier one instead of being counted twice.
    """
    from sqlalchemy.dialects.postgresql import insert as pg_insert

    from app.models.poll_answer import PollAnswer

    poll_id = str(answer.get("poll_id") or "")
    user_id = (answer.get("user") or {}).get("id")
    if not poll_id or user_id is None:
        return

    from app.models.poll_send import PollSend

    result = await db.execute(
        select(BotBlock)
        .join(PollSend, PollSend.block_id == BotBlock.id)
        .where(PollSend.telegram_poll_id == poll_id, PollSend.bot_id == bot_id)
    )
    block = result.scalar_one_or_none()
    if block is None:
        return

    options = [int(index) for index in (answer.get("option_ids") or [])]
    with contextlib.suppress(Exception):
        await db.execute(
            pg_insert(PollAnswer)
            .values(
                id=uuid.uuid4(),
                bot_id=bot_id,
                block_id=block.id,
                telegram_user_id=user_id,
                telegram_poll_id=poll_id,
                option_ids=options,
            )
            .on_conflict_do_update(
                constraint="uq_poll_answer",
                set_={"option_ids": options, "updated_at": datetime.now(timezone.utc)},
            )
        )
        await db.commit()


async def _send_block(
    bot: Bot, chat_id: int, block: BotBlock, db: AsyncSession | None = None, footer: str = ""
) -> None:
    """`footer` дописывается к тексту блока. Нужен рассылке: подпись «чтобы
    не получать — /stop» обязана быть в самом сообщении, иначе человек, до
    которого мы дотянулись сами, не знает, как это прекратить, и блокирует
    бота вместе с купленным доступом."""
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
        # Not anonymous by default any more: an anonymous poll's answers
        # carry no user, so Telegram sends no `poll_answer` at all and the
        # owner gets a vote count they cannot act on. The block can still ask
        # for anonymity explicitly — it just no longer does so by accident.
        sent = await bot.send_poll(
            chat_id, question=question, options=options, is_anonymous=bool(content.get("anonymous", False))
        )
        await _remember_poll(db, block, sent)
        return

    # Whitespace is not content: a block holding only spaces used to pass the
    # emptiness check and send a bubble containing "   ".
    text = (content.get("text") or "").strip()
    if footer:
        text = f"{text}\n\n{footer}" if text else footer
    media_file_id = content.get("media_file_id")
    media_type = content.get("media_type")
    keyboard = _build_keyboard(block.id, content) if block.block_type == BlockType.buttons else None

    if not text and not media_file_id and not keyboard:
        return

    if media_file_id:
        # A caption is capped at 1024, a quarter of a message — and the block
        # that runs long is «Выдача», which is exactly the one that also
        # carries the file. The whole call used to be refused, so the buyer
        # paid and got nothing. What fits stays with the file; the rest
        # follows as ordinary messages, which is also the order it reads in.
        caption, overflow = _caption_and_rest(text)
        if media_type == "photo":
            await bot.send_photo(chat_id, media_file_id, caption=caption, reply_markup=None if overflow else keyboard)
        elif media_type == "audio":
            await bot.send_audio(chat_id, media_file_id, caption=caption, reply_markup=None if overflow else keyboard)
        elif media_type == "video":
            await bot.send_video(chat_id, media_file_id, caption=caption, reply_markup=None if overflow else keyboard)
        else:
            await bot.send_document(chat_id, media_file_id, caption=caption, reply_markup=None if overflow else keyboard)
        for index, piece in enumerate(overflow):
            # The keyboard belongs on the last thing sent, wherever that is.
            last = index == len(overflow) - 1
            await bot.send_message(chat_id, piece, reply_markup=keyboard if last else None)
    else:
        # Split rather than refused. Telegram rejects anything over 4096
        # characters outright, and the block that most often runs long is
        # «Выдача» — so the shop's own guide came out as an error instead of
        # a message, after the buyer had already paid. The keyboard rides on
        # the last piece, where it belongs.
        chunks = _split_for_telegram(text or "…")
        for piece in chunks[:-1]:
            await bot.send_message(chat_id, piece)
        await bot.send_message(chat_id, chunks[-1], reply_markup=keyboard)


#: Telegram's own caps. A message is 4096 characters; a caption attached to
#: a photo or a document is a quarter of that, and going over means the send
#: is refused outright rather than truncated.
_TELEGRAM_TEXT_LIMIT = 4096
_TELEGRAM_CAPTION_LIMIT = 1024


def _caption_and_rest(text: str) -> tuple[str | None, list[str]]:
    """What can ride with the file, and what has to follow it.

    Cut on a paragraph or line break where there is one in the last fifth of
    the caption, so the split lands between thoughts rather than mid-sentence
    — a guide that breaks after "Шаг 3." reads as intended, one that breaks
    after "Шаг" reads as damage.
    """
    text = (text or "").strip()
    if not text:
        return None, []
    if len(text) <= _TELEGRAM_CAPTION_LIMIT:
        return text, []

    window = text[:_TELEGRAM_CAPTION_LIMIT]
    cut = max(window.rfind("\n\n"), window.rfind("\n"))
    if cut < _TELEGRAM_CAPTION_LIMIT * 4 // 5:
        cut = window.rfind(" ")
    if cut <= 0:
        cut = _TELEGRAM_CAPTION_LIMIT
    return text[:cut].rstrip(), _split_for_telegram(text[cut:].lstrip())


def _split_for_telegram(text: str) -> list[str]:
    """Break an over-long message on the nicest boundary available.

    Paragraph, then line, then word, then — only if a single word really is
    longer than the limit — mid-word. A guide chopped between paragraphs
    reads as a guide; one chopped every 4096 characters reads as damage.
    """
    if len(text) <= _TELEGRAM_TEXT_LIMIT:
        return [text]

    pieces: list[str] = []
    rest = text
    while len(rest) > _TELEGRAM_TEXT_LIMIT:
        window = rest[:_TELEGRAM_TEXT_LIMIT]
        cut = max(window.rfind("\n\n"), window.rfind("\n"), window.rfind(" "))
        # No breathing space anywhere in 4096 characters — one very long
        # word, or a language that does not use spaces. Cut it squarely.
        if cut <= 0:
            cut = _TELEGRAM_TEXT_LIMIT
        pieces.append(rest[:cut].rstrip())
        rest = rest[cut:].lstrip()
    if rest:
        pieces.append(rest)
    return pieces


async def _send_media_only(bot: Bot, chat_id: int, block: BotBlock) -> None:
    """Вложение блока без его текста — текст уже ушёл с приглашением."""
    content = block.content or {}
    file_id = content.get("media_file_id")
    media_type = content.get("media_type")
    if not file_id:
        return
    if media_type == "photo":
        await bot.send_photo(chat_id, file_id)
    elif media_type == "audio":
        await bot.send_audio(chat_id, file_id)
    elif media_type == "video":
        await bot.send_video(chat_id, file_id)
    else:
        await bot.send_document(chat_id, file_id)


async def walk_chain(
    bot: Bot,
    chat_id: int,
    start_block_id: uuid.UUID,
    bot_id: uuid.UUID,
    db: AsyncSession,
    telegram_user_id: int | None = None,
    subscription_id: uuid.UUID | None = None,
    footer: str = "",
) -> bool:
    """Send `start_block_id` and keep following next_block_id, pausing for
    typing/delay between steps, until the chain ends or hits a branch
    point (a buttons block with at least one connected button).

    Returns False if any block failed to go out. A failure is still not
    allowed to stop the rest of the chain — one broken image must not
    swallow the four messages after it — but the caller has to be able to
    tell. `resume_after_payment` stamps an order as delivered on the
    strength of this answer, and while it was `None` a delivery block that
    Telegram refused (text over 4096, an image it could not fetch, a buyer
    who blocked the bot) was recorded as handed over: the retry sweep skips
    anything stamped, so the money stayed taken and the goods never came.

    A long "Пауза" ends the walk too — the rest of the chain is handed to
    the scheduler and resumes from here, in a later process, whenever the
    pause is up. `subscription_id` rides along so that everything queued
    downstream stays attached to the subscription that started it and can
    be withdrawn in one go when it lapses."""

    next_id: uuid.UUID | None = start_block_id
    visited: set[uuid.UUID] = set()
    steps = 0
    first = True
    # Flipped by the one `except` below and never flipped back: a chain is
    # only "delivered" if everything in it went out.
    delivered = True

    while next_id is not None:
        steps += 1
        if steps > _MAX_CHAIN_STEPS:
            logger.warning("Bot %s dialogue chain exceeded %d steps — stopping.", bot_id, _MAX_CHAIN_STEPS)
            # Раньше обрыв был молчаливым с обеих сторон: покупатель видел
            # оборванный разговор, владелец не узнавал ничего — а конструктор
            # при этом позволяет собрать 200 блоков в одну цепочку.
            await _tell_owner(
                db, bot_id,
                f"⚠️ Сценарий оборвался: подряд идёт больше {_MAX_CHAIN_STEPS} блоков без кнопки "
                f"или паузы, и бот остановился на полпути. Разбей цепочку кнопкой «дальше» "
                f"или блоком «Пауза».",
            )
            return False
        if next_id in visited:
            # A revisit means a cycle (a real, deliberate pattern in a
            # visual flow graph) with no branch point to break it up — each
            # step in this loop is paced with a real typing delay, so
            # waiting for _MAX_CHAIN_STEPS to catch this could hold a
            # webhook request open for tens of seconds. Catch it the
            # instant it's actually detected instead.
            logger.warning("Bot %s dialogue hit a loop at block %s — stopping.", bot_id, next_id)
            return delivered
        visited.add(next_id)

        result = await db.execute(select(BotBlock).where(BotBlock.id == next_id, BotBlock.bot_id == bot_id))
        block = result.scalar_one_or_none()
        if block is None:
            return delivered  # dangling/removed target — nothing left to do

        try:
            if block.block_type == BlockType.payment:
                if not first:
                    await bot.send_chat_action(chat_id, "typing")
                    await _pause(db, _TYPING_DELAY_MIN)
                if await _send_payment_block(bot, chat_id, block, bot_id, db, telegram_user_id):
                    # Paid delivery waits for the provider's callback — see
                    # payment_service.resume_after_payment.
                    return delivered
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
                    return delivered
                await _pause(db, seconds)
            else:
                if not first:
                    text = (block.content or {}).get("text") or ""
                    await bot.send_chat_action(chat_id, "typing")
                    await _pause(db, _typing_delay(text))
                handled = False
                if block.block_type == BlockType.delivery:
                    handled = await _deliver_group_invite(
                        bot, chat_id, block, bot_id, db, telegram_user_id
                    )
                # Приглашение в группу и файл — не «или-или». Продавец,
                # который продаёт «доступ в клуб + методичку», прикладывает к
                # блоку и то и другое, а получал покупатель только клуб:
                # приглашение считалось обработкой всего блока, и файл молча
                # не уходил. Текст при этом уже ушёл вместе с приглашением,
                # поэтому дальше отправляется только вложение.
                if handled and (block.content or {}).get("media_file_id"):
                    await _send_media_only(bot, chat_id, block)
                elif not handled:
                    # Подпись — только на первом блоке цепочки: повторять её
                    # под каждым сообщением рассылки незачем.
                    await _send_block(bot, chat_id, block, db, footer=footer if first else "")
        except Exception:
            logger.exception("Failed to send block %s for bot %s", block.id, bot_id)
            delivered = False

        first = False

        # A buttons block with any branch configured is a real decision
        # point — stop and wait for the tap instead of barrelling through
        # to next_block_id regardless of what the user picks. Without any
        # branch configured it's just another block in the chain (matches
        # every bot built before branching existed).
        if block.block_type == BlockType.buttons and _button_has_branches(block.content or {}):
            return delivered

        next_id = block.next_block_id

    return delivered


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
    until = dates.day(subscription.current_period_end)
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

    poll_answer = update.get("poll_answer")
    if poll_answer:
        await _handle_poll_answer(poll_answer, bot_id, db)
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

    # Отписка. До этого выйти из рассылки можно было только заблокировав
    # бота — а `blocked_at` сбрасывается первым же сообщением от человека,
    # так что одно «спасибо» возвращало его в рассылку. Человек, который не
    # может отписаться, жалуется не боту, а Telegram.
    if text.startswith("/stop"):
        await subscribers.set_unsubscribed(db, bot_id, sender_id, value=True)
        await bot.send_message(
            chat_id,
            "Готово — рассылку больше не пришлю 👍\nПокупки и доступы это не отменяет. "
            "Если передумаешь, напиши /start.",
        )
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

    # Явный /start — единственное, что снимает отписку: вернуться человек
    # должен сам, а не потому, что однажды что-то написал.
    await subscribers.set_unsubscribed(db, bot_id, sender_id, value=False)

    if start_block_id is None:
        await bot.send_message(chat_id, "Этот бот пока пуст 🤷")
        return

    await walk_chain(bot, chat_id, start_block_id, bot_id, db, telegram_user_id=sender_id)
