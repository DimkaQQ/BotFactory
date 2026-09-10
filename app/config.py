from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application configuration, loaded from environment variables / .env."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Database
    database_url: str = "postgresql+asyncpg://botfactory:botfactory@localhost:5432/botfactory"

    # Meta-bot (the bot that opens the constructor Mini App)
    meta_bot_token: str = ""
    # Its @username (no @), needed client-side to render the Telegram Login
    # Widget for the standalone web version of the constructor.
    meta_bot_username: str = ""

    # Optional: base URL of a reverse proxy in front of the Telegram Bot API
    # (e.g. a Cloudflare Worker), for deployments where api.telegram.org is
    # blocked/throttled directly (common for RU-hosted servers). Leave empty
    # to talk to api.telegram.org directly. Expected to proxy requests
    # 1:1 — https://<worker>/bot<token>/<method> -> Telegram's own endpoint.
    telegram_api_base_url: str = ""

    # Public HTTPS base URL of the deployment, e.g. https://your-domain.com
    public_base_url: str = "https://your-domain.com"

    # Fernet master key used to encrypt client bot tokens at rest.
    # Generate with: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
    fernet_key: str = ""

    # CORS - Mini App origin(s), comma separated. "*" for local dev.
    cors_origins: str = "*"

    # Where uploaded media (photos/videos attached directly, not via a
    # pasted link) land on disk. Relative paths resolve against the
    # process's cwd — /srv in the Docker image (see Dockerfile's WORKDIR),
    # mounted as a named volume in docker-compose.yml so uploads survive
    # a redeploy.
    media_upload_dir: str = "media_uploads"
    # Cap on a direct upload — Telegram itself allows much larger files,
    # but this app proxies the bytes onto local disk, so a generous-but-
    # bounded limit here. Bigger files are what the "paste a link" option
    # (still on every media block) is for.
    media_max_upload_mb: int = 20

    # ---- Платформа: платная публикация бота ----
    # How *we* get paid, as a JSON array — one entry per method the client
    # may choose at checkout. Several are needed because no single provider
    # covers everyone: cards abroad go through Stripe (which does not operate
    # in Russia or Kazakhstan and so needs a company elsewhere), local cards
    # through a local acquirer, and crypto through Crypto Bot, which needs no
    # company at all.
    #
    # Each entry carries its own price, because the same publication costs
    # $9, ₸4500 and 9 USDT — one number in one currency cannot express that.
    #
    #   [{"provider": "stripe",    "price_minor": 900,    "currency": "USD",
    #     "credentials": {"secret_key": "sk_live_…", "webhook_secret": "whsec_…"}},
    #    {"provider": "robokassa", "price_minor": 450000, "currency": "KZT",
    #     "credentials": {"merchant_login": "…", "password1": "…", "password2": "…"}},
    #    {"provider": "cryptobot", "price_minor": 900,    "currency": "USDT",
    #     "credentials": {"token": "…"}}]
    #
    # Empty falls back to the single-provider settings below, so an existing
    # deployment keeps working untouched.
    platform_payment_methods: str = ""

    # Single-method fallback, kept for deployments configured before the list
    # existed.
    platform_payment_provider: str = "test"
    # That provider's credentials as JSON, e.g.
    # {"secret_key": "sk_live_…", "webhook_secret": "whsec_…"} — one variable
    # instead of a field per provider, since each wants a different set.
    platform_payment_credentials: str = ""
    platform_payment_is_test: bool = True
    # Price of publishing one bot, in minor units (kopeks/tiyn/cents).
    # 0 disables the paywall entirely — publishing stays free until a price
    # is actually configured, so a fresh deployment is never locked.
    publication_price_minor: int = 0
    publication_currency: str = "KZT"

    @property
    def webapp_url(self) -> str:
        # Same app the web version lives at — the Mini App just opens it and
        # detects at runtime that it's inside Telegram (see App.tsx).
        return self.public_base_url.rstrip("/") + "/"

    def webhook_url(self, bot_id: str) -> str:
        return f"{self.public_base_url.rstrip('/')}/webhook/{bot_id}"

    @property
    def cors_origin_list(self) -> list[str]:
        if self.cors_origins.strip() == "*":
            return ["*"]
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
