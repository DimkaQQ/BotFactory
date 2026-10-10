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
| `routers/bot_profile.py` | оформление бота в Telegram: имя, описание, фото (Bot API токеном бота, у нас не хранится) |
| `routers/crm.py` | мини-CRM и календарь записи: клиенты, карточка, календарь, закрытие времени, отмена записи |
| `routers/reports.py` | страница жалоб `/report` (без входа) |
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
| `services/booking.py` | календарь записи: слоты, придержка/бронь, отмена, часовые пояса |
| `services/booking_flow.py` | диалог записи и блока «Контакты», подтверждение после оплаты |
| `services/moderation.py` | жалобы, журнал действий, снятие бота/блокировка владельца |
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
- `handlers/support.py` — поддержка: сообщения человека копируются в `SUPPORT_CHAT_ID`, ответ владельца через Reply возвращается автору **одним сообщением**: «Пришёл ответ от поддержки!» + все его ещё не отвеченные вопросы (до 5, цитатами) + «Ответ от поддержки» + подсказка писать снова через «💬 Поддержка» (вложение или ответ >3900 знаков уходит следующим сообщением; тексты вопросов — `support_relay.question_text`, `answered_at`, миграция 0019); диалог открыт 24 ч, троттлинг 12 сообщений/10 мин.
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
| `components/SalesPanel.tsx`, `SalesOverviewPanel.tsx`, `BroadcastButton.tsx`, `BillingBanner.tsx` | продажи бота, продажи и нажатия по всем ботам, рассылка, баннер периода |
| `components/CrmPanel.tsx`, `BookingEditor.tsx`, `BotProfilePanel.tsx` | клиенты и календарь записи, блоки «Запись»/«Контакты», оформление бота |
| `components/LivePreview.tsx`, `BlockPreviewFlyout.tsx` | предпросмотр сценария |
| `templates.ts`, `blockTypes.ts`, `humanDelay.ts` | шаблоны, типы блоков, «человеческая» пауза |
| `hooks/` | `useDraggablePanel`, `useEscape` (стопка окон: Escape закрывает одно верхнее), `useDialogA11y` (role=dialog, фокус), `useSwipeToDismiss`, `useTelegramWebApp`, `useWideScreen` |
| `plural.ts`, `placeholders.ts`, `motion.ts` | склонения, подстановка `[цена]` в предпросмотре (как `fill_placeholders` в боте), прокрутка с учётом `prefers-reduced-motion` |
| `confirm.ts` | подтверждение: нативный `showConfirm` Mini App только при `initData` и версии ≥ 6.2, иначе `window.confirm` |

### Прочее

- `migrations/versions/0001…0022` — alembic (список в §5).
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
- `bot_blocks` — блоки графа: `block_type` (`welcome, description, image, video, buttons, poll, delivery, delay, payment, booking, contact`), `content` JSONB, `next_block_id`, `position_x/y`, `order_index`.
- `bot_subscribers` — все, кто писал боту (имя, язык, `blocked_at`, `unsubscribed_at`).
- `payments` — **и** покупки в ботах (`kind=order`), **и** оплата платформе (`publication`, `renewal`): `invoice_no`, `status` (`pending|paid|failed|refunded`), `provider`, `amount_minor`, `currency`, `bot_id`/`client_id` (**`ON DELETE SET NULL`** — учёт переживает удаление бота/аккаунта), `block_id`, `telegram_user_id`, `chat_id`, `meta` JSONB (`delivered_at`, `checkout_url`, …).
- `subscriptions` — подписки покупателей бота (период, провайдер, доступ в чат).
- `scheduled_steps` — отложенные шаги/рассылки (`pending|sent|failed|cancelled`).
- `poll_answers`, `poll_sends` — ответы на опросы.
- `support_relay` — соответствие «сообщение в чате поддержки ↔ автор».
- `bookings` — записи клиентов, придержки и закрытое время (частичный уникальный индекс `uq_booking_active_slot`: одно время — одна активная запись); `chat_states` — бот ждёт ответ текстом (имя, телефон); `button_clicks` — нажатия кнопок; `abuse_reports`, `moderation_actions` — жалобы и журнал модерации. У `bot_subscribers` есть `contact_name/phone/note`.

Миграции: 0001 initial · 0002 имя бота · 0003 граф блоков · 0004 платежи ·
0005 backfill `delivered_at` · 0006 подписчики/планировщик/подписки · 0007 опросы ·
0008 продления платформы · 0009 poll_sends · 0010 отписка · 0011 enum-проверки ·
0012 отзыв сессий · 0013 принятие условий · 0014 `support_relay` · 0015 `paused` +
`notify_sales` · 0016 платежи не каскадом · 0017 `banned_at` · 0018 флаг чека · 0019 вопросы поддержки · 0020 модерация · 0021 нажатия кнопок · 0022 запись и CRM. `alembic check` чистый: Enum без нативного типа сравнивается с VARCHAR как равный (`migrations/env.py`).

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
- Оформление бота: `GET|PUT /api/bots/{id}/profile`, `POST|DELETE …/profile/photo`. Статистика: `GET …/button-stats`. `GET /api/meta-bot/status`.
- CRM и запись: `GET /api/crm/customers`, `GET|PATCH /api/crm/customers/{bot_id}/{telegram_user_id}`, `GET …/calendar`, `POST …/calendar/block`, `POST …/bookings/{id}/cancel`.
- Жалобы: `GET|POST /report` (без входа, лимит 5/час с адреса).
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

### Что подтверждено, а что нет (аудит 5 октября 2026)

**Подтверждено на живом шлюзе: ни одна касса** — ни одного реального платежа не
проводилось (`docs/live-payment-tests.md`, «Статус знаний»). Код и тесты зелёные
на моках; это не то же самое, что «касса работает». Уровни уверенности:

| Уровень | Кассы | Основание |
|---|---|---|
| Сверено с официальной докой/схемой (живого платежа нет) | ЮKassa (OpenAPI), Т-Банк, Robokassa, lava.top, ioka, Freedom Pay | файлы `docs/*` |
| Сверено с выжимкой (не первоисточник) | Stripe, Crypto Bot, LiqPay, Prodamus, LIFE PAY |
| Сверено с официальной докой с сайта провайдера (5 окт. 2026, `docs/official/*`), живого платежа нет | PayMaster (`/api/v2`), Payme (Merchant API целиком: методы, ошибки, состояния, ссылка checkout), ioka (`/v2/orders`, статусы, хосты), Click (Shop API: подпись Prepare/Complete, коды ошибок) |
| Сверено с полной официальной докой (`docs/cloudpayments-docs.txt`), живого платежа нет | CloudPayments, **кроме автопродлений** (см. ниже) | `docs/payment-providers-docs.md` |
| Не проверено, есть известная дыра | Processing.kz (нет официальной доки, боевой хост и единицы суммы неизвестны) | — |
| Не требует внешней проверки | Telegram Stars (апдейт Telegram), «по ссылке» (вручную) | — |

В UI и на лендинге не называть кассу «подключённой/проверенной», пока по ней не
пройден живой тест.

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
| `CORS_ORIGINS` | пусто (по умолчанию — только `PUBLIC_BASE_URL`); `*` только для разработки |
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
`cd frontend && npx esbuild src/templates.ts --bundle --format=esm --platform=node --outfile=/tmp/tpl.mjs && node -e "import('/tmp/tpl.mjs').then(m=>require('fs').writeFileSync('../tests/fixtures/templates.json',JSON.stringify(m.BOT_TEMPLATES.map(t=>({id:t.id,label:t.label,needsSubscriptions:!!t.needsSubscriptions,blocks:t.blocks,nexts:t.nexts,links:t.links})),null,1)))"`.
`tests/test_all_providers_contract.py` — общий договор всех касс (описание для формы
настроек, подделка уведомления не считается оплатой).

**Ловушки (набитые шишки):**

- Postgres в песочнице часто не запущен → массовые ERROR: `pg_ctlcluster 16 main start`.
- Тесты нужен `FERNET_KEY` (любой сгенерированный) и системный `python`, а не `uv`.
- aiogram: роутер подключается только к одному `Dispatcher`; тесты используют
  сессионный `meta_dp`. В обработчиках — явные `bot.edit_message_text`/`bot.answer_callback_query`
  (не `query.answer`, у `CallbackQuery` из теста нет привязанного бота).
- Подмены `platform_billing._tell_owner` в тестах должны принимать `**_` (есть параметр `renew`).
- Не используй `pkill -f` с шаблоном, совпадающим с твоей же командой — убьёт оболочку.
- Не вкладывай f-строки так, что нужен Python 3.12 (PEP 701), если хочешь гонять локально на 3.11.
- `ruff` в новой версии включает `BLE001` — новые `except Exception` помечай `# noqa: BLE001` с причиной.
- `nginx -t` для `nginx/default.conf`: `nginx -t -c` с обёрткой `events{} http{ include …/default.conf; }`.
- Платёжные провайдеры: деньги целыми; Stars — число звёзд ×100; не логируй токены.
- Миграции: цепочка линейная; `alembic check` должен быть чистым — при правке моделей держи их в соответствии с миграциями (индексы объявляются в модели).

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
- **Ответы на открытые вопросы по кассам (`docs/payment-open-questions.md`).** Реализовано: Prodamus — подпись по официальному канону (значения как PHP `strval`, `/` → `\/`, исключая `signature/sign/_payform_sign`), второй ключ `webhook_secret` для уведомлений; Robokassa — тестовые пароли #1/#2 (`test_password1/2`), режим платежа запоминается (`meta.robokassa_test`) и уведомление проверяется паролем именно его режима, тестовое уведомление для боевого платежа отклоняется; Payme — таймаут 12 ч в Perform и повторном Create (причина 4, -31008), новая транзакция после отмены, песочница `test.paycom.uz` в тестовом режиме; Freedom Pay — поле `country` (kz/kg) выбирает хост; LiqPay — подписка только на 30/365 дней (иначе ошибка), `sandbox` засчитывается только тестовому платежу; чеки 54-ФЗ — для ЮKassa (`receipt`) и Т-Банка (`Receipt`) (первая версия — по заполненной `fiscal_email`; позже заменено явным флагом, см. следующую запись), НДС/СНО из полей кассы. **Не реализовано из ответов:** чеки Robokassa/PayMaster/Prodamus и общая модель `Receipt` с флагом фискализации в UI; Payme `-31007` и `GetStatement`; Freedom Pay ответ `rejected` при `pg_can_reject=1` и сохранение ответа для повторов; lava.top — `periodicity` из оффера и отмена подписки; LiqPay — обработка `action=regular`; Processing.kz — сверка суммы до `completeTransaction` (ждём единицы суммы и боевой хост от менеджера); CloudPayments — подписки провайдера вместо хранения токена. Нужно руками: Processing.kz (WSDL и единицы), тестовый платёж Freedom Pay (имя скрипта в подписи ответа), LiqPay (приходит ли `success` с `subscribed`), числовые `vat_code` ЮKassa для 22%, сохранить первый живой webhook Prodamus как регрессионный тест.
- **Остаток по кассам (`payments_remaining`, присланный владельцем).** Реализовано: общая модель чека 54-ФЗ в `base.py` (`Receipt`/`ReceiptItem`, `Vat` с 22%, `receipt_from_credentials`; чек уходит **строго по явному переключателю** `fiscalization_enabled` («Передавать чек», 1/0; `base.fiscalization_enabled`) — никаких догадок по заполненной почте; магазинам, у которых почта для чеков уже была, флаг `1` проставила миграция данных `0018` (читает настройки тем же `FERNET_KEY`; не расшифровалась ни одна строка — миграция падает, а не молчит); флаг включён, а слать некуда → ошибка ДО создания платежа (`check_receipt_contact` в `payment_service._create`) и «касса не настроена». Кому уходит чек: контакт покупателя (`CheckoutRequest.buyer_email/buyer_phone`, из `meta.buyer_email/buyer_phone` платежа; для автосписаний — с первого платежа подписки через служебные ключи `_buyer_*` в credentials) → иначе почта продавца; **сейчас ни один шаг диалога контакт покупателя не собирает** (нужны шаг в диалоге, колонка и правка политики конфиденциальности — минимизация данных), поэтому на практике чек идёт на почту продавца; неизвестная ставка — ошибка, а не молчаливая подмена) и мапперы ЮKassa (`vat_code` 11 = 22%, 12 = 22/122; коды для 5/7% не сверены — отказ), Т-Банк (копейки, `vat22`; `vat20` больше нет), Robokassa (чек входит в подпись `Login:Sum:InvId:Receipt:Пароль1`, один раз закодированный `quote_plus`; в GET-ссылке он закодирован ещё раз — иначе ошибка 29), PayMaster (CamelCase). **Prodamus: налог в `products` НЕ передаём** — имена и коды полей не подтверждены первоисточником. `CredentialField.required` (необязательные поля — чеки, тестовые пароли — не мешают «касса подключена»; в форме подпись «необязательно»). Payme: `CancelTransaction` выполненной и уже выданной (`meta.delivered_at`) транзакции → `-31007`; `GetStatement` собирается роутером по платежам Payme, чей ключ подошёл к заголовку (`payme.statement_response`), для этого в `meta.payme` теперь хранятся `payme_time`, `amount`, `account`. Freedom Pay: `pg_can_reject=1` и проблема (сумма, валюта, заказ уже оплачен) → `rejected`; безотзывный платёж → `ok`, но товар не выдаём, `meta.freedompay_manual_refund` + ERROR в лог (вернуть деньги вручную); повтор уведомления получает тот же ответ байт в байт (`meta.freedompay_replies`). lava.top: период берётся из выбранной цены оффера (`block_fields.periodicity`), цена оффера сверяется по каталогу `offer_prices` (недоступен каталог — проверка пропускается), `cancel_subscription` (DELETE `/api/v1/subscriptions`, contractId первого платежа) вызывается из `subscription_service.cancel` для подписок на `RecurringMode.gateway` (общий хук `ProviderDefaults.cancel_subscription`, по умолчанию «не умею»; результат в `subscription.meta.gateway_cancel`). LiqPay: `action=regular`+`success` — продление (`WebhookResult.meta.gateway_renewal=<payment_id>`; `apply_result` двигает период один раз на id, повтор — нет, список в `payment.meta.renewals_seen`), `subscribed` — только запись, `unsubscribed` — отмена с сохранением оплаченного периода, `regular`+`failure` — лог. Processing.kz: сумма и валюта сверяются ДО `completeTransaction`; не сошлись — `completeTransaction(false)` (холд снимается), платёж `failed`. CloudPayments: `create_subscription` и `recurrent_state` написаны, но **не подключены** (режим остаётся `token`): прежде чем перейти на подписки шлюза, нужен живой тест — с каким `InvoiceId` приходят плановые Pay. **Не проверено на живых кассах ничего из этого.** Проверено отдельно: весь набор тестов проходит на версиях из `requirements.txt` и на **Python 3.12.3** как на сервере (fastapi 0.142.2, starlette 1.7.0 — два «песочных» падения были из-за старого starlette локально); миграции 0013–0018 накатаны и откатаны на смоделированной базе (схема 0012 + 6 касс с зашифрованными ключами и 6 платежей) — ключи и платежи не изменились, все кассы остались «настроена»; **копию настоящей боевой базы я не видел — прогнать на ней перед `bfdeploy` должен владелец** (`pg_dump` → временная БД → `alembic upgrade head`). Осталось на человека: Processing.kz (WSDL, единицы суммы), тестовые платежи Freedom Pay и LiqPay, первый боевой вебхук Prodamus, коды налогов Prodamus, тест продлений CloudPayments. **Чек-лист живых тестов по каждой кассе — `docs/live-payment-tests.md`** (держать в синхроне с адаптерами). UI для чека (переключатель «передавать чек», выбор тарифа lava из `offer_prices`) пока только через поля кассы/блока — отдельного экрана нет.
- **Поддержка — понятные тексты и ответ одним сообщением.** Экран «Поддержка» для людей: «Пишите сюда своё сообщение — оно уйдёт в техподдержку, ответ получите здесь же, отвечаем в течение 24 часов»; для владельца — объяснение, как отвечать (Reply). Квитанция «Сообщение отправлено в поддержку…». Ответ владельца собирается в одно сообщение с вопросами человека (`support.compose_answer`, HTML экранируется). Раньше бот копировал ответ как есть, и человеку было непонятно, на что это. Миграция 0019 — две nullable-колонки (expand, старый код не мешает). Если `SUPPORT_CHAT_ID` не задан, бот отвечает «Поддержка пока не подключена» — после правки `.env` контейнер `bot` надо пересоздать (`docker compose up -d --no-deps --force-recreate bot`), `restart` переменные не перечитывает.
- **Т-Банк по официальной документации (`docs/tbank-docs.md`).** Сверен `tbank.py`; исправлено: тестовый режим теперь реально идёт на `rest-api-test.tinkoff.ru` (раньше «тест» ходил на боевой хост; терминал с `DEMO` — на боевой), режим платежа в `meta.tbank_test`; подпись `Token` уведомления проверяется ДО обращения в банк (раньше любой мог заставить нас ходить в банк с ключами продавца), `null` в подписи пропускается; `Init`: `OrderId` — 32 знака без дефисов (`payment_id.hex`; старые с дефисами по-прежнему находятся), `Description` ≤ 140 и без `& < > ' "`, `PayType` НЕ передаётся (не должен противоречить терминалу продавца), для подписки `DATA.OperationInitiatorType` = `"1"`, продления — `"R"` с чеком в `Init` (в `Charge` чека нет); двухстадийный терминал: на `AUTHORIZED` адаптер вызывает `Confirm` (с тем же чеком из `meta.tbank_receipt`) и верит только следующему `GetState`; успех = `Success` И `ErrorCode == "0"`, коды ошибок объясняются по-русски (10 — автоплатежи не включены, 204/205/322 — ключи, 309 — нужен чек и т.д.); результат `Charge` при обрыве связи не повторяется, а проверяется `GetState` (`_Unknown`); сверка `OrderId`; `RebillId` берётся и из `GetState`; нет `PaymentURL` → объяснение, как включить платёжную форму. **Признак расчёта в чеке теперь `full_payment`** (для ЮKassa/Т-Банка/Robokassa/PayMaster; раньше `full_prepayment` из общей модели — без закрывающего чека это налоговая недоработка). **TLS:** банк переходит на сертификаты Минцифры, которых нет в certifi: `TBANK_CA_BUNDLE`, `./certs` монтируется в `api` и `worker` (`docker-compose.yml`), `deploy/install-russian-ca.sh` скачивает и печатает отпечатки (сверить вручную). Не сделано: возвраты из конструктора (`Cancel` + `ExternalRequestId`), проверка IP банка, `RemoveCard` при отмене подписки, кнопка «Проверить подключение», текст согласия на автосписания. Не проверено на живом терминале.
- **lava.top, ioka, Robokassa и Freedom Pay по присланной документации** (`docs/lava-top-api.yaml`, `docs/ioka-api.json`, `docs/robokassa-docs.txt`). **lava.top:** продление подписки находится по `parentContractId` (раньше по новому `contractId` — платёж не находился, и продления не продлевали период), продление идёт через `gateway_renewal` и не перезаписывает `provider_payment_id` первой покупки; событие `subscription.cancelled` проверяется `GET /api/v1/subscriptions/{id}`; цена блока сверяется с каталогом (число с копейками), а не с целой суммой из ответа на создание счёта. **ioka:** только тенге (`KZT`); ключ API по Client ID/Secret (`POST /v2/auth/token`, истекает: кэш в памяти, обновление за минуту до срока и после 401; поле `api_key` оставлено для старых настроек); вебхук регистрируется адаптером при первой оплате (`POST /v2/webhooks`, если нашего адреса нет); возврат определяется по `refunded_amount` платежей на событие `REFUND_APPROVED`; уведомления про чужие заказы магазина подтверждаются 200. **Robokassa:** алгоритм хэша из настроек магазина (`hash_algo`: md5 по умолчанию, sha1/256/384/512, ripemd160) для подписи ссылки, ResultURL и рекуррента — раньше был жёстко MD5, и магазин с другим алгоритмом получал ошибку 29 на каждый платёж; `Shp_*` участвуют в проверке ResultURL; описание очищается от спецсимволов. **Freedom Pay:** первый файл — пересказ ассистента, не первоисточник; следом пришёл официальный Overview (`docs/freedompay-docs.txt`) и подтвердил наш код (`init_payment.php`, подпись с именем скрипта): для приёма платежей Merchant API и Partner API не нужны, затем пришла схема Recurrent (`docs/freedompay-docs.txt`): списание по профилю — `POST /g2g/recurrent`, подпись от имени `recurrent` (раньше был легаси `make_recurring_payment` — исправлено), добавлен хост Узбекистана `api.freedompay.uz` (`country=uz`); тестовые карты и телефоны — в `docs/live-payment-tests.md`. **Не использовано:** `api.yaml` — это API платформы XL.ru (курсы и CRM), не платёжная касса. Не проверено на живых кассах.
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
- **Полные доки Robokassa/lava.top/Freedom Pay (5 октября 2026)** (`docs/robokassa-openapi.yaml`, `docs/lava-top-docs.txt`, `docs/freedompay-docs.txt`; два прежних куска Freedom Pay удалены как устаревшие). **Freedom Pay:** `init_payment.php` подтверждён как корректный способ создания платежа; добавлены статус по запросу (`/g2g/status_v2`, `supports_status_check`), подтверждение двухстадийных платежей (`/g2g/clearing` при `pg_captured=0`, товар только после списания), `pg_order_id` — hex платежа (`meta.freedompay_order_id`), `pg_idempotency_key` в автоплатежах, статус сразу после продления. **Robokassa:** статус по запросу через `OpStateExt` (только боевой режим), чек в рекуррентном запросе и его подписи. **lava.top:** адреса возврата отправляются только если `https` и ≤512 знаков. **Не сделано:** возврат Robokassa (Refund API, Password3/JWT), возврат/отмена и фискальные чеки KZ у Freedom Pay, поля result-URL Freedom Pay вне базовых не описаны, возвраты/чарджбэки lava.top нельзя привязать к платежу (нет `contractId`). Не проверено на живых кассах.
- **Решение владельца (5 октября 2026): возвраты и отмены платежей из конструктора не делаем.** Клиенты возвращают деньги сами, в личных кабинетах платёжных провайдеров. Не реализуем и не предлагаем: Refund API Robokassa, возврат/отмену Freedom Pay, возврат ioka, Cancel T-Bank. Адаптеры только *замечают* возврат, если провайдер его сообщил (статус `refunded`), а кнопка «Возврат» в боте лишь закрывает заказ у нас. Из «не сделано» эти пункты вычеркнуты как осознанный отказ, а не долг.
- **ЮKassa по официальному OpenAPI (`docs/yookassa-openapi.yaml`).** Телефон в чеке — только цифры (схема: `[0-9]{4,15}`, раньше уходил с «+»), `quantity` — числом; уведомление `refund.succeeded` теперь находит платёж по `object.payment_id` (раньше искало по id возврата и не находило); частичный возврат больше не помечает платёж `refunded` (только когда возвращена вся сумма, как и написано в чек-листе); новое необязательное поле `tax_system_code` (1–6, тег 1055). Коды НДС 5 %/7 % не добавлены: в файле только диапазон 1–12 без таблицы. Не использовано: `/me` (мог бы проверять подключение и включённые чеки), `POST /receipts`, сделки и выплаты.
- **Решение владельца (5 октября 2026): платформа не ведёт учёт возвратов и чарджбэков.** Шлюз подтвердил оплату — выдаём товар; что было дальше (возврат, спор), клиент решает и делает сам в кабинете провайдера. Поэтому не привязываем возвраты lava.top к платежам, не показываем их владельцу и не доделываем распознавание возвратов у остальных касс. Что остаётся и не убирается: запись о платеже нужна для идемпотентности (`mark_paid`, повторные уведомления), периодов подписок и учёта продаж — это не «статус заказа для клиента», а защита от двойной выдачи. Уже существующее распознавание возврата (`refunded`) только меняет метку в статистике продаж, доступ и выданный товар не отзывает; оставлено как есть.
- **Критерий «закрыта ли касса» (решение владельца, 5 октября 2026).** Касса считается закрытой, если покупатель владельца может оплатить и получить товар: создание платежа → подтверждение оплаты (вебхук с проверкой подписи или перечитывание статуса) → выдача, плюс продления для подписок. Всё остальное, чего у провайдера нет или что нам не нужно (возвраты, отмены, чарджбэки, статусы по запросу, фискальные чеки KZ, сделки и выплаты), — не пробел. Нерешённым остаётся только то, что ломает основной путь: Processing.kz (нет официальной доки, неизвестны боевой хост и единицы суммы), поля result-URL у Freedom Pay (проверить в первом живом платеже). Подписки Prodamus — только если продаём подписки через неё. Настоящее закрытие любой кассы — живой тест по `docs/live-payment-tests.md`.
- **Аудит подтверждённости касс (5 октября 2026).** Ни одна касса не проверена живым платежом; в README §7 добавлена таблица уровней уверенности. Пробелы, ломающие основной путь: Processing.kz, result-URL Freedom Pay. CloudPayments: по официальному тексту «Проверка уведомлений» `Content-HMAC` — от URL-encoded тела, `X-Content-HMAC` — от decoded; адаптер сверяет каждый заголовок только со своим вариантом (раньше принимал любую комбинацию), тест `test_cloudpayments_pairs_each_hmac_header_with_its_own_body_variant`. Адреса CloudPayments для уведомлений: 185.98.81.0/28, 87.251.91.160/27, 46.46.175.96/27, 46.46.168.160/27, 162.55.174.97/32, 91.216.178.243/32 (фильтрация по IP не включена).
- **CloudPayments — полная официальная дока сохранена (`docs/cloudpayments-docs.txt`).** Сверка: `orders/create`, `v2/payments/find`, подпись уведомлений, статусы (`Completed`/`Authorized`/`Declined`/`Cancelled`), `{"code":0}`, Basic Auth, валюты (RUB/USD/EUR/GBP/UAH/KZT) — совпадают с адаптером. **Найдено расхождение в автопродлениях (не исправлено, нужно решение):** токен карты приходит в Pay только если в платеж передан `AccountId` и `SaveCard=true`, а в кабинете включена настройка «Сохранение токена карты». `orders/create` параметра `SaveCard` не имеет, и мы не передаём `AccountId`, поэтому для платежа по ссылке токена не будет, и `recurring = token` (списание через `payments/tokens/charge`) не сработает. Рабочие пути: подписка на стороне шлюза через `SubscriptionBehavior=CreateMonthly|CreateWeekly` в `orders/create` (плановые Pay приходят с `SubscriptionId`; с каким `InvoiceId` — проверить живым тестом) либо платёж через виджет с `SaveCard`. Разовые продажи не затронуты. Тестовые карты: 4242 4242 4242 4242 (успех), 4012 8888 8888 1881 (нет средств); срок любой, CVV любой.
- **Официальная документация с сайтов провайдеров (5 октября 2026, `docs/official/`).** Скачано: Robokassa, ioka, PayMaster, Payme, Freedom Pay (KZ), Click (из JS-чанков сайта, текст шумный: страницы дублируются), LIFE PAY (только маркетинговая страница LIFE POS — это не та дока). **Сверено без правок кода:** PayMaster (адреса, тело счёта, статусы, отсутствие подписи уведомления — подтверждено, истина берётся из `GET /payments/{id}`), Payme (все методы, коды -31001/-31003/-31007/-31008/-31050…, состояния 1/2/-1/-2, таймаут 12 ч, ссылка `checkout.paycom.uz/base64(m;ac.*;a;c)`, песочница `test.paycom.uz`), ioka (`POST /v2/orders`, хосты `api`/`stage-api`, статусы заказа; подпись вебхука — HMAC-SHA256 от JSON с отсортированными ключами без пробелов, заголовок `X-Signature`, IP отправителя 94.247.132.210; мы подпись не проверяем, а перечитываем заказ через API — это надёжнее), Click (формулы `sign_string` Prepare/Complete, коды ошибок 0…-9). **Недоступно с этого хоста (прокси):** liqpay.ua, developer.tbank.ru, docs.life-pay.ru; Freedom Pay UZ (`freedompay.uz/docs-en`) отдаёт пустую страницу без JS. Для них нужны разрешённые домены в сетевой политике окружения или текст документации файлом. Формат платёжной ссылки Click в скачанном тексте не найден.
- **Ответы провайдеров на письма (6 октября 2026).** **Prodamus:** подписок в сервисе нет, только разовые платежи (поэтому подписки через Prodamus не продаём; в настройках блока не предлагать); тестовая платёжная страница есть, нужен ответ, с каким сервисом интеграция; инструкция по REST API: help.prodamus.ru/payform/integracii/rest-api/instrukcii-dlya-samostoyatelnaya-integracii-servisov (с этого хоста закрыта прокси). **LiqPay:** отдельной песочницы нет, тестовые ключи выдаются после регистрации мерчанта; агентская схема требует ≥1 млн грн/мес, клиентов вне ПриватБанка, сферу деятельности в Украине и 3+ месяца опыта — не проходим; документация: liqpay.ua/doc/api/testing, /checkout, /callback, /information/status_payment (закрыта прокси). **Т-Банк, LIFE PAY:** без ИНН компании не помогают. **ЮKassa, Payme, Processing.kz:** обращение принято, ждём ответа. **CloudPayments, Click:** ответили в Telegram (созвон и «платёжный узел» через юрлицо/ЯТТ).
- **Старт с проверяемыми кассами (6 октября 2026).** Решение владельца: убрать всех провайдеров, кроме тех, кто дал тестовый доступ или не требует юрлица. Click и LIFE PAY отказали без юрлица/ЯТТ (Click: ключи выдаются только после договора и открытия «узлового сервиса»), Т-Банк просит ИНН, Payme просит договор, LiqPay — только после регистрации мерчанта. Реализовано переменной `OFFERED_PAYMENT_PROVIDERS` (slug через запятую, `*` — все; по умолчанию `stars,yookassa,cloudpayments,prodamus,cryptobot,link,test`): `describe_providers(offered_only=True)` отдаёт каталог конструктору (`GET /api/payments/providers`) и лендингу (`/config`), `PUT payment-settings` не принимает скрытую кассу для нового выбора (бот, который уже ею пользуется, не ломается). Адаптеры остаются в реестре и принимают вебхуки. Вернуть кассу: добавить slug в переменную и пересоздать контейнер `api`. Подписки на старте выключены (`SUBSCRIPTIONS_ENABLED=0`, `.env.example`). Prodamus (в представительстве ТОО «ПРО ЭДЮКЕЙШН») заявил, что подписок в их сервисе нет.
- **Robokassa ответила (6 октября 2026).** Тест: достаточно зарегистрировать кабинет, тестовые настройки доступны сразу, без активации магазина и документов; рекуррент — только после полной анкеты и активации. `SuccessURL2` необязателен, но если он передаётся, входит в подпись; `Shp_*` всегда входят в подпись по алфавиту. Наш код `SuccessURL2` не отправляет, `Shp_*` при проверке уведомления учитывает — менять нечего. Касса возвращена в `OFFERED_PAYMENT_PROVIDERS`. Партнёрская программа: robokassa.com/offers/partners.php.
- **PayMaster, lava.top и ioka возвращены в каталог (6 октября 2026, решение владельца).** `OFFERED_PAYMENT_PROVIDERS` по умолчанию: `stars,yookassa,cloudpayments,prodamus,robokassa,paymaster,lavatop,ioka,cryptobot,link,test`. Они в запуске без пройденного теста: код сверен с документацией, но доступа/песочницы нет (PayMaster — нужен кабинет, у lava.top в адаптере нет тестового режима и проверка — минимальный настоящий платёж, у ioka stage выдаёт менеджер). Пошаговая инструкция по подключению: `docs/provider-setup.md`; подробная для владельцев ботов — `docs/kassa-guide.md` (места под скриншоты `docs/img/*.png` — снимки делаются с живых кабинетов).
- **PayMaster, lava.top и ioka убраны из каталога (7 октября 2026, решение владельца).** `OFFERED_PAYMENT_PROVIDERS` по умолчанию: `stars,yookassa,cloudpayments,prodamus,robokassa,stripe,cryptobot,link,test`. Код и вебхуки остаются; вернуть — добавить slug в `.env` и пересоздать `api`.
- **UI-раунд 1 (7 октября 2026).** Лендинг: кассы одним списком без деления по странам. Тема: только тёмная (по умолчанию) и светлая, режим «авто» убран (`theme.ts`, `ThemeToggle.tsx`, скрипт в `index.html`; старое значение `system` в localStorage игнорируется). Виджет входа Telegram в тёмной теме: `color-scheme: light` и скругление на iframe. Пустой список ботов: стрелка короче и не заходит на кнопку. Текстовые поля блоков (`.chat-bubble__textarea`) прокручиваются при длинном тексте (`overflow-y: auto`, `max-height`). Файл «Выдачи»: в редакторе имя показывается без `<uuid>-`, а покупателю в Telegram `send_document` отдаёт имя без префикса (`_document_input` в `bot_dispatcher.py`, `URLInputFile`); в выбор файла добавлены JPG/PNG/видео (раньше `accept` их не пускал). Окно правки блока: свои keyframes (`panel-in-*`, на десктопе общий `sheet-in` сдвигал его как центрированную модалку и окно «прыгало»), плавное закрытие, шире на десктопе (420px), `82dvh` и safe-area на телефоне.
- **UI-раунд 2 (7 октября 2026).** (1) Настройка оплаты (`PaymentSettingsPanel.tsx`): кассы одним списком, «Своя ссылка» и «Пока без оплаты» — отдельными понятными карточками, «Демо-оплата» спрятана в раскрывающийся блок (больше не подсвечивается рядом с кассами), вверху строка «Сейчас: …», режим кассы — два явных варианта «🧪 Тестовый / 💰 Боевой». (2) Запуск бота: мета-бот должен уметь писать владельцу (`platform_billing.can_reach_owner`, `GET /api/meta-bot/status`); пока Telegram отвечает «нельзя», `publish` отдаёт 409, а форма публикации показывает шаг 1 «нажми Start в @мета-боте», шаг 2 — токен. Сбой проверки (сеть, мета-бот не настроен) не блокирует. После запуска мета-бот присылает «✅ Бот запущен». (3) Оформление бота (`app/routers/bot_profile.py`, `BotProfilePanel.tsx`): имя, «Что умеет этот бот» (≤512, видно до /start), краткое описание (≤120), фото (клиент приводит к квадратному JPEG) — через Bot API токеном бота, у нас не хранится. (4) Быстрые кнопки: `content.keyboard = "reply"` в блоке «Кнопки» отправляет `ReplyKeyboardMarkup`, нажатие приходит текстом и находится по подписи (`_handle_reply_button`); подписи лучше делать разными. (5) Заготовки `[цена]`, `[название продукта]` в тексте блоков подставляются из первого блока оплаты бота (`fill_placeholders`), без данных — убираются. (6) Список блоков на телефоне: фон не прокручивается, нижний пункт приподнят над панелью Safari.
- **Быстрые кнопки: режим «убрать» и демо (7 октября 2026).** `content.keyboard = "remove"` в блоке «Кнопки» шлёт `ReplyKeyboardRemove` (текст по умолчанию «Кнопки убраны»), цепочка идёт дальше по обычной стрелке. Редактор кнопок: три режима (под сообщением / быстрые внизу / убрать) с пояснением, когда нужен «убрать», и мини-макетом «так это увидит покупатель». Предпросмотр «Как в чате» показывает быстрые кнопки внизу и снимает их после блока «убрать». Новый шаблон «Меню с быстрыми кнопками» (`quick-menu`, разводка кнопок по блокам через `links` в `templates.ts`). Переключение вида действует сразу после автосохранения (~0,5 с): бот читает блоки из БД на каждое сообщение, уже отправленные сообщения не меняются.
- **Свободное расписание записи без привязки к городу (8 октября 2026).** В блоке «Запись» часы теперь задаются по каждому дню недели, с несколькими промежутками на день (перерыв) и особыми датами (`content.weekly` — `{"0": [["10:00","13:00"],["14:00","19:00"]], …}`, пустой список = выходной; `content.exceptions` — `{"2026-10-19": []}` закрыто весь день, или свои часы только на эту дату). Прежний формат (`days`/`start`/`end`) читается как раньше. Часовой пояс больше не «Алматы» по умолчанию: редактор подставляет пояс устройства владельца и позволяет выбрать любой из списка IANA; без пояса сервер берёт UTC. Расписание правится и прямо в «Клиенты → Календарь → ⚙ Расписание» (`GET/PUT /api/bots/{id}/booking-schedule`, пишет в первый блок «Запись» бота; не-IANA пояс — 400) и там же кнопки «Закрыть день / Открыть день» на каждом дне. Сервис: `booking.schedule_of/intervals_for/day_slots/clean_schedule`; интерфейс: `ScheduleFields` в `BookingEditor.tsx`, `src/booking.ts`. Время в расписании и клиенту показывается по выбранному поясу.
- **Платёж за каждый бот + одна подписка на все (8 октября 2026).** Цены задаются как раньше в `PLATFORM_PAYMENT_METHODS`: `price_minor` — разовая плата за запуск каждого бота ($49 = 4900), `renewal_price_minor` — одна подписка на все боты клиента за 30 дней ($15 = 1500). Как считается: оплата запуска первого бота (подписки ещё нет или она кончилась) включает первый месяц для всех ботов клиента (`platform_billing.open_for_launch`); запуск следующих ботов при идущей подписке стоит только $49, дата подписки у всех ботов общая и не двигается; продление $15 двигает счётчик всем ботам сразу (`extend_all`) и возвращает остановленных (`resume`); открытый счёт на продление переиспользуется, из какого бота ни нажали «Продлить» (`_open_platform_payment` по `client_id`). Проверка периода идёт по ботам, но напоминания приходят один раз на клиента (самый ранний бот — «якорь»), снимаются с эфира все боты клиента. Публикация бота при просроченной подписке: 402. `bots.paid_until` — общая дата подписки у ботов клиента (копия для интерфейса и мета-бота); отдельного счётчика на клиенте нет. Тексты на лендинге, в пейволле и баннере продления переписаны под модель «запуск за бот + одна подписка». Тесты: `tests/test_shared_subscription.py`. Для запуска в `.env`: `PLATFORM_PAYMENT_METHODS=[{"provider":"stripe","price_minor":4900,"renewal_price_minor":1500,"currency":"USD",...}, {"provider":"cryptobot",...,"currency":"USDT"}, {"provider":"stars","price_minor":245000,"renewal_price_minor":75000,"currency":"XTR"}]` (см. `.env.example`), `SUBSCRIPTIONS_ENABLED=0` (это про подписки покупателей, не про подписку платформы).
- **Решения владельца по итогам аудита (7 октября 2026).** (1) Слепок кассы: при выставлении счёта в `payment.meta["kassa"]` кладутся зашифрованные ключи и режим; пока счёт не оплачен (и не старше 48 ч), он подтверждается этими ключами, даже если владелец сменил кассу или ключи (`credentials_for`); при оплате и через 48 ч слепок стирается (`scrub_old_kassa_snapshots`). Прежняя блокировка смены кассы на 2 часа убрана — она не нужна и мешала при утечке ключа. (2) Не больше 3 подтверждённых будущих записей на человека в боте (`MAX_ACTIVE_PER_PERSON`, `BookingLimitError`). (3) Заглушки в скобках по-прежнему только предупреждение. (4) Все тексты для покупателей — на «вы» (бот, шаблоны, подписки, рассылочный /stop); интерфейс владельца остаётся на «ты». (5) Миграция `0023` и `app/services/housekeeping.py`: напоминания клиенту о записи за сутки и за 2 часа (галочка в блоке «Запись», по умолчанию включено; захват условным UPDATE — не придёт дважды) и уборка: `button_clicks` 180 дней, записи 365 дней, просроченные `chat_states`, старые слепки ключей. (6) `CORS_ORIGINS` по умолчанию пуст = только `PUBLIC_BASE_URL`; `*` — для разработки. (7) nginx: отдельный `location /api/media/` с зоной `bf_media` (100 r/s, burst 300) в `nginx/default.conf` и `deploy/nginx-vhost.example.conf`, чтобы рассылка картинок не упиралась в общий лимит `/api/`; после выкладки `nginx -t` и reload (локально проверить синтаксис нечем: нет docker/nginx).
- **Календарь записи и мини-CRM (7 октября 2026).** Миграция `0022` (только добавление): `bookings` (запись/придержка/закрытое время; частичный уникальный индекс `uq_booking_active_slot` по (бот, время) для статусов held/confirmed/blocked — двоих на один слот не записать даже при одновременных нажатиях), `chat_states` (бот ждёт ответ текстом) и колонки `bot_subscribers.contact_name/phone/note`. Новые блоки: «Запись» (`BlockType.booking`: рабочие дни, часы, длина слота 15–480 мин, горизонт 1–60 дней, «не позже чем за N ч», часовой пояс, по умолчанию Asia/Almaty; календарь один на бота) и «Контакты» (`contact`: `ask_phone`, `ask_name` — Telegram-имя и @username приходят сами, спрашивается только то, что включено и чего ещё нет; телефон — кнопка «Отправить мой номер» или текстом). Логика: `app/services/booking.py` (слоты, бронь, отмена), `app/services/booking_flow.py` (диалог: дни → время → придержка на 60 минут, если дальше оплата, или сразу подтверждение; подтверждение после оплаты через `payment.meta.booking_id` в `payment_service.apply_result`; если время успели занять — владельцу уходит предупреждение; контакты по `chat_states`). Выбранное время попадает в «Выбрал: …» заказа. Владелец получает «📅 Новая запись». API (`app/routers/crm.py`): `/api/crm/customers` (список, поиск, карточка, правка имени/телефона/заметки), `/api/bots/{id}/calendar`, `/calendar/block`, `/bookings/{id}/cancel` (клиенту уходит сообщение). Интерфейс: кнопка «👥 Клиенты» в списке ботов (`CrmPanel`: вкладки «Клиенты» и «Календарь» — закрыть время, отменить запись), редакторы блоков `BookingEditor`/`ContactEditor`, шаблоны «Запись по предоплате» (контакты → календарь → предоплата → подтверждение) и «Запись без оплаты». Ограничения MVP: напоминаний клиентам за N часов нет, перенос записи делается отменой и новой записью, один специалист на бот (одно время — одна запись).
- **Продажи, нажатия кнопок и запись по датам (7 октября 2026).** Миграция `0021` (только добавление): таблица `button_clicks` (бот, блок, подпись кнопки, id человека в Telegram, `collect_choice`). Диспетчер пишет каждое нажатие (инлайн и быстрые кнопки, `_record_click`). Блок «Кнопки» с галочкой «Запомнить выбор покупателя» (`content.collect_choice`): последние нажатия покупателя за 3 часа (по одному на блок) попадают в `payment.meta["choices"]`, видны в списке заказов (`choices`) и в уведомлении владельцу («Выбрал: Чт · 14:00»). `GET /api/bots/{id}/button-stats?days=` — нажатия и число людей по кнопкам. В списке ботов кнопка «💰 Продажи» открывает `SalesOverviewPanel`: фильтр по боту (или все), вкладки «Продажи» и «Нажатия кнопок» с периодом; из шапки конструктора кнопка продаж убрана (остаётся в окне «Приём оплаты»). Кнопка «Оформление» теперь того же вида, что «Касса». Шаблон «Салон / барбер» переименован в «Запись по предоплате» и получил выбор дня и времени кнопками; доступность слотов бот не проверяет (занятое время не скрывается). Подсказка кассы «Оплата по ссылке» разбита на абзацы, строка про вставку ссылки в блок оплаты выделена. Про Prodamus исправлено: подписки он поддерживает (ID подписки в блоке), раньше в доках стояло «подписок нет».
- **Быстрые кнопки: автоматическое снятие и новые шаблоны (7 октября 2026).** Режим «убрать быстрые кнопки» убран из редактора (выглядел пугающе). Вместо него: если в блоке переключить «Быстрые внизу» → «Под сообщением», в контенте ставится `clear_reply`, редактор показывает предупреждение «вы меняете вид кнопок», а бот при следующем показе блока шлёт служебное сообщение с `ReplyKeyboardRemove` и сразу его удаляет (`_send_block`). У тех, кто уже получил блок раньше, клавиатура уйдёт только при повторном показе. Шаблоны: добавлены «Салон / барбер: запись с предоплатой», «Магазин: каталог и покупка», «Частые вопросы и поддержка», «Бесплатный подарок и продажа», «Мини-курс по дням», «Мероприятие: билеты», «Поддержать автора», «Опрос клиентов» (итого 14 с «С нуля»). В `templates.ts` у шаблона можно задать разводку: `nexts` (стрелки «дальше») и `links` (куда ведёт каждая кнопка). `tests/fixtures/templates.json` выгружен заново (теперь с `nexts`/`links`), `test_templates_e2e` проходит каждый шаблон, включая нажатие каждой быстрой кнопки.
- **Ревью двумя агентами (7 октября 2026).** Исправлено: SSRF в `_document_input` (скачиваем только со своего `PUBLIC_BASE_URL/api/media/`); reply-кнопка не ведёт к «Выдаче» в обход оплаты (`_reaches_delivery_before_payment`, вести нужно на блок оплаты); страница тестовой оплаты работает только если у бота выбрана касса `test`; IP жалоб берётся из `X-Real-IP` (не из `CF-Connecting-IP`); `test` убран из `OFFERED_PAYMENT_PROVIDERS` по умолчанию; заглушки `[цена]`/`[название продукта]` подставляются и в тексте блока оплаты, а в чек кассы не попадают; предупреждение о несохранённом больше не висит вечно; кнопка входа после ошибки возвращается; нечитаемая кнопка «Открыть бота» исправлена. Открыто (решать после запуска): оплаты, начатые до смены кассы, проверяются новыми ключами (нужен слепок кассы в `payment.meta`); подсказки шаблонов без скобок доходят до покупателя; `ReplyKeyboardRemove`; проверка пустых изображений и валюты кассы при публикации; предпросмотр не останавливается на оплате; дрейф `alembic check`; мёртвый CSS.
- **Stripe возвращён в каталог (6 октября 2026).** У владельца есть аккаунт Stripe, проверка — тестовым режимом (`sk_test_…`, вебхук `whsec_…`). Сверка кода только по выжимке документации, не по первоисточнику. Не работает для плательщиков из РФ и Беларуси.
- **Stripe сверен с официальной OpenAPI-схемой (6 октября 2026, версия 2026-09-30.endive; с github.com/stripe/openapi, файл 8 МБ не коммитим).** `api.stripe.com` с хоста достижим (без ключа отвечает 401), `docs.stripe.com` закрыт прокси. Совпали: `POST /v1/checkout/sessions` и все наши поля (`mode`, `success_url`, `cancel_url`, `client_reference_id`, `metadata`, `payment_intent_data[metadata]`, `line_items[].price_data` с `currency`/`unit_amount`/`product_data[name]`/`recurring[interval|interval_count]`, `subscription_data[metadata]`), значения `mode` (`payment|subscription|setup`), поля ответа сессии (`url`, `payment_status` ∈ `paid|unpaid|no_payment_required`, `amount_total`, `currency`, `payment_intent`), все наши события вебхука существуют. Без ключа создание сессии не проверить (запрос отклоняется на авторизации): остаётся тестовый платёж с `sk_test_…`. Подпись `Stripe-Signature` в схеме не описана, остаётся по выжимке.
- **CloudPayments: первый тестовый платёж пройден (6 октября 2026, владелец).** Тестовый сайт, Pay-уведомление на `https://bot.dimkaprojects.xyz/webhook/pay/cloudpayments`, платёж 1 ₽: бот выдал PDF один раз, владельцу пришло «Оплачен заказ №1000», CloudPayments прислал квитанцию. Подтверждено владельцем: выдача пришла сама, сразу после оплаты (то есть по Pay-уведомлению, кнопка «Я оплатил» не нажималась); повторное нажатие «Я оплатил» → «Эта покупка уже оплачена ✅», второй выдачи нет. Отказ подтверждён владельцем (в тестовом окружении CloudPayments выбран исход «отказ»): товар не выдан, на «Я оплатил» бот отвечает «оплата ещё не дошла». Разовые платежи CloudPayments в тестовом режиме пройдены; не проверены отмена на странице оплаты, другая валюта и автопродления.
- **Акция первых клиентов на лендинге (7 октября 2026).** Плашка с таймером в разделе «Сколько стоит»: `LAUNCH_OFFER_ENDS_AT` (ISO 8601 с поясом) и `LAUNCH_OFFER_REGULAR_PRICE` (цена «потом», текстом). Таймер считает до **одного и того же момента для всех**, а не «7 дней с твоего захода», перезагрузка его не сбрасывает; по истечении срока плашка пропадает сама (`/api/config` отдаёт пустые поля, `app/routers/auth.py::_launch_offer`, `frontend/src/components/LaunchOffer.tsx`). Намеренно **не** сделано: «вечный» таймер, который сбрасывается каждому посетителю, и зачёркнутая «старая цена», которой не было (это вводит в заблуждение и нарушает правила рекламы во многих юрисдикциях). Цену «потом» нужно действительно поднять к сроку в `PLATFORM_PAYMENT_METHODS`.
- **Модерация: жалобы, журнал, снятие бота (7 октября 2026).** Принцип «уведомление и действие»: платформа не читает боты и переписку покупателей заранее, реагирует на жалобу, требование органов или платёжной системы. **Жалобы:** страница `/report` (без входа, не зависит от юр. реквизитов; ловушка-поле, 5 жалоб в час с адреса, nginx-location в `nginx/default.conf`), команда `/report` в каждом клиентском боте (ссылка на форму с подставленным именем), ссылка в подвале сайта. **Хранение:** миграция `0020` (expand: таблицы `abuse_reports`, `moderation_actions`, колонка `bots.moderation_blocked_at`); журнал не стирается вместе с ботом/аккаунтом. **Панель оператора** — в мета-боте, только для Telegram id из `ADMIN_TELEGRAM_IDS`: `/reports` (карточка жалобы с кнопками «Снять бота» / «Заблокировать владельца» / «Отклонить», с подтверждением), `/journal`, `/block @бот причина`, `/restore @бот`, `/ban id причина`, `/unban id`; о новой жалобе мета-бот пишет операторам (или в `SUPPORT_CHAT_ID`, если id не заданы). **Снятие бота** (`app.services.moderation.block_bot`): пауза + отметка оператора + отмена отложенных сообщений; владелец вернуть бота не может (`owner_panel.set_paused`), продление периода тоже не возвращает; ничего не удаляется. `python -m app.admin ban/unban` теперь тоже пишет в журнал (`actor=cli`). **Тексты:** раздел 4 оферты и «Правила допустимого использования» (RU и EN) дополнены порядком рассмотрения жалоб, правом проверить настройки бота и отсутствием предварительной проверки; это шаблон, юристу показать. Не сделано: жалоба «в одно касание» из самого бота (сейчас — ссылка), уведомление владельца о снятии бота, апелляция через форму.
- **Быстрые команды оператора (7 октября 2026).** К панели модерации в мета-боте добавлены: `/admin` (меню с кнопками), `/stats` (сводка: владельцы, боты, паузы, снятые, заказы, жалобы), `/find id|@бот` (карточка с кнопками: снять/вернуть бота, заблокировать/разблокировать владельца, выгрузка, удаление), `/export id` (файл JSON без токенов и ключей, в журнал), `/delete id` (необратимо, только после кнопки «Да»; в журнал). Меню команд Telegram выставляется **только операторам** (`set_admin_commands`, область «чат оператора»), остальные его не видят; оно появляется после первого сообщения оператора боту и при следующем запуске `bot`. Все действия пишутся в журнал (`export_client`, `delete_account` добавлены к `block_bot`, `restore_bot`, `ban_client`, `unban_client`, `dismiss_report`).
- **ЮKassa протестирована владельцем (7 октября 2026).** Подтверждено владельцем в тестовом магазине: успех, приход вебхука, повторное нажатие «Я оплатил» без второй выдачи, отказ, а также путь без вебхука (товар выдаётся после кнопки «Я оплатил» — опрос статуса через API). Не проверены: чек 54-ФЗ, возврат, автосписания.
- **Исправлено: Stars не попадали в каталог (7 октября 2026).** В `OFFERED_PAYMENT_PROVIDERS` по умолчанию стояло `telegram_stars`, а slug провайдера — `stars`; из-за опечатки звёзды не предлагались клиентам. Исправлено в `app/config.py`, `.env.example`; добавлен тест `test_every_default_offered_slug_is_a_real_provider`, который проверяет, что каждый slug из списка по умолчанию существует. Если `OFFERED_PAYMENT_PROVIDERS` уже задан в `.env` на сервере со старым `telegram_stars`, замени его на `stars`.
- **Stripe, Stars, Crypto Bot, «по ссылке» проверены владельцем (7 октября 2026).** Владелец сообщил, что все четыре работают; подробности сценариев (успех/отказ/повтор) по Stripe, Stars и «по ссылке» не зафиксированы. **Crypto Bot:** первый платёж дал `401 UNAUTHORIZED`, потому что в настройках кассы не стояла галочка «Тестовый режим»: токен из `@CryptoTestnetBot` работает только на `testnet-pay.crypt.bot`, токен из `@CryptoBot` — только на боевой сети. После включения галочки платёж прошёл. Чтобы это не повторялось, при 401 адаптер теперь пишет подсказку про «Тестовый режим» и текущее положение галочки.
- **Поправка (7 октября 2026):** «Оплата по ссылке» владельцем ещё **не проверялась** (в предыдущей записи она была ошибочно включена в проверенные). Проверены: Stripe, Stars, Crypto Bot — со слов владельца. lava.top проверяется сейчас.
- **lava.top: в поле «offerId» можно вставить ссылку на страницу товара (7 октября 2026).** Владельцу трудно найти offerId в кабинете, а id товара и адрес `app.lava.top/products/<id>/content` видны сразу. `resolve_offer_id` (`app/services/payments/lavatop.py`) принимает offerId, id товара или ссылку со страницы товара и находит оффер по каталогу (`GET /api/v2/products`): если у товара один оффер с нужной валютой и периодом — берёт его, если несколько — просит указать offerId, если нет подходящего — пишет, какие цены есть. Каталог недоступен — вставленное идёт дальше как есть. Каталог теперь читается один раз на платёж (раньше — только для сверки цены).
- **lava.top: каталог читался не полностью (7 октября 2026).** По схеме `GET /api/v2/products` отдаёт по умолчанию только видимые товары (`feedVisibility=ONLY_VISIBLE`), а товар, который продаётся только по ссылке/API, обычно скрыт; лента к тому же постраничная (`nextPage`). Из-за этого оффер скрытого товара не находился, и в счёт уходил «как есть» с ответом lava.top `Product with offer id = … not found`. Теперь запрос идёт с `feedVisibility=ALL` и идёт по `nextPage` (до 10 страниц); при ошибке «not found» от lava.top в сообщении появляется подсказка (тот ли аккаунт и ключ, есть ли у товара оффер с ценой).
- **lava.top: настоящий ответ каталога отличается от схемы, и это ломало поиск оффера (7 октября 2026).** По снимку живого ответа владельца `GET /api/v2/products?feedVisibility=ALL` товар лежит **прямо в элементе списка** (`items[].id/title/offers/isDynamicPrice`), а не под `data`, как в OpenAPI-схеме; наш разбор читал только `data` и всегда получал пустой каталог. Теперь `data or item` (читаются оба вида). **Динамическая цена:** у товара с `isDynamicPrice=true` оффер может стоить 0, а сумма задаётся в самом счёте (`amount` в `POST /api/v3/invoice`); адаптер в этом случае отправляет цену блока в `amount` и не сверяет её с ценой оффера (у обычного товара цена берётся из оффера и обязана совпасть с блоком). Тест `test_lava_reads_the_real_catalogue_shape_and_sends_the_amount_for_dynamic_prices`. **Ключ API владельца попал в чат — его нужно отозвать и выпустить новый.**
- **lava.top: подсказки к двум частым отказам (7 октября 2026).** При тесте владельца: `The amount is too small to create an invoice` (цена в блоке ниже минимума lava.top; по проверке владельца для рублей минимум 50 ₽) и `Incorrect email to purchase` («Почта для чеков» в настройках кассы не принята). Теперь адаптер до запроса проверяет вид адреса почты и дописывает подсказку к обоим ответам lava.top. Причину `Incorrect email` по тексту ответа точно определить нельзя: проверяется формат и, при необходимости, другой адрес.
- **Ревью-исправление, раунд 3 (7 октября 2026).** Деньги: у адаптеров ЮKassa, Т-Банк, PayMaster, Freedom Pay, Crypto Bot, Prodamus, Robokassa (статус по API) и Stripe отсутствие суммы в ответе больше не считается «сошлось» (оплата не засчитывается); lava.top читает счёт, id которого сохранён при создании, а не `contractId` из неподписанного тела (чужой оплаченный счёт той же цены мог «оплатить» наш заказ), id проверяется регэкспом; Payme и секрет вебхука Telegram сравниваются в постоянное время и не падают на не-ASCII. Запись: просроченная придержка не цепляется к чужой покупке, слоты пропускают несуществующее время при переходе на летнее, подтверждение и отмена считают время по блоку записи, список без рабочих дней = запись закрыта (раньше открывались будни), `days` не списком не роняет диалог; контакты: номер только цифрами/скобками/плюсом и только свой (чужая карточка контакта отклоняется), имя одной строкой. Быстрые кнопки не ведут к тексту/файлу из «оплаченной зоны» (блоки после оплаты до ближайших кнопок), а не только к «Выдаче». Опрос: вопрос ≤300, вариант ≤100, ≤10 вариантов; кнопка-ссылка с плохим адресом пропускается, а не роняет блок. Модерация: `find_bot_by_username` точный (`_` в LIKE был подстановкой — `/block @my_bot` мог снять `myxbot`); поиск клиентов без подстановок. Схема: `alembic check` чистый (индексы в моделях, Enum↔VARCHAR в `migrations/env.py`). Фронтенд: Escape закрывает одно верхнее окно (стопка в `useEscape`), `useDialogA11y` (role=dialog, фокус, Tab), touch-цели ≥44px на телефоне/планшете, склонения и «ты», предпросмотр останавливается на оплате/записи, не считает ветвление петлёй и подставляет `[цена]`, итоги «Продаж по всем ботам» берутся с сервера (раньше суммировались по последним 100 заказам), полусобранный бот по шаблону удаляется при сбое, прозрачный PNG в фото бота ложится на белое, ошибки Bot API по-русски без токена, вложенные кнопки в карточке бота разведены, удалён мёртвый `BlockPreviewFlyout` и неиспользуемые стили. Не сделано и вынесено владельцу: слепок кассы в `payment.meta` для открытых счетов при смене ключей внутри одной кассы; лимит активных записей на человека (запись без оплаты можно «забить» всем расписанием); срок хранения `button_clicks`; единый тон «ты/вы» в текстах для покупателей (запись/контакты — «вы», остальное — «ты»).
- **Обратная связь и идеи клиентов (8 октября 2026).** Миграция `0024`, таблица `suggestions` (`app/models/suggestion.py`, `app/services/suggestions.py`, `app/routers/suggestions.py`, `meta_bot/handlers/ideas.py`). Клиент отправляет идею/ошибку/вопрос из сайта (кнопка «💡 Идея» в списке ботов) или в мета-боте (`/idea`, кнопка «💡 Предложить идею»). Оператору (`ADMIN_TELEGRAM_IDS`) сразу приходит карточка с кнопками «✅ Беру / ✔ Сделано / 🗑 Игнор»; `/ideas` — список открытых. Автору сообщение уходит только при «беру» и «сделано»; «игнор» молчаливый, автор видит «на рассмотрении». Лимиты: 10–2000 символов, 5 в сутки на клиента, дубль за 30 дней отклоняется. Порядок роутеров мета-бота: ideas после menu и до support.
- **Prodamus: тестовая среда и параметр sys (9 октября 2026).** Prodamus выдал тестовую платёжную страницу (`test-integration-1.payform.ru`; логин/пароль кабинета — в письме владельцу, в репозиторий не кладём) и просит передавать `sys=BotFactory`: параметр добавлен в платёжную ссылку и входит в подпись. По подпискам подтвердили: в ссылку передаётся id подписки в параметре `subscription`, уведомления приходят по первой оплате, по каждому платежу и по отмене подписки. После живого теста нужно написать менеджеру Prodamus (Екатерина Савиных) для публикации на витрине партнёров; партнёрская программа — по желанию.
- **PayMaster: тестовый кабинет выдан, касса возвращена в каталог (9 октября 2026).** Поддержка PayMaster открыла тестовый ЛК (`paymaster.ru/cpl`, пароль задаётся по ссылке из письма), тестовая карта `4100 0000 0000 0001`; подтвердили, что уведомление без подписи нужно перепроверять `GET /payments/{id}` (так и сделано), партнёрской программы нет. `paymaster` снова в `OFFERED_PAYMENT_PROVIDERS` по умолчанию; на сервере добавить slug в `.env` и пересоздать `api`. Токен и merchantId владелец берёт в кабинете сам.
- **Страница продавца для банка (9 октября 2026).** Причина: CloudPayments KZ сообщил, что в Казахстане банки не принимают оплату «внутри Telegram» — нужен сайт у каждого продавца с описанием, ценами и документами и кнопкой в бота; одной ссылки на бота банк не примет (подтверждено в переписке, проверить требования в договоре). Реализация: миграция `0025`, таблица `bot_sites`, `app/routers/site.py`. Владелец в конструкторе (кнопка «🌐 Страница» в шапке бота, `SitePanel.tsx`) задаёт адрес, название, описание, реквизиты (название, ИИН/БИН/ИНН, почта или телефон — обязательны для включения), при желании свой текст условий возврата. Публично: `/s/{адрес}` (описание, товары и цены из блоков оплаты, кнопка «Открыть в Telegram», реквизиты) и `/s/{адрес}/offer|refunds|privacy` (типовые шаблоны, внизу напоминание про юриста). Страница видна только при включении, активном боте и без блокировки модерацией; весь текст владельца экранируется. nginx: `location /s/` в `nginx/default.conf` (в хостовом vhost `location /` уже ведёт в контейнер). **Открыто:** не знаем, примет ли банк адрес на нашем домене или нужен отдельный домен продавца — ждём ответ CloudPayments; шаблоны документов не проверены юристом; нет своего домена на продавца, нет оформления/картинок на странице.
- **Редизайн лендинга и приложения (10 октября 2026).** Только фронтенд, маршруты, тексты юридического характера и аналитика не менялись. Токены (`frontend/src/index.css`): холодные нейтрали и один акцент-изумруд вместо индиго/лаванды (внутри Mini App по-прежнему побеждают `--tg-theme-*`), шрифт Onest (родная кириллица) и JetBrains Mono для цифр (`@fontsource-variable/*`, без внешних запросов), единая шкала скруглений 12/16/22/999, тени без цветного свечения. Иконки: `@phosphor-icons/react` вместо эмодзи в интерфейсе (`src/icons.tsx`: `BlockIcon`, `TemplateIcon`, `BrandMark`); эмодзи остались только в текстах сообщений бота (шаблоны, превью чата). Лендинг (`LoginScreen.tsx`, стили `src/landing.css`, префикс `lp-`, компоненты в `components/landing/`): короткий hero с живым превью диалога, строка из трёх фактов, «для кого» строками, шаги + живое демо рядом, витрина возможностей (5 ячеек разной формы), кассы, лента шаблонов, цена (бесплатное против запуска, калькулятор окупаемости), доверие, FAQ, финальный призыв; одна подпись для входа везде: «Начать бесплатно»; в тексте лендинга нет длинных тире. Вход через виджет Telegram, согласие у кнопки, залипающая кнопка на телефоне сохранены. Удалено ~220 неиспользуемых правил старого лендинга из `App.css`. Проверено: `tsc`, `npm run build`, скриншоты светлой и тёмной тем на 1440 и 390 px, нет горизонтального переполнения. Не делалось: замена длинных тире во всём интерфейсе приложения, картинки/фото (генератора изображений нет, визуал строится из живых компонентов), Lighthouse.
- **Правки по аудиту агентов (10 октября 2026).** Четыре независимых агента (аудит кода, аудит сайта, «клиент» с полным проходом, жёсткий критик дизайна) дали отчёты; исправлено: (1) невидимая запасная кнопка входа на лендинге (цвет ссылки перебивал цвет кнопки); (2) `PLATFORM_PAYMENT_METHODS` с опечаткой больше не делает публикацию бесплатной: публикация отвечает 503 (`platform_methods_misconfigured`), пустая переменная по-прежнему значит «платной публикации нет»; (3) при пустом `ADMIN_TELEGRAM_IDS` оператором считается личный `SUPPORT_CHAT_ID`, иначе кнопки «Беру/Сделано/Игнор» и жалоб не принимали нажатий; (4) страница `/s/{адрес}` скрывается после `ban` владельца; (5) выгрузка `export` не содержит слепок кассы и ссылки оплаты из `payments.meta`; (6) карточка идеи режет текст до экранирования; (7) страница продавца: текст про оплату зависит от кассы бота (Stars, Crypto Bot, карты), блок «Как заказать», цены с узким пробелом, уникальные заголовки, `<main>`, description; (8) лендинг: формулировки про цену (запуск и подписка), «до 20 ботов», видимая кнопка входа до загрузки виджета, фокус на блок входа, липкая кнопка не перекрывает конец страницы, Telegram-скрипт в `index.html` не блокирует отрисовку вне Mini App, og/canonical, демо не крутится при «уменьшить движение». Осталось открытым: двойная выдача товара при перезапуске worker (В5), потеря выдачи при снятом с эфира боте (В6), `SUBSCRIPTIONS_ENABLED` по умолчанию `True` в коде (на сервере проверить `.env`), мобильный конструктор вместо графа (список блоков), CSP на `/s/*`.
- **Правки по проходу «клиента» (10 октября 2026).** Окна на ноутбуке больше не уходят нижним краем за экран (`max-height` от верха окна, прокручивается тело); при Telegram Stars редактор блока оплаты предупреждает, что цена теперь в звёздах (раньше 4 990 ₸ молча становились 4 990 звёзд); если у мета-бота не задано имя, вместо вечной «Загрузки…» на лендинге объяснение и ссылка на поддержку; новый блок оплаты в Казахстане (по часовому поясу) начинается с тенге; сохранение кассы с незаполненными полями больше не показывает чистое зелёное «Сохранено»; ИИН/БИН/ИНН на странице для банка проверяется (10-12 цифр подряд); английские ответы сервера («Bot not found») показываются по-русски; статус идеи «получили, посмотрим». Не сделано: страна и рекомендация кассы при подключении, переписывание технических терминов кассы простыми словами, Kaspi в подсказках, показ PDF в предпросмотре, мобильный конструктор списком вместо графа, шаблон под маникюр в тенге.
- **Приём денег платформы: инструкция и проверка (10 октября 2026).** Код Stripe, Crypto Bot и Stars готов и проверен тестами, но настоящие аккаунты и ключи владельца не подключены, поэтому оплата запуска пока идти некуда. Добавлены пошаговая инструкция `docs/platform-payments-setup.md` и проверка без денег `python -m app.platform_check` (читает `PLATFORM_PAYMENT_METHODS`, спрашивает у Stripe «кто я», у Crypto Bot `getMe`, у Telegram `getMe` мета-бота, печатает адреса вебхуков; ключи не печатает). Открыто: Stripe для Казахстана требует компании в поддерживаемой стране; условия вывода звёзд (Fragment) проверить у Telegram до включения способа.
