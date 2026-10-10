"""Сохранённые данные неактивных оплат бота.

Только добавление (expand): одна nullable-колонка.

Revision ID: 0026
Revises: 0025
"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "0026"
down_revision: Union[str, None] = "0025"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("bots", sa.Column("payment_saved_encrypted", sa.LargeBinary(), nullable=True))


def downgrade() -> None:
    op.drop_column("bots", "payment_saved_encrypted")
