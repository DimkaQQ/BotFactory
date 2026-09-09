"""payments: orders inside client bots + paid publication

Adds one payments table covering both money flows (a bot's customer paying
that bot's owner, and an owner paying us to publish), plus the per-bot
payment provider settings and the flag that gates publishing.

Nothing here changes behaviour for existing bots: payment_provider stays
null (no payment blocks can run without it), and publication_paid_at is
backfilled as "already paid" for every bot that is *already* published, so
a live bot is never retroactively knocked off the air by the new paywall.

Revision ID: 0004
Revises: 0003
Create Date: 2026-09-09

"""
from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0004"
down_revision: Union[str, None] = "0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("bots", sa.Column("payment_provider", sa.String(length=32), nullable=True))
    op.add_column("bots", sa.Column("payment_credentials_encrypted", sa.LargeBinary(), nullable=True))
    op.add_column(
        "bots", sa.Column("payment_is_test", sa.Boolean(), nullable=False, server_default=sa.true())
    )
    op.add_column("bots", sa.Column("publication_paid_at", sa.DateTime(timezone=True), nullable=True))

    # Grandfather in everything already live — the paywall applies to the
    # next publication, not to bots that are already running.
    op.execute("UPDATE bots SET publication_paid_at = published_at WHERE published_at IS NOT NULL")

    op.create_table(
        "payments",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("invoice_no", sa.BigInteger(), sa.Identity(start=1000), nullable=False, unique=True),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="pending"),
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column("provider_payment_id", sa.String(length=255), nullable=True),
        sa.Column("amount_minor", sa.BigInteger(), nullable=False),
        sa.Column("currency", sa.String(length=8), nullable=False),
        sa.Column("description", sa.String(length=255), nullable=False, server_default=""),
        sa.Column("bot_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("bots.id", ondelete="CASCADE"), nullable=True),
        sa.Column(
            "client_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("clients.id", ondelete="CASCADE"), nullable=True
        ),
        sa.Column(
            "block_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("bot_blocks.id", ondelete="SET NULL"), nullable=True
        ),
        sa.Column("telegram_user_id", sa.BigInteger(), nullable=True),
        sa.Column("chat_id", sa.BigInteger(), nullable=True),
        sa.Column("meta", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("paid_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_payments_bot_id", "payments", ["bot_id"])
    op.create_index("ix_payments_client_id", "payments", ["client_id"])
    op.create_index("ix_payments_status", "payments", ["status"])


def downgrade() -> None:
    op.drop_index("ix_payments_status", table_name="payments")
    op.drop_index("ix_payments_client_id", table_name="payments")
    op.drop_index("ix_payments_bot_id", table_name="payments")
    op.drop_table("payments")
    op.drop_column("bots", "publication_paid_at")
    op.drop_column("bots", "payment_is_test")
    op.drop_column("bots", "payment_credentials_encrypted")
    op.drop_column("bots", "payment_provider")
