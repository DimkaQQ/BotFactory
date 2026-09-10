"""Mark every already-delivered order as delivered.

Delivery moved to a background task, and to survive a restart mid-flight the
code now records `meta.delivered_at` when the goods actually go out, then
re-delivers anything paid that lacks it.

Every order paid before this field existed lacks it — so without this
backfill the first startup after the upgrade would look at a shop's entire
history and conclude that none of it was ever delivered, re-sending the
goods (and "✅ Оплата получена, спасибо!") to every past buyer.

The stamp is deliberately the payment's own `paid_at` rather than now: it
says when the order was handed over, and for these it was at payment time.

Revision ID: 0005
Revises: 0004
"""

from typing import Sequence, Union

from alembic import op

revision: str = "0005"
down_revision: Union[str, None] = "0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        UPDATE payments
           SET meta = COALESCE(meta, '{}'::jsonb)
                      || jsonb_build_object(
                             'delivered_at',
                             to_char(COALESCE(paid_at, created_at) AT TIME ZONE 'UTC',
                                     'YYYY-MM-DD"T"HH24:MI:SS"+00:00"'))
         WHERE kind = 'order'
           AND status = 'paid'
           AND NOT (COALESCE(meta, '{}'::jsonb) ? 'delivered_at')
        """
    )


def downgrade() -> None:
    op.execute(
        """
        UPDATE payments
           SET meta = COALESCE(meta, '{}'::jsonb) - 'delivered_at'
         WHERE kind = 'order'
        """
    )
