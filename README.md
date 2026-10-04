# Bot Factory

Визуальный конструктор Telegram-ботов без кода (блоки + стрелки), который
продаётся клиентам из СНГ (РФ, КЗ, УЗ, …). Клиент собирает бота бесплатно,
платит платформе за **запуск** (и ежемесячно за работу), а бот сам принимает
оплату покупателей (в **кассу владельца**, не через платформу) и выдаёт товар.

> **Этот README — единственный источник правды о проекте.** Он написан так, чтобы
> новый разработчик или другой Claude Code мог продолжить работу, не зная
> истории. Если ты меняешь поведение системы — обнови здесь соответствующий
> раздел и допиши строку в [«Журнал решений»](#журнал-решений) в конце.
> Краткая памятка для агентов — в [`CLAUDE.md`](CLAUDE.md).

## Оглавление

1. [Что это и как зарабатывает](#1-что-это-и-как-зарабатывает)
2. [Текущее состояние и открытые вопросы](#2-текущее-состояние-и-открытые-вопросы)
3. [Архитектура и процессы](#3-архитектура-и-процессы)
4. [Карта кода](#4-карта-кода)
5. [Модель данных](#5-модель-данных)
6. [HTTP API](#6-http-api)
7. [Платежи](#7-платежи)
8. [Биллинг платформы (запуск и продления)](#8-биллинг-платформы-запуск-и-продления)
9. [Мета-бот @DragDropBot](#9-мета-бот-dragdropbot)
10. [Клиентские боты: как идёт диалог](#10-клиентские-боты-как-идёт-диалог)
11. [Юридический слой](#11-юридический-слой)
12. [Безопасность](#12-безопасность)
13. [Конфигурация (.env)](#13-конфигурация-env)
14. [Деплой и эксплуатация](#14-деплой-и-эксплуатация)
15. [Масштабирование](#15-масштабирование)
16. [Разработка, тесты, ловушки](#16-разработка-тесты-ловушки)
17. [Фронтенд и дизайн-проверка](#17-фронтенд-и-дизайн-проверка)
18. [Журнал решений](#журнал-решений)
19. [Чего пока нет / идеи](#19-чего-пока-нет--идеи)

---

## 1. Что это и как зарабатывает

**Продукт.** Один React-фронтенд в двух режимах:

- **Веб** (`https://<домен>/`, вход через Telegram Login Widget) — основной
  конструктор: шаблоны, холст (блоки + стрелки, ветвления по кнопкам),
  предпросмотр «как в реальности», касса, продажи, рассылки, лендинг для
  незарегистрированных.
- **Telegram Mini App** (кнопка у мета-бота) — лёгкий дашборд; сложное
  редактирование там неудобно, поэтому только просмотр и «Открыть в браузере».

Оба режима под одним аккаунтом: `Client.telegram_user_id` объединяет вход через
Mini App (`initData`) и веб-логин.

**Деньги.**

| Что | Кто платит | Куда идут деньги |
|---|---|---|
| Покупки в клиентских ботах | покупатели бота | **в кассу владельца бота** напрямую; платформа деньги не держит и не пересылает |
| Запуск бота (разово) и продление (за период) | владелец бота | платформе, через `PLATFORM_PAYMENT_METHODS` (Stripe, Crypto Bot, Telegram Stars) |

Рекомендованные цены: **запуск $129, далее $15 за 30 дней** (в звёздах для РФ:
6490 ⭐ / 750 ⭐). Ориентир — разработчик на заказ просит $200–300. Цены
показываются на лендинге (блок «Цена» + калькулятор окупаемости) и в пейволле.
Автосписаний нет ни у кого: только счета (у Crypto Bot автосписаний не
существует вовсе).

**Аудитория и география.** Клиенты из РФ, КЗ, УЗ. Из РФ платят криптой
(Crypto Bot) или звёздами; из КЗ/УЗ — ещё и картой Stripe (Stripe не работает с
плательщиками из РФ/Беларуси). Сервис не предлагается потребителям ЕС.

**Юрлицо.** Исполнитель по оферте — тот, кто задан в `LEGAL_NAME` (планируется
эстонское OÜ; Stripe-аккаунт тоже на OÜ). Открытый вопрос для владельца:
Crypto Bot и звёзды без юрлица приходят лично владельцу — это вопрос налогов
и учёта (см. [раздел 2](#2-текущее-состояние-и-открытые-вопросы)).

## 2. Текущее состояние и открытые вопросы

Ветка разработки: `claude/davay-sdelaem-eto-59liqr` (репозиторий
`DimkaQQ/BotFactory`). Боевой сервер владельца — **общий русский VPS за
Cloudflare** с другими сервисами, режим деплоя `shared` (host-nginx + certbot →
`127.0.0.1:8010`), каталог `/opt/docker/BotFactory`, команда обновления
`bfdeploy` (симлинк на `deploy/deploy.sh`). На последнем подтверждённом
деплое применены миграции до `0012`; всё новее (миграции `0013`–`0017`,
кабинет владельца, звёзды, `worker`, бэкап/cron и т.д.) **запушено, но
не подтверждено как задеплоенное**.

**Что владелец должен сделать (чек-лист):**

- [ ] `bfdeploy` (он создаст `worker`, поставит cron бэкапа и сторожа,
      применит миграции 0013–0017).
- [ ] В `.env`: `SUPPORT_CHAT_ID=408204060` (Telegram id владельца),
      `LEGAL_COUNTRY=Эстония`, `DATA_LOCATION=Россия`, при наличии `LEGAL_VAT`,
      `PLATFORM_PAYMENT_METHODS` (пример с ценами $129/$15 — в `.env.example`).
- [ ] Хост-nginx: подключить `deploy/cloudflare-realip.conf`, в vhost —
      `location /webhook/` без `limit_req` (пример: `deploy/nginx-vhost.example.conf`).
- [ ] Cloudflare: SSL Full (strict), WAF-правило «Skip» для `/webhook/*`.
- [ ] Сохранить `BACKUP_PASSPHRASE` и `FERNET_KEY` отдельно от сервера;
      проверить восстановление (`deploy/ops.md`).
- [ ] Юрист (Эстония): оферта/политика, передача данных в РФ, соглашение об
      обработке данных (ст. 28 GDPR), налог на цифровые услуги, санкции ЕС.
- [ ] Stripe: сайт `bot.dimkaprojects.xyz`, descriptor, имя аккаунта,
      support-email; отозвать утёкший токен ресторанного бота.
- [ ] Решить: исполнитель по оферте = OÜ, а Crypto Bot / кошелёк звёзд тоже на OÜ
      (рекомендация) — или раздельные исполнители (тогда оферту переписать).

**Известные ограничения.** Нагрузка рассчитана по коду, не измерена. У
контейнера `api` в режиме shared лимит 256 МБ (при росте числа ботов поднимать).
Миграции с удалением/переименованием ломают плавное обновление (см. §15).

## 3. Архитектура и процессы

```
                 Cloudflare ──► host nginx (certbot) ──► 127.0.0.1:8010
                                                          │
                                       ┌──────────────────▼──────────────────┐
                                       │ frontend (nginx в контейнере)       │
                                       │  • отдаёт SPA (React, Vite build)   │
                                       │  • проксирует /api /webhook /legal  │
                                       │    /health в api (resolver 5с, по   │
                                       │    кругу на все экземпляры api)     │
                                       │  • лимиты запросов, CSP-report-only │
                                       └──────────────────┬──────────────────┘
                                                          ▼
 Telegram ── POST /webhook/{bot_id} ──►  api (FastAPI, N экземпляров, без фоновых задач)
 Провайдер ─ POST /webhook/pay/{slug} ─►  api
                                                          │ Postgres
 worker  (python -m app.worker) — планировщик, продления, повторная выдача, чистка файлов
 bot     (python -m meta_bot.main) — мета-бот @DragDropBot, long polling
 db      Postgres 16
 migrate одноразовый `alembic upgrade head`
```

**Процессы (docker compose, `docker-compose.yml`):**

| Сервис | Команда | Роль | Несколько экземпляров |
|---|---|---|---|
| `db` | postgres:16 | данные | нет |
| `migrate` | `alembic upgrade head` | миграции перед стартом | одноразово |
| `api` | `uvicorn app.main:app` (`RUN_BACKGROUND=false`) | HTTP: веб-API, вебхуки Telegram и платёжных систем | **да** (`API_REPLICAS`) |
| `worker` | `python -m app.worker` | фоновые задачи (`app/tasks.py`) | да, безопасно (захват условным UPDATE) |
| `bot` | `python -m meta_bot.main` | мета-бот (кабинет, поддержка, звёзды за запуск) | **нет** (long polling) |
| `frontend` | nginx | SPA + прокси | да |

`RUN_BACKGROUND=true` (по умолчанию в коде) заставляет `api` вести фоновые
задачи сам — так работает простая установка в один процесс и все тесты.

**Диалог клиентского бота.** Вебхук отвечает Telegram сразу, а «разговор»
(паузы между репликами, до 15 с на блок) идёт в фоне через `background.spawn`
с очередью «одно сообщение за раз на чат» (`services/background.py`). Иначе
Telegram считал бы вебхук зависшим и повторял апдейт.

**Платёжные уведомления** → `routers/payments.py` → проверка подписи или
обратный запрос в API провайдера → `payment_service.apply_result` → одно
условное `UPDATE ... WHERE status != 'paid'`: повтор не выдаёт товар второй раз.

## 4. Карта кода

### Backend `app/`

| Файл | Назначение |
|---|---|
| `main.py` | FastAPI-приложение, lifespan (запуск фоновых задач только при `RUN_BACKGROUND`), роутеры, `/health` (проверяет и БД), CORS, `/api/media` |
| `config.py` | все настройки (`pydantic-settings`), см. §13 |
| `database.py` | async-движок (пул 10+20), `AsyncSessionLocal`, `Base` |
| `deps.py` | `get_current_client` (Bearer-сессия или `initData`), блокировка забаненных, `get_owned_bot` |
| `tasks.py` | `start_background_tasks()` — список фоновых задач (используют `main.py` и `worker.py`) |
| `worker.py` | точка входа процесса `worker` (SIGTERM → доделать задачи → закрыть сессии) |
| `admin.py` | CLI владельца: `ban`, `unban`, `export`, `delete` (см. `deploy/runbook.md`) |
| `rotate_keys.py` | перешифрование хранимых секретов при смене `FERNET_KEY` |
| `models/` | таблицы (см. §5) |
| `schemas/` | pydantic-схемы ответов/запросов (`bot`, `bot_block`, `client`, `payment`) |
| `routers/auth.py` | `GET /api/config` (публичный конфиг лендинга, цены, документы), вход через Login Widget, `logout`, запись принятия условий |
| `routers/bots.py` | `/api/me`, список/создание/правка (в т.ч. `paused`)/удаление ботов, публикация |
| `routers/builder.py` | блоки бота: CRUD, `reorder` |
| `routers/media.py` | загрузка файлов (магические байты, квота, uuid-имя) |
| `routers/payments.py` | уведомления платёжных систем, настройки кассы, пейволл, заказы, подписчики, рассылка, возвраты, CSV |
| `routers/webhook.py` | `POST /webhook/{bot_id}` — апдейты Telegram (проверка `secret_token`) |
| `routers/legal.py`, `legal_en.py` | юридические страницы из настроек, RU и EN |
| `services/bot_dispatcher.py` | обход графа блоков, кнопки, оплата, `/start /stop /cancel /paysupport`, пауза бота, уведомления владельцу |
| `services/bot_registry.py` | кэш экземпляров `aiogram.Bot`, регистрация вебхуков, `refresh_all_webhooks` |
| `services/payment_service.py` | создание платежей, `apply_result`/`mark_paid` (идемпотентность), платформенные методы (`platform_methods`, `_WHO_CAN_PAY`), Stars-токен мета-бота, `tell_owner` (уведомления владельцу через мета-бота) |
| `services/payments/` | по файлу на провайдера (§7), `base.py` — контракт и `money()` |
| `services/platform_billing.py` | период работы бота, напоминания, грейс, снятие с эфира, возврат одной оплатой |
| `services/scheduler.py` | отложенные шаги (долгие паузы, напоминания) |
| `services/subscription_service.py` | подписки покупателей и закрытие периодов |
| `services/group_access.py` | выдача/снятие доступа в закрытый чат |
| `services/owner_panel.py` | данные кабинета владельца в мета-боте: карточки ботов, пауза, уведомления, принятие условий |
| `services/subscribers.py` | журнал людей, писавших боту, отписки, блокировки |
| `services/media_gc.py` | чистка файлов, на которые никто не ссылается |
| `services/security.py` | Fernet (MultiFernet, ротация), `secret_token` вебхука |
| `services/session_token.py` | подписанные веб-сессии на 30 дней |
| `services/telegram_validator.py` | проверка токена через `getMe` (человеческие ошибки, токен не в сообщениях) |
| `services/telegram_session.py` | HTTP-сессия aiogram с учётом `TELEGRAM_API_BASE_URL` |
| `services/background.py` | `spawn`, очереди по ключу, `wait_for_all`, `cancel_all` |
| `services/dates.py` | форматирование дат в `DISPLAY_TIMEZONE` |

### Мета-бот `meta_bot/`

- `main.py` — `build_dispatcher()`: порядок роутеров **важен** (проверен тестом):
  `payments` (звёзды) → `menu` → `support` (ловит всё не-командное, поэтому последний).
- `handlers/menu.py` — кабинет: главный экран, «Мои боты», карточка бота (пауза/включить), настройки (уведомления о продажах, «Выйти везде», документы), принятие условий (`m:terms`), кнопка «Поддержка». Callback-префиксы: `m:`, `b:`, `bp:`, `br:`, `s:`, `sup:`. Экраны редактируются на месте.
- `handlers/support.py` — поддержка: сообщения человека копируются в `SUPPORT_CHAT_ID`, ответ владельца через Reply возвращается автору (`support_relay`); диалог открыт 24 ч, троттлинг 12 сообщений/10 мин.
- `handlers/payments.py` — оплата запуска звёздами: `pre_checkout_query` + `successful_payment` → `payment_service.apply_result`.
- `handlers/start.py` — реэкспорт для обратной совместимости.

### Фронтенд `frontend/src/` (React 18 + Vite + TS, `@xyflow/react`, `framer-motion`)

| Файл | Назначение |
|---|---|
| `App.tsx`, `main.tsx` | вход, определение режима (Mini App/веб), маршруты |
| `App.css`, `index.css` | вся стилизация; токены на `:root`, тёмная тема, дизайн-токены `--sp-*`, `--radius-*`; **правки последних волн дописаны в конец `App.css`** |
| `api/builderApi.ts` | клиент API, типы, `money()`, `formatAmount()`, `currencyUnit()` |
| `components/LoginScreen.tsx` | **лендинг** + вход: герой, сравнение, возможности, оплата, цена (+`PaybackCalculator`), доверие, FAQ, липкая CTA |
| `components/SiteFooter.tsx` | подвал: кнопка «Поддержка», документы, платёжный агент |
| `components/BotList.tsx` | список ботов, шаблоны (раскладка на холсте: десктоп — ряды по 4, телефон — колонка) |
| `components/BotBuilder.tsx` | экран конструктора, баннеры статуса, чек-лист проблем (`publishProblems`) |
| `components/flow/FlowCanvas.tsx` | холст, `smoothstep`-стрелки, `fitViewOptions()` (на телефоне minZoom 0.8) |
| `components/flow/BlockNode.tsx`, `StartNode.tsx` | узлы; на десктопе стрелки слева→направо (`useWideScreen`) |
| `components/flow/BlockEditPanel.tsx` | панель правки блока (инспектор справа на десктопе, лист на телефоне; перетаскивается) |
| `components/PublishPaywall.tsx` | свёрнутая кнопка → лист с оплатой запуска (Stripe/Crypto Bot/Stars) |
| `components/PublishButton.tsx`, `BotFatherSteps.tsx` | форма токена после оплаты, инструкция 4 шага |
| `components/PaymentSettingsPanel.tsx`, `PaymentEditor.tsx` | касса и блок «Оплата» |
| `components/SalesPanel.tsx`, `BroadcastButton.tsx`, `BillingBanner.tsx` | продажи, рассылка, баннер периода |
| `components/LivePreview.tsx`, `BlockPreviewFlyout.tsx` | предпросмотр сценария |
| `templates.ts`, `blockTypes.ts`, `humanDelay.ts` | шаблоны, типы блоков, «человеческая» пауза |
| `hooks/` | `useDraggablePanel`, `useEscape`, `useSwipeToDismiss`, `useTelegramWebApp`, `useWideScreen` |
| `confirm.ts` | подтверждение: нативный `showConfirm` Mini App только при `initData` и версии ≥ 6.2, иначе `window.confirm` |

### Прочее

- `migrations/versions/0001…0017` — alembic (список в §5).
- `nginx/default.conf` — nginx фронтенд-контейнера (лимиты, resolver, прокси, CSP report-only).
- `deploy/` — `deploy.sh`, `deployfirst.sh`, `backup.sh`, `watchdog.sh`, `install-cron.sh`, `nginx-vhost.example.conf`, `cloudflare-realip.conf`, `ops.md`, `runbook.md`, `scaling.md`.
- `Caddyfile`, `docker-compose.prod.yml` — вариант А (чистый VPS с Caddy).
- `docker-compose.shared-vps.yml` — вариант Б (общий VPS, лимиты памяти).
- `.github/workflows/ci.yml` — ruff, миграции, pytest+coverage, pip-audit, bandit, сборка фронта, npm audit.
- `tests/` — pytest на **настоящем Postgres** (§16).

## 5. Модель данных

Таблицы (миграции — `migrations/versions`):

- `clients` — владелец бота: `telegram_user_id`, `full_name`, `sessions_valid_from` (выход везде), `notify_sales`, `banned_at`, `terms_version`/`terms_accepted_at`.
- `bots` — клиентский бот: `client_id`, `name`, `bot_token_encrypted`, `telegram_bot_username`, `status` (`draft|active|disabled`), `start_block_id`, `payment_provider`, `payment_credentials_encrypted`, `payment_is_test`, `publication_paid_at`, `paid_until`, `paused` (пауза владельца — на уровне диспетчера, **не** то же, что биллинговый `disabled`), `billing_notice_stage`.
- `bot_blocks` — блоки графа: `block_type` (`welcome, description, image, video, buttons, poll, delivery, delay, payment`), `content` JSONB, `next_block_id`, `position_x/y`, `order_index`.
- `bot_subscribers` — все, кто писал боту (имя, язык, `blocked_at`, `unsubscribed_at`).
- `payments` — **и** покупки в ботах (`kind=order`), **и** оплата платформе (`publication`, `renewal`): `invoice_no`, `status` (`pending|paid|failed|refunded`), `provider`, `amount_minor`, `currency`, `bot_id`/`client_id` (**`ON DELETE SET NULL`** — учёт переживает удаление бота/аккаунта), `block_id`, `telegram_user_id`, `chat_id`, `meta` JSONB (`delivered_at`, `checkout_url`, …).
- `subscriptions` — подписки покупателей бота (период, провайдер, доступ в чат).
- `scheduled_steps` — отложенные шаги/рассылки (`pending|sent|failed|cancelled`).
- `poll_answers`, `poll_sends` — ответы на опросы.
- `support_relay` — соответствие «сообщение в чате поддержки ↔ автор».

Миграции: 0001 initial · 0002 имя бота · 0003 граф блоков · 0004 платежи ·
0005 backfill `delivered_at` · 0006 подписчики/планировщик/подписки · 0007 опросы ·
0008 продления платформы · 0009 poll_sends · 0010 отписка · 0011 enum-проверки ·
0012 отзыв сессий · 0013 принятие условий · 0014 `support_relay` · 0015 `paused` +
`notify_sales` · 0016 платежи не каскадом · 0017 `banned_at`.

Деньги везде — **целые минорные единицы** (копейки, центы). Звёзды: цена в
`amount_minor` = звёзды × 100.

## 6. HTTP API

Префикс `/api` (кроме вебхуков и `/legal`). Авторизация: `Authorization: Bearer
<сессия>` (веб) или `X-Telegram-Init-Data` (Mini App).

- Публично: `GET /api/config`, `POST /api/auth/telegram-login`, `GET /legal/*`, `GET /health`.
- Аккаунт: `GET /api/me`, `POST /api/auth/logout`.
- Боты: `GET|POST /api/bots`, `GET|PATCH|DELETE /api/bots/{id}`, `POST /api/bots/{id}/publish`.
- Блоки: `/api/bots/{id}/blocks` (`GET|POST`, `PATCH /reorder`, `PATCH|DELETE /{block_id}`).
- Файлы: `POST /api/bots/{id}/media/upload`; раздача `/api/media/<клиент>/<uuid>-имя` (**без авторизации** — адрес нельзя угадать, но можно переслать).
- Платежи/касса: `GET /api/payments/providers`, `GET|PUT /api/bots/{id}/payment-settings`, `GET /api/bots/{id}/publication`, `POST …/publication-checkout`, `POST …/renewal-checkout`, `GET …/billing`, `GET /api/payments/{id}`.
- Продажи: `GET …/orders` (+`.csv`), `POST …/orders/{id}/confirm|refund|redeliver|reject`, `GET …/subscribers`, `POST …/broadcast`, `GET …/broadcasts`, `GET …/polls`.
- Вебхуки: `POST /webhook/{bot_id}` (Telegram, `secret_token`), `POST /webhook/pay/{provider}` (платёжки), `GET /webhook/pay/test/{id}` (тестовый провайдер), `GET /api/pay/redirect/{id}`, `GET /api/pay/done`.

## 7. Платежи

### Клиентские кассы (деньги владельца бота — напрямую ему)

| Где | Провайдер | Подтверждение |
|---|---|---|
| Везде в Telegram | Telegram Stars | апдейт боту (`successful_payment`) |
| Россия | ЮKassa, Т-Банк, CloudPayments, PayMaster, LIFE PAY | обратный запрос в API провайдера |
| Россия | Prodamus, Robokassa | подпись уведомления |
| Россия (плательщик из-за рубежа) | lava.top | обратный запрос |
| КЗ, УЗ, КГ | Freedom Pay | подпись |
| КЗ | ioka, Processing.kz | обратный запрос |
| УЗ | Click, Payme | подпись / протокол кассы |
| Украина | LiqPay | подпись |
| Мир | Stripe | подпись |
| Мир, без юрлица | Crypto Bot (USDT, TON) | подпись + обратный запрос |
| Любое | «Оплата по ссылке» (`link.py`) | вручную, подтверждает продавец |

Правила для всех: суммы целыми минорными единицами; **товар уходит только после
внешнего подтверждения** (подпись, ответ API провайдера или сам продавец);
повтор уведомления не выдаёт товар второй раз; сравнение подписей —
`hmac.compare_digest`; XML — `defusedxml`. События провайдера, не относящиеся к
платежу (например, возврат Stripe), подтверждаются кодом 200 (`error_body`),
чтобы провайдер не повторял их и не отключил вебхук; возвраты и споры делаются
вручную (`deploy/runbook.md`).

**Новый провайдер** — один модуль по контракту `services/payments/base.py`
(`credential_fields`, `block_fields`, `create_checkout`, `locate_payment`,
`verify_webhook`, `error_body`, …). Форма настроек и поля блока строятся из
объявленного — фронтенд не трогать.

### Платформа получает оплату за запуск/продление

`PLATFORM_PAYMENT_METHODS` — JSON-список методов (`provider`, `price_minor`,
`renewal_price_minor`, `currency`, `credentials`). Поддерживаются `stripe`,
`cryptobot`, `stars`. Подсказка «кому подходит» — `_WHO_CAN_PAY` в
`payment_service.py` (Stripe: не для РФ/Беларуси).

- **Stars для платформы**: счёт выставляет **мета-бот** (`_platform_bot_token`
  берёт `META_BOT_TOKEN`), подтверждение приходит в `meta_bot/handlers/payments.py`
  (`pre_checkout_query` → проверка суммы и статуса; `successful_payment` →
  `apply_result`). Цена: звёзд × 100 в `price_minor`, валюта `XTR`, credentials не нужны.
  Для плательщика звезда ≈ $0,02, на вывод через Fragment ≈ $0,013 (~21 день).
- Старый одиночный формат (`PLATFORM_PAYMENT_PROVIDER` + `PUBLICATION_PRICE_MINOR`)
  работает, если список пуст. Провайдер `test` как «наша касса» отключён без
  `PLATFORM_ALLOW_TEST_TILL=true` (он отдаёт публикацию даром).

## 8. Биллинг платформы (запуск и продления)

- Запуск включает первый период (`RENEWAL_PERIOD_DAYS`, 30 дн.); дальше приходит
  счёт. Автосписаний нет.
- За `N` дней до конца — напоминание **через мета-бота** с кнопкой «🔄 Продлить»
  (WebApp на `/bot/<id>/`). Нельзя доставить — стадия не помечается, повтор на
  следующем проходе (`_notify_once`: сначала отправить, потом записать).
- После конца бот работает ещё `RENEWAL_GRACE_DAYS` (7), потом снимается с эфира
  (`suspend`: вебхук убирается, `status=disabled`); **ничего не удаляется**.
  Продление возвращает бота одной кнопкой (`resume`). Отложенные шаги такого
  бота удерживаются (`scheduler._hold`), а не сгорают.
- Платёж платформе при удалении бота остаётся в `payments` (`SET NULL`).
- Уведомления владельцу о продажах и ошибках: `payment_service.tell_owner` —
  сначала мета-бот, запасной путь — бот магазина (он может писать только тем,
  кто ему писал).

## 9. Мета-бот @DragDropBot

Кабинет владельца: `/start` → экран с цифрами (боты, клиенты, заказы, выручка по
валютам) → «Мои боты» → карточка (пауза/включить, «Редактировать в
конструкторе») → «Настройки» → «Поддержка». Новому человеку объясняет, что это
за сервис, и просит принять условия кнопкой «✅ Принимаю условия» (запись в
`clients.terms_version`; при веб-входе принятие пишется при логине).
Поддержка — пересылка в `SUPPORT_CHAT_ID`, ответ через Reply.
Пауза бота — `Bot.paused`: новых диалогов нет, оплаты/возвраты/выдача работают.

## 10. Клиентские боты: как идёт диалог

1. Владелец публикует: токен проверяется `getMe`, шифруется Fernet, ставится
   вебхук `/webhook/{bot_id}` с `secret_token`, `status=active`.
2. `/start` покупателя → диспетчер обходит граф от `start_block_id`.
3. Блок «Кнопки» с ветвями **останавливается и ждёт нажатия**; блок «Оплата»
   создаёт счёт, после подтверждения продолжает с `next_block_id` (фиксируется в
   `meta.deliver_from` при создании счёта — правки холста не ломают оплаченное).
4. Команды: `/stop` (отписка от рассылки), `/cancel` (отмена подписки),
   `/paysupport` (обязательная для платных ботов; отправляет к продавцу).
5. Свободный текст: бот отвечает «Я отвечаю на кнопки…» (общение покупатель↔продавец
   в боте не реализовано).
6. Пауза бота (`paused`) блокирует навигацию, но не оплату/выдачу/возвраты.

## 11. Юридический слой

Страницы `/legal/{offer,privacy,refunds,acceptable-use,data-processing,cookies}`
+ индекс, RU и EN (`?lang=en`), **генерируются из `.env`**
(`LEGAL_NAME`, `LEGAL_ID`, `LEGAL_ADDRESS`, `LEGAL_VAT`, `DATA_LOCATION`,
`LEGAL_COUNTRY`, `AGENT_*`, `SUPPORT_*`). Пока `LEGAL_NAME` и `LEGAL_ID` пусты —
404, ссылок в подвале нет. Цены в оферте берутся из тех же настроек, что и счёт.
`REVISION` в `routers/legal.py` — дата редакции, меняется вместе с текстом.
Раздел «9. Применимое право и споры» выводится только при `LEGAL_COUNTRY`.
Политика: минимум данных (Telegram id/имя, сценарии, журнал заказов,
технические журналы), сервис «для СНГ, не для потребителей ЕС», бэкапы
шифруются, хранятся ≤ 90 дней, возможна копия в закрытом чате Telegram.
**Тексты — шаблон; до продаж их должен прочитать юрист.**
Для запросов субъектов данных — `python -m app.admin export|delete`.

## 12. Безопасность

- Токены ботов и ключи касс — Fernet (`MultiFernet`, ротация без потерь:
  новый ключ в `FERNET_KEY`, старый в `FERNET_KEYS_RETIRED`, перезапуск,
  `python -m app.rotate_keys`, убрать старый). Перед первой ротацией задать
  отдельный `WEBHOOK_SECRET_KEY`.
- Вход: `initData` проверяется HMAC на каждом запросе; Login Widget → токен на
  30 дней; «Выйти» отзывает все токены (`sessions_valid_from`). Забаненный
  аккаунт (`banned_at`) получает 403.
- Вебхук бота — только с `secret_token` (из ключа и id бота); платёжные
  уведомления — подпись/обратный запрос.
- Загрузки: тип, магические байты, размер (20 МБ), квота на аккаунт (300 МБ),
  uuid-имя; CSV защищён от формул.
- `httpx`/`httpcore` в логах на уровне WARNING (иначе в логах URL с токеном).
- Контейнер не от root (uid 10001), `HEALTHCHECK`, порт БД наружу закрыт,
  `/docs` выключен (`ENABLE_API_DOCS`).
- nginx: лимиты (`bf_login` 5 r/s, `bf_api` 30 r/s, `bf_pay` 20 r/s; вебхуки
  Telegram без лимита), `real_ip` из docker-сетей; CSP пока **Report-Only**.
- Известный компромисс: токен веб-сессии лежит в `localStorage` на 30 дней;
  CSP-report-only от XSS не защищает — когда в консоли чисто, включить
  `Content-Security-Policy`.

## 13. Конфигурация (.env)

Шаблон — `.env.example` (полный и прокомментированный). Основное:

| Переменная | Назначение |
|---|---|
| `DATABASE_URL`, `DATABASE_URL_SYNC` | Postgres (async для приложения, sync для alembic). **При установке пароль БД должен совпадать в обеих строках и в `POSTGRES_PASSWORD`** (`deployfirst.sh` это делает сам) |
| `META_BOT_TOKEN`, `META_BOT_USERNAME` | мета-бот |
| `TELEGRAM_API_BASE_URL` | прокси к Bot API (если `api.telegram.org` недоступен с РФ-хоста); им пользуются сервис, бэкап и сторож |
| `PUBLIC_BASE_URL` | публичный https-адрес (вебхуки, ссылки) |
| `FERNET_KEY`, `FERNET_KEYS_RETIRED`, `WEBHOOK_SECRET_KEY` | ключи |
| `CORS_ORIGINS` | свой домен, не `*` |
| `PLATFORM_PAYMENT_METHODS` | способы и цены запуска/продления (§7) |
| `RENEWAL_PERIOD_DAYS` / `RENEWAL_GRACE_DAYS` | период и грейс (30/7) |
| `PLATFORM_PAYMENT_IS_TEST`, `PLATFORM_ALLOW_TEST_TILL` | боевые: `false`/`false` |
| `SUPPORT_TELEGRAM`, `SUPPORT_EMAIL`, `SUPPORT_CHAT_ID` | поддержка (`SUPPORT_CHAT_ID` — id владельца) |
| `LEGAL_NAME`, `LEGAL_ID`, `LEGAL_ADDRESS`, `LEGAL_VAT`, `DATA_LOCATION`, `LEGAL_COUNTRY`, `AGENT_*` | юридические реквизиты (§11) |
| `MAX_BOTS_PER_CLIENT` (20), `MAX_BLOCKS_PER_BOT` (200), `MAX_BLOCK_CONTENT_KB` (64), `MEDIA_QUOTA_MB_PER_CLIENT` (300), `MEDIA_MAX_UPLOAD_MB` (20), `MEDIA_ORPHAN_TTL_HOURS` (24) | лимиты |
| `DISPLAY_TIMEZONE` | часовой пояс дат в сообщениях |
| `ENABLE_API_DOCS` | `/docs` (только разработка) |
| `RUN_BACKGROUND` | фоновые задачи внутри `api` (в compose у `api` `false`, у `worker` `true`) |
| `API_REPLICAS` | число экземпляров `api` (по умолчанию 1) |
| `POSTGRES_USER/PASSWORD/DB`, `DOMAIN` | для compose / Caddy |
| `BACKUP_PASSPHRASE`, `BACKUP_CHAT_ID` (иначе `SUPPORT_CHAT_ID`), `BACKUP_KEEP`, `BACKUP_MAX_SEND_MB` (45), `BACKUP_MAX_TOTAL_MB` (1500), `HEALTH_URL` | бэкап и сторож |

## 14. Деплой и эксплуатация

**Один скрипт — одна команда.** На сервере `sudo ln -sf
/opt/docker/BotFactory/deploy/deploy.sh /usr/local/bin/bfdeploy`, дальше `bfdeploy`.

- `deploy/deployfirst.sh` — **один раз** (ставит Docker, генерирует `.env`/ключи/пароль БД,
  запускает, TLS, cron); повторно не запустится (`.deployfirst.done`).
  Режимы: `--mode caddy` (чистый VPS) или `--mode shared` (свой nginx на хосте).
- `deploy/deploy.sh` — обновление: `--dry-run` (только сборка), `--restart`,
  `--rollback`, `--branch`, `--mode`. Порядок: снять дамп БД в `backups/` → получить
  код → **собрать образы до остановки** → миграции → **плавное обновление `api`**
  (новые экземпляры рядом со старыми, ждём `healthy`, потом убираем старые;
  только если в обновлении нет миграций) → `up -d` остальных → ждать `/health` →
  при неудаче без миграций **автооткат** кода. Marker-файлы (в `.gitignore`):
  `.deploy-mode`, `.deploy-running` (какой коммит реально работает),
  `.deploy-prev`, `.deploy-branch`, `.media_chown_done`.
  Весь код обёрнут в `main()` (иначе `git merge` мог перезаписать скрипт на ходу).
  Скрипт **не** чистит общие образы Docker и не использует `--remove-orphans`
  (на сервере живут чужие проекты). В конце один раз ставит cron (`install-cron.sh`).
- `deploy/backup.sh` — ежедневно 04:17: дамп БД → если изменился → архив
  (БД + файлы + `.env`) → шифрование (`BACKUP_PASSPHRASE`, aes-256-cbc) → Telegram
  (`BACKUP_CHAT_ID`/`SUPPORT_CHAT_ID`); архив >45 МБ режется на части
  `…part-NN`; >1,5 ГБ — отправляются только БД и `.env`.
- `deploy/watchdog.sh` — каждые 5 мин: `/health`, контейнеры, диск, свежесть
  бэкапа; пишет в Telegram только при смене состояния. В режиме shared проверяет
  `127.0.0.1:8010/health` (nginx контейнера проксирует в api).
- `deploy/install-cron.sh` — идемпотентно ставит оба задания, при отсутствии
  создаёт `BACKUP_PASSPHRASE` и печатает его один раз.
- `deploy/ops.md` — бэкапы, восстановление, мониторинг, Cloudflare в РФ, лимиты, non-root.
- `deploy/runbook.md` — нарушители (`app.admin ban`), GDPR-запросы, возвраты, авария, утечки ключей.
- `deploy/scaling.md` — этапы роста и запасной план.

**Ручной деплой (если скрипты не подходят).**

```bash
# Вариант А — чистый VPS: Caddy сам выпускает сертификат, владеет 80/443
cp .env.example .env   # META_BOT_TOKEN, FERNET_KEY, PUBLIC_BASE_URL, DOMAIN, POSTGRES_PASSWORD
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build

# Вариант Б — на хосте уже свой nginx: frontend слушает только 127.0.0.1:8010
docker compose -f docker-compose.yml -f docker-compose.shared-vps.yml up -d --build
sudo cp deploy/nginx-vhost.example.conf /etc/nginx/sites-available/botfactory.conf   # прописать домен
sudo ln -s /etc/nginx/sites-available/botfactory.conf /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx && sudo certbot --nginx -d <домен>
```

На уже работающем сервере пароль БД через `.env` менять нельзя — он зашит в том
`db_data` (меняется в самой базе). Если том загрузок создан до перехода на non-root,
один раз `chown -R 10001:10001 /srv/media_uploads` (см. `deploy/ops.md`).

**Cloudflare/РФ-хост:** подключить `deploy/cloudflare-realip.conf` (настоящий IP),
SSL Full (strict), правило WAF «Skip» для `/webhook/*`, при блокировке Telegram —
`TELEGRAM_API_BASE_URL`. Локализация данных (152-ФЗ) и передача данных ЕС в РФ
(GDPR) — вопрос для юриста.

## 15. Масштабирование

Подробно — `deploy/scaling.md`. Коротко: `api` stateless, умножается;
`worker` отдельно и безопасен в нескольких копиях (захват условным UPDATE);
мета-бот один. Правило **expand → contract** для миграций: миграция должна
работать и со старым кодом (добавляй колонки/таблицы с дефолтом; удаление и
переименование — отдельным следующим обновлением), иначе плавное обновление
невозможно, и `deploy.sh` перезапустит `api` обычным способом.
Этапы: (1) один VPS, `API_REPLICAS=1`; (2) `API_REPLICAS=2–4`, S3 для файлов,
настройка Postgres; (3) отдельная БД + pgbouncer, второй VPS, метрики.
Узкие места: лимит Telegram 30 сообщений/с на бота, память (клиент на бота
~1–3 МБ), последовательный прогон вебхуков при старте `worker`.
**Цифры нагрузки — расчёт по коду, не замер: перед этапом 2 сделать нагрузочный тест.**

## 16. Разработка, тесты, ловушки

**Локально.** Python 3.12 (локально проходит и на 3.11), Postgres, `.env` из
`.env.example` (`FERNET_KEY` сгенерировать). `alembic upgrade head`, затем
`uvicorn app.main:app --reload` и (отдельно) `python -m meta_bot.main`;
`cd frontend && npm i && npm run dev`. Docker: `docker compose up --build`.

**Проверки (то же делает CI):**

```bash
pip install -r requirements-dev.txt
ruff check app meta_bot tests         # линтер (pyproject.toml: E,F,I,B,UP,BLE)
pytest -q                              # на настоящем Postgres из .env, ASGI в процессе
pip-audit -r requirements.txt && bandit -q -r app meta_bot -ll
cd frontend && npx tsc --noEmit && npm run build
```

**Тесты** (`tests/`): граф диалога, каждый платёжный провайдер (подписи/ответы),
денежные правила (идемпотентность `mark_paid`), биллинг платформы, подписки,
планировщик, мета-бот (`_tg_fakes.py`: `FakeSession` без сети, сессионная
фикстура `meta_dp`), юридические страницы, лендинг-конфиг, поддержка, кабинет,
админ-CLI, звёзды за запуск, сохранность платежей, hardening. Каждый тест
заводит своего клиента (`owner`, `stranger`) и удаляет его в конце
(`_purge_client` в `conftest.py` — платежи **не** удаляются каскадом).

**Сквозные проверки.** `tests/test_templates_e2e.py` проходит КАЖДЫЙ шаблон
конструктора как покупатель (старт → кнопка → счёт → оплата → выдача ровно один
раз → уведомление владельцу; для «Записи на сессию» — с именем покупателя).
Шаблоны берутся из `tests/fixtures/templates.json`, выгруженного из
`frontend/src/templates.ts` — **после правки шаблонов перевыгрузить**:
`cd frontend && npx esbuild src/templates.ts --bundle --format=esm --platform=node --outfile=/tmp/tpl.mjs && node -e "import('/tmp/tpl.mjs').then(m=>require('fs').writeFileSync('../tests/fixtures/templates.json',JSON.stringify(m.BOT_TEMPLATES.map(t=>({id:t.id,label:t.label,needsSubscriptions:!!t.needsSubscriptions,blocks:t.blocks})),null,1)))"`.
`tests/test_all_providers_contract.py` — общий договор всех касс (описание для формы
настроек, подделка уведомления не считается оплатой).

**Ловушки (набитые шишки):**

- Postgres в песочнице часто не запущен → массовые ERROR: `pg_ctlcluster 16 main start`.
- В песочнице стоят старые fastapi/starlette (нет `HTTP_413_CONTENT_TOO_LARGE`) →
  2 теста падают (`test_uploads_are_capped_per_account`, `test_a_block_cannot_hold_megabytes`);
  в CI с pinned-версиями проходят.
- aiogram: роутер подключается только к одному `Dispatcher`; тесты используют
  сессионный `meta_dp`. В обработчиках — явные `bot.edit_message_text`/`bot.answer_callback_query`
  (не `query.answer`, у `CallbackQuery` из теста нет привязанного бота).
- Подмены `platform_billing._tell_owner` в тестах должны принимать `**_` (есть параметр `renew`).
- Не используй `pkill -f` с шаблоном, совпадающим с твоей же командой — убьёт оболочку.
- Не вкладывай f-строки так, что нужен Python 3.12 (PEP 701), если хочешь гонять локально на 3.11.
- `ruff` в новой версии включает `BLE001` — новые `except Exception` помечай `# noqa: BLE001` с причиной.
- `nginx -t` для `nginx/default.conf`: `nginx -t -c` с обёрткой `events{} http{ include …/default.conf; }`.
- Платёжные провайдеры: деньги целыми; Stars — число звёзд ×100; не логируй токены.
- Миграции: цепочка линейная; `alembic check` на этой схеме шумит из-за enum-типов (известно, не ошибка).

## 17. Фронтенд и дизайн-проверка

Сборка: `cd frontend && npm run build` (tsc + vite). Дизайн-токены в `index.css`
(`--tg-*`, `--text-*`, `--accent-*`, `--sp-*`, `--radius-*`), тема светлая/тёмная
(`theme.ts`, ключ `bf_theme`), панели перетаскиваются (`bf_panel_offset`).
Брейкпоинты: 720px (лендинг), 960px (десктопный конструктор).

**Визуальная проверка** (Playwright, Chromium уже в `/opt/pw-browsers`, не
запускать `playwright install`): собрать фронт, запустить `npx vite preview --port
4173`, мокать `/api/*` через `page.route` (последний зарегистрированный маршрут
приоритетнее: `/api/config` регистрировать **после** общего `**/api/**`).
Снимать 1440×900, 390×844 и 360×640, светлую и тёмную темы.
Оценки независимого дизайнера по блокам (шкала 1–10) по ходу работ:
лендинг 8→8.5, конструктор десктоп 6.5→7.5, телефон 3.5→6.5, пейволл/предпросмотр
6.5→7.5; свежая оценка — в журнале.

## Журнал решений

Хронология важных решений (новое — внизу). Формат: что сделано → почему.

- **Аудит и жёсткая сборка.** Зависимости подняты (fastapi 0.142, sqlalchemy 2.1, aiogram 3.31, …), `hmac.compare_digest` и `defusedxml` в платёжных адаптерах, контейнер не от root, CI с pip-audit/bandit, `/docs` выключен, CSP report-only. → закрыть очевидные уязвимости до продаж.
- **Скрипты деплоя** (`deploy.sh`, `deployfirst.sh`). Сборка до остановки, дамп БД перед обновлением, автооткат только если не было миграций (иначе схема не совпадёт с кодом), `.deploy-running` вместо «HEAD = то, что работает» (после ручного `git pull` HEAD обманывал). Весь скрипт в `main()`. Нет `docker image prune` и `--remove-orphans` — на сервере чужие проекты.
- **Лендинг, юридические страницы, подвал.** Лендинг без выдуманных отзывов; документы из `.env`; кнопка «Поддержка» заметная, документы тихо.
- **Поддержка через @DragDropBot.** Relay в `SUPPORT_CHAT_ID`, `copy_message` вместо пересылки.
- **Кабинет владельца в мета-боте.** Пауза бота отдельно от биллингового `disabled`; пауза на уровне диспетчера.
- **Независимая проверка (3 агента).** Ревьюер, дизайнер, «клиент». Исправлено: токены в логах (httpx), платежи не каскадом (миграция 0016), пароль БД в `deployfirst.sh`, бэкап частями, `/health` в nginx, ротация логов, админ-CLI/блокировка (0017), уведомления о продажах через мета-бота, кнопка «Продлить», принятие условий в мета-боте, инструкция по токену, честный лендинг (нет «записи на время»), события Stripe без платежа → 200.
- **Оплата запуска по странам.** РФ — Crypto Bot и звёзды; КЗ/УЗ — + Stripe. Звёзды за запуск через мета-бота (`handlers/payments.py`). → Stripe не берёт плательщиков из РФ.
- **Цены.** $129 запуск + $15/мес, показываются на сайте (калькулятор окупаемости; прозрачность цены нужна и Stripe). Звёзды: 6490/750 (на руки меньше из-за курса Fragment).
- **Хостинг: русский VPS за Cloudflare.** `cloudflare-realip.conf`, WAF-skip для `/webhook/*`, `TELEGRAM_API_BASE_URL`, `DATA_LOCATION=Россия` + оговорка про GDPR.
- **Бэкапы «всё».** Части по 45 МБ, cron ставится из `bfdeploy`, `BACKUP_CHAT_ID` по умолчанию = `SUPPORT_CHAT_ID`.
- **Масштабирование.** Фоновые задачи вынесены в `worker`, `api` — в нескольких экземплярах (`API_REPLICAS`), плавное обновление, nginx переразрешает `api` каждые 5 с; пул БД 10+20. План — `deploy/scaling.md`. → «обновления не должны мешать работе».
- **GDPR.** Минимум данных, «сервис для СНГ». Обойти GDPR нельзя: эстонское OÜ подпадает по месту регистрации; отдельный риск — данные ЕС на сервере в РФ (передача за пределы ЕЭЗ). Решает юрист.
- **Дизайн, волны правок.** Пейволл — лист с затемнением (свёрнут по умолчанию), инспектор сбоку на десктопе, стрелки `smoothstep` слева→направо на десктопе, шаблон в 2 ряда, minZoom 0.8 на телефоне, хинт скрыт на телефоне. Все правки волн дописаны в конец `App.css`.
- **Полная проверка дизайна (5-я).** Оценки: лендинг десктоп 8.5, телефон 8, цена 8.5, конструктор десктоп 7.5, телефон 7, пейволл/предпросмотр 8. Исправлено: центрирование выбранного блока при открытии панели, новый блок под нижним (без наложения), чек-лист замечаний у живого бота в `<details>`, чипы лендинга короче, `undefined-й период` в продажах, оформление `/legal/*` (шапка, ссылка на сайт). Не сделано: форма токена в одной шторке с пейволлом, стартовый кадр холста на телефоне с узла «Старт», оформление «Выдача/Изображение/Видео» (эхо-подпись), касса (метки).
- **Проверка системы.** Все 19 касс: у каждой есть собственные тесты и общий договор (подделка ≠ оплата). Все 5 шаблонов (в т.ч. «Запись на сессию») проходят сквозной тест через настоящий диспетчер. Дизайн: форма токена — лист, схема на телефоне открывается со «Старт», подписи в кассе и панелях исправлены.
- **Как платят клиенты (UX оплаты запуска).** Пейволл угадывает страну по часовому поясу/языку и ставит первым рекомендованный способ (РФ → звёзды/крипта, КЗ/УЗ → карта); у каждого способа — «что произойдёт после нажатия» (`_HOW_IT_GOES` в `payment_service.py`) и «кому подходит» (`_WHO_CAN_PAY`); после ЛЮБОЙ оплаты платформе человеку приходит подтверждение в Telegram (`_confirm_to_client`, из `mark_paid`; звёзды отдельно не пишут). Ожидание оплаты — с подсказкой «напиши в поддержку».
- **Скорость оплаты.** Уведомления людям после оплаты (владельцу о продаже, клиенту о получении денег) уходят отдельной задачей со своей сессией БД (`_later` в `payment_service.py`), а не внутри ответа платёжной системе: медленный/недоступный Telegram с РФ-хоста иначе держал бы вебхук провайдера и вызывал повторы. Замер в песочнице без сети (Telegram недоступен): callback оплаты p50 22 мс, p95 78 мс; `/health` ×100 параллельно ≈1 с. Реальной нагрузки и живых провайдеров не измеряли.
- **Сверка касс с документацией (попытка).** Из песочницы официальные сайты провайдеров заблокированы прокси (`EGRESS_BLOCKED`), поэтому сверка шла по выдержкам поиска, докстрингам aiogram и сторонним SDK; **ни одна касса не подтверждена по первоисточнику.** Исправлено по подтверждённому: Freedom Pay `pg_recurring_lifetime` — месяцы (24, допустимо 1–156), а не 730 «дней»; Click — при несовпадении суммы ответ с кодом `-2`; Stripe — события `checkout.session.async_payment_succeeded/failed`, `payment_intent_data[metadata][payment_id]`, частичный возврат не отменяет заказ, любое подписанное событие без нашего платежа подтверждается 200. **Бэклог на проверку по документации** (гипотезы, не расхождения): ЮKassa/Т-Банк/Robokassa/PayMaster/Prodamus — нужен ли чек 54-ФЗ (`receipt`) при подключённой онлайн-кассе; Prodamus — экранирование `/` в JSON подписи; Robokassa — `SuccessURL2` в подписи; CloudPayments — откуда берётся токен для рекуррента; PayMaster — поле токена (`paymentToken`?); Freedom Pay — хост `api.freedompay.money` vs `.kz`, карты «Мир» (не подтверждены); Click — коды `-4`/`-9`; Payme — `GetStatement`, `-31007` при отмене выполненной, таймаут в Perform, `detail` для фискализации; ioka — единицы суммы и список статусов; Stripe — `invoice.paid` для продлений подписок; Stars — `refundStarPayment` (возврат звёзд не реализован), `pre_checkout_query` на продлениях подписки; LiqPay — статус `subscribed` и продления. Прогнать по документации с машины без блокировок.
- **Сверка по выжимке документации (`docs/payment-providers-docs.md`, собрана владельцем с помощью другого ассистента; статусы [офиц]/[не первоисточник]/НЕ СОБРАНО внутри).** По ней исправлено: Freedom Pay — хост `api.freedompay.kz` (официальный; для КГ `api.freedompay.kg`); Click — при отрицательном `error` от Click отвечаем `-9`; боты принимают команду `/terms` (требование Telegram для платящих ботов; у клиентских ботов нейтральный текст, у мета-бота — ссылка на оферту) и мета-бот — `/paysupport`. Совпало с документацией без правок: подпись/сырое тело Stripe и Crypto Bot, статусы Crypto Bot, подпись Click, коды Payme (-31001/-31050), `X-Content-HMAC` CloudPayments, подпись и статусы LiqPay. Остаётся сверить: всё из «НЕ СОБРАНО» в файле (PayMaster, LIFE PAY, lava.top, ioka, Processing.kz, чеки 54-ФЗ, рекуррент CloudPayments/Т-Банк).
- **Сверка кода с подробной выжимкой (`docs/payment-providers-docs.md`, 3 агента).** Исправлено: Prodamus — вебхук `multipart/form-data` разбирается через `form`, `order_canceled` = неуспех; lava.top — опрос счёта по `/api/v2/invoices/{id}`, события без нашего платежа (возвраты/чарджбэки без `contractId`) подтверждаются 200, а не 404; ioka — `CAPTURED` = оплата, `APPROVED` без списанной суммы = холд (не оплата), неизвестный статус = pending (не ошибка); LIFE PAY — ответ `/bill/status` как словарь `{number:{status}}`, уведомление о возврате ищет платёж по `original_number`; PayMaster — токен карты из `paymentToken.id`; Т-Банк — `PayType=O`, булевы в подписи словами `true/false`, `REVERSED` = неуспех (не возврат); CloudPayments — `TrInitiatorCode=0`, `PaymentScheduled=1`, `X-Request-ID`, HMAC принимается из любого из двух заголовков и в двух вариантах тела; Robokassa — убран `SuccessURL2` (его состав в подписи не подтверждён; адрес возврата — в кабинете); Payme — повторный `CancelTransaction` отменённой транзакции отвечает тем же состоянием, неизвестный id транзакции → `-31003`; Click — `-4` (уже оплачено), `-6` (чужой `merchant_prepare_id`), `-3` (неизвестное действие). Роутер теперь передаёт в адаптер `meta["_status"]`. **Осталось (нужно решение или первоисточник):** Prodamus — экранирование `/` в JSON подписи (проверить на demo.payform.ru); ЮKassa/Т-Банк/Robokassa/PayMaster/Prodamus — чек 54-ФЗ (`receipt`); Robokassa — тестовые пароли #1/#2 при `IsTest=1`; Payme — 12-часовой таймаут в Perform, повторное Create после отмены, `-31007`, `GetStatement`, тестовый хост `test.paycom.uz`; Freedom Pay — `pg_request_method`/`_method`, хост `.kg`, `pg_can_reject`; lava.top — `periodicity` из оффера; LiqPay — статус `subscribed`, продления `regular`, период 90 дней округляется в месяц, `sandbox` только в тесте; Processing.kz — единицы `totalAmount`, прод-хост, сверка суммы до `completeTransaction`; CloudPayments — откуда берётся токен, `orders/create`.
- **Ответы на открытые вопросы по кассам (`docs/payment-open-questions.md`).** Реализовано: Prodamus — подпись по официальному канону (значения как PHP `strval`, `/` → `\/`, исключая `signature/sign/_payform_sign`), второй ключ `webhook_secret` для уведомлений; Robokassa — тестовые пароли #1/#2 (`test_password1/2`), режим платежа запоминается (`meta.robokassa_test`) и уведомление проверяется паролем именно его режима, тестовое уведомление для боевого платежа отклоняется; Payme — таймаут 12 ч в Perform и повторном Create (причина 4, -31008), новая транзакция после отмены, песочница `test.paycom.uz` в тестовом режиме; Freedom Pay — поле `country` (kz/kg) выбирает хост; LiqPay — подписка только на 30/365 дней (иначе ошибка), `sandbox` засчитывается только тестовому платежу; чеки 54-ФЗ — для ЮKassa (`receipt`) и Т-Банка (`Receipt`) при заполненном `fiscal_email` (почта продавца, т.к. покупатель из Telegram почту не оставляет), НДС/СНО из полей кассы. **Не реализовано из ответов:** чеки Robokassa/PayMaster/Prodamus и общая модель `Receipt` с флагом фискализации в UI; Payme `-31007` и `GetStatement`; Freedom Pay ответ `rejected` при `pg_can_reject=1` и сохранение ответа для повторов; lava.top — `periodicity` из оффера и отмена подписки; LiqPay — обработка `action=regular`; Processing.kz — сверка суммы до `completeTransaction` (ждём единицы суммы и боевой хост от менеджера); CloudPayments — подписки провайдера вместо хранения токена. Нужно руками: Processing.kz (WSDL и единицы), тестовый платёж Freedom Pay (имя скрипта в подписи ответа), LiqPay (приходит ли `success` с `subscribed`), числовые `vat_code` ЮKassa для 22%, сохранить первый живой webhook Prodamus как регрессионный тест.
- **Остаток по кассам (`payments_remaining`, присланный владельцем).** Реализовано: общая модель чека 54-ФЗ в `base.py` (`Receipt`/`ReceiptItem`, `Vat` с 22%, `receipt_from_credentials`; чек уходит по явному переключателю `fiscalization_enabled` («Передавать чек», 1/0; `base.fiscalization_enabled`) — не по факту заполненной почты; включён без почты → внятная ошибка и «касса не настроена»; для настроек, сохранённых до переключателя (поля нет, почта есть), прежнее поведение; неизвестная ставка — ошибка, а не молчаливая подмена) и мапперы ЮKassa (`vat_code` 11 = 22%, 12 = 22/122; коды для 5/7% не сверены — отказ), Т-Банк (копейки, `vat22`; `vat20` больше нет), Robokassa (чек входит в подпись `Login:Sum:InvId:Receipt:Пароль1`, один раз закодированный `quote_plus`; в GET-ссылке он закодирован ещё раз — иначе ошибка 29), PayMaster (CamelCase). **Prodamus: налог в `products` НЕ передаём** — имена и коды полей не подтверждены первоисточником. `CredentialField.required` (необязательные поля — чеки, тестовые пароли — не мешают «касса подключена»; в форме подпись «необязательно»). Payme: `CancelTransaction` выполненной и уже выданной (`meta.delivered_at`) транзакции → `-31007`; `GetStatement` собирается роутером по платежам Payme, чей ключ подошёл к заголовку (`payme.statement_response`), для этого в `meta.payme` теперь хранятся `payme_time`, `amount`, `account`. Freedom Pay: `pg_can_reject=1` и проблема (сумма, валюта, заказ уже оплачен) → `rejected`; безотзывный платёж → `ok`, но товар не выдаём, `meta.freedompay_manual_refund` + ERROR в лог (вернуть деньги вручную); повтор уведомления получает тот же ответ байт в байт (`meta.freedompay_replies`). lava.top: период берётся из выбранной цены оффера (`block_fields.periodicity`), цена оффера сверяется по каталогу `offer_prices` (недоступен каталог — проверка пропускается), `cancel_subscription` (DELETE `/api/v1/subscriptions`, contractId первого платежа) вызывается из `subscription_service.cancel` для подписок на `RecurringMode.gateway` (общий хук `ProviderDefaults.cancel_subscription`, по умолчанию «не умею»; результат в `subscription.meta.gateway_cancel`). LiqPay: `action=regular`+`success` — продление (`WebhookResult.meta.gateway_renewal=<payment_id>`; `apply_result` двигает период один раз на id, повтор — нет, список в `payment.meta.renewals_seen`), `subscribed` — только запись, `unsubscribed` — отмена с сохранением оплаченного периода, `regular`+`failure` — лог. Processing.kz: сумма и валюта сверяются ДО `completeTransaction`; не сошлись — `completeTransaction(false)` (холд снимается), платёж `failed`. CloudPayments: `create_subscription` и `recurrent_state` написаны, но **не подключены** (режим остаётся `token`): прежде чем перейти на подписки шлюза, нужен живой тест — с каким `InvoiceId` приходят плановые Pay. **Не проверено на живых кассах ничего из этого.** Проверено отдельно: весь набор тестов проходит на версиях из `requirements.txt` (fastapi 0.142.2, starlette 1.7.0 — два «песочных» падения были из-за старого starlette локально); миграции 0013–0017 накатаны и откатаны на смоделированной базе (схема 0012 + 6 касс с зашифрованными ключами и 6 платежей) — ключи и платежи не изменились, все кассы остались «настроена»; **копию настоящей боевой базы я не видел — прогнать на ней перед `bfdeploy` должен владелец** (`pg_dump` → временная БД → `alembic upgrade head`). Осталось на человека: Processing.kz (WSDL, единицы суммы), тестовые платежи Freedom Pay и LiqPay, первый боевой вебхук Prodamus, коды налогов Prodamus, тест продлений CloudPayments. UI для чека (переключатель «передавать чек», выбор тарифа lava из `offer_prices`) пока только через поля кассы/блока — отдельного экрана нет.
- **Документация.** Этот README переписан целиком как справочник для следующих разработчиков и агентов.

## 19. Чего пока нет / идеи

- Чек 54-ФЗ для Prodamus (нужны коды налога из help.prodamus.ru), для рекуррентных списаний Robokassa; экран выбора тарифа lava.top по `offer_prices`; подписки CloudPayments на стороне шлюза (см. журнал).
- Нагрузочный тест и метрики (Prometheus/Uptime Kuma); структурированные логи.
- Инструмент для возвратов/споров Stripe (сейчас вручную по runbook).
- Вход в браузер по ссылке из мета-бота (сейчас запасной путь — «Открыть конструктор» в боте).
- Общение покупатель↔продавец внутри бота; свободный текст не обрабатывается.
- Подписанные временные ссылки на файлы; хранение файлов в S3.
- Мультиязычный интерфейс; включение боевого CSP; backpressure на вебхуки.
- Идеи по кабинету: график продаж, топ товаров, ежедневная сводка в мета-боте.
- Планировщик: параллельный прогон, обработка `RetryAfter` Telegram.
