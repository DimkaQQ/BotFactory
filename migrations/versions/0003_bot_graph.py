"""bot dialogue graph: next_block_id, canvas position, start_block_id

Backfills existing bots' implicit order_index sequence into an explicit
linear next_block_id chain (+ a simple vertical canvas layout + start_block_id
pointing at the first block), so every bot built before the visual flow
editor keeps dispatching exactly as it did under the old order_index-only
model — nothing to migrate by hand, nothing changes for a client who never
opens the new canvas.

Revision ID: 0003
Revises: 0002
Create Date: 2026-08-16

"""
from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0003"
down_revision: Union[str, None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_ROW_HEIGHT = 160
_START_X = 80
_START_Y = 80


def upgrade() -> None:
    op.add_column(
        "bot_blocks",
        sa.Column(
            "next_block_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("bot_blocks.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.add_column("bot_blocks", sa.Column("position_x", sa.Float(), nullable=False, server_default="0"))
    op.add_column("bot_blocks", sa.Column("position_y", sa.Float(), nullable=False, server_default="0"))
    op.create_index("ix_bot_blocks_next_block_id", "bot_blocks", ["next_block_id"])

    op.add_column(
        "bots",
        sa.Column(
            "start_block_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("bot_blocks.id", ondelete="SET NULL", use_alter=True, name="fk_bots_start_block_id"),
            nullable=True,
        ),
    )

    conn = op.get_bind()
    bot_ids = [row[0] for row in conn.execute(sa.text("SELECT id FROM bots")).fetchall()]
    for bot_id in bot_ids:
        block_ids = [
            row[0]
            for row in conn.execute(
                sa.text("SELECT id FROM bot_blocks WHERE bot_id = :bot_id ORDER BY order_index"),
                {"bot_id": bot_id},
            ).fetchall()
        ]
        for i, block_id in enumerate(block_ids):
            next_id = block_ids[i + 1] if i + 1 < len(block_ids) else None
            conn.execute(
                sa.text(
                    "UPDATE bot_blocks SET next_block_id = :next_id, position_x = :x, position_y = :y WHERE id = :id"
                ),
                {"next_id": next_id, "x": _START_X, "y": _START_Y + i * _ROW_HEIGHT, "id": block_id},
            )
        if block_ids:
            conn.execute(
                sa.text("UPDATE bots SET start_block_id = :start WHERE id = :bot_id"),
                {"start": block_ids[0], "bot_id": bot_id},
            )


def downgrade() -> None:
    op.drop_column("bots", "start_block_id")
    op.drop_index("ix_bot_blocks_next_block_id", table_name="bot_blocks")
    op.drop_column("bot_blocks", "position_y")
    op.drop_column("bot_blocks", "position_x")
    op.drop_column("bot_blocks", "next_block_id")
