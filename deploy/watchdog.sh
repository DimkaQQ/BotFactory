#!/usr/bin/env bash
#
# Сторож: раз в пять минут проверяет, что сервис жив, и пишет в Telegram,
# когда что-то сломалось — и когда починилось.
#
# Чего он НЕ умеет, и это важно понимать сразу: он крутится на том же
# сервере. Если сервер выключился, сгорел диск или хостер отрубил машину —
# сторож умрёт вместе с ним и не напишет ничего. Тишина от него не означает
# «всё хорошо».
#
# Поэтому он умеет второе: посылать «я жив» на внешний адрес (HEARTBEAT_URL,
# подойдёт бесплатный healthchecks.io или Better Stack). Перестали приходить
# сигналы — внешний сервис напишет сам. Только эта пара закрывает и «упало
# приложение», и «упал сервер».
#
# Установка:
#   chmod +x deploy/watchdog.sh
#   crontab -e
#   */5 * * * * /srv/botfactory/deploy/watchdog.sh >> /var/log/bf-watchdog.log 2>&1

set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

STATE_DIR="${WATCHDOG_STATE_DIR:-/var/tmp/bf-watchdog}"
HEALTH_URL="${HEALTH_URL:-http://127.0.0.1:8000/health}"
DISK_LIMIT="${DISK_LIMIT_PERCENT:-85}"

log() { printf '%s  %s\n' "$(date -u +'%Y-%m-%d %H:%M:%S')" "$*"; }

[ -f .env ] || { log "нет .env"; exit 1; }
# shellcheck disable=SC1091
set -a; . ./.env; set +a
mkdir -p "$STATE_DIR"
# Тот же адрес, что и у самого сервиса: на серверах в России api.telegram.org
# бывает недоступен напрямую, и там в .env уже стоит прокси (см. config.py).
# Скрипты обязаны ходить туда же, иначе бэкап и тревоги молча не дойдут —
# именно тогда, когда они нужнее всего.
TG_API="${TELEGRAM_API_BASE_URL:-https://api.telegram.org}"

tell() {
  [ -n "${META_BOT_TOKEN:-}" ] && [ -n "${BACKUP_CHAT_ID:-}" ] || { log "некуда писать"; return; }
  curl -sS --max-time 20 \
    "${TG_API}/bot${META_BOT_TOKEN}/sendMessage" \
    -d chat_id="${BACKUP_CHAT_ID}" \
    --data-urlencode "text=$1" >/dev/null || log "не смог написать в Telegram"
}

# Сообщение только на смене состояния. Без этого «нет места на диске» пришло
# бы 288 раз за сутки, и на третий день их перестали бы читать — ровно перед
# тем, как случится что-то настоящее.
report() {
  local name="$1" ok="$2" detail="$3"
  local file="$STATE_DIR/$name"
  local was="ok"
  [ -f "$file" ] && was="$(cat "$file")"

  if [ "$ok" = "yes" ]; then
    if [ "$was" != "ok" ]; then
      tell "✅ Восстановилось: $name"
      log "восстановилось: $name"
    fi
    echo ok > "$file"
  else
    if [ "$was" = "ok" ]; then
      tell "🔴 Bot Factory: $detail"
      log "упало: $name — $detail"
    else
      log "всё ещё лежит: $name"
    fi
    echo fail > "$file"
  fi
}

FAILED=0

# --- 1. API и база ----------------------------------------------------------
# /health ходит в базу (см. app/main.py), поэтому одна проверка закрывает обе:
# раньше он возвращал константу и бодро отвечал «ok» при мёртвой базе.
BODY="$(curl -sS --max-time 10 -w '\n%{http_code}' "$HEALTH_URL" 2>/dev/null)"
CODE="$(printf '%s' "$BODY" | tail -n1)"
if [ "$CODE" = "200" ]; then
  report api yes ""
else
  report api no "не отвечает API ($HEALTH_URL, код ${CODE:-нет ответа}). Боты сейчас не принимают оплату."
  FAILED=1
fi

# --- 2. Контейнеры ----------------------------------------------------------
if command -v docker >/dev/null && [ -f docker-compose.yml ]; then
  DOWN="$(docker compose ps --format '{{.Service}} {{.State}}' 2>/dev/null \
          | awk '$2 != "running" { printf "%s ", $1 }')"
  if [ -z "$DOWN" ]; then
    report containers yes ""
  else
    report containers no "не запущены контейнеры: $DOWN"
    FAILED=1
  fi
fi

# --- 3. Диск ----------------------------------------------------------------
# Кончившееся место — самая частая смерть маленького сервера, и выглядит она
# как что угодно, кроме кончившегося места: Postgres перестаёт писать, боты
# молчат, в логах ерунда.
USED="$(df --output=pcent / | tail -n1 | tr -dc '0-9')"
if [ "${USED:-0}" -lt "$DISK_LIMIT" ]; then
  report disk yes ""
else
  report disk no "диск занят на ${USED}% (порог ${DISK_LIMIT}%). Postgres скоро перестанет писать."
  FAILED=1
fi

# --- 4. Свежесть бэкапа -----------------------------------------------------
# Бэкап тихо перестал делаться — узнать об этом хочется не в день восстановления.
BACKUP_DIR="${BACKUP_DIR:-$ROOT/backups}"
NEWEST="$(ls -1t "$BACKUP_DIR"/botfactory-*.tar.gz.enc 2>/dev/null | head -n1)"
if [ -z "$NEWEST" ]; then
  report backup no "ни одного бэкапа в $BACKUP_DIR — бэкап не настроен или падает молча."
elif [ "$(find "$NEWEST" -mtime +2 | wc -l)" -gt 0 ]; then
  report backup no "последний бэкап старше двух суток: $(basename "$NEWEST")"
else
  report backup yes ""
fi

# --- 5. «Я жив» наружу ------------------------------------------------------
# Только когда всё в порядке: иначе внешний сервис будет считать, что сервер
# здоров, ровно в тот момент, когда он не здоров.
if [ -n "${HEARTBEAT_URL:-}" ] && [ "$FAILED" -eq 0 ]; then
  curl -sS --max-time 10 "$HEARTBEAT_URL" >/dev/null || log "не смог отправить heartbeat"
fi

exit 0
