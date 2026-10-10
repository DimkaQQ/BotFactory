"""The bot's paid period.

Publishing was a one-off sale: pay once, the bot runs forever. A deployment
can now also charge per period, and that needs exactly one new fact per bot
— when the paid period runs out.

NULL is deliberate and load-bearing. Every bot that exists when this runs
has no clock, and backfilling one would drop every live bot into its grace
period the moment the column appeared. They stay on the old terms; only
what is launched after a price is configured gets a `paid_until`.

Nothing is needed for the new `renewal` payment kind: `payments.kind` is a
plain VARCHAR(16) with no CHECK behind it (see 0004), and the value fits.

Revision ID: 0008
Revises: 0007
"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "0008"
down_revision: Union[str, None] = "0007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("bots", sa.Column("paid_until", sa.DateTime(timezone=True), nullable=True))
    # How far the owner has already been warned about *this* period, so an
    # hourly sweep reminds once instead of every hour. Reset to 0 whenever
    # `paid_until` moves forward, which is what ties it to one period.
    op.add_column(
        "bots",
        sa.Column("billing_notice_stage", sa.SmallInteger(), nullable=False, server_default="0"),
    )
    # Only ever scanned for periods that are running out, soonest first.
    op.create_index("ix_bots_paid_until", "bots", ["paid_until"])


def downgrade() -> None:
    op.drop_index("ix_bots_paid_until", table_name="bots")
    op.drop_column("bots", "billing_notice_stage")
    # They refer to a period that no longer exists anywhere.
    op.execute("DELETE FROM payments WHERE kind = 'renewal'")
    op.drop_column("bots", "paid_until")
