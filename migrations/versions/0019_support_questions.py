"""Поддержка: помним текст вопросов, чтобы ответ приходил одним сообщением вместе с ними.

Revision ID: 0019
Revises: 0018
"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "0019"
down_revision: Union[str, None] = "0018"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("support_relay", sa.Column("question_text", sa.Text(), nullable=True))
    op.add_column("support_relay", sa.Column("answered_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("support_relay", "answered_at")
    op.drop_column("support_relay", "question_text")
