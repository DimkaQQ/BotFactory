"""Чат поддержки: какому человеку принадлежит сообщение.

Новая таблица, существующих данных не касается.

Revision ID: 0014
Revises: 0013
"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "0014"
down_revision: Union[str, None] = "0013"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "support_relay",
        sa.Column("admin_message_id", sa.BigInteger(), primary_key=True, autoincrement=False),
        sa.Column("user_chat_id", sa.BigInteger(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_support_relay_user_chat_id", "support_relay", ["user_chat_id"])


def downgrade() -> None:
    op.drop_index("ix_support_relay_user_chat_id", table_name="support_relay")
    op.drop_table("support_relay")
