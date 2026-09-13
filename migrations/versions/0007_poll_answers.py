"""Poll answers, which used to go nowhere.

The «Опрос» block sent a real Telegram poll and the landing page sold it as
a way to «узнать, чего хотят подписчики» — but `poll_answer` was not in the
bot's `allowed_updates`, so Telegram never delivered the answers, and there
was no table to put them in if it had.

`telegram_poll_id` is the join: an incoming answer names Telegram's poll,
not our block, so the id is recorded when the poll is sent.

Revision ID: 0007
Revises: 0006
"""

from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0007"
down_revision: Union[str, None] = "0006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "poll_answers",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("bot_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("bots.id", ondelete="CASCADE"), nullable=False),
        sa.Column(
            "block_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("bot_blocks.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("telegram_user_id", sa.BigInteger(), nullable=False),
        sa.Column("telegram_poll_id", sa.String(length=64), nullable=False),
        sa.Column("option_ids", postgresql.ARRAY(sa.BigInteger()), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("block_id", "telegram_user_id", name="uq_poll_answer"),
    )
    op.create_index("ix_poll_answers_bot_id", "poll_answers", ["bot_id"])
    op.create_index("ix_poll_answers_block_id", "poll_answers", ["block_id"])
    op.create_index("ix_poll_answers_telegram_poll_id", "poll_answers", ["telegram_poll_id"])


def downgrade() -> None:
    op.drop_table("poll_answers")
