import os
import sys
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

sys.path.insert(0, os.getcwd())

from app.database import Base  # noqa: E402
from app.models import (  # noqa: E402,F401  (register models on Base.metadata)
    Bot,
    BotBlock,
    BotSubscriber,
    Client,
    PollAnswer,
    ScheduledStep,
    Subscription,
)

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def _sync_db_url() -> str:
    url = os.environ.get("DATABASE_URL_SYNC")
    if url:
        return url
    # Fall back to converting the async URL used by the app at runtime.
    async_url = os.environ.get("DATABASE_URL", "postgresql+asyncpg://botfactory:botfactory@localhost:5432/botfactory")
    return async_url.replace("+asyncpg", "+psycopg2")


def run_migrations_offline() -> None:
    context.configure(
        url=_sync_db_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    configuration = config.get_section(config.config_ini_section) or {}
    configuration["sqlalchemy.url"] = _sync_db_url()
    connectable = engine_from_config(configuration, prefix="sqlalchemy.", poolclass=pool.NullPool)

    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
