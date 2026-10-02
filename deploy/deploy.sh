#!/usr/bin/env bash
#
# Обновление и перезапуск уже установленного проекта. Безопасно запускать
# сколько угодно раз.
#
#   ./deploy/deploy.sh                  # подтянуть свежий код и перезапустить
#   ./deploy/deploy.sh --branch main    # обновиться с другой ветки
#   ./deploy/deploy.sh --restart        # только перезапуск, без обновления кода
#   ./deploy/deploy.sh --dry-run        # репетиция: получит код и соберёт образы, работающие
#                                       # контейнеры не трогает (папка проекта обновится)
#   ./deploy/deploy.sh --rollback       # вернуться на предыдущую версию кода
#   ./deploy/deploy.sh --mode caddy     # задать режим вручную (обычно определяется сам)
#
# Рассчитан на УЖЕ РАБОТАЮЩИЙ сервер: пока идёт сборка нового образа, старая
# версия продолжает отвечать. Порядок: проверки → копия базы → git pull →
# сборка (старое ещё живо) → миграции и перезапуск (пауза в секунды) →
# ожидание /health. Если новая версия не поднялась и миграций не было,
# скрипт сам возвращает прежний код; если миграции были — печатает, что делать.
#
# Первая установка — отдельный скрипт deploy/deployfirst.sh.

set -euo pipefail

# Всё ниже лежит в функции не случайно: обновление кода (git merge) может
# заменить этот самый файл прямо во время работы, а bash читает скрипт по
# кускам и тогда выполнил бы обрывок новой версии. Функция разбирается целиком
# до первого запуска.
main() {

ROOT="$(cd "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")/.." && pwd)"
cd "$ROOT"

MODE_FILE=".deploy-mode"
PREV_FILE=".deploy-prev"
BACKUP_DIR="${BACKUP_DIR:-$ROOT/backups}"
KEEP_DUMPS=7

c_red=$'\e[31m'; c_grn=$'\e[32m'; c_ylw=$'\e[33m'; c_off=$'\e[0m'
say()  { printf '%s\n' "${c_grn}==>${c_off} $*"; }
warn() { printf '%s\n' "${c_ylw}!!${c_off}  $*" >&2; }
die()  { printf '%s\n' "${c_red}ОШИБКА:${c_off} $*" >&2; exit 1; }

BRANCH=""; RESTART_ONLY=0; ROLLBACK=0; MODE_ARG=""; DRY=0
while [ $# -gt 0 ]; do
  case "$1" in
    --branch)   BRANCH="${2:-}"; shift 2 ;;
    --restart)  RESTART_ONLY=1; shift ;;
    --rollback) ROLLBACK=1; shift ;;
    --dry-run)  DRY=1; shift ;;
    --mode)     MODE_ARG="${2:-}"; shift 2 ;;
    -h|--help)  sed -n '2,20p' "$0"; exit 0 ;;
    *) die "неизвестный параметр: $1" ;;
  esac
done

# ---------------------------------------------------------------- проверки

command -v docker >/dev/null 2>&1 || die "Docker не установлен"
docker compose version >/dev/null 2>&1 || die "нет плагина docker compose"
[ -f .env ] || die "нет .env — сначала первая установка: sudo ./deploy/deployfirst.sh"

if [ -n "$MODE_ARG" ]; then
  case "$MODE_ARG" in caddy|shared) echo "$MODE_ARG" > "$MODE_FILE" ;; *) die "--mode: caddy или shared" ;; esac
fi
if [ ! -f "$MODE_FILE" ]; then
  # Сервер ставили вручную: смотрим, что реально запущено. Ошибка здесь
  # опасна (не те файлы compose = другие контейнеры), поэтому угадываем
  # только по однозначным признакам и просим подтвердить.
  running="$(docker ps --format '{{.Names}} {{.Ports}}' 2>/dev/null || true)"
  guess=""
  if printf '%s' "$running" | grep -qi 'caddy'; then guess="caddy"
  elif printf '%s' "$running" | grep -q '127.0.0.1:8010->80'; then guess="shared"; fi
  [ -n "$guess" ] || die "не удалось определить режим установки (нет $MODE_FILE).
    Укажи один раз:  ./deploy/deploy.sh --mode caddy   (есть контейнер caddy)
                или:  ./deploy/deploy.sh --mode shared  (свой nginx на хосте, порт 8010)"
  say "Похоже, установка в режиме «$guess» (по запущенным контейнерам)."
  read -r -p "Верно? (y/N) " reply
  [ "$reply" = "y" ] || die "тогда задай явно: ./deploy/deploy.sh --mode caddy|shared"
  echo "$guess" > "$MODE_FILE"
fi
MODE="$(cat "$MODE_FILE")"
if [ "$MODE" = "caddy" ]; then
  COMPOSE=(docker compose -f docker-compose.yml -f docker-compose.prod.yml)
else
  COMPOSE=(docker compose -f docker-compose.yml -f docker-compose.shared-vps.yml)
fi

env_get() { grep -E "^$1=" .env 2>/dev/null | tail -n1 | cut -d= -f2- || true; }

wait_healthy() {
  for _ in $(seq 1 60); do
    if "${COMPOSE[@]}" exec -T api python -c \
        "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/health',timeout=4).status==200 else 1)" \
        >/dev/null 2>&1; then return 0; fi
    sleep 3
  done
  return 1
}

if [ "$(env_get POSTGRES_PASSWORD)" = "botfactory" ] || [ -z "$(env_get POSTGRES_PASSWORD)" ]; then
  warn "пароль базы — «botfactory» (по умолчанию). Порт базы наружу закрыт, так что это не срочно,"
  warn "но сменить его стоит. Через .env это не делается: пароль уже записан в том базы."
fi

# Конфигурация compose должна читаться ДО того, как что-то будет остановлено.
"${COMPOSE[@]}" config -q || die "docker compose не принимает конфигурацию — ничего не тронуто"

# ---------------------------------------------------------------- откат

if [ "$ROLLBACK" -eq 1 ]; then
  [ -f "$PREV_FILE" ] || die "нет сохранённой предыдущей версии ($PREV_FILE)"
  PREV="$(cat "$PREV_FILE")"
  warn "Откат кода на $PREV. Миграции базы НЕ откатываются: если новая версия меняла схему,"
  warn "а старый код её не понимает, восстанавливай базу из копии в $BACKUP_DIR."
  read -r -p "Продолжить? (y/N) " reply
  [ "$reply" = "y" ] || die "отменено"
  git checkout --quiet "$PREV"
  "${COMPOSE[@]}" up -d --build
  wait_healthy && say "Откат выполнен, сервис отвечает." || die "после отката API не отвечает — смотри: ${COMPOSE[*]} logs api"
  exit 0
fi

# ---------------------------------------------------------------- состояние

CURRENT="$(git rev-parse HEAD)"
if [ "$RESTART_ONLY" -ne 1 ]; then
  [ -z "$(git status --porcelain --untracked-files=no)" ] \
    || die "в проекте есть локальные правки отслеживаемых файлов — закоммить или отмени их (git status), иначе обновление затрёт их"
  [ -n "$BRANCH" ] || BRANCH="$(git rev-parse --abbrev-ref HEAD)"
  # После --rollback репозиторий стоит на конкретном коммите, а не на ветке:
  # тогда берём ту, с которой обновлялись в прошлый раз.
  if [ "$BRANCH" = "HEAD" ] && [ -f .deploy-branch ]; then BRANCH="$(cat .deploy-branch)"; fi
  [ "$BRANCH" != "HEAD" ] || die "репозиторий не на ветке (detached HEAD) — укажи ветку: --branch main"
  echo "$BRANCH" > .deploy-branch
  git fetch --quiet origin "$BRANCH" || die "не удалось получить $BRANCH с origin"
  if [ "$(git rev-parse HEAD)" = "$(git rev-parse "origin/$BRANCH")" ]; then
    say "Код уже свежий ($(git rev-parse --short HEAD)). Пересоберу и перезапущу на всякий случай."
  else
    say "Что изменится:"
    git --no-pager log --oneline --no-decorate "HEAD..origin/$BRANCH" | head -20 || true
  fi
fi

# ---------------------------------------------------------------- копия базы

mkdir -p "$BACKUP_DIR"
chmod 700 "$BACKUP_DIR"
if [ "$DRY" -eq 1 ]; then
  say "Репетиция: копию базы пропускаю"
elif "${COMPOSE[@]}" ps --status running db 2>/dev/null | grep -q db; then
  DUMP="$BACKUP_DIR/pre-deploy-$(date -u +%Y%m%d-%H%M%S).sql.gz"
  say "Копия базы перед обновлением → $DUMP"
  DB_USER="$(env_get POSTGRES_USER)"; DB_NAME="$(env_get POSTGRES_DB)"
  if "${COMPOSE[@]}" exec -T db pg_dump -U "${DB_USER:-botfactory}" "${DB_NAME:-botfactory}" | gzip > "$DUMP" \
      && [ -s "$DUMP" ]; then
    chmod 600 "$DUMP"
    # храним последние несколько
    ls -1t "$BACKUP_DIR"/pre-deploy-*.sql.gz 2>/dev/null | tail -n +$((KEEP_DUMPS + 1)) | xargs -r rm -f
  else
    rm -f "$DUMP"
    die "не удалось сделать копию базы — обновление остановлено, чтобы ничего не потерять"
  fi
else
  warn "контейнер базы не запущен — копию не делаю"
fi
echo "$CURRENT" > "$PREV_FILE"

# ---------------------------------------------------------------- код

if [ "$RESTART_ONLY" -ne 1 ]; then
  say "Обновляю код ($BRANCH)"
  git checkout --quiet "$BRANCH"
  git merge --ff-only "origin/$BRANCH" --quiet \
    || die "ветка разошлась с origin/$BRANCH — быстрая перемотка невозможна. Разберись вручную (git status / git log)."
fi

# Новые настройки, которые появились в .env.example, но отсутствуют в .env.
missing=()
while IFS= read -r key; do
  grep -qE "^#?[[:space:]]*${key}=" .env || missing+=("$key")
done < <(grep -E '^[A-Z_][A-Z0-9_]*=' .env.example | cut -d= -f1)
if [ "${#missing[@]}" -gt 0 ]; then
  warn "в .env.example появились настройки, которых нет в твоём .env (работают значения по умолчанию):"
  printf '    %s\n' "${missing[@]}"
fi

# Образ api с версии «без root»: том загрузок, созданный раньше, принадлежит root.
if [ ! -f .media_chown_done ] && [ "$DRY" -ne 1 ]; then
  say "Один раз правлю владельца тома загрузок"
  "${COMPOSE[@]}" run --rm --no-deps --user root --entrypoint chown api -R 10001:10001 /srv/media_uploads \
    && touch .media_chown_done || warn "не удалось поправить права тома — если загрузка файлов даст 500, выполни команду из deploy/ops.md"
fi

# ---------------------------------------------------------------- сборка и запуск

# Сначала только сборка: пока она идёт, прежние контейнеры работают как
# работали. Упадёт установка зависимостей или сборка фронтенда — сервис даже
# не заметит.
say "Собираю новые образы (старая версия пока работает)"
"${COMPOSE[@]}" build || die "сборка не удалась — рабочая версия не тронута"

if [ "$DRY" -eq 1 ]; then
  say "Репетиция закончена: код получен, образы собраны, конфигурация верна."
  say "Работающие контейнеры не остановлены и не перезапущены. Для настоящего обновления — без --dry-run."
  exit 0
fi

MIGRATIONS_CHANGED=0
if [ -n "${CURRENT:-}" ] && ! git diff --quiet "$CURRENT" HEAD -- migrations/versions 2>/dev/null; then
  MIGRATIONS_CHANGED=1
  warn "в этом обновлении есть миграции базы — автоматический откат кода будет невозможен"
fi

say "Перезапускаю (миграции применятся автоматически, пауза — секунды)"
"${COMPOSE[@]}" up -d

say "Жду, пока API ответит на /health"
if ! wait_healthy; then
  "${COMPOSE[@]}" logs --tail=80 api migrate || true
  if [ "$MIGRATIONS_CHANGED" -eq 0 ] && [ "$RESTART_ONLY" -ne 1 ] && [ -n "${CURRENT:-}" ]; then
    warn "Новая версия не поднялась. Миграций не было — возвращаю прежний код автоматически."
    git checkout --quiet "$CURRENT"
    "${COMPOSE[@]}" up -d --build
    if wait_healthy; then
      die "Откат выполнен: сервис работает на прежней версии ($(git rev-parse --short HEAD)). Причина — в логах выше."
    fi
    die "После отката API тоже не отвечает. Смотри: ${COMPOSE[*]} logs api. Копии базы: $BACKUP_DIR"
  fi
  die "API не поднялся за 3 минуты. Логи выше.
    Вернуть прошлую версию кода:  ./deploy/deploy.sh --rollback
    Если были миграции — база уже изменена; копии в: $BACKUP_DIR"
fi

# Старые образы и кэш сборки не чистим: на сервере живут и другие проекты, а
# `docker image prune` действует на весь хост. Если место кончается —
# `docker image prune` и `docker builder prune` вручную, когда сам решишь.

say "Готово: $(git rev-parse --short HEAD) — $(git log -1 --pretty=%s)"
"${COMPOSE[@]}" ps
}

main "$@"
exit $?
