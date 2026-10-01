#!/usr/bin/env bash
#
# ПЕРВАЯ установка на чистый VPS. Запускается ОДИН раз.
# Для всех последующих обновлений используй deploy/deploy.sh.
#
#   sudo ./deploy/deployfirst.sh                 # с вопросами
#   sudo ./deploy/deployfirst.sh --mode shared   # на сервере уже есть свой nginx
#
# Режимы:
#   caddy   чистый сервер: Caddy сам займёт 80/443 и выпустит сертификат (по умолчанию)
#   shared  на хосте уже стоит nginx: проект слушает 127.0.0.1:8010,
#           в nginx добавляется vhost, сертификат выпускает certbot
#
# Что делает: ставит Docker (если нет), готовит .env (сам генерирует ключи и
# пароль базы), поднимает проект, ждёт /health, настраивает TLS, ставит
# бэкап и сторож в cron. В конце пишет метку .deployfirst.done — после неё
# скрипт отказывается запускаться, чтобы случайный повторный запуск не
# перезаписал .env и не разрушил рабочий сервер.

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

DONE_MARK=".deployfirst.done"
MODE_FILE=".deploy-mode"
MODE="caddy"
FORCE=0

c_red=$'\e[31m'; c_grn=$'\e[32m'; c_ylw=$'\e[33m'; c_off=$'\e[0m'
say()  { printf '%s\n' "${c_grn}==>${c_off} $*"; }
warn() { printf '%s\n' "${c_ylw}!!${c_off}  $*" >&2; }
die()  { printf '%s\n' "${c_red}ОШИБКА:${c_off} $*" >&2; exit 1; }

while [ $# -gt 0 ]; do
  case "$1" in
    --mode) MODE="${2:-}"; shift 2 ;;
    --force) FORCE=1; shift ;;
    -h|--help) sed -n '2,20p' "$0"; exit 0 ;;
    *) die "неизвестный параметр: $1" ;;
  esac
done
case "$MODE" in caddy|shared) ;; *) die "--mode: caddy или shared" ;; esac

# ---------------------------------------------------------------- защита

if [ -f "$DONE_MARK" ]; then
  die "первая установка уже выполнена ($(cat "$DONE_MARK")).
    Для обновления запускай:  ./deploy/deploy.sh
    Этот скрипт нужен ровно один раз и повторно не запустится."
fi

# Следы живой установки без метки (например, ставили руками по README):
# запуск поверх них перезаписал бы .env и потерял бы ключи.
if [ "$FORCE" -ne 1 ]; then
  if docker volume ls -q 2>/dev/null | grep -q "db_data$"; then
    die "на этом сервере уже есть база проекта (docker volume *_db_data).
    Это не первая установка. Обновляй через:  ./deploy/deploy.sh --mode $MODE
    Если ты точно знаешь, что делаешь, — добавь --force."
  fi
fi

[ "$(id -u)" -eq 0 ] || die "запусти от root:  sudo ./deploy/deployfirst.sh"

# ---------------------------------------------------------------- помощники

env_get() { grep -E "^$1=" .env 2>/dev/null | tail -n1 | cut -d= -f2- || true; }

env_set() {  # env_set KEY VALUE — заменить строку или дописать
  local key="$1" val="$2" esc
  esc="$(printf '%s' "$val" | sed -e 's/[\\|&]/\\&/g')"
  if grep -qE "^#?[[:space:]]*${key}=" .env; then
    sed -i -E "0,/^#?[[:space:]]*${key}=.*/s||${key}=${esc}|" .env
  else
    printf '%s=%s\n' "$key" "$val" >> .env
  fi
}

ask() {  # ask "вопрос" [значение_по_умолчанию]
  local prompt="$1" def="${2:-}" reply
  if [ -n "$def" ]; then read -r -p "$prompt [$def]: " reply; echo "${reply:-$def}"
  else read -r -p "$prompt: " reply; echo "$reply"; fi
}

need_value() {  # need_value KEY "вопрос" — спросить, если пусто или плейсхолдер
  local key="$1" prompt="$2" cur
  cur="$(env_get "$key")"
  case "$cur" in
    ""|*your-domain.com*|*YourMetaBot*|*"your-meta-bot-token"*)
      cur="$(ask "$prompt")"
      [ -n "$cur" ] || die "$key обязателен"
      env_set "$key" "$cur" ;;
  esac
}

# ---------------------------------------------------------------- Docker

if ! command -v docker >/dev/null 2>&1; then
  say "Docker не найден — ставлю"
  curl -fsSL https://get.docker.com | sh
fi
docker compose version >/dev/null 2>&1 || die "нет плагина docker compose — поставь docker-compose-plugin"
command -v git >/dev/null 2>&1 || die "нужен git"
command -v curl >/dev/null 2>&1 || die "нужен curl"

# ---------------------------------------------------------------- .env

say "Готовлю .env"
if [ ! -f .env ]; then
  cp .env.example .env
  chmod 600 .env

  # Ключ Fernet — это 32 случайных байта в urlsafe-base64; Docker для этого не нужен.
  FERNET="$(head -c 32 /dev/urandom | base64 | tr '+/' '-_' | tr -d '\n')"
  [ -n "$FERNET" ] || die "не удалось сгенерировать FERNET_KEY"
  env_set FERNET_KEY "$FERNET"
  env_set WEBHOOK_SECRET_KEY "$(head -c 32 /dev/urandom | od -An -tx1 | tr -d ' \n')"
  env_set POSTGRES_PASSWORD "$(head -c 24 /dev/urandom | od -An -tx1 | tr -d ' \n')"
  env_set BACKUP_PASSPHRASE "$(head -c 24 /dev/urandom | od -An -tx1 | tr -d ' \n')"
  env_set CORS_ORIGINS ""
else
  warn ".env уже есть — оставляю как есть, дополняю только недостающее"
fi
chmod 600 .env

need_value META_BOT_TOKEN    "Токен мета-бота (от @BotFather)"
need_value META_BOT_USERNAME "Username мета-бота без @"
need_value PUBLIC_BASE_URL   "Публичный адрес сайта, например https://bots.example.com"

PUBLIC_URL="$(env_get PUBLIC_BASE_URL)"
case "$PUBLIC_URL" in https://*) ;; *) die "PUBLIC_BASE_URL должен начинаться с https://" ;; esac
DOMAIN_NAME="${PUBLIC_URL#https://}"; DOMAIN_NAME="${DOMAIN_NAME%%/*}"
env_set DOMAIN "$DOMAIN_NAME"
env_set CORS_ORIGINS "$PUBLIC_URL"

# Адрес куда приходят бэкапы и тревоги
if [ -z "$(env_get BACKUP_CHAT_ID)" ]; then
  chat="$(ask "Твой Telegram id для бэкапов и тревог (узнать: @userinfobot; Enter — пропустить)" "")"
  [ -z "$chat" ] || env_set BACKUP_CHAT_ID "$chat"
fi

# ---------------------------------------------------------------- DNS и порты

say "Проверяю DNS для $DOMAIN_NAME"
MY_IP="$(curl -fsS https://api.ipify.org 2>/dev/null || true)"
DNS_IP="$(getent hosts "$DOMAIN_NAME" 2>/dev/null | awk '{print $1; exit}' || true)"
if [ -n "$MY_IP" ] && [ -n "$DNS_IP" ] && [ "$MY_IP" != "$DNS_IP" ]; then
  warn "$DOMAIN_NAME указывает на $DNS_IP, а IP сервера — $MY_IP. Сертификат не выпустится, пока DNS не исправлен."
  [ "$(ask "Продолжить всё равно? (y/N)" "N")" = "y" ] || die "исправь A-запись и запусти заново"
elif [ -z "$DNS_IP" ]; then
  warn "у $DOMAIN_NAME нет A-записи. Сертификат не выпустится."
  [ "$(ask "Продолжить всё равно? (y/N)" "N")" = "y" ] || die "создай A-запись и запусти заново"
fi

if command -v ufw >/dev/null 2>&1 && ufw status 2>/dev/null | grep -q "Status: active"; then
  say "Открываю 80 и 443 в ufw"
  ufw allow 80,443/tcp >/dev/null
fi

# ---------------------------------------------------------------- запуск

if [ "$MODE" = "caddy" ]; then
  COMPOSE=(docker compose -f docker-compose.yml -f docker-compose.prod.yml)
else
  COMPOSE=(docker compose -f docker-compose.yml -f docker-compose.shared-vps.yml)
fi

say "Собираю и запускаю (режим: $MODE) — первый раз это несколько минут"
"${COMPOSE[@]}" up -d --build

say "Жду, пока API ответит на /health"
ok=0
for _ in $(seq 1 60); do
  if "${COMPOSE[@]}" exec -T api python -c \
      "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/health',timeout=4).status==200 else 1)" \
      >/dev/null 2>&1; then ok=1; break; fi
  sleep 3
done
if [ "$ok" -ne 1 ]; then
  "${COMPOSE[@]}" logs --tail=60 api migrate || true
  die "API не поднялся за 3 минуты. Логи выше. Исправь причину и запусти ./deploy/deploy.sh --mode $MODE"
fi

# ---------------------------------------------------------------- TLS

if [ "$MODE" = "shared" ]; then
  command -v nginx >/dev/null 2>&1 || die "режим shared требует nginx на хосте"
  say "Добавляю vhost в nginx"
  VHOST=/etc/nginx/sites-available/botfactory.conf
  sed "s/your-domain.com/$DOMAIN_NAME/g" deploy/nginx-vhost.example.conf > "$VHOST"
  ln -sf "$VHOST" /etc/nginx/sites-enabled/botfactory.conf
  nginx -t
  systemctl reload nginx
  if command -v certbot >/dev/null 2>&1; then
    email="$(ask "Email для Let's Encrypt (уведомления о сертификате)")"
    certbot --nginx -d "$DOMAIN_NAME" --non-interactive --agree-tos -m "$email" --redirect \
      || warn "certbot не справился — запусти вручную: certbot --nginx -d $DOMAIN_NAME"
  else
    warn "certbot не установлен. Поставь его и выполни: certbot --nginx -d $DOMAIN_NAME"
  fi
else
  say "Caddy сам получит сертификат при первом запросе (логи: docker compose logs -f caddy)"
fi

# ---------------------------------------------------------------- бэкап и сторож

chmod +x deploy/backup.sh deploy/watchdog.sh deploy/deploy.sh 2>/dev/null || true
if [ -n "$(env_get BACKUP_CHAT_ID)" ]; then
  say "Ставлю бэкап и сторож в cron"
  CRON_TMP="$(mktemp)"
  crontab -l 2>/dev/null | grep -v "botfactory-managed" > "$CRON_TMP" || true
  {
    echo "17 4 * * * $ROOT/deploy/backup.sh >> /var/log/bf-backup.log 2>&1  # botfactory-managed"
    echo "*/5 * * * * $ROOT/deploy/watchdog.sh >> /var/log/bf-watchdog.log 2>&1  # botfactory-managed"
  } >> "$CRON_TMP"
  crontab "$CRON_TMP"; rm -f "$CRON_TMP"
else
  warn "BACKUP_CHAT_ID не задан — бэкапы и сторож НЕ включены (см. deploy/ops.md)"
fi

# ---------------------------------------------------------------- метка

echo "$MODE" > "$MODE_FILE"
date -u +"установлено %Y-%m-%d %H:%M:%S UTC, режим $MODE" > "$DONE_MARK"
# Том загрузок создан уже под нужным владельцем — отдельный chown в deploy.sh не нужен.
touch .media_chown_done

cat <<MSG

${c_grn}Готово.${c_off}  Открой:  $PUBLIC_URL

ОБЯЗАТЕЛЬНО СОХРАНИ В МЕНЕДЖЕР ПАРОЛЕЙ (без них бэкапы и данные бесполезны):
  FERNET_KEY        = $(env_get FERNET_KEY)
  BACKUP_PASSPHRASE = $(env_get BACKUP_PASSPHRASE)

Не забудь в @BotFather для мета-бота:  /setdomain  →  $DOMAIN_NAME

Дальше обновлять проект так:  ./deploy/deploy.sh
Этот скрипт больше не запустится (метка $DONE_MARK).
MSG
