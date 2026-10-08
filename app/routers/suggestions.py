"""Идеи и пожелания из конструктора: отправить и посмотреть свои."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.deps import get_current_client
from app.models.client import Client
from app.services import background, suggestions

router = APIRouter(prefix="/api", tags=["suggestions"])


class SuggestionIn(BaseModel):
    text: str = Field(max_length=suggestions.MAX_LEN + 500)
    category: str = "idea"


def _view(item) -> dict:
    return {
        "id": str(item.id),
        "category": item.category,
        "text": item.text,
        "status": suggestions.CLIENT_STATUS.get(item.status, "на рассмотрении"),
        "done": item.status == "done",
        "created_at": item.created_at,
    }


@router.post("/suggestions", status_code=status.HTTP_201_CREATED)
async def send_suggestion(
    payload: SuggestionIn, client: Client = Depends(get_current_client), db: AsyncSession = Depends(get_db)
) -> dict:
    try:
        item = await suggestions.submit(db, client, text=payload.text, category=payload.category)
    except suggestions.SuggestionError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    # Оператору — после ответа клиенту, чтобы медленный Telegram не держал форму.
    background.spawn(suggestions.notify_operators(item, client), name=f"suggestion-{item.id}")
    return _view(item)


@router.get("/suggestions")
async def my_suggestions(client: Client = Depends(get_current_client), db: AsyncSession = Depends(get_db)) -> dict:
    return {"suggestions": [_view(i) for i in await suggestions.mine(db, client)]}
