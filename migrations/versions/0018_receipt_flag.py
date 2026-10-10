"""Чек 54-ФЗ — только по явному флагу: тем, у кого почта для чеков уже заполнена, флаг ставится сейчас.

Revision ID: 0018
Revises: 0017

Раньше чек уходил, если в настройках кассы заполнена `fiscal_email`; теперь — только при
`fiscalization_enabled = 1` (см. `payments.base.fiscalization_enabled`). Чтобы ни у кого чеки не
пропали, флаг проставляется явно всем магазинам, у которых почта уже есть, а флага ещё нет.

Данные кассы лежат зашифрованными (Fernet), поэтому миграция читает их тем же ключом, что и
приложение: `FERNET_KEY` должен быть в окружении (у сервиса `migrate` он есть — `env_file: .env`).
Строка, которую расшифровать нельзя, пропускается: приложение читает её как пустые настройки, чека у
неё и так нет. Если не расшифровалась ни одна строка из непустых — это неверный ключ, и миграция
останавливается, а не молча оставляет магазины без чеков.
"""

import json
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "0018"
down_revision: Union[str, None] = "0017"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    rows = conn.execute(
        sa.text("SELECT id, payment_credentials_encrypted FROM bots WHERE payment_credentials_encrypted IS NOT NULL")
    ).fetchall()
    if not rows:
        return

    from app.services.security import decrypt_token, encrypt_token

    unreadable: list[str] = []
    switched = 0
    for bot_id, blob in rows:
        try:
            credentials = json.loads(decrypt_token(bytes(blob)))
        except Exception:  # noqa: BLE001 — неверный ключ или битые данные
            unreadable.append(str(bot_id))
            continue
        has_email = bool(str(credentials.get("fiscal_email") or "").strip())
        if has_email and "fiscalization_enabled" not in credentials:
            credentials["fiscalization_enabled"] = "1"
            conn.execute(
                sa.text("UPDATE bots SET payment_credentials_encrypted = :blob WHERE id = :id"),
                {"blob": encrypt_token(json.dumps(credentials, ensure_ascii=False)), "id": bot_id},
            )
            switched += 1

    if len(unreadable) == len(rows):
        raise RuntimeError(
            "0018: ни одни настройки касс не расшифровались — проверь FERNET_KEY в окружении миграции. "
            "Без этого флаг чека не проставить, а чеки без него больше не отправляются."
        )
    if unreadable:
        print(f"0018: не расшифрованы настройки касс у ботов {', '.join(unreadable)} — пропущены")
    print(f"0018: флаг чека включён у {switched} касс")


def downgrade() -> None:
    # Флаг — обычное поле настроек; прежний код его не читает и не мешает. Откатывать нечего.
    pass
