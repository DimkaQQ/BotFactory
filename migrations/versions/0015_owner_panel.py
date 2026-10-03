"""Кабинет владельца в мета-боте: пауза бота и уведомления о продажах.

Две булевы колонки с безопасными значениями по умолчанию: бот не на паузе,
уведомления включены — то есть всё работает ровно так, как до миграции.

Revision ID: 0015
Revises: 0014
"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "0015"
down_revision: Union[str, None] = "0014"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("bots", sa.Column("paused", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("clients", sa.Column("notify_sales", sa.Boolean(), nullable=False, server_default=sa.true()))


def downgrade() -> None:
    op.drop_column("clients", "notify_sales")
    op.drop_column("bots", "paused")
