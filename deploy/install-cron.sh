#!/usr/bin/env bash
#
# Ставит в cron ежедневный бэкап (04:17) и сторожа (каждые 5 минут).
# Безопасно запускать сколько угодно раз: свои строки узнаются по метке
# «# botfactory:» и заменяются, чужие строки crontab не трогаются.
#
# Если в .env нет BACKUP_PASSPHRASE — создаёт его и ПЕЧАТАЕТ один раз:
# сохрани в менеджере паролей отдельно от сервера, без него бэкап не открыть.

set -euo pipefail

ROOT="$(cd "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")/.." && pwd)"
cd "$ROOT"

[ -f .env ] || { echo "нет .env в $ROOT" >&2; exit 1; }
command -v crontab >/dev/null || { echo "нет crontab — бэкап по расписанию не установлен" >&2; exit 1; }

if ! grep -qE '^BACKUP_PASSPHRASE=.+' .env; then
  PASS="$(head -c 24 /dev/urandom | od -An -tx1 | tr -d ' \n')"
  if grep -qE '^#?[[:space:]]*BACKUP_PASSPHRASE=' .env; then
    sed -i -E "0,/^#?[[:space:]]*BACKUP_PASSPHRASE=.*/s||BACKUP_PASSPHRASE=${PASS}|" .env
  else
    printf 'BACKUP_PASSPHRASE=%s\n' "$PASS" >> .env
  fi
  echo "!! Создан BACKUP_PASSPHRASE: $PASS"
  echo "!! Сохрани его в менеджере паролей ОТДЕЛЬНО от сервера — без него бэкап не расшифровать."
fi

chmod +x deploy/backup.sh deploy/watchdog.sh
TAG="# botfactory:"
BACKUP_LINE="17 4 * * * $ROOT/deploy/backup.sh >> /var/log/bf-backup.log 2>&1 $TAG backup"
WATCH_LINE="*/5 * * * * $ROOT/deploy/watchdog.sh >> /var/log/bf-watchdog.log 2>&1 $TAG watchdog"

CURRENT="$(crontab -l 2>/dev/null || true)"
{
  printf '%s\n' "$CURRENT" | grep -v "$TAG" || true
  echo "$BACKUP_LINE"
  echo "$WATCH_LINE"
} | crontab -
echo "Установлено: бэкап ежедневно в 04:17, сторож каждые 5 минут (журналы: /var/log/bf-*.log)"
