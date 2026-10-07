"""Напоминания о записи: отметки, что напоминание клиенту уже ушло.

Только добавление (expand): пустые колонки.

Revision ID: 0023
Revises: 0022
"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "0023"
down_revision: Union[str, None] = "0022"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("bookings", sa.Column("reminded_day_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("bookings", sa.Column("reminded_hours_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("bookings", "reminded_hours_at")
    op.drop_column("bookings", "reminded_day_at")
