"""Платёжные записи переживают удаление бота и аккаунта.

Раньше удаление бота или клиента каскадом стирало платежи — а это бухгалтерский
учёт и доказательства на случай споров. Теперь связь просто обнуляется
(колонки и так допускали NULL), а сами записи остаются.

Revision ID: 0016
Revises: 0015
"""

from typing import Sequence, Union

from alembic import op

revision: str = "0016"
down_revision: Union[str, None] = "0015"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _recreate(column: str, target: str, ondelete: str) -> None:
    name = f"payments_{column}_fkey"
    op.drop_constraint(name, "payments", type_="foreignkey")
    op.create_foreign_key(name, "payments", target, [column], ["id"], ondelete=ondelete)


def upgrade() -> None:
    _recreate("bot_id", "bots", "SET NULL")
    _recreate("client_id", "clients", "SET NULL")


def downgrade() -> None:
    _recreate("bot_id", "bots", "CASCADE")
    _recreate("client_id", "clients", "CASCADE")
