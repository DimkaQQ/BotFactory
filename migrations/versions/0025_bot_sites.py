"""Публичная страница продавца для бота (для эквайринга КЗ).

Только добавление (expand): новая таблица.

Revision ID: 0025
Revises: 0024
"""

from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0025"
down_revision: Union[str, None] = "0024"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _text(name: str, size: int | None = None, **kw):
    kind = sa.String(size) if size else sa.Text()
    return sa.Column(name, kind, nullable=False, server_default="", **kw)


def upgrade() -> None:
    op.create_table(
        "bot_sites",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("bot_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("bots.id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("slug", sa.String(40), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default="false"),
        _text("title", 120),
        _text("about"),
        _text("seller_name", 200),
        _text("seller_id", 64),
        _text("seller_address", 300),
        _text("email", 120),
        _text("phone", 40),
        _text("refund_text"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_bot_sites_slug", "bot_sites", ["slug"], unique=True)


def downgrade() -> None:
    op.drop_table("bot_sites")
