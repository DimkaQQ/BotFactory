"""Отправленные опросы: какой poll_id какому блоку принадлежит.

Telegram выдаёт НОВЫЙ `poll_id` на каждый чат, а хранился он в одном поле
`content["telegram_poll_id"]` — то есть каждая следующая отправка затирала
предыдущую, и ответы принимались только от того подписчика, кому опрос ушёл
последним. Всем остальным отвечало молчание.

Одна строка на отправку. `telegram_poll_id` уникален — он и есть то, что
приходит в ответе.

Revision ID: 0009
Revises: 0008
"""

from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0009"
down_revision: Union[str, None] = "0008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "poll_sends",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("bot_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("bots.id", ondelete="CASCADE"), nullable=False),
        sa.Column(
            "block_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("bot_blocks.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("telegram_poll_id", sa.String(length=64), nullable=False, unique=True),
        sa.Column("chat_id", sa.BigInteger(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_poll_sends_block_id", "poll_sends", ["block_id"])


def downgrade() -> None:
    op.drop_table("poll_sends")
