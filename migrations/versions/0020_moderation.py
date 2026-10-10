"""Модерация: жалобы на ботов, журнал решений, снятие бота оператором.

Только добавление (expand): старый код этих таблиц и колонки не видит.

Revision ID: 0020
Revises: 0019
"""

from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0020"
down_revision: Union[str, None] = "0019"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("bots", sa.Column("moderation_blocked_at", sa.DateTime(timezone=True), nullable=True))
    op.create_table(
        "abuse_reports",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("bot_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("bots.id", ondelete="SET NULL"), nullable=True),
        sa.Column("bot_ref", sa.String(255), nullable=False),
        sa.Column("category", sa.String(32), nullable=False),
        sa.Column("details", sa.Text(), nullable=False),
        sa.Column("contact", sa.String(255), nullable=True),
        sa.Column("status", sa.String(16), nullable=False, server_default="new"),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_abuse_reports_created_at", "abuse_reports", ["created_at"])
    op.create_index("ix_abuse_reports_bot_id", "abuse_reports", ["bot_id"])
    op.create_index("ix_abuse_reports_status", "abuse_reports", ["status"])
    op.create_table(
        "moderation_actions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column(
            "report_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("abuse_reports.id", ondelete="SET NULL"), nullable=True
        ),
        sa.Column("bot_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("bots.id", ondelete="SET NULL"), nullable=True),
        sa.Column("client_telegram_id", sa.BigInteger(), nullable=True),
        sa.Column("action", sa.String(24), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False, server_default=""),
        sa.Column("actor", sa.String(64), nullable=False),
    )
    op.create_index("ix_moderation_actions_created_at", "moderation_actions", ["created_at"])


def downgrade() -> None:
    op.drop_table("moderation_actions")
    op.drop_table("abuse_reports")
    op.drop_column("bots", "moderation_blocked_at")
