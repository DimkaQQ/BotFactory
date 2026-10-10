"""Запись о принятии условий: какая редакция оферты и когда.

Только добавление двух необязательных колонок: существующие строки остаются
как есть (пусто = регистрация была до появления записи), никакой пересчёт не
нужен.

Revision ID: 0013
Revises: 0012
"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "0013"
down_revision: Union[str, None] = "0012"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("clients", sa.Column("terms_version", sa.String(16), nullable=True))
    op.add_column("clients", sa.Column("terms_accepted_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("clients", "terms_accepted_at")
    op.drop_column("clients", "terms_version")
