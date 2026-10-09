"""Публичная страница продавца для бота и её настройки.

Зачем: банки Казахстана не пропускают приём оплаты «внутри Telegram» — нужен
сайт с описанием товара, ценами, реквизитами продавца и документами, а с него —
кнопка в бота. Страница живёт на нашем домене: `/s/{slug}`. Товары и цены берутся
из блоков оплаты бота, чтобы страница не расходилась с ботом.

Тексты документов — шаблоны: за их соответствие закону и требованиям банка
отвечает продавец, юристу их показать нужно (об этом сказано на самой странице).
"""

from __future__ import annotations

import html
import re
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.database import get_db
from app.deps import get_current_client
from app.models.bot import Bot, BotStatus
from app.models.bot_block import BlockType, BotBlock
from app.models.bot_site import BotSite
from app.models.client import Client

api = APIRouter(prefix="/api/bots/{bot_id}/site", tags=["site"])
public = APIRouter(tags=["site-public"])

SLUG_RE = re.compile(r"^[a-z0-9](?:[a-z0-9-]{1,38})[a-z0-9]$")
RESERVED = {"api", "legal", "webhook", "report", "assets", "admin", "builder", "static", "s"}
SIGNS = {"RUB": "₽", "KZT": "₸", "USD": "$", "EUR": "€", "UAH": "₴", "BYN": "Br", "XTR": "★", "USDT": "USDT"}


class SiteIn(BaseModel):
    slug: str | None = Field(default=None, max_length=40)
    enabled: bool | None = None
    title: str | None = Field(default=None, max_length=120)
    about: str | None = Field(default=None, max_length=4000)
    seller_name: str | None = Field(default=None, max_length=200)
    seller_id: str | None = Field(default=None, max_length=64)
    seller_address: str | None = Field(default=None, max_length=300)
    email: str | None = Field(default=None, max_length=120)
    phone: str | None = Field(default=None, max_length=40)
    refund_text: str | None = Field(default=None, max_length=4000)


FIELDS = ("title", "about", "seller_name", "seller_id", "seller_address", "email", "phone", "refund_text")


def _default_slug(bot: Bot) -> str:
    base = re.sub(r"[^a-z0-9]+", "-", (bot.telegram_bot_username or "").lower()).strip("-")
    if len(base) < 3:
        base = f"shop-{str(bot.id)[:8]}"
    return base[:40].strip("-")


def _out(site: BotSite | None, bot: Bot) -> dict:
    base = get_settings().public_base_url.rstrip("/")
    if site is None:
        return {
            "slug": _default_slug(bot), "enabled": False, "saved": False, "url": "",
            **{f: "" for f in FIELDS},
            "can_publish": bot.status == BotStatus.active and bool(bot.telegram_bot_username),
        }
    return {
        "slug": site.slug, "enabled": site.enabled, "saved": True, "url": f"{base}/s/{site.slug}",
        **{f: getattr(site, f) for f in FIELDS},
        "can_publish": bot.status == BotStatus.active and bool(bot.telegram_bot_username),
    }


async def _owned_bot(bot_id: uuid.UUID, client: Client, db: AsyncSession) -> Bot:
    bot = (await db.execute(select(Bot).where(Bot.id == bot_id, Bot.client_id == client.id))).scalar_one_or_none()
    if bot is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Bot not found")
    return bot


@api.get("")
async def get_site(
    bot_id: uuid.UUID, client: Client = Depends(get_current_client), db: AsyncSession = Depends(get_db)
) -> dict:
    bot = await _owned_bot(bot_id, client, db)
    site = (await db.execute(select(BotSite).where(BotSite.bot_id == bot.id))).scalar_one_or_none()
    return _out(site, bot)


@api.put("")
async def save_site(
    bot_id: uuid.UUID,
    payload: SiteIn,
    client: Client = Depends(get_current_client),
    db: AsyncSession = Depends(get_db),
) -> dict:
    bot = await _owned_bot(bot_id, client, db)
    site = (await db.execute(select(BotSite).where(BotSite.bot_id == bot.id))).scalar_one_or_none()
    slug = (payload.slug or (site.slug if site else _default_slug(bot))).strip().lower()
    if not SLUG_RE.match(slug) or slug in RESERVED:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Адрес страницы: 3–40 символов, латиница, цифры и дефис (не в начале и не в конце).",
        )
    if site is None:
        site = BotSite(bot_id=bot.id, slug=slug)
        db.add(site)
    site.slug = slug
    for field in FIELDS:
        value = getattr(payload, field)
        if value is not None:
            setattr(site, field, value.strip())
    if payload.enabled is not None:
        if payload.enabled:
            missing = [
                label
                for label, value in (
                    ("название продавца", site.seller_name),
                    ("ИИН/БИН/ИНН", site.seller_id),
                    ("почта или телефон", site.email or site.phone),
                )
                if not value
            ]
            if bot.status != BotStatus.active or not bot.telegram_bot_username:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT, detail="Страницу можно включить после публикации бота."
                )
            if missing:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Заполните перед включением: " + ", ".join(missing) + ".",
                )
        site.enabled = payload.enabled
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Этот адрес уже занят, выберите другой.") from exc
    await db.refresh(site)
    await db.refresh(bot)
    return _out(site, bot)


# ---------------------------------------------------------------- публичные страницы


def _e(value: str) -> str:
    return html.escape(value or "", quote=True)


async def _load(slug: str, db: AsyncSession) -> tuple[BotSite, Bot]:
    row = (
        await db.execute(
            select(BotSite, Bot).join(Bot, Bot.id == BotSite.bot_id).where(BotSite.slug == slug.lower())
        )
    ).first()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")
    site, bot = row
    if not site.enabled or bot.status != BotStatus.active or not bot.telegram_bot_username or bot.moderation_blocked_at:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")
    return site, bot


async def _products(bot: Bot, db: AsyncSession) -> list[dict]:
    blocks = (
        await db.execute(
            select(BotBlock)
            .where(BotBlock.bot_id == bot.id, BotBlock.block_type == BlockType.payment)
            .order_by(BotBlock.order_index, BotBlock.created_at)
        )
    ).scalars().all()
    items: list[dict] = []
    for block in blocks:
        content = block.content or {}
        title = re.sub(r"\[[^\]]*\]", "", str(content.get("title") or "")).strip()
        price = str(content.get("price") or "").strip()
        if not title or not price:
            continue
        cur = str(content.get("currency") or "").upper()
        items.append(
            {
                "title": title,
                "price": f"{price} {SIGNS.get(cur, cur)}".strip(),
                "subscription": bool(content.get("subscription")) and get_settings().subscriptions_enabled,
            }
        )
    return items


_STYLE = """
:root { color-scheme: light dark; --fg:#1b1d22; --bg:#fff; --mut:#6b7280; --acc:#2563eb; --card:#f4f5f8; }
@media (prefers-color-scheme: dark) { :root { --fg:#e8e9ee; --bg:#14151a; --mut:#9aa0ab; --acc:#6aa3ff; --card:#1f2128; } }
* { box-sizing: border-box; }
body { margin:0 auto; padding:28px 18px 72px; max-width:720px; background:var(--bg); color:var(--fg);
  font:16px/1.6 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif; }
h1 { font-size:28px; line-height:1.2; margin:0 0 8px; } h2 { font-size:19px; margin:32px 0 10px; }
a { color:var(--acc); } .mut { color:var(--mut); font-size:14px; }
.about { white-space:pre-line; }
.item { display:flex; justify-content:space-between; gap:16px; padding:14px 16px; background:var(--card);
  border-radius:12px; margin-bottom:8px; } .item b { white-space:nowrap; }
.cta { display:block; text-align:center; padding:15px; border-radius:12px; background:var(--acc); color:#fff;
  font-weight:700; text-decoration:none; margin:22px 0; }
.docs a { margin-right:14px; } .req { background:var(--card); border-radius:12px; padding:14px 16px; font-size:14px; }
.note { margin-top:36px; font-size:13px; color:var(--mut); }
"""


def _shell(site: BotSite, title: str, body: str) -> HTMLResponse:
    name = _e(site.title or site.seller_name)
    return HTMLResponse(
        f"""<!doctype html>
<html lang="ru"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex">
<title>{_e(title)} — {name}</title><style>{_STYLE}</style></head>
<body>{body}
<p class="note">Страница создана в конструкторе Bot Factory. За содержание, цены и документы отвечает продавец.</p>
</body></html>"""
    )


def _requisites(site: BotSite) -> str:
    lines = [f"<b>{_e(site.seller_name)}</b>", _e(site.seller_id)]
    if site.seller_address:
        lines.append(_e(site.seller_address))
    if site.phone:
        lines.append(f'<a href="tel:{_e(re.sub(r"[^0-9+]", "", site.phone))}">{_e(site.phone)}</a>')
    if site.email:
        lines.append(f'<a href="mailto:{_e(site.email)}">{_e(site.email)}</a>')
    return '<div class="req">' + "<br>".join(line for line in lines if line) + "</div>"


def _docs_nav(slug: str) -> str:
    base = f"/s/{_e(slug)}"
    return (
        f'<p class="docs"><a href="{base}/offer">Оферта</a><a href="{base}/refunds">Условия возврата</a>'
        f'<a href="{base}/privacy">Политика конфиденциальности</a></p>'
    )


@public.get("/s/{slug}", response_class=HTMLResponse)
async def landing(slug: str, db: AsyncSession = Depends(get_db)) -> HTMLResponse:
    site, bot = await _load(slug, db)
    products = await _products(bot, db)
    rows = "".join(
        f'<div class="item"><span>{_e(p["title"])}{" <span class=mut>(подписка)</span>" if p["subscription"] else ""}</span>'
        f'<b>{_e(p["price"])}</b></div>'
        for p in products
    )
    heading = _e(site.title or site.seller_name)
    body = f"""<h1>{heading}</h1>
{f'<p class="about">{_e(site.about)}</p>' if site.about else ""}
<a class="cta" href="https://t.me/{_e(bot.telegram_bot_username)}">Открыть в Telegram →</a>
<h2>Товары и цены</h2>
{rows or '<p class="mut">Цены будут опубликованы в боте.</p>'}
<p class="mut">Оплата происходит в боте: после выбора товара вы переходите на защищённую страницу платёжной системы.
Данные карты мы не получаем и не храним.</p>
<h2>Реквизиты продавца</h2>{_requisites(site)}
<h2>Документы</h2>{_docs_nav(slug)}"""
    return _shell(site, site.title or site.seller_name, body)


def _offer(site: BotSite) -> str:
    return f"""<h1>Публичная оферта</h1>
<p>Продавец — <b>{_e(site.seller_name)}</b> ({_e(site.seller_id)}) — предлагает неограниченному кругу лиц
приобрести товары и услуги, перечисленные на этой странице и в Telegram-боте @{{bot}}, на следующих условиях.</p>
<ol>
<li>Заказ оформляется в Telegram-боте. Акцепт оферты — оплата выбранного товара или услуги.</li>
<li>Цена указана на странице и в боте. Оплата проводится на странице платёжной системы банковской картой или
иным доступным способом; данные карты продавцу не передаются.</li>
<li>Цифровой товар или доступ предоставляется в боте сразу после подтверждения оплаты платёжной системой.</li>
<li>Условия возврата — в разделе «Условия возврата».</li>
<li>Вопросы по заказу: {_e(site.email or site.phone)}.</li>
</ol>"""


def _refunds(site: BotSite) -> str:
    custom = (
        f'<p class="about">{_e(site.refund_text)}</p>'
        if site.refund_text
        else "<p>Если товар не был предоставлен или не соответствует описанию, напишите продавцу по контактам ниже — "
        "заявка рассматривается в разумный срок, возврат производится на ту карту, с которой была оплата.</p>"
    )
    return f"<h1>Условия возврата</h1>{custom}"


def _privacy(site: BotSite) -> str:
    return f"""<h1>Политика конфиденциальности</h1>
<p>Оператор данных — <b>{_e(site.seller_name)}</b> ({_e(site.seller_id)}). Мы получаем от Telegram ваш
идентификатор, имя и username, а также данные заказа (что куплено, когда, сумма) — только для выполнения заказа,
выдачи товара и связи с вами по заказу. Данные банковской карты вводятся на странице платёжной системы и нам
не передаются. Мы не продаём ваши данные. Запрос на удаление или уточнение данных: {_e(site.email or site.phone)}.</p>"""


@public.get("/s/{slug}/{doc}", response_class=HTMLResponse)
async def document(slug: str, doc: str, db: AsyncSession = Depends(get_db)) -> HTMLResponse:
    site, bot = await _load(slug, db)
    builders = {"offer": _offer, "refunds": _refunds, "privacy": _privacy}
    build = builders.get(doc)
    if build is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")
    text = build(site).replace("{bot}", _e(bot.telegram_bot_username))
    body = (
        f'<p><a href="/s/{_e(slug)}">← {_e(site.title or site.seller_name)}</a></p>{text}'
        f"<h2>Реквизиты продавца</h2>{_requisites(site)}"
        '<p class="note">Текст — типовой шаблон конструктора; продавцу рекомендуется показать его юристу.</p>'
    )
    return _shell(site, "Документ", body)
