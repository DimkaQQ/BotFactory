"""Выход из аккаунта, который действительно закрывает доступ.

Кнопки «Выйти» не было вовсе, а когда она появилась, она стирала токен
только в браузере. Сам токен оставался действительным тридцать дней, и
отозвать его было нечем: за ним касса, список покупателей и кнопка снятия
бота с эфира. На чужом или общем компьютере это ровно то, ради чего выход
и нажимают.

Отметка на клиенте, а не таблица сессий: токен и так несёт время выпуска,
и сравнить его с одной датой дешевле, чем держать строку на каждое устройство.
Цена — выход сразу на всех устройствах; для аккаунта, у которого один
владелец, это скорее то, чего от кнопки и ждут.

Revision ID: 0012
Revises: 0011
"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "0012"
down_revision: Union[str, None] = "0011"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("clients", sa.Column("sessions_valid_from", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("clients", "sessions_valid_from")
