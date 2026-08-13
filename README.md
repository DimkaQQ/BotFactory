# Bot Factory — MVP (Фаза 1)

Telegram Mini App, в котором человек без навыков программирования визуально
собирает своего Telegram-бота через drag-and-drop конструктор блоков и
получает готового работающего бота.

**Фаза 1** — без оплаты. Цель: полный механизм от начала до конца —
мета-бот → конструктор → публикация → готовый клиентский бот.

## Стек

- Backend: Python 3.12, FastAPI, SQLAlchemy 2.0 (async), asyncpg
- БД: PostgreSQL
- Мета-бот и клиентские боты: aiogram 3
- Mini App: React + Vite + `@twa-dev/sdk`-совместимый `window.Telegram.WebApp`
- Drag-and-drop: `@dnd-kit/core` + `@dnd-kit/sortable`
- Деплой: Docker Compose (db + api + bot + frontend/nginx)

## Структура проекта

```
app/            FastAPI backend (модели, роутеры, сервисы)
meta_bot/       мета-бот (aiogram, long polling)
frontend/       Mini App (React + Vite)
migrations/     alembic
nginx/          конфиг реверс-прокси для прод-деплоя
docker-compose.yml
```

Подробное описание — см. модели, роутеры и сервисы в `app/`.

## Быстрый старт (локально, без Docker)

### 1. База данных

```bash
# нужен локальный PostgreSQL с БД botfactory и пользователем botfactory
createuser botfactory --pwprompt
createdb -O botfactory botfactory
```

### 2. Backend

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env
# заполнить META_BOT_TOKEN (токен от @BotFather для мета-бота),
# PUBLIC_BASE_URL (HTTPS-адрес, напр. Cloudflare Tunnel для локальной разработки),
# FERNET_KEY:
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"

# применить миграции
DATABASE_URL_SYNC=postgresql+psycopg2://botfactory:botfactory@localhost:5432/botfactory alembic upgrade head

# поднять API
uvicorn app.main:app --reload --port 8000

# в отдельном терминале — мета-бот (long polling)
python -m meta_bot.main
```

### 3. Frontend

```bash
cd frontend
npm install
npm run dev   # проксирует /api на localhost:8000, см. vite.config.ts
```

Так как Telegram требует HTTPS для Mini App и вебхуков, для локальной
разработки нужен туннель (например, Cloudflare Tunnel) наружу на порт
frontend/nginx, и `PUBLIC_BASE_URL` в `.env` должен указывать на его адрес.

## Запуск через Docker Compose

```bash
cp .env.example .env   # заполнить META_BOT_TOKEN, PUBLIC_BASE_URL, FERNET_KEY
docker compose up --build
```

Поднимутся: `db` (Postgres), `migrate` (разовый прогон alembic),
`api` (FastAPI на 8000), `bot` (мета-бот, long polling), `frontend`
(nginx на 80, отдаёт Mini App и проксирует `/api` и `/webhook` на `api`).

## Путь пользователя end-to-end

1. Пользователь пишет `/start` мета-боту → получает кнопку
   «🛠 Открыть конструктор» (`WebAppInfo`).
2. Открывается Mini App, backend валидирует подпись `initData` от
   Telegram и создаёт/находит `Client` и черновик `Bot`.
3. Пользователь добавляет блоки (`welcome`/`description`/`buttons`/
   `delivery`), перетаскивает их для смены порядка — всё автосохраняется
   (debounce 500мс, `PATCH /api/bots/{id}/blocks/{block_id}`).
4. Жмёт «Опубликовать», вставляет токен от @BotFather. Backend проверяет
   токен через `getMe`, шифрует его (Fernet) и сохраняет, регистрирует
   webhook `POST /webhook/{bot_id}`, переводит бота в статус `active`.
5. Любой пользователь пишет `/start` новому боту → общий вебхук
   находит бота по `bot_id` из URL, поднимает (или берёт из кэша)
   `aiogram.Bot` с расшифрованным токеном и последовательно отправляет
   все блоки бота.

## Безопасность

- Токены ботов шифруются `cryptography.fernet.Fernet` до записи в БД;
  расшифровка происходит только внутри `app/services/bot_registry.py`,
  в момент создания `aiogram.Bot` — расшифрованный токен никогда не
  попадает в API-ответы или логи.
- `X-Telegram-Init-Data` на каждом запросе к `/api/*` проверяется по
  HMAC-подписи (`app/services/telegram_validator.py`), как того требует
  Telegram, — подделать `telegram_user_id` нельзя.
- Ошибка в диалоге одного клиентского бота не может уронить общий
  вебхук — исключения в `bot_dispatcher` логируются и гасятся в
  `routers/webhook.py`.

## Что осознанно не сделано в Фазе 1

- Оплата (Tribute/Stars) и блок `payment` — Фаза 2.
- Редактирование уже опубликованного бота.
- Мультиязычность интерфейса.
- Ветвления/условия в диалоге — только линейная последовательность блоков.
