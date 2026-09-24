#!/usr/bin/env bash
#
# Один бэкап: база + загруженные файлы + .env, зашифровано и отправлено в
# Telegram.
#
# Почему в Telegram: копия, которая лежит на том же сервере, — не копия.
# Умер диск или хостер отключил машину — умерло и то и другое разом. Отправка
# в Telegram даёт копию вне сервера, сразу на телефоне, без отдельного
# аккаунта в облаке. Когда база перевалит за ~45 МБ, скрипт сам скажет, что
# пора заводить S3, и не будет молча ничего не отправлять.
#
# Почему зашифровано: в архиве лежит .env, а в нём FERNET_KEY. Без этого
# ключа бэкап базы бесполезен — токены ботов и ключи от касс расшифровать
# нечем. Вместе с ним архив стоит ровно столько же, сколько весь сервис,
# поэтому без BACKUP_PASSPHRASE скрипт не запускается вообще.
#
# Установка (раз в сутки в 04:17):
#   chmod +x deploy/backup.sh
#   crontab -e
#   17 4 * * * BACKUP_PASSPHRASE='…' /srv/botfactory/deploy/backup.sh >> /var/log/bf-backup.log 2>&1
#
# Восстановление описано в deploy/ops.md. Бэкап, из которого ни разу не
# восстанавливали, — это не бэкап, а надежда.

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

BACKUP_DIR="${BACKUP_DIR:-$ROOT/backups}"
KEEP="${BACKUP_KEEP:-14}"
# Telegram отказывает ботам в файлах больше 50 МБ. Порог ниже, чтобы
# предупреждение пришло раньше отказа.
MAX_SEND_MB="${BACKUP_MAX_SEND_MB:-45}"
# С секундами: два запуска в одну минуту иначе дали бы одно имя файла, и
# второй молча затёр бы первый.
STAMP="$(date -u +%Y-%m-%d_%H-%M-%S)"

log() { printf '%s  %s\n' "$(date -u +'%Y-%m-%d %H:%M:%S')" "$*"; }
die() { log "ОШИБКА: $*"; exit 1; }

[ -f .env ] || die "нет .env в $ROOT"
# shellcheck disable=SC1091
set -a; . ./.env; set +a

: "${BACKUP_PASSPHRASE:?нужен BACKUP_PASSPHRASE — в архиве лежит FERNET_KEY, без шифрования его отдавать нельзя}"
: "${META_BOT_TOKEN:?нужен META_BOT_TOKEN, чтобы прислать бэкап в Telegram}"
: "${BACKUP_CHAT_ID:?нужен BACKUP_CHAT_ID — твой Telegram id, куда слать архив}"

command -v openssl >/dev/null || die "нет openssl"
# Тот же адрес, что и у самого сервиса: на серверах в России api.telegram.org
# бывает недоступен напрямую, и там в .env уже стоит прокси (см. config.py).
# Скрипты обязаны ходить туда же, иначе бэкап и тревоги молча не дойдут —
# именно тогда, когда они нужнее всего.
TG_API="${TELEGRAM_API_BASE_URL:-https://api.telegram.org}"
mkdir -p "$BACKUP_DIR"

tell() {
  curl -sS --max-time 30 \
    "${TG_API}/bot${META_BOT_TOKEN}/sendMessage" \
    -d chat_id="${BACKUP_CHAT_ID}" \
    --data-urlencode "text=$1" >/dev/null || log "не смог написать в Telegram"
}

# Ошибка бэкапа, о которой никто не узнал, хуже отсутствия бэкапа: есть
# ложное спокойствие. Любой выход не по плану — сообщение в Telegram.
trap 'code=$?; [ $code -ne 0 ] && tell "🔴 Бэкап Bot Factory упал (код $code). Смотри /var/log/bf-backup.log"' EXIT

# --- 1. Дамп базы -----------------------------------------------------------
# Под docker compose pg_dump живёт внутри контейнера, локально — в системе.
dump_db() {
  if docker compose ps db --status running 2>/dev/null | grep -q db; then
    docker compose exec -T db pg_dump -U "${POSTGRES_USER:-botfactory}" "${POSTGRES_DB:-botfactory}"
  elif command -v pg_dump >/dev/null; then
    pg_dump "${DATABASE_URL/+asyncpg/}"
  else
    die "не нашёл ни контейнера db, ни pg_dump"
  fi
}

WORK="$(mktemp -d)"
trap 'code=$?; rm -rf "$WORK"; [ $code -ne 0 ] && tell "🔴 Бэкап Bot Factory упал (код $code). Смотри /var/log/bf-backup.log"' EXIT

log "снимаю дамп базы"
dump_db > "$WORK/db.sql"
[ -s "$WORK/db.sql" ] || die "дамп пустой"

# --- 2. Изменилось ли что-нибудь -------------------------------------------
# Отпечаток берётся не со всего файла. Выкинуты строки, которые меняются
# сами по себе:
#   * комментарии — pg_dump пишет в шапку время и версию;
#   * \restrict / \unrestrict — pg_dump 17+ ставит в них СЛУЧАЙНЫЙ токен,
#     новый на каждый запуск.
# Без этой чистки «только если есть новое» не сработало бы ни одного дня:
# каждый дамп отличался бы от предыдущего, и полный архив уезжал бы в
# Telegram ежедневно, даже если в базе не поменялось ни строки.
FINGERPRINT="$(grep -vE '^(--|\\restrict |\\unrestrict |$)' "$WORK/db.sql" | sha256sum | cut -d' ' -f1)"
LAST_FILE="$BACKUP_DIR/.last-fingerprint"

if [ -f "$LAST_FILE" ] && [ "$(cat "$LAST_FILE")" = "$FINGERPRINT" ]; then
  # Файлы могли добавиться и без единой строки в базе — но у нас любая
  # загрузка создаёт запись в блоке, так что база меняется вместе с ними.
  log "с прошлого раза ничего не изменилось — новый архив не нужен"
  exit 0
fi

# --- 3. Архив: база + файлы + .env -----------------------------------------
ARCHIVE="$BACKUP_DIR/botfactory-$STAMP.tar.gz.enc"
log "собираю архив"

MEDIA_DIR="${MEDIA_UPLOAD_DIR:-media_uploads}"
if docker volume ls -q 2>/dev/null | grep -q media_uploads; then
  # Тома docker не лежат в проекте; вытаскиваем их через временный контейнер.
  docker run --rm -v botfactory_media_uploads:/from -v "$WORK":/to alpine \
    sh -c 'cp -a /from/. /to/media 2>/dev/null || true' || true
elif [ -d "$MEDIA_DIR" ]; then
  cp -a "$MEDIA_DIR" "$WORK/media"
fi
mkdir -p "$WORK/media"
cp .env "$WORK/.env"

tar -C "$WORK" -czf - db.sql .env media \
  | openssl enc -aes-256-cbc -pbkdf2 -iter 200000 -salt \
      -pass env:BACKUP_PASSPHRASE -out "$ARCHIVE"

SIZE_MB=$(( $(stat -c%s "$ARCHIVE") / 1024 / 1024 ))
log "архив готов: $ARCHIVE (${SIZE_MB} МБ)"
echo "$FINGERPRINT" > "$LAST_FILE"

# --- 4. Унести с сервера ----------------------------------------------------
if [ "$SIZE_MB" -ge "$MAX_SEND_MB" ]; then
  tell "⚠️ Бэкап на ${SIZE_MB} МБ — Telegram столько от бота не примет (потолок 50 МБ).
Архив лежит на сервере: $ARCHIVE
Пора подключать внешнее хранилище — до тех пор копии вне сервера нет."
  log "слишком большой для Telegram, не отправляю"
else
  log "отправляю в Telegram"
  curl -sS --max-time 300 \
    "${TG_API}/bot${META_BOT_TOKEN}/sendDocument" \
    -F chat_id="${BACKUP_CHAT_ID}" \
    -F document=@"$ARCHIVE" \
    -F caption="🗄 Бэкап Bot Factory · $STAMP UTC · ${SIZE_MB} МБ
Расшифровать: openssl enc -d -aes-256-cbc -pbkdf2 -iter 200000 -in <файл> | tar xz" \
    >/dev/null || die "не смог отправить архив в Telegram"
fi

# --- 5. Убрать старое -------------------------------------------------------
# Нумерованная сортировка по имени = по дате, потому что имя начинается с даты.
ls -1 "$BACKUP_DIR"/botfactory-*.tar.gz.enc 2>/dev/null | sort | head -n -"$KEEP" | while read -r old; do
  log "удаляю старый: $old"
  rm -f "$old"
done

log "готово"
trap - EXIT
rm -rf "$WORK"
