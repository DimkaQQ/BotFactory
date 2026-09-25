import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Response, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.config import get_settings
from app.routers import auth, bots, builder, media, payments, webhook
from app.services import (
    background,
    bot_registry,
    media_gc,
    payment_service,
    platform_billing,
    scheduler,
    subscription_service,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Brings bots published before webhook secrets existed up to date, so the
    # webhook route can refuse anything that arrives without one.
    background.spawn(bot_registry.refresh_all_webhooks(), name="refresh-all-webhooks")
    # Anything a previous run was paid for but never handed over — the
    # provider was already acknowledged, so nothing else would ever retry.
    background.spawn(payment_service.redeliver_undelivered(), name="redeliver-undelivered")
    # And keep looking: a delivery can also fail mid-flight (Telegram 5xx, a
    # rate limit), and until this existed the only retry was the next deploy.
    background.spawn(payment_service.redeliver_forever(), name="redeliver-forever", daemon=True)
    # Conversations that were told to continue later — a long "Пауза", a
    # renewal reminder. Run once at boot before the loop starts, because
    # everything that came due while the process was down is due *now*.
    background.spawn(scheduler.run_due(), name="scheduled-steps-catchup")
    background.spawn(scheduler.run_forever(), name="scheduled-steps", daemon=True)
    # And close out periods that ran out while nobody was watching. Separate
    # from the queue above on purpose: access must end when the period ends
    # even if no step survived to say so.
    background.spawn(subscription_service.expire_due(), name="subscriptions-catchup")
    background.spawn(subscription_service.expire_forever(), name="subscriptions-expiry", daemon=True)
    # What the bot owners owe *us*: remind while a period is running out,
    # take the bot off the air once the grace period has run out too. Same
    # shape as above and for the same reason — a period that ended during a
    # deploy ended, whether or not anything was running to notice.
    # Загруженные файлы, на которые больше никто не ссылается: они
    # переживали и блок, и бота, и клиента, а каталог лежит на том же томе,
    # что и база.
    background.spawn(media_gc.sweep_forever(), name="media-gc", daemon=True)
    background.spawn(platform_billing.sweep_once(), name="billing-catchup")
    background.spawn(platform_billing.sweep_forever(), name="billing-sweep", daemon=True)
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


app = FastAPI(title="Bot Factory API", version="0.1.0", lifespan=lifespan)

settings = get_settings()
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(bots.router)
app.include_router(builder.router)
app.include_router(media.router)
app.include_router(payments.router)
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
    except Exception as exc:
        logger.error("Health check failed: %s", exc)
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return {"status": "error", "database": "unreachable"}

    return {"status": "ok", "database": "ok"}
