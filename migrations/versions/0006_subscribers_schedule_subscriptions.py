"""Subscribers, scheduled steps, subscriptions.

Three tables that between them close the two holes a bot builder cannot work
around: the engine could not send anything after the update that triggered it
(so "3-4 видео в течение месяца" was unbuildable), and no provider could
charge a second time (so "подписка" was a word in a template, not a
behaviour).

* `bot_subscribers` — the person on the other side. Nothing stored one
  before: a buyer existed only as `payments.telegram_user_id`, which is why
  the sales log could show an amount but not a name, and why nothing could
  be sent to them later.
* `scheduled_steps` — "resume this conversation from this block at this
  time". A table rather than an in-process timer because a month outlives
  any deployment.
* `subscriptions` — one person's standing access, a period at a time, with
  `billing_mode` recording the difference that decides the shop's business
  model: Telegram Stars can charge again by itself, every other provider
  can only be re-invoiced.

Purely additive: no existing table is touched, so every bot already running
behaves exactly as before until its owner marks a payment block as a
subscription or sets a Пауза longer than fifteen seconds.

Revision ID: 0006
Revises: 0005
"""

from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0006"
down_revision: Union[str, None] = "0005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "bot_subscribers",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("bot_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("bots.id", ondelete="CASCADE"), nullable=False),
        sa.Column("telegram_user_id", sa.BigInteger(), nullable=False),
        sa.Column("chat_id", sa.BigInteger(), nullable=False),
        sa.Column("first_name", sa.String(length=128), nullable=False, server_default=""),
        sa.Column("last_name", sa.String(length=128), nullable=False, server_default=""),
        sa.Column("username", sa.String(length=64), nullable=False, server_default=""),
        sa.Column("language_code", sa.String(length=16), nullable=False, server_default=""),
        sa.Column("blocked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("bot_id", "telegram_user_id", name="uq_bot_subscriber"),
    )
    op.create_index("ix_bot_subscribers_bot_id", "bot_subscribers", ["bot_id"])

    op.create_table(
        "subscriptions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("bot_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("bots.id", ondelete="CASCADE"), nullable=False),
        sa.Column(
            "block_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("bot_blocks.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("telegram_user_id", sa.BigInteger(), nullable=False),
        sa.Column("chat_id", sa.BigInteger(), nullable=False),
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column("billing_mode", sa.String(length=16), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="active"),
        sa.Column("period_days", sa.Integer(), nullable=False, server_default="30"),
        sa.Column("amount_minor", sa.BigInteger(), nullable=False),
        sa.Column("currency", sa.String(length=8), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False, server_default=""),
        sa.Column("current_period_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("periods_paid", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("provider_subscription_id", sa.String(length=255), nullable=True),
        sa.Column("granted_chat_id", sa.BigInteger(), nullable=True),
        sa.Column("meta", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_subscriptions_bot_id", "subscriptions", ["bot_id"])
    op.create_index("ix_subscriptions_telegram_user_id", "subscriptions", ["telegram_user_id"])
    op.create_index("ix_subscriptions_provider_subscription_id", "subscriptions", ["provider_subscription_id"])
    op.create_index("ix_subscriptions_period_end", "subscriptions", ["current_period_end"])

    op.create_table(
        "scheduled_steps",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("bot_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("bots.id", ondelete="CASCADE"), nullable=False),
        sa.Column(
            "block_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("bot_blocks.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("telegram_user_id", sa.BigInteger(), nullable=True),
        sa.Column("chat_id", sa.BigInteger(), nullable=False),
        sa.Column(
            "subscription_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("subscriptions.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column("reason", sa.String(length=32), nullable=False, server_default="delay"),
        sa.Column("run_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="pending"),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_error", sa.String(length=500), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("ran_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_scheduled_steps_bot_id", "scheduled_steps", ["bot_id"])
    op.create_index("ix_scheduled_steps_subscription_id", "scheduled_steps", ["subscription_id"])
    # Partial: everything already sent stays as history, and within a week of
    # real use it would otherwise dominate the one index the sweep uses.
    op.create_index(
        "ix_scheduled_steps_due",
        "scheduled_steps",
        ["run_at"],
        postgresql_where=sa.text("status = 'pending'"),
    )


def downgrade() -> None:
    op.drop_table("scheduled_steps")
    op.drop_table("subscriptions")
    op.drop_table("bot_subscribers")
