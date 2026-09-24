"""Web login (outside the Telegram Mini App) via the Telegram Login Widget.

The Mini App never touches this — it authenticates every request with a
fresh `X-Telegram-Init-Data` header instead (see app/deps.py). This is
only for a plain browser session, where a client logs in once and the
frontend replays the resulting bearer token.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.database import get_db
from app.models.client import Client
from app.services.session_token import create_session_token
from app.services.telegram_validator import InvalidInitData, validate_login_widget_data

router = APIRouter(prefix="/api", tags=["auth"])


class GatewayRegion(BaseModel):
    """One heading on the landing's list of supported acquirers."""

    slug: str
    title: str
    gateways: list[str]


class PublicConfig(BaseModel):
    meta_bot_username: str
    # What the landing says about taking money. Served rather than written
    # into the page so the claim cannot drift from the code: adding or
    # removing an adapter moves the number on the landing with it.
    payment_regions: list[GatewayRegion] = []
    gateway_count: int = 0


#: Not acquirers, and listing them as such would be a lie on a sales page.
#: "test" hands goods over without money, and "link" is a human confirming a
#: transfer by hand.
_NOT_A_GATEWAY = frozenset({"test", "link"})


@router.get("/config", response_model=PublicConfig)
async def get_public_config() -> PublicConfig:
    """Unauthenticated — what a browser needs before anyone has logged in:
    which bot to render the Telegram Login Widget for, and the acquirer list
    the landing page sells."""
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
    return PublicConfig(
        meta_bot_username=get_settings().meta_bot_username,
        # An empty heading would render as a section title with nothing
        # under it, which is exactly how "Украина" looked.
        payment_regions=[r for r in regions if r.gateways],
        gateway_count=len(real),
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
