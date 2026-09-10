"""Telegram updates for published client bots.

Two things happen before an update is believed, and one after.

Before: the URL carries the bot's id, which is a UUID4 and therefore hard to
guess — but "hard to guess" is not authentication, and a forged update here
could impersonate anyone, including the shop owner confirming their own
payment. So Telegram is asked to echo a per-bot secret on every delivery
(`secret_token`), and an update that fails to carry it is refused.

After: the dialogue is sent from a background task rather than from this
request. Blocks are paced with typing delays and a "Пауза" block can hold
for fifteen seconds, which is far longer than Telegram waits before
redelivering the update — and a redelivered update replays the whole
conversation.
"""

import hmac
import logging
import uuid

from fastapi import APIRouter, Header, HTTPException, status

from app.database import AsyncSessionLocal
from app.services import background, bot_dispatcher, bot_registry
from app.services.security import webhook_secret

logger = logging.getLogger(__name__)

router = APIRouter(tags=["webhook"])


async def _dispatch(bot_id: uuid.UUID, update: dict) -> None:
    """Own session: the request that scheduled this has already returned, and
    its session is closed."""
    async with AsyncSessionLocal() as db:
        bot_instance = await bot_registry.get_or_create(bot_id, db)
        if bot_instance is None:
            return
        try:
            await bot_dispatcher.process_update(bot_instance, update, bot_id, db)
        except Exception:
            # One bot's broken dialogue must never affect another's.
            logger.exception("Error handling update for bot %s", bot_id)


@router.post("/webhook/{bot_id}")
async def handle_update(
    bot_id: uuid.UUID,
    update: dict,
    x_telegram_bot_api_secret_token: str | None = Header(default=None),
) -> dict:
    # A missing header is refused exactly like a wrong one. Letting it
    # through — which this route briefly did, as a migration path for bots
    # published before secrets existed — is not a smaller hole than having no
    # check at all: an attacker simply omits the header. Those older bots are
    # instead re-registered at startup (see app/main.py), so nothing has to be
    # trusted on the way past.
    if x_telegram_bot_api_secret_token is None or not hmac.compare_digest(
        x_telegram_bot_api_secret_token, webhook_secret(bot_id)
    ):
        logger.warning("Rejected an update for bot %s: bad or missing secret token", bot_id)
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Bad secret token")

    background.spawn(_dispatch(bot_id, update), name=f"update:{bot_id}")
    return {"ok": True}
