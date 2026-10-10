"""Явная отписка от рассылки.

Единственным способом перестать получать рассылку было заблокировать бота, а
`blocked_at` сбрасывается первым же сообщением от человека — то есть стоило
ему что-нибудь написать, и рассылки возобновлялись. Это не «мы не подумали»,
а причина, по которой на нас однажды пожалуются: человек, который не может
отписаться, жалуется не боту, а Telegram.

Отдельное поле, а не переиспользование `blocked_at`: «я не хочу писем» и
«бот у меня заблокирован» — разные факты с разными последствиями, и
объединять их значит терять оба.

Revision ID: 0010
Revises: 0009
"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "0010"
down_revision: Union[str, None] = "0009"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("bot_subscribers", sa.Column("unsubscribed_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("bot_subscribers", "unsubscribed_at")
