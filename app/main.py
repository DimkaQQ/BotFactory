import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Response, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.config import get_settings
from app.routers import auth, bot_profile, bots, builder, crm, legal, media, payments, reports, webhook
from app.services import (
    background,
    bot_registry,
    platform_billing,
)
from app.tasks import start_background_tasks

logging.basicConfig(level=logging.INFO)
# httpx на INFO пишет полный URL запроса, а в нём токен бота (.../bot<TOKEN>/getMe).
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    if get_settings().run_background:
        start_background_tasks()
    yield
    # Dialogues and deliveries scheduled off a request are still in flight;
    # give them a moment to finish rather than dropping a buyer's goods
    # halfway through a deploy. Whatever is still going after that is
    # cancelled *before* the bot sessions close, so it fails cleanly instead
    # of tripping over a connection pulled out from under it — and anything
    # undelivered is picked up on the next boot.
    # Longer than the longest single pause a block can hold (15s), so an
    # in-flight delivery finishes rather than being cut in half and
    # replayed from the start on the next boot.
    await background.wait_for_all(timeout=25.0)
    await background.cancel_all()
    await bot_registry.close_all()
    await platform_billing.close_meta_bot()


settings = get_settings()
_docs = settings.enable_api_docs
app = FastAPI(
    title="Bot Factory API",
    version="0.1.0",
    lifespan=lifespan,
    docs_url="/docs" if _docs else None,
    redoc_url="/redoc" if _docs else None,
    openapi_url="/openapi.json" if _docs else None,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(bots.router)
app.include_router(bot_profile.router)
app.include_router(builder.router)
app.include_router(crm.router)
app.include_router(legal.router)
app.include_router(media.router)
app.include_router(payments.router)
app.include_router(reports.router)
app.include_router(webhook.router)

# Serves what media.router just saved to disk — mounted under /api/ so it
# rides the same nginx/Caddy proxy rule as the rest of the API, no separate
# reverse-proxy config needed per deployment flavor.
Path(settings.media_upload_dir).mkdir(parents=True, exist_ok=True)
app.mount("/api/media", StaticFiles(directory=settings.media_upload_dir), name="media")


@app.get("/health")
async def health(response: Response) -> dict:
    """Liveness *and* the database, because the two fail separately.

    This used to return a constant. A constant answers "ok" while Postgres
    is gone, the disk is full or the pool is exhausted — which is precisely
    the moment a health check exists for, and precisely when both the
    watchdog and any external uptime service would have said nothing.

    A failure is reported with 503 rather than an exception: an uptime
    monitor reads the status code, and a traceback would look like an
    application bug rather than "the database is down".
    """
    from sqlalchemy import text

    from app.database import AsyncSessionLocal

    try:
        # Bounded: an unreachable database otherwise holds this request for
        # the pool's full timeout, and a health check that hangs reads as a
        # dead server to some monitors and a healthy one to others.
        async with asyncio.timeout(5):
            async with AsyncSessionLocal() as db:
                await db.execute(text("SELECT 1"))
    except Exception as exc:  # noqa: BLE001 — любой сбой БД = 503
        logger.error("Health check failed: %s", exc)
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return {"status": "error", "database": "unreachable"}

    return {"status": "ok", "database": "ok"}
