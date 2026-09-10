import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.config import get_settings
from app.routers import auth, bots, builder, media, payments, webhook
from app.services import background, bot_registry

logging.basicConfig(level=logging.INFO)


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    # Dialogues and deliveries scheduled off a request are still in flight;
    # give them a moment to finish rather than dropping a buyer's goods
    # halfway through a deploy.
    await background.wait_for_all()
    await bot_registry.close_all()


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
async def health() -> dict:
    return {"status": "ok"}
