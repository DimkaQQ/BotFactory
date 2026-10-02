"""Web login (outside the Telegram Mini App) via the Telegram Login Widget.

The Mini App never touches this — it authenticates every request with a
fresh `X-Telegram-Init-Data` header instead (see app/deps.py). This is
only for a plain browser session, where a client logs in once and the
frontend replays the resulting bearer token.
"""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.database import get_db
from app.deps import get_current_client
from app.models.client import Client
from app.services.session_token import create_session_token
from app.services.telegram_validator import InvalidInitData, validate_login_widget_data

router = APIRouter(prefix="/api", tags=["auth"])


class GatewayRegion(BaseModel):
    """One heading on the landing's list of supported acquirers."""

    slug: str
    title: str
    gateways: list[str]


class PricePoint(BaseModel):
    """Одна цена с лендинга: чем платишь, сколько за запуск, сколько за период."""

    method: str
    launch: str
    renewal: str = ""


class PublicConfig(BaseModel):
    meta_bot_username: str
    #: Куда писать живому человеку. Без @; пусто не бывает — если своей
    #: поддержки не завели, это наш собственный бот.
    support_telegram: str = ""
    support_email: str = ""
    #: Кто получает деньги, как в документах. Пусто, пока реквизиты не
    #: заполнены, — и тогда подвал не показывает ни названия, ни ссылок на
    #: документы, потому что документов в этом случае тоже нет.
    legal_name: str = ""
    legal_documents: bool = False
    #: Какие документы показать в подвале (путь и название). Пусто, пока
    #: реквизиты не заполнены.
    legal_docs: list[dict[str, str]] = []
    #: Кто принимает оплату от имени Исполнителя. Пусто, если агента нет.
    payment_agent: str = ""
    # What the landing says about taking money. Served rather than written
    # into the page so the claim cannot drift from the code: adding or
    # removing an adapter moves the number on the landing with it.
    payment_regions: list[GatewayRegion] = []
    gateway_count: int = 0
    #: Что стоит запуск бота. Пусто — платёжных способов платформы нет, и
    #: запуск бесплатный; цифры берутся из той же настройки, что и кнопка
    #: публикации, поэтому лендинг не может обещать не то, что спишется.
    pricing: list[PricePoint] = []
    renewal_period_days: int = 0
    renewal_grace_days: int = 0


#: Not acquirers, and listing them as such would be a lie on a sales page.
#: "test" hands goods over without money, and "link" is a human confirming a
#: transfer by hand.
_NOT_A_GATEWAY = frozenset({"test", "link"})


@router.get("/config", response_model=PublicConfig)
async def get_public_config() -> PublicConfig:
    """Unauthenticated — what a browser needs before anyone has logged in:
    which bot to render the Telegram Login Widget for, and the acquirer list
    the landing page sells."""
    from app.routers import legal
    from app.services import payment_service, platform_billing
    from app.services import payments as payment_providers

    real = [p for p in payment_providers.describe_providers() if p["slug"] not in _NOT_A_GATEWAY]
    regions = [
        GatewayRegion(
            slug=slug,
            title=title,
            gateways=[p["title"] for p in real if p["region"] == slug],
        )
        for slug, title in payment_providers.REGIONS
    ]
    settings = get_settings()
    methods = payment_service.platform_methods()
    pricing = [
        PricePoint(
            method=m.title,
            launch=payment_providers.money(m.price_minor, m.currency),
            renewal=payment_providers.money(m.renewal_price_minor, m.currency) if m.renewal_price_minor > 0 else "",
        )
        for m in methods
    ]
    return PublicConfig(
        meta_bot_username=settings.meta_bot_username,
        support_telegram=settings.support_contact,
        support_email=settings.support_email,
        legal_name=settings.legal_name if settings.legal_ready else "",
        legal_documents=settings.legal_ready,
        legal_docs=legal.document_links(),
        payment_agent=settings.agent_name if settings.legal_ready and settings.agent_ready else "",
        # An empty heading would render as a section title with nothing
        # under it, which is exactly how "Украина" looked.
        payment_regions=[r for r in regions if r.gateways],
        gateway_count=len(real),
        pricing=pricing,
        renewal_period_days=platform_billing.period_days() if any(p.renewal for p in pricing) else 0,
        renewal_grace_days=platform_billing.grace_days() if any(p.renewal for p in pricing) else 0,
    )


class TelegramLoginPayload(BaseModel):
    id: int
    first_name: str
    last_name: str | None = None
    username: str | None = None
    photo_url: str | None = None
    auth_date: int
    hash: str


class TelegramLoginResponse(BaseModel):
    token: str


@router.post("/auth/telegram-login", response_model=TelegramLoginResponse)
async def telegram_login(
    payload: TelegramLoginPayload,
    db: AsyncSession = Depends(get_db),
) -> TelegramLoginResponse:
    data = payload.model_dump(exclude_none=True)
    try:
        validate_login_widget_data(data)
    except InvalidInitData as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc

    full_name = " ".join(filter(None, [payload.first_name, payload.last_name])) or None

    result = await db.execute(select(Client).where(Client.telegram_user_id == payload.id))
    client = result.scalar_one_or_none()

    if client is None:
        client = Client(telegram_user_id=payload.id, full_name=full_name)
        db.add(client)
        await db.commit()
        await db.refresh(client)
    elif full_name and client.full_name != full_name:
        client.full_name = full_name
        await db.commit()

    return TelegramLoginResponse(token=create_session_token(client.id))


@router.post("/auth/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    client: Client = Depends(get_current_client),
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Закрыть доступ по всем выданным токенам этого аккаунта.

    Стереть токен в браузере — не то же самое, что выйти: он действителен
    тридцать дней, и за ним касса, список покупателей и кнопка снятия бота
    с эфира. Отметка одна на аккаунт, поэтому выход происходит сразу
    везде — о чём кнопка и предупреждает.
    """
    client.sessions_valid_from = datetime.now(timezone.utc)
    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
