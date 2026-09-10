# Bot Factory — MVP (Фаза 1)

Визуальный drag-and-drop конструктор Telegram-ботов — без кода. Один и тот
же React-фронтенд работает в двух режимах:

- **Веб** (`https://your-domain.com/`, вход через Telegram Login Widget) —
  основной, полноценный конструктор: шаблоны сценариев, визуальный холст
  (блоки + стрелки, ветвления по кнопкам — как в Human Resource Machine),
  live-превью с реальными переходами по нажатой кнопке, приём оплаты в
  боте (блок «Оплата» → выдача после платежа).
- **Telegram Mini App** (открывается кнопкой у мета-бота) — лёгкий
  дашборд: список ботов, статус, публикация, просмотр содержимого. Сложное
  редактирование в Telegram WebView неудобно, поэтому там read-only превью
  и кнопка «Открыть на компьютере →».

Оба режима работают под одним аккаунтом — `telegram_user_id` объединяет
вход через Mini App (`initData`) и через веб-логин (Login Widget).

**Фаза 1** — без оплаты. Цель: полный механизм от начала до конца —
мета-бот → конструктор → публикация → готовый клиентский бот.

## Стек

- Backend: Python 3.12, FastAPI, SQLAlchemy 2.0 (async), asyncpg
- БД: PostgreSQL
- Мета-бот и клиентские боты: aiogram 3
- Frontend: React + Vite, `window.Telegram.WebApp` (Mini App) +
  Telegram Login Widget (веб)
- Визуальный холст сценария: `@xyflow/react` (React Flow)
- Платежи: свой слой поверх провайдеров — один файл в
  `app/services/payments/` на провайдера, форма настроек и вебхук
  строятся из него сами (см. «Приём оплаты» ниже)
- Деплой: Docker Compose (db + api + bot + frontend/nginx)

## Структура проекта

```
app/            FastAPI backend (модели, роутеры, сервисы)
meta_bot/       мета-бот (aiogram, long polling)
frontend/       конструктор (React + Vite) — веб и Mini App одним билдом
migrations/     alembic
nginx/          конфиг реверс-прокси для прод-деплоя
docker-compose.yml
```

Подробное описание — см. модели, роутеры и сервисы в `app/`.

## Приём оплаты

Владелец бота подключает свой шлюз — деньги идут ему напрямую, платформа
их не держит и не пересылает. Что доступно:

| Где | Провайдер | Как подтверждается оплата |
|---|---|---|
| Везде, где есть Telegram | Telegram Stars | сам Telegram, апдейтом боту |
| Россия | ЮKassa, Т-Банк, CloudPayments, PayMaster, LIFE PAY | обратным запросом в API провайдера |
| Россия | Prodamus, Robokassa | подписью уведомления |
| Россия (плательщик из-за рубежа) | lava.top | обратным запросом в API |
| Казахстан, Узбекистан, Кыргызстан | Freedom Pay | подписью уведомления |
| Казахстан | Processing.kz | обратным запросом в API (уведомлений нет) |
| Узбекистан | Click, Payme | подписью / собственным протоколом кассы |
| Украина | LiqPay | подписью уведомления |
| Мир | Stripe | подписью уведомления |
| Мир, без юрлица | Crypto Bot (USDT, TON) | подписью и обратным запросом |
| Что угодно | «Оплата по ссылке» | вручную, подтверждает продавец |

Два правила, общих для всех: суммы везде в **минорных единицах** (копейки,
тиыны, тийины) и целыми числами, а товар уходит только после того, как
оплату подтвердил кто-то извне — уведомление с проверенной подписью, ответ
API провайдера или сам продавец.

Новый провайдер — это один модуль по контракту из
`app/services/payments/base.py`. Форма настроек, адрес для уведомлений и
поля на блоке оплаты строятся из объявленных им `credential_fields` и
`block_fields`, поэтому фронтенд трогать не нужно.

Платформа за публикацию берёт деньги отдельно и только через Stripe и
Crypto Bot — см. `PLATFORM_PAYMENT_METHODS` в `.env.example`.

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

## Тесты

```bash
pip install -r requirements-dev.txt
pytest
```

Нужен только PostgreSQL из `.env` — сервер поднимать не надо: тесты ходят в
приложение через ASGI внутри процесса. Пишут они в ту же базу, что и
разработка, но каждый тест заводит своего клиента и в конце удаляет его, а
вместе с ним по каскаду ботов, блоки и платежи.

Что покрыто: обход графа диалога (ветвления, тупики, защита от циклов),
подписи и проверка уведомлений всех платёжных провайдеров, а также два
денежных правила, ради которых всё и затевалось — товар не уходит, пока
оплату не подтвердил кто-то извне, и повторное уведомление не выдаёт его
второй раз.

Тест, помеченный `xfail`, — это описанный баг, который ещё не починен;
`strict=True` означает, что после починки он потребует снять маркер.

## Запуск через Docker Compose

```bash
cp .env.example .env   # заполнить META_BOT_TOKEN, PUBLIC_BASE_URL, FERNET_KEY
docker compose up --build
```

Поднимутся: `db` (Postgres), `migrate` (разовый прогон alembic),
`api` (FastAPI на 8000), `bot` (мета-бот, long polling), `frontend`
(nginx на 80, отдаёт Mini App и проксирует `/api` и `/webhook` на `api`).

## Продакшен-деплой на VPS

Есть два сценария — какой использовать, зависит от того, свободен сервер
или на нём уже что-то работает.

### Вариант А — чистый VPS, ничего больше не крутится

`docker-compose.prod.yml` добавляет `caddy`, который сам получает и
продлевает Let's Encrypt сертификат и владеет портами 80/443.

**Перед стартом:**

1. Настрой DNS: A-запись `your-domain.com → IP_VPS`.
2. Открой на VPS порты `80` и `443` (например, `ufw allow 80,443/tcp`).
3. Установи Docker Engine + Compose plugin, если их ещё нет:
   ```bash
   curl -fsSL https://get.docker.com | sh
   ```

**Деплой:**

```bash
git clone https://github.com/DimkaQQ/BotFactory.git
cd BotFactory
git checkout claude/davay-sdelaem-eto-59liqr

cp .env.example .env
# заполнить META_BOT_TOKEN, FERNET_KEY,
# PUBLIC_BASE_URL=https://your-domain.com, DOMAIN=your-domain.com,
# и сменить POSTGRES_PASSWORD на нечто не дефолтное

docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build
```

Caddy сам выпустит сертификат при первом запросе на порт 80/443 —
логи можно посмотреть через `docker compose logs -f caddy`.

### Вариант Б — на VPS уже есть свой nginx на хосте (порты 80/443 заняты)

Здесь `caddy` не подойдёт — он тоже хочет владеть 80/443. Вместо этого
используется оверлей `docker-compose.shared-vps.yml`: контейнер `frontend`
слушает только `127.0.0.1:8010` (наружу не торчит), а `api`/`bot`/`db`
вообще не публикуют портов на хост. Существующий nginx получает новый
vhost, который проксирует на `127.0.0.1:8010`, и TLS для него выпускает
certbot — так же, как для остальных сайтов на сервере, без затрагивания
их конфигов.

```bash
git clone https://github.com/DimkaQQ/BotFactory.git
cd BotFactory
git checkout claude/davay-sdelaem-eto-59liqr

cp .env.example .env
# заполнить META_BOT_TOKEN, FERNET_KEY,
# PUBLIC_BASE_URL=https://your-domain.com
# (DOMAIN отсюда не используется — Caddy тут не участвует)
# сменить POSTGRES_PASSWORD на нечто не дефолтное

docker compose -f docker-compose.yml -f docker-compose.shared-vps.yml up -d --build

# добавляем vhost в существующий host-nginx
sudo cp deploy/nginx-vhost.example.conf /etc/nginx/sites-available/botfactory.conf
sudo nano /etc/nginx/sites-available/botfactory.conf   # прописать реальный домен
sudo ln -s /etc/nginx/sites-available/botfactory.conf /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx
sudo certbot --nginx -d your-domain.com
```

Оба сервиса (`api`, `bot`, `db`) в этом варианте получают лимиты памяти
(`mem_limit`), чтобы не мешать другим сервисам на общем сервере.

## Путь пользователя end-to-end

1. Пользователь пишет `/start` мета-боту → получает кнопку
   «🛠 Открыть конструктор» (`WebAppInfo`).
2. Открывается Mini App, backend валидирует подпись `initData` от
   Telegram и создаёт/находит `Client` и черновик `Bot`.
3. Пользователь добавляет блоки — приветствие, текст, изображение, видео,
   кнопки, опрос, выдача файла/ссылки, пауза (`welcome`/`description`/
   `image`/`video`/`buttons`/`poll`/`delivery`/`delay`) — из постоянной
   библиотеки блоков (боковая панель на десктопе, шторка на мобильном),
   с анимированным превью при наведении, и перетаскивает их для смены
   порядка — всё автосохраняется (debounce 500мс,
   `PATCH /api/bots/{id}/blocks/{block_id}`). Кнопка «Смотреть, как в
   реальности» проигрывает весь сценарий с той же паузой между
   сообщениями, что и у настоящего бота.
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
