"""Ограничения на колонки-перечисления.

Колонки объявлены как `SAEnum(..., native_enum=False)`, то есть приложение
считает их перечислениями, — а в базе это обычный VARCHAR без единой
проверки: таблицы создавались через `sa.String`. Разница обнаружилась
буквально: в `bots.status` попало значение `published`, которого в
перечислении нет, и строка стала нечитаемой — SQLAlchemy бросает
`LookupError` при чтении, то есть бот исчезает из списка вместе с ошибкой
500, и починить это можно только руками в базе.

Пишет такие значения не человек — их пишет приложение, — но ровно поэтому
проверка и нужна: плохое значение может появиться от миграции, от ручной
правки во время аварии или от будущей ошибки, и лучше получить отказ в
момент записи, чем нечитаемую строку неизвестно когда.

`reason` у отложенных шагов намеренно остаётся свободной строкой: это не
перечисление в коде, а пометка «зачем поставлен шаг», и новый вид работы не
должен требовать миграции.

Revision ID: 0011
Revises: 0010
"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "0011"
down_revision: Union[str, None] = "0010"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

#: (таблица, колонка, имя ограничения, допустимые значения)
_CHECKS = [
    ("bots", "status", "ck_bots_status", ("draft", "active", "disabled")),
    ("payments", "kind", "ck_payments_kind", ("order", "publication", "renewal")),
    ("payments", "status", "ck_payments_status", ("pending", "paid", "failed", "refunded")),
    ("scheduled_steps", "status", "ck_scheduled_steps_status", ("pending", "sent", "failed", "cancelled")),
    ("subscriptions", "status", "ck_subscriptions_status", ("active", "expired", "cancelled")),
    ("subscriptions", "billing_mode", "ck_subscriptions_billing_mode", ("auto", "renewal")),
]


def upgrade() -> None:
    for table, column, name, values in _CHECKS:
        # Строки, уже нарушающие правило, не дали бы создать ограничение —
        # а данные ценнее правила. Они помечаются и остаются как есть;
        # ограничение вешается NOT VALID, то есть стережёт новые записи, а
        # старые не трогает.
        listed = ", ".join(f"'{value}'" for value in values)
        bad = op.get_bind().execute(
            sa.text(f"SELECT count(*) FROM {table} WHERE {column} NOT IN ({listed})")
        ).scalar()
        if bad:
            print(f"ВНИМАНИЕ: в {table}.{column} {bad} строк(и) с неизвестным значением — ограничение NOT VALID")
        op.execute(
            f"ALTER TABLE {table} ADD CONSTRAINT {name} "
            f"CHECK ({column} IN ({listed})) NOT VALID"
        )
        if not bad:
            # Чисто — проверяем и старые строки тоже, чтобы ограничение было
            # полноценным, а не только на будущее.
            op.execute(f"ALTER TABLE {table} VALIDATE CONSTRAINT {name}")


def downgrade() -> None:
    for table, _column, name, _values in _CHECKS:
        op.execute(f"ALTER TABLE {table} DROP CONSTRAINT IF EXISTS {name}")
