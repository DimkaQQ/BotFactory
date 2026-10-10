"""Нажатия на кнопки: статистика и выбор покупателя в заказе.

Только добавление (expand): старый код таблицу не видит.

Revision ID: 0021
Revises: 0020
"""

from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0021"
down_revision: Union[str, None] = "0020"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "button_clicks",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("bot_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("bots.id", ondelete="CASCADE"), nullable=False),
        sa.Column("block_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("button_index", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("label", sa.String(64), nullable=False),
        sa.Column("collect_choice", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("telegram_user_id", sa.BigInteger(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_button_clicks_bot_id", "button_clicks", ["bot_id"])
    op.create_index("ix_button_clicks_telegram_user_id", "button_clicks", ["telegram_user_id"])
    op.create_index("ix_button_clicks_created_at", "button_clicks", ["created_at"])


def downgrade() -> None:
    op.drop_table("button_clicks")
