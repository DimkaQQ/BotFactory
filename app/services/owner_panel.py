"""Что владелец видит и делает в мета-боте, не заходя в конструктор.

Здесь только данные и правила; кнопки и тексты — в meta_bot/handlers. Так всё,
что считается и меняется, проверяется тестами без Telegram.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.bot import Bot, BotStatus
from app.models.bot_subscriber import BotSubscriber
from app.models.client import Client
from app.models.payment import Payment, PaymentKind, PaymentStatus
from app.models.subscription import Subscription, SubscriptionStatus

WEEK = timedelta(days=7)


@dataclass
class BotCard:
    """Один бот и его цифры — то, что показывается в списке и на карточке."""

    bot: Bot
    clients: int = 0
    new_this_week: int = 0
    blocked: int = 0
    active_subscriptions: int = 0
    orders: int = 0
    orders_this_week: int = 0
    #: [(валюта, сумма в минорных единицах)] — по валютам, а не одним числом:
    #: рубли и звёзды складывать нельзя.
    revenue: list[tuple[str, int]] = field(default_factory=list)

    @property
    def state(self) -> str:
        """Одно слово для человека: работает, пауза, черновик, остановлен."""
        if self.bot.status == BotStatus.draft:
            return "draft"
        if self.bot.status == BotStatus.disabled:
            return "disabled"
        return "paused" if self.bot.paused else "live"


async def client_by_telegram(db: AsyncSession, telegram_user_id: int) -> Client | None:
    result = await db.execute(select(Client).where(Client.telegram_user_id == telegram_user_id))
    return result.scalar_one_or_none()


async def accept_terms(db: AsyncSession, telegram_user_id: int, full_name: str | None) -> Client:
    """Записать, что человек принял действующую редакцию условий (кнопка в
    мета-боте). Аккаунта может ещё не быть — тогда он создаётся, как при первом
    входе в конструктор."""
    from app.routers.legal import REVISION

    client = await client_by_telegram(db, telegram_user_id)
    if client is None:
        client = Client(telegram_user_id=telegram_user_id, full_name=full_name)
        db.add(client)
    if client.terms_version != REVISION:
        client.terms_version = REVISION
        client.terms_accepted_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(client)
    return client


async def list_cards(db: AsyncSession, client: Client) -> list[BotCard]:
    """Все боты клиента с цифрами. Один проход по каждой таблице, а не запрос
    на бота: у владельца до двадцати ботов, и меню не должно тормозить."""
    bots = list(
        (await db.execute(select(Bot).where(Bot.client_id == client.id).order_by(Bot.created_at.desc()))).scalars()
    )
    if not bots:
        return []
    cards = {bot.id: BotCard(bot=bot) for bot in bots}
    ids = list(cards)
    week_ago = datetime.now(timezone.utc) - WEEK

    for bot_id, total, fresh, blocked in (
        await db.execute(
            select(
                BotSubscriber.bot_id,
                func.count(),
                func.count().filter(BotSubscriber.first_seen_at >= week_ago),
                func.count().filter(BotSubscriber.blocked_at.is_not(None)),
            )
            .where(BotSubscriber.bot_id.in_(ids))
            .group_by(BotSubscriber.bot_id)
        )
    ).all():
        cards[bot_id].clients, cards[bot_id].new_this_week, cards[bot_id].blocked = total, fresh, blocked

    for bot_id, active in (
        await db.execute(
            select(Subscription.bot_id, func.count())
            .where(Subscription.bot_id.in_(ids), Subscription.status == SubscriptionStatus.active)
            .group_by(Subscription.bot_id)
        )
    ).all():
        cards[bot_id].active_subscriptions = active

    for bot_id, currency, count, fresh, total in (
        await db.execute(
            select(
                Payment.bot_id,
                Payment.currency,
                func.count(),
                func.count().filter(Payment.paid_at >= week_ago),
                func.coalesce(func.sum(Payment.amount_minor), 0),
            )
            .where(
                Payment.bot_id.in_(ids),
                Payment.kind == PaymentKind.order,
                Payment.status == PaymentStatus.paid,
            )
            .group_by(Payment.bot_id, Payment.currency)
        )
    ).all():
        card = cards[bot_id]
        card.orders += count
        card.orders_this_week += fresh
        card.revenue.append((currency, int(total)))

    return [cards[bot.id] for bot in bots]


async def get_card(db: AsyncSession, client: Client, bot_id: uuid.UUID) -> BotCard | None:
    """Карточка одного бота — только если он принадлежит этому клиенту."""
    for card in await list_cards(db, client):
        if card.bot.id == bot_id:
            return card
    return None


@dataclass
class Totals:
    bots: int = 0
    live: int = 0
    clients: int = 0
    orders: int = 0
    revenue: dict[str, int] = field(default_factory=dict)


def totals(cards: list[BotCard]) -> Totals:
    result = Totals(bots=len(cards))
    for card in cards:
        result.live += card.state == "live"
        result.clients += card.clients
        result.orders += card.orders
        for currency, amount in card.revenue:
            result.revenue[currency] = result.revenue.get(currency, 0) + amount
    return result


class PauseError(Exception):
    """Почему паузу нельзя включить или снять — человеческим языком."""


async def set_paused(db: AsyncSession, client: Client, bot_id: uuid.UUID, paused: bool) -> Bot:
    result = await db.execute(select(Bot).where(Bot.id == bot_id, Bot.client_id == client.id))
    bot = result.scalar_one_or_none()
    if bot is None:
        raise PauseError("Бот не найден.")
    if client.banned_at is not None:
        raise PauseError("Аккаунт заблокирован за нарушение правил. Напиши в поддержку.")
    if bot.status == BotStatus.draft:
        raise PauseError("Бот ещё не опубликован — ставить на паузу нечего.")
    if bot.status == BotStatus.disabled:
        raise PauseError("Бот остановлен из-за неоплаты периода — продли его в конструкторе, и он вернётся.")
    bot.paused = paused
    await db.commit()
    return bot


async def set_notify_sales(db: AsyncSession, client: Client, value: bool) -> None:
    client.notify_sales = value
    await db.commit()


async def sign_out_everywhere(db: AsyncSession, client: Client) -> None:
    """То же, что «Выйти» в конструкторе: все выданные токены перестают работать."""
    client.sessions_valid_from = datetime.now(timezone.utc)
    await db.commit()
