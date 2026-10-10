"""Запись по календарю и мини-CRM: записи, ожидание ответа, контакты клиента.

Только добавление (expand): новые таблицы и колонки с значениями по умолчанию.

Revision ID: 0022
Revises: 0021
"""

from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0022"
down_revision: Union[str, None] = "0021"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("bot_subscribers", sa.Column("contact_name", sa.String(128), nullable=False, server_default=""))
    op.add_column("bot_subscribers", sa.Column("phone", sa.String(32), nullable=False, server_default=""))
    op.add_column("bot_subscribers", sa.Column("note", sa.Text(), nullable=False, server_default=""))

    op.create_table(
        "bookings",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("bot_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("bots.id", ondelete="CASCADE"), nullable=False),
        sa.Column("block_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("telegram_user_id", sa.BigInteger(), nullable=True),
        sa.Column("chat_id", sa.BigInteger(), nullable=True),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ends_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="held"),
        sa.Column("held_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("note", sa.Text(), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_bookings_bot_id", "bookings", ["bot_id"])
    op.create_index("ix_bookings_telegram_user_id", "bookings", ["telegram_user_id"])
    op.create_index("ix_bookings_status", "bookings", ["status"])
    op.create_index(
        "uq_booking_active_slot",
        "bookings",
        ["bot_id", "starts_at"],
        unique=True,
        postgresql_where=sa.text("status IN ('held','confirmed','blocked')"),
    )

    op.create_table(
        "chat_states",
        sa.Column("bot_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("bots.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("telegram_user_id", sa.BigInteger(), primary_key=True),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("chat_states")
    op.drop_table("bookings")
    op.drop_column("bot_subscribers", "note")
    op.drop_column("bot_subscribers", "phone")
    op.drop_column("bot_subscribers", "contact_name")
