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
