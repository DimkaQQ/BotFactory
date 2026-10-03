# Платёжные провайдеры Bot Factory: подробная документация

Версия 2. Сборка: 3 октября 2026. Это пересказ официальной документации своими словами (не дословная копия), с таблицами полей, статусов и формулами подписи. По каждому разделу есть ссылки на первоисточник. Кода репозитория у меня нет, поэтому это справочник для сверки, а не отчёт о расхождениях.

## Обозначения

- **[офиц]** — прочитано на официальной странице провайдера.
- **[не первоисточник]** — SDK, модули CMS, статьи. Перепроверить.
- **НЕ СОБРАНО** — страницу не открыл, фактов нет.
- **⚠ Сверить** — места, где чаще всего ошибаются в адаптерах.

## Статус охвата

| # | Провайдер | Охват | Главное, что осталось |
|---|---|---|---|
| 1 | Stripe | хороший | возвраты и `charge.*`, Adaptive Pricing, `expired` |
| 2 | Crypto Bot | полный | — |
| 3 | Telegram Stars | хороший | точная текущая формулировка про `subscription_period` |
| 4 | ЮKassa | хороший | детали возвратов, тестовые карты |
| 5 | Т-Банк | хороший | полный список полей Init и Receipt |
| 6 | CloudPayments | хороший | поля каждого уведомления, разница двух HMAC-заголовков |
| 7 | PayMaster | полный | подпись уведомлений (в API v2 не описана) |
| 8 | Robokassa | хороший | XML-интерфейс статуса, API возвратов |
| 9 | LIFE PAY | полный | подписи у уведомлений нет в доке |
| 10 | Prodamus | средний | официальная сериализация для подписи, подписки |
| 11 | lava.top | полный (OpenAPI 1.22.0) | — |
| 12 | Freedom Pay | хороший | единицы `pg_recurring_lifetime`, «Мир» |
| 13 | ioka | хороший | возвраты, полный справочник ошибок |
| 14 | Processing.kz | слабый (только SDK) | официальная дока, прод-хост, единицы суммы |
| 15 | Click | хороший | требование к HTTP-коду ответа |
| 16 | Payme | хороший | GetStatement, `detail` для чека |
| 17 | LiqPay | хороший | формат `order_id` регулярных списаний |
| 18 | Оплата по ссылке | без внешнего API | только код |
| 19 | Тестовая касса | без внешнего API | только код |

## Сводная таблица по ключевым точкам

| Провайдер | Единицы суммы | Подпись уведомления | Что ответить |
|---|---|---|---|
| Stripe | минорные (центы); zero-decimal — целые | HMAC-SHA256 (`t.body`), `Stripe-Signature` | любой 2xx быстро |
| Crypto Bot | строка-дробь в единицах актива/фиата | HMAC-SHA256 тела, ключ = SHA256(token), hex | 2xx |
| Telegram Stars | целые Stars | нет (Bot API) | `answerPreCheckoutQuery` ≤ 10 с |
| ЮKassa | строка `"100.00"` (рубли) | нет; IP или перезапрос | HTTP 200 |
| Т-Банк | целое (уточнить единицы) | SHA-256 Token по полям + Password | `OK` |
| CloudPayments | число, 2 знака (рубли) | HMAC-SHA256 base64, API Secret | `{"code":0}` |
| PayMaster | decimal (рубли) | не описана; перезапрос `GET /payments/{id}` | 2xx (не описано явно) |
| Robokassa | строка (рубли) | MD5 и др., Пароль #2 | `OK{InvId}` |
| LIFE PAY | строка, 2 знака (рубли) | не описана | HTTP 200 |
| Prodamus | рубли | HMAC-SHA256 hex, заголовок `Sign` | 200 + `success` (не первоисточник) |
| lava.top | рубли/USD/EUR дробью | Basic или `X-Api-Key` | 2xx или 3xx |
| Freedom Pay | тенге | md5 `pg_sig` | XML `pg_status=ok` |
| ioka | **тиыны** (×100) | HMAC-SHA256, `X-Signature` | HTTP 200 за 10 с |
| Processing.kz | НЕ СОБРАНО | — | — |
| Click | сумы | MD5 `sign_string` | JSON с `error` |
| Payme | **тийины** (×100) | Basic-авторизация + IP | JSON-RPC result/error |
| LiqPay | гривны | base64(sha1(pk+data+pk)) | НЕ СОБРАНО |

---

## 1. Stripe

Источники **[офиц]**:
- https://docs.stripe.com/checkout/fulfillment
- https://docs.stripe.com/webhooks.md
- https://docs.stripe.com/billing/subscriptions/webhooks.md
- https://docs.stripe.com/currencies

### Процесс разовой оплаты

1. Сервер создаёт Checkout Session (`POST https://api.stripe.com/v1/checkout/sessions`, Basic-авторизация секретным ключом как логин). В примере доки передаются `line_items[0][price]`, `line_items[0][quantity]`, `mode=payment`, `ui_mode`, `return_url` с плейсхолдером `{CHECKOUT_SESSION_ID}`.
2. Клиент платит на странице Stripe.
3. Stripe шлёт вебхук. Выдача товара обязательно по вебхуку: клиент может не вернуться на сайт.
4. Дополнительно ту же функцию выдачи можно вызвать при заходе на страницу возврата (по session id из URL), чтобы выдать сразу.

### Функция fulfill (требования доки)

- Безопасна при повторном и параллельном вызове с одним session id.
- Получает Session через API с `expand: line_items`.
- Выдаёт, только если `payment_status != "unpaid"`.
- Записывает факт выдачи для этой сессии.
- При большом числе позиций — постраничная выгрузка line_items.

### События для Checkout

| Событие | Смысл |
|---|---|
| `checkout.session.completed` | клиент прошёл Checkout (для мгновенных способов деньги есть) |
| `checkout.session.async_payment_succeeded` | отложенный способ (например ACH) успешно оплачен позже |
| `checkout.session.async_payment_failed` | отложенная оплата не прошла |

Для отложенных способов объект висит в processing до успеха или провала. ⚠ Сверить: выдача по `completed` без проверки `payment_status`.

### События подписок

| Событие | Смысл |
|---|---|
| `customer.subscription.created` | подписка создана |
| `customer.subscription.updated` | подписка началась или изменилась |
| `customer.subscription.deleted` | подписка закончилась |
| `customer.subscription.trial_will_end` | за 3 дня до конца триала |
| `invoice.paid` | счёт оплачен (в том числе продление) |
| `invoice.payment_failed` | оплата счёта не прошла |

Отслеживать подписку дока велит по событиям `customer.subscription.*`. Пример из доки: создание подписки даёт `customer.subscription.created`, `invoice.created`, `invoice.paid`, `charge.created`, и порядок прихода не гарантирован.

### Подпись вебхука

- Заголовок `Stripe-Signature: t=<timestamp>,v1=<hex>[,v1=…][,v0=…]` (в реальности одной строкой).
- `signed_payload = <timestamp> + "." + <сырое тело>`. Подпись = HMAC-SHA256 с ключом `whsec_…` эндпоинта.
- Учитывать только `v1`. `v0` — фиктивная подпись тестовых событий.
- Сравнение за константное время. Допуск по времени в SDK — 5 минут; 0 отключает проверку, так делать нельзя.
- При каждом повторе генерируются новые timestamp и подпись.
- Нужно **сырое тело**: любая обработка фреймворком ломает проверку.
- Секрет свой у каждого эндпоинта и разный для test и live. При ротации до 24 часов приходит несколько `v1`.
- Stripe рекомендует и подпись, и allowlist IP (https://docs.stripe.com/ips).

### Доставка

- Нужен быстрый 2xx до тяжёлой логики. 3xx считается провалом. TLS 1.2 или 1.3.
- Повторы: до 3 суток с экспоненциальной паузой в live; в sandbox 3 раза за несколько часов.
- Ручной resend: Dashboard до 15 дней, CLI до 30 дней.
- Дубли возможны: хранить `event.id`. Бывает, что создаются два разных Event на одно изменение, тогда сравнивать `data.object.id` + `type`.
- Поле `created` в секундах, поэтому порядок по нему не определять.
- Структура события зависит от версии API аккаунта на момент события.
- До 16 эндпоинтов. Рекомендуют подписываться только на нужные события и обрабатывать их через очередь.

### Валюты и суммы

- Все суммы в **минорных единицах**: 1000 = 10 USD.
- Для zero-decimal валют (JPY и др.) сумма передаётся целиком: 10 = 10 JPY.
- Особые случаи: ISK и UGX передаются как двухзнаковые с `00` в дробной части; HUF и TWD нулевые только для выплат.
- Минимальная сумма зависит от валюты расчётного счёта (пример из доки: эквивалент £0.30 для GBP).
- KZT есть в списке валют. ⚠ Сверить по странице currencies, отмечен ли KZT как zero-decimal: в выдержке это не видно.

### Тест

Карта `4242 4242 4242 4242`, любой будущий срок, любой CVV, индекс `90210`. Локально: `stripe listen --forward-to localhost:4242/webhook`, `stripe trigger <event>`.

### НЕ СОБРАНО

Возвраты и события `charge.refunded`/`charge.*`, `checkout.session.expired`, Adaptive Pricing, параметры hosted-режима (`success_url`/`cancel_url`).

---

## 2. Crypto Bot (Crypto Pay API)

Источник **[офиц, прочитано целиком]**: https://help.send.tg/en/articles/10279948-crypto-pay-api. Версия API 1.5.2 (18.03.2026).

### Доступ

- Токен приложения: @CryptoBot (тестнет @CryptoTestnetBot) → Crypto Pay → Create App.
- Заголовок `Crypto-Pay-API-Token`. URL: `https://pay.crypt.bot/api/<метод>`. Тестнет: `testnet-pay.crypt.bot` (из SDK; на офиц. странице адрес не извлёкся).
- HTTPS, UTF-8, GET или POST. Параметры: query, JSON, urlencoded или multipart.
- Ответ: `{ok: true, result}` или `{ok: false, error}`.

### Методы

| Метод | Назначение |
|---|---|
| `getMe` | проверка токена |
| `createInvoice` | счёт |
| `deleteInvoice` | удалить счёт (`invoice_id`) |
| `getInvoices` | список; фильтры asset, fiat, invoice_ids, status (`active`/`paid`), offset, count 1–1000 (по умолчанию 100) |
| `createCheck`, `deleteCheck`, `getChecks` | чеки |
| `transfer`, `getTransfers` | переводы пользователю (по умолчанию выключено; идемпотентность через `spend_id` до 64 символов) |
| `getBalance`, `getExchangeRates`, `getCurrencies`, `getStats` | справочные |

### createInvoice

| Поле | Описание |
|---|---|
| `currency_type` | `crypto` (по умолчанию) или `fiat` |
| `asset` | при crypto: USDT, TON, BTC, ETH, LTC, BNB, TRX, USDC |
| `fiat` | при fiat: USD, EUR, RUB, BYN, UAH, GBP, CNY, KZT, UZS, GEL, TRY, AMD, THB, INR, BRL, IDR, AZN, AED, PLN, ILS |
| `accepted_assets` | для fiat: чем можно платить, через запятую |
| `amount` | **строка с дробью** (`"125.50"`), не минорные единицы |
| `swap_to` | авто-обмен после оплаты (не гарантирован) |
| `description` | до 1024 символов |
| `hidden_message` | до 2048 символов, показывается после оплаты |
| `paid_btn_name` / `paid_btn_url` | кнопка после оплаты: viewItem, openChannel, openBot, callback |
| `payload` | до 4 КБ, вернётся в вебхуке |
| `allow_comments`, `allow_anonymous` | по умолчанию true |
| `expires_in` | 1–2678400 секунд |

### Ссылки на оплату

- **`bot_invoice_url`** — основная.
- `mini_app_invoice_url` — для Mini App.
- `web_app_invoice_url` — веб-версия.
- **`pay_url` устарел** с версии 1.2. ⚠ Сверить.

### Invoice: статусы и поля

- `status`: `active`, `paid`, `expired`.
- После оплаты: `paid_at`, `paid_asset`, `paid_amount`, `paid_usd_rate`, `paid_fiat_rate` (для fiat), `fee_asset`, `fee_amount`, `paid_anonymously`, `comment`.
- Устарели: `fee`, `usd_rate`.

### Вебхук

- Включение: Crypto Pay → My Apps → приложение → Webhooks → Enable, указать HTTPS URL.
- POST JSON: `update_id` (**не уникален**), `update_type` = `invoice_paid`, `request_date`, `payload` (Invoice).
- **Подпись**: заголовок `crypto-pay-api-signature` = hex(HMAC-SHA256(key, raw_body)), где `key = SHA256(token)` в бинарном виде, `raw_body` — неразобранная JSON-строка.
- Дополнительно: проверять давность `request_date`; можно использовать секретный путь в URL.
- Повторы: до 17 попыток за 3 суток (от 10 секунд до 8 часов). После полной неудачи вебхуки приложения отключаются, и включать их надо вручную.
- ⚠ Сверить: пример в доке пересериализует тело через `JSON.stringify` — надёжнее считать по сырым байтам.

### Прочее

Allowlist IP в разделе Security приложения.

---

## 3. Telegram Stars (XTR)

Источники:
- https://core.telegram.org/bots/payments-stars **[офиц]**
- Зеркала Bot API (aiogram, gramio, telegram.js) и changelog aiogram для Bot API 8.0 **[не первоисточник, но повторяют Bot API]**

### Процесс

1. `sendInvoice` или `createInvoiceLink` с `currency: "XTR"`, `provider_token` пустой, ровно одна позиция в `prices`, сумма — целое число Stars.
2. Приходит update `pre_checkout_query` (`id`, `from`, `currency`, `total_amount`, `invoice_payload`).
3. Бот отвечает `answerPreCheckoutQuery(ok, error_message)` **за 10 секунд**, иначе транзакция отменяется. При отказе текст показывается пользователю.
4. Приходит сообщение `successful_payment`. **Выдавать только после него.**
5. Сохранить `telegram_payment_charge_id`: он нужен для возврата.

Счёт, отправленный в другой чат, можно оплатить многократно (multi-chat, inline). Решать, принимать ли повторную оплату, должен бот.

### Подписки (Bot API 8.0)

- `createInvoiceLink(subscription_period=…)` работает только с XTR.
- Цена подписки не больше **10000 Stars**. У бота может быть сколько угодно активных подписок, в том числе несколько от одного пользователя.
- В `SuccessfulPayment` есть поля `subscription_expiration_date`, `is_recurring`, `is_first_recurring`.
- Метод `editUserStarSubscription` — отмена или возобновление продления подписки пользователя.
- ⚠ Сверить: старые описания говорят, что `subscription_period` пока всегда **2592000** (30 дней). В свежих автогенерированных типах (gramio 10.2) эта фраза уже отсутствует. Проверить текущую страницу Bot API.
- Статья на Хабре (не первоисточник): `is_first_recurring` ведёт себя не так, как ожидается. Срок доступа лучше обновлять по `subscription_expiration_date` при каждом `successful_payment`.

### Возврат

`refundStarPayment(user_id, telegram_payment_charge_id)`.

### Тест

Тестовая среда Telegram: https://core.telegram.org/bots/features#testing-your-bot.

### Требования перед запуском

- Ответ на `/terms`.
- Поддержка клиентов и ответ на `/paysupport` для споров.
- Ответственность за диспуты и чарджбэки на владельце бота.
- Для цифровых товаров внутри Telegram — только XTR.

### Вебхук

Чтобы получать `pre_checkout_query`, его нужно включить в `allowed_updates` (Хабр, не первоисточник).

---

## 4. ЮKassa

Источники **[офиц]**:
- https://yookassa.ru/developers/using-api/webhooks
- https://yookassa.ru/developers/payment-acceptance/getting-started/payment-process
- `/scenario-extensions/recurring-payments/*`
- https://yookassa.ru/developers/54fz/payments

### Доступ

- Базовый адрес `https://api.yookassa.ru/v3`. Авторизация HTTP Basic `shop_id:secret_key` (для партнёров — OAuth Bearer).
- На каждый POST передаётся заголовок `Idempotence-Key` (любое уникальное значение).

### Создание платежа: POST /v3/payments

| Поле | Описание |
|---|---|
| `amount.value` | строка с двумя знаками, `"100.00"` |
| `amount.currency` | `RUB` и др. |
| `capture` | `true` — одностадийный (сразу `succeeded`), `false` — двухстадийный |
| `confirmation` | `{type: "redirect", return_url}` (также external, qr, embedded, mobile_application) |
| `description` | назначение |
| `metadata` | ключ-значение, возвращается без изменений |
| `receipt` | чек 54-ФЗ (см. ниже) |
| `save_payment_method` | `true` — сохранить способ для автоплатежей |
| `payment_method_id` | оплата сохранённым способом (автоплатёж) |

Ответ: платёж в статусе `pending` и `confirmation.confirmation_url`, куда перенаправить клиента. После оплаты клиент возвращается на `return_url`.

### Статусы

| Статус | Значение | Переходы |
|---|---|---|
| `pending` | ждёт действий клиента (или регистрации чека при сценарии «сначала чек»; или охлаждения кредита) | → succeeded / waiting_for_capture / canceled |
| `waiting_for_capture` | оплачен и заморожен | → succeeded / canceled |
| `succeeded` | успешно, финальный | — |
| `canceled` | отменён, финальный | — |

Отдельные статусы могут пропускаться, но порядок не меняется.

Причины отмены (часть): `expired_on_confirmation` (клиент не подтвердил в срок), `expired_on_capture` (не списали в срок).

### Двухстадийная оплата

- Холд держится от 2 часов до 7 дней в зависимости от способа; точный срок в `expires_at`.
- Списание: `POST /payments/{id}/capture`. Пустое тело — вся сумма; `amount` — часть, остаток вернётся клиенту.
- Частичное списание доступно для карт, кошелька ЮMoney, SberPay, Mir Pay, T-Pay, Alfa Pay, «Покупок в кредит» и «Плати частями».
- Отмена: `POST /payments/{id}/cancel`, только из `waiting_for_capture`. Комиссия при этом не удерживается.
- Из `succeeded` возможен только возврат.

### Чек 54-ФЗ

- Объект `receipt` передаётся в запросе на создание платежа: `customer` и `items` с `vat_code` и т.д.
- При частичном списании в capture нужно передать новый `receipt`.
- Если чек отправляется отдельным запросом (`POST /v3/receipts`), платёж создаётся без `receipt`, иначе будет ошибка.
- Если ответ по чеку не пришёл за 5 минут, ЮKassa отменяет платёж и возвращает деньги (по странице 54-ФЗ).
- Для платежа юрлица через СберБанк Бизнес Онлайн `receipt` не нужен.
- Обязательность чека зависит от настроек магазина. ⚠ Сверить в кабинете.

### Автоплатежи

1. Первый платёж с `save_payment_method: true`. Через виджет возможно и условное сохранение по ID пользователя.
2. После успеха сохранить `payment_method.id`.
3. Автоплатёж: `POST /payments` с `amount`, `capture`, `payment_method_id`, `description`. Подтверждение клиента не требуется.
4. `save_payment_method: false` — платёж без сохранения, даже если магазин настроен на автоплатежи.
5. Есть привязка на нулевую сумму, событие `payment_method.active`.
6. Частичное списание при рекурренте работает для всех способов, кроме кошелька ЮMoney.

Автоплатежи включаются по согласованию с ЮKassa.

### Уведомления

- События: `payment.waiting_for_capture`, `payment.succeeded`, `payment.canceled`, `refund.succeeded`, `payment_method.active` (а также выплаты и сделки).
- Настройка при Basic: личный кабинет → Интеграция → HTTP-уведомления. При OAuth — только API `POST /webhooks`.
- URL: HTTPS, порт 443 или 8443, TLS 1.2+, сертификат любой.
- Тело: `{type: "notification", event, object}`.
- Ответ: **HTTP 200**, тело игнорируется. Иначе повторы **24 часа**.
- **Подписи нет.** Проверка подлинности: перезапросить объект через API (`GET /payments/{id}`) или проверить IP:
  - 185.71.76.0/27
  - 185.71.77.0/27
  - 77.75.153.0/25
  - 77.75.156.11
  - 77.75.156.35
  - 77.75.154.128/25
  - 2a02:5180::/32

### Тест

Тестовый магазин с ключами `test_…`. Для чеков есть режим проверки, который имитирует ОФД (модуль MiniShop3, не первоисточник).

### НЕ СОБРАНО

Детали `POST /refunds`, тестовые карты.

---

## 5. Т-Банк (интернет-эквайринг, T-Касса)

Источники **[офиц, выдержки страниц developer.tbank.ru]**:
- `/eacq/api/init`
- `/eacq/intro/developer/token`
- `/eacq/intro/developer/notification`
- `/eacq/api/get-state`
- `/eacq/api/check-order`
- `/eacq/intro/errors/test-cases`
- `/eacq/intro/errors/test-sbp`

Сайт запрещает автоматическое чтение, поэтому всё ниже — по выдержкам поиска.

### Хосты

- Боевой: `https://securepay.tinkoff.ru/v2/<Метод>`.
- **Тест: терминал с приставкой `DEMO`, запросы идут на тот же боевой адрес** `https://securepay.tinkoff.ru/v2`.
- ⚠ Сверить: если в адаптере `rest-api-test.tinkoff.ru` — это устаревший вариант (так делают сторонние модули).

### Основные методы

`Init`, `FinishAuthorize`, `Confirm`, `Cancel`, `GetState`, `CheckOrder`, `Charge` (по сохранённым реквизитам), `GetQrState` (СБП), `getConfirmOperation` (справка по операции), методы чеков.

### Init: что известно

| Поле | Описание |
|---|---|
| `TerminalKey` | ID терминала из Т-Бизнес |
| `Amount` | Integer (int64). Пример в доке по токену: `"19200"`. ⚠ единицы (копейки) в выдержке прямо не подтверждены |
| `OrderId` | ID заказа, уникален для операции |
| `Description` | описание |
| `PayType` | `O` — одностадийная, `T` — двухстадийная; если не передан, берётся из настроек терминала |
| `Recurrent` | `Y` — сохранить карту; после оплаты в уведомлении AUTHORIZED придёт `RebillId` |
| `NotificationURL` | куда слать уведомления (иначе из ЛК) |
| `SuccessURL` / `FailURL` | возврат клиента (иначе из ЛК) |
| `DATA` | до 20 пар ключ:значение; ключ до 20 символов, значение до 100; спецсимволы через urlencode |
| `Receipt` | чек 54-ФЗ (также в Confirm и Cancel) |
| `Token` | подпись |

Ответ содержит `PaymentURL` для перенаправления клиента (по модулю MiniShop3) и `PaymentId`.

### Формула Token (для запросов)

1. Взять пары ключ-значение **только корневого уровня**. Вложенные объекты (`Receipt`, `DATA`) **не включаются**.
2. Добавить пару `{"Password": "<пароль терминала>"}`.
3. Отсортировать по ключу по алфавиту.
4. Склеить значения в одну строку (стандартный шаг; в выдержке виден отсортированный массив).
5. SHA-256 с UTF-8 → hex → в поле `Token`.

Для отдельных методов (например `getConfirmOperation`) токен строится только из `Password` и `TerminalKey`.

### Уведомления

- Настройка: ЛК → Терминалы → Настроить → способ получения: почта, HTTP(S) или оба.
- POST на `NotificationURL`. Сервис ждёт ответа **10 секунд**.
- При одностадийной оплате отправляются сразу **два уведомления: AUTHORIZED и CONFIRMED**.
- **Ответ: тело `OK`** (HTTP 200, без тегов, заглавными латинскими). Иначе уведомление считается неуспешным; тест-кейсы прямо на этом падают.
- Проверка Token уведомления: взять все поля кроме `Token`, добавить `Password`, отсортировать, склеить значения, SHA-256. В примере поля: `TerminalKey`, `OrderId`, `Success`, `Status`, `PaymentId`, `ErrorCode`, `Amount`, `CardId`, `Pan`, `ExpDate`, `RebillId`.
- **Булевы значения участвуют строкой `"true"`/`"false"`** (в примере `{"Success": "true"}`). ⚠ Сверить: Python `str(True)` даёт `"True"`, это сломает подпись.

### Статусы

| Статус | Смысл |
|---|---|
| `NEW` | создан |
| `AUTHORIZED` | авторизован; при двухстадийной ждёт Confirm |
| `CONFIRMED` | подтверждён, деньги списаны (оплачено) |
| `REJECTED` | отклонён |
| `AUTH_FAIL` | неуспешная попытка (T-Pay: после 3 попыток → REJECTED) |
| `REVERSED` | отмена холда |
| `REFUNDED` | возврат |

Полный перечень статусов в офиц. справочнике не прочитан. Т-Банк советует после оплаты дополнительно проверять статус через `GetState` и сверять `Amount`.

### Тест СБП

Метод создания тестовой платёжной сессии с `PaymentId`. Флаг `IsRejected=true` даёт отказ; итог проверяется через `GetState` (CONFIRMED / REJECTED / REFUNDED после Cancel).

### НЕ СОБРАНО

Точная структура `Receipt`, полный список полей ответа Init.

---

## 6. CloudPayments

Источник **[офиц]**: https://developers.cloudpayments.ru (прочитана первая половина страницы, уведомления — по выдержкам).

### Основы API

- Адрес `https://api.cloudpayments.ru`. HTTP Basic: логин **Public ID**, пароль **API Secret**. Без них ответ 401.
- POST; тело `key=value` или JSON. Ответ всегда с `Success` и `Message` (+ `Model`).
- `Success` отражает успех запроса, а не статус транзакции: статус в `Model.Status`.
- **Идемпотентность**: заголовок `X-Request-ID`, результат хранится 1 час.
- Лимит одновременных запросов: 5 для теста, 30 для боя, сверх — HTTP 429. Таймаут ответа 5 минут.
- Проверка доступа: `POST https://api.cloudpayments.ru/test`.

### Суммы и карты

- Сумма — число в валюте с точкой, до 2 знаков, минимум 0.01. Валюта по умолчанию RUB.
- Карты Visa, MasterCard, **МИР**. Есть Mir Pay, SberPay, T-Pay, СБП, «Долями», иностранные карты.

### Схемы оплаты

- Single (одностадийная) и Dual (двухстадийная). На подтверждение до 7 дней, иначе автоотмена; можно настроить автоподтверждение.
- Отмена возможна только при Dual. Возврат всегда привязан к оплате, полный или частичный.

### Методы

| Метод | Назначение |
|---|---|
| `payments/cards/charge`, `/auth` | оплата по криптограмме (Checkout-скрипт) |
| `payments/cards/post3ds` | завершение 3-D Secure (TransactionId + PaRes) |
| `payments/tokens/charge`, `/auth` | оплата по токену |
| подтверждение, отмена, возврат | Confirm / Void / Refund |
| `subscriptions/create` и др. | подписки |
| `orders/create`, `orders/cancel` | счёт по ссылке/почте (название полей ответа НЕ СОБРАНО) |
| `payments/find` (по InvoiceId) | проверка статуса (детали НЕ СОБРАНО) |

### Виджет (основной способ приёма)

- Ключевые параметры: `publicTerminalId`, `amount`, `currency`, `paymentSchema` (`Single`/`Dual`), `externalId` (ID заказа, приходит в уведомлениях), `metadata`, `receipt` (CloudKassir), `tokenize`, `recurrent`, `userInfo.accountId`, `successRedirectUrl`, `failRedirectUrl`.
- Контроль суммы — задача мерчанта: уведомление Check до оплаты и Pay после.

### Токены и рекуррент

- Токен приходит в Pay-уведомлении и в ответе API.
- В API токен возвращается при `SaveCard: true`, если в ЛК включено «Сохранение токена карты».
- Токен работает **только на терминале, где получен**.
- `tokens/charge`: обязательны `Amount`, `AccountId`, `Token`, `TrInitiatorCode` (0 — инициатор ТСП, 1 — клиент). При ТСП нужен `PaymentScheduled` (0/1).
- Подписки CloudPayments: интервал Day/Week/Month, период, maxPeriods, startDate, свой amount.
  - Интервал между платежами не больше года.
  - При неудаче повтор на следующий день; после 3 неудач подряд подписка отменяется.
  - Клиент может сам отменить подписку на my.cloudpayments.ru.

### Уведомления

- Типы: **Check, Pay, Fail, Confirm, Refund, Recurrent, Cancel** (и Receipt у CloudKassir).
- Все уведомления несут два заголовка: **`X-Content-HMAC`** и **`Content-HMAC`**.
  - Алгоритм HMAC-SHA256, ключ API Secret, результат в base64.
  - Сообщение = тело запроса для POST, строка параметров для GET.
  - Чем отличаются два заголовка, в выдержке не указано. ⚠ Сверить по разделу «Проверка уведомлений».
- Ответ: JSON `{"code": 0}`.
- Коды ответа на **Check**:

| Код | Смысл | Итог |
|---|---|---|
| 0 | платёж можно провести | авторизация |
| 10 | неверный номер заказа | отказ |
| 11 | некорректный AccountId | отказ |
| 12 | неверная сумма | отказ |
| 13 | платёж не может быть принят | отказ |
| 20 | платёж просрочен | отказ, плательщик получит уведомление |

- IP отправки уведомлений (список в выдержке обрезан): 185.98.81.0/28, 87.251.91.160/27, 46.46.175.96/27, 46.46.168.160/27, 162.55.174.97/32 и другие.
- Не первоисточник (модуль MiniShop3): после Pay со статусом `Authorized` заказ ещё не оплачен, нужен Confirm. Статус `Completed` — оплачено. Редирект 301 на эндпоинте ломает доставку.

### Статусы (из примеров ответов)

`Authorized` (StatusCode 2), `Completed`, `Declined` (StatusCode 5) и др. Полный справочник «Статусы операций» НЕ СОБРАН.

### Тест

Тестовые терминалы `test_api_…`. Тестовые карты в разделе «Тестирование» (номера НЕ СОБРАНЫ).

---

## 7. PayMaster (REST API v2)

Источник **[офиц, прочитано целиком]**: https://paymaster.ru/docs/ru/api/

### Доступ

- Базовый адрес `https://paymaster.ru`, HTTPS, GET/POST/PUT, JSON.
- Заголовок `Authorization: Bearer <token>`. Токен генерируется в ЛК мерчанта.
- POST-запросы могут нести **`Idempotency-Key`**. Повтор ключа даёт ошибку `idempotency_key_violation`.
- Ошибка: `{code, message, errors[]}`. Даты ISO 8601. Списки постраничные через `cursor`.

### Сценарий 1: ссылка на оплату — POST /api/v2/invoices

| Поле | Описание |
|---|---|
| **merchantId** | ID магазина |
| dualMode | двухстадийный (по умолчанию false) |
| testMode | тестовый платёж (по умолчанию false) |
| tokenization.type | `cof` / `recurring` (сохранить способ) |
| tokenization.purpose, tokenization.callbackUrl | описание подписки, уведомления по токену |
| **invoice.description** | назначение |
| invoice.orderNo, expires, params | номер заказа, срок, доп. параметры |
| **amount.value / amount.currency** | decimal (`10.50`), ISO 4217 |
| paymentMethod | способ (см. справочник) |
| protocol.returnUrl / protocol.callbackUrl | возврат клиента / URL уведомления |
| customer | email, phone (без «+»), ip, account |
| receipt | `client`, `items`, `settlements` |

Ответ: `{paymentId, url}`. Клиента перенаправляют на `url`.

### Сценарий 2: прямой платёж — POST /api/v2/payments

- Передаются данные карты (`paymentData.card`), ApplePay/GooglePay (`dsrp`), телефон/аккаунт или **токен** (`paymentData.token.id`).
- Ответ может потребовать подтверждения `confirmation`:
  - `External` — `paymentUrl`
  - `SmsOtp`
  - `ThreeDSMethod`
  - `ThreeDSChallenge` — `acsUrl`, `creq`
  - `ThreeDSv1` — `acsUrl`, `PAReq`
- Завершение подтверждения: `PUT /api/v2/payments/{id}/complete` (`code` / `cres` / `PARes` / `threeDSCompInd`).
- В деталях платежа есть **`paymentToken {id, expires, title}`** — сохранённый токен.

### Управление платежом

| Запрос | Назначение |
|---|---|
| `PUT /api/v2/payments/{id}/confirm` | списание холда (amount + опционально receipt); ответ — пустой 200 |
| `PUT /api/v2/payments/{id}/cancel` | отмена; ответ — пустой 200 |
| `GET /api/v2/payments/{id}` | детали платежа |
| `GET /api/v2/payments?merchantId&start&end` | список за период |

### Статусы платежа

| Статус | Смысл |
|---|---|
| `Pending` | выполняется |
| `Confirmation` | нужно доп. подтверждение |
| `Authorized` | авторизован (холд, при dualMode) |
| `Settled` | **проведён — оплачено** |
| `Cancelled` | отменён |
| `Rejected` | отклонён |

Коды отказа: TransactionDeclined, IssuerUnavailable, RejectedByFraud, InvalidAmount, InvalidAccount, BlockedAccount, OperationNotAllowed, InsufficientFunds, ExpiredAccount, PaymentLimitExceeded, PaymentCountExceeded, CardNotEnrolled, ThreeDSecureFailed, CancelledByUser, PaymentExpired.

### Возвраты

- `POST /api/v2/refunds` (paymentId, amount, receipt).
- Статусы: `Pending`, `Success`, `Rejected`.
- `GET /api/v2/refunds/{id}`, список по периоду.

### Токены (рекуррент)

| Запрос | Назначение |
|---|---|
| `POST /api/v2/tokenization` | ссылка на привязку (type `recurring`, purpose, paymentMethod, customer.account) → `{tokenId, url}` |
| `POST /api/v2/paymenttokens` | привязка напрямую (карта/СБП), может потребовать подтверждение |
| `PUT /paymenttokens/{id}/complete` | завершить подтверждение |
| `GET /paymenttokens/{id}` | данные токена |
| `PUT /paymenttokens/{id}/revoke` | отозвать |

- Статусы токена: `Active` / `Revoked` / `Declined` (в примере ответа ещё `Created`).
- Ошибки токена: `payment_token_revoked`, `payment_token_blocked`.

### Чеки

- `POST /api/v2/receipts`: paymentId, amount, `type` (`Payment` — приход, `Refund` — возврат прихода), `client` (email/phone/name/inn), `items` (name, quantity, price, measure, **vatType**, **paymentSubject**, **paymentMethod**, marking, agentType, supplier), `settlements`.
- Ставки НДС: None, Vat0, Vat5, Vat7, Vat10, **Vat22**, Vat105, Vat107, Vat110, **Vat122**. Ставок 20/120 в справочнике уже нет. ⚠ Сверить.
- Статус регистрации чека: Success / Rejected / Cancelled / Pending.

### Уведомления

- `POST {callbackUrl}` JSON с полями: `id`, `created`, `testMode`, `status`, `merchantId`, `invoice`, `amount`, `paymentData`.
- По токену отдельное уведомление: `id`, `status`, `title`, `expires`.
- **Подпись в API v2 не описана.** Надёжная проверка — перезапросить `GET /api/v2/payments/{id}` и сверить статус и сумму. В модулях BILLmanager (не первоисточник) в ЛК PayMaster упоминаются «тип подписи» и «секретный ключ» — вероятно, наследие старого протокола. ⚠ Сверить.
- Требование к ответу (код, тело) в API v2 не описано.

### Способы оплаты

`bankcard`, `sbp`, `sberpay`, `tpay`, `alfapay`, `yandexpay`, `wbpay`, `dolyame`, `davaydelit`. Карты «Мир» поддерживаются (по модулю BILLmanager, не первоисточник).

### Тест

Флаг `testMode`. Не первоисточник: тестовая карта `4100000000000010`.

---

## 8. Robokassa

Источники **[офиц]**:
- https://docs.robokassa.ru/ru/pay-interface
- `/ru/notifications-and-redirects`
- `/ru/testing-mode`
- `/ru/recurring-payments`
- `/ru/invoice-api`
- `/code-examples`
- `/script-parameters`

### Процесс

1. Магазин формирует форму или ссылку на `https://auth.robokassa.ru/Merchant/Index.aspx` с `MerchantLogin`, `OutSum`, `InvId` (в примерах встречается и `InvoiceID`), `Description`, `SignatureValue`, опционально `Receipt`, `Shp_*`, `IncCurrLabel`, `Culture`, `Email`, `IsTest`.
2. Клиент платит.
3. Robokassa шлёт фоновый запрос на **ResultURL**. Магазин проверяет подпись и отвечает `OK{InvId}`.
4. Клиент возвращается на SuccessURL или FailURL.

### Формулы подписи

Алгоритм хеширования выбирается в технических настройках (в примерах MD5).

| Где | Строка |
|---|---|
| Запрос оплаты | `MerchantLogin:OutSum:InvId:Пароль#1` |
| Без InvId | `MerchantLogin:OutSum::Пароль#1` |
| С Receipt и Shp | `MerchantLogin:OutSum:InvId:Receipt:Пароль#1:Shp_item=…` |
| Общий вид | `MerchantLogin:OutSum:InvId[:модификаторы]:Пароль#1[:Shp_*]` |
| С ResultUrl2 | `MerchantLogin:OutSum:InvId:Receipt:StepByStep:ResultUrl2:Пароль#1` |
| С Success/FailUrl2 | `MerchantLogin:OutSum:InvId:Receipt:StepByStep:ResultUrl2:SuccessUrl2:SuccessUrl2Method:FailUrl2:FailUrl2Method:Пароль#1` |
| **ResultURL (проверка)** | `OutSum:InvId:Пароль#2[:Shp_*]` |
| SuccessURL (проверка) | `OutSum:InvId:Пароль#1[:Shp_*]` |

Пояснения:
- `Shp_*` пишутся как `Shp_имя=значение`, через двоеточие, в конце. Пример: `100.000000:450009:Пароль#2:Shp_login=Vasya:Shp_oplata=1`.
- `OutSum` в ResultURL приходит с 6 знаками (`100.000000`). ⚠ Сверить: в подпись брать строку **как пришла**, не пересобирать число.
- Пример кода сравнивает подписи в верхнем регистре (`strtoupper`). ⚠ Сверить регистр.
- Модификаторы (Receipt, StepByStep, ResultUrl2 и т.д.) включаются в подпись, только если передаются. Это вывод из формул.

### Ответ на ResultURL

- Текст **`OK{InvId}`** (например `OK5`), без лишнего.
- Дока советует сверять подпись и параметры (`OutSum`, `InvId`, `Shp_*`) до смены статуса заказа.
- IP Robokassa (по странице KZ): 185.59.216.65, 185.59.217.65.
- Есть второй вид уведомления, ResultUrl2 (JSON с `shop`, `invId`, `state: "OK"`, …). Детали НЕ СОБРАНЫ.

### Тестовый режим

- **Отдельные тестовые Пароль #1 и #2** в технических настройках; алгоритм хеша как в бою.
- В запросе **`IsTest=1`**. Если параметр отсутствует, равен 0 или пустой, создаётся **боевой** платёж.
- В Invoice API при `IsTest=1` подпись считается тестовым паролем; Split с IsTest несовместим.

### Рекуррент

- Услуга только по согласованию. Есть готовый сервис «Подписки» в ЛК.
- Материнский платёж — обычная форма с `Recurring=true`.
- Дочерний: POST на **`https://auth.robokassa.ru/Merchant/Recurring`** с `MerchantLogin`, новым `InvoiceID`, **`PreviousInvoiceID`** (номер материнского), `OutSum`, `Description`, `SignatureValue`.
- Ответ `OK+InvoiceId` значит только «операция создана», не «оплачено». Результат проверять по ResultURL / ResultUrl2 или через XML-интерфейс.
- В Invoice API можно передать только один из `StepByStep` / `Recurring` / `Token`.

### Invoice API (выставление счетов)

`https://services.robokassa.ru/InvoiceServiceWebApi/api/CreateInvoice`, запрос в формате JWT, подписанный Паролем #1. Поля: InvId, OutSum, Culture, IsTest, Recurring и др.

### Прочее

Есть холдирование (`/ru/holding`), оплата по сохранённой карте (`/ru/saving`), API возвратов (`/ru/refund-api`), СБП-QR, сплит. Детали НЕ СОБРАНЫ.

Для произвольной суммы в форме используется `FreeOutSum` (Хабр Q&A, не первоисточник).

---

## 9. LIFE PAY

Источники **[офиц]**:
- https://apidoc.life-pay.ru/bill/index
- https://apidoc.life-pay.ru/notification/index
- https://apidoc.life-pay.ru/transactions/refund

### Выставить счёт: POST https://api.life-pay.ru/v1/bill

Тело — JSON.

| Поле | Обяз. | Описание |
|---|---|---|
| `apikey` | да | API-ключ компании из ЛК |
| `login` | да | логин администратора, обычно телефон `7xxxxxxxxxx` |
| `amount` | да | **строка**, до 2 знаков, точка (`100.00`, `140`, `25.50`) |
| `description` | да | назначение, попадает в чек; формат `товар x кол-во = сумма, …` разбивает чек на позиции |
| `customer_phone` | условно | обязателен для `mobileCommerce` |
| `customer_email` | нет | |
| `method` | нет | `sbp` (по умолчанию), `internetAcquiring`, `mobileCommerce` |
| `callback_url` | нет | URL уведомления о смене статуса; сопоставление по `number` |

Ответ: `{code: 0, message, data: {status, number, created, interval, paymentUrl, paymentUrlWeb}}`.
- `paymentUrl` — ссылка клиенту.
- `paymentUrlWeb` — только для `sbp`, с выбором банка.
- `interval` — рекомендуемый шаг опроса статуса в секундах.
- `number` — номер транзакции, по нему всё дальнейшее.

### Статусы счёта

| Код | Смысл |
|---|---|
| 0 | инициирована |
| **10** | **успешна** |
| 15 | ожидает подтверждения |
| 20 | неуспешна |
| 30 | отменена |

### Другие методы счёта

- Статус: `GET https://api.life-pay.ru/v1/bill/status?apikey&login&number`. Можно передать несколько номеров через запятую. Ответ — словарь `{number: {status, msg}}`.
- Отмена неоплаченного счёта: `POST https://api.life-pay.ru/v1/bill/cancellation` (apikey, login, number).

### Уведомления о транзакциях (версия 2.0)

- URL задаётся в ЛК (Настройки → Разработчикам) или через `callback_url` счёта.
- POST JSON после **каждой** транзакции, успешной и неуспешной.
- Поля:
  - `number`, `original_number` (для возврата — номер платежа)
  - `type` (`payment` / `refund`)
  - **`status` (`success` / `fail`)**
  - `method` (`card`, `cash`, `recurrent`, `internetAcquiring`, `mobileInternetAcquiring`)
  - `amount` (строка, 2 знака), `tip_amount`, `discount_amount`
  - `description`, `phone`, `email`, `pan` (маска), `cardholder`, `rrn`, `created` (ISO 8601)
  - `purchase[]`, `order{}`, `add_fields`, `original_add_fields`
- Ответ: **HTTP 200**. Иначе повторы через 1, 3, 5, 10 минут, затем раз в час; всего **не более 10 попыток**.
- **Подписи у уведомления в доке нет.** Проверять перезапросом `/v1/bill/status` по `number`. ⚠ Сверить.

### Возврат

- `POST https://api.life-pay.ru/v1/transactions/refund`: apikey, login, `number` (14-значный номер платежа), `uuid` (идемпотентность), `items` (для частичного возврата).
- Запросы с одинаковым `uuid` повторно не обрабатываются.

---

## 10. Prodamus

Источники:
- help.prodamus.ru: «Уведомления при оплате», «Инструкция для самостоятельной интеграции» **[офиц, выдержки]**
- Модуль MiniShop3, Ruby-гем `prodamus`, python-prodamus, Хабр **[не первоисточник]**

### Получение ссылки

- Запрос (GET или POST) на адрес вашей платёжной формы `https://<поддомен>.payform.ru/`.
- `do=link` — вернуть ссылку для клиента; `do=pay` — сразу отправить на оплату.
- Поля (не первоисточник): `order_id`, `customer_phone`, `customer_email`, корзина `products[]`, `urlSuccess`, `urlReturn`, `urlNotification`, `sys`, `_param_*`, `demo_mode=1`.
  - Для `urlNotification` из запроса нужен согласованный с поддержкой код `sys`.
- Подпись запроса передаётся параметром `signature`.
- Способы оплаты включают рассрочки: `installment_*`, Тинькофф, «ВсегдаДа».

### Уведомление (вебхук)

- POST **`multipart/form-data`** на URL из настроек формы.
- Подпись в заголовке **`Sign`** (hex, 64 символа = SHA-256).
- Поле `payment_status`: `success` (оплачен), `order_canceled` (отменён покупателем).
- После успешно доставленного уведомления повторов нет (офиц.).
- Тестовое уведомление можно отправить из настроек формы (кнопка повтора).

### Алгоритм подписи (не первоисточник)

1. Взять данные (поля формы как словарь).
2. Рекурсивно отсортировать по ключам.
3. Сериализовать в JSON.
4. HMAC-SHA256 с секретным ключом **этой страницы**, hex.

Дополнительно:
- При выключенном боевом режиме страницы используется другой ключ (суффикс `demo`).
- ⚠ Сверить сериализацию: эталонная реализация на PHP (`json_encode` по умолчанию экранирует `/` как `\/`), а Ruby `to_json` и Python `json.dumps` — по-разному (кириллица, пробелы). Подпись сойдётся, только если байты JSON совпадут с эталоном. Официальный PHP-класс Hmac я не прочитал.

### Прочее (не первоисточник)

- Ответ на вебхук: HTTP 200 и текст `success`.
- Двухстадийной оплаты и API статуса нет.
- Сумма меньше 1 копейки не отправляется.
- Факт оплаты подтверждает только вебхук с верной подписью `Sign`, а не переход на `urlSuccess`.

### НЕ СОБРАНО

Поля `tax`/`sno` в `products` для фискализации, подписки Prodamus, полный список `payment_status`.

---

## 11. lava.top

Источник **[офиц, OpenAPI 1.22.0, прочитан целиком]**: https://gate.lava.top/docs/documentation.yaml. Также https://developers.lava.top/ru.

### Доступ

- Базовый адрес `https://gate.lava.top`. Заголовок **`X-Api-Key`**.
- Ключ: ЛК автора → Интеграции → Public API → Создать API key.

### Процесс

1. `GET /api/v2/products` → продукты и офферы (`offers[].id`, цены по валютам и `periodicity`).
2. **`POST /api/v3/invoice`** (v1 и v2 устарели) → `{id, status, amountTotal, paymentUrl}`.
3. Перенаправить клиента на `paymentUrl` (для бесплатного продукта он пустой).
4. Ждать вебхук или опрашивать `GET /api/v2/invoices/{id}`.

### POST /api/v3/invoice

| Поле | Описание |
|---|---|
| `email` | почта покупателя (обязательна на практике) |
| `offerId` | UUID оффера (цены); чужой или несуществующий даёт 404 |
| `currency` | `RUB`, `USD`, `EUR` |
| `paymentProvider` | `SMART_GLOCAL`, `PAY2ME` (для RUB); `UNLIMIT`, `PAYPAL` (для USD/EUR). По умолчанию RUB → SMART_GLOCAL, USD/EUR → UNLIMIT |
| `paymentMethod` | `CARD`, `SBP`, `PAYPAL`, `PIX` (и в примерах APPLE_PAY, SEPATRANSFER, IDEAL, BIZUM, MBWAY, BANCONTACT) |
| `periodicity` | `ONE_TIME`, `MONTHLY`, `PERIOD_90_DAYS`, `PERIOD_180_DAYS`, `PERIOD_YEAR` |
| `buyerLanguage` | `EN` (по умолчанию), `RU`, `ES` |
| `amount` | только для продуктов с динамической ценой |
| `promoCode` | 3–36 символов, A-Z, 0-9, `-`, `_` |
| `fullName`, `walletId` | для BANCONTACT и BIZUM |
| `clientUtm` | utm_source, utm_medium, utm_campaign, utm_term, utm_content |
| `successful_return_url`, `failure_return_url`, `cancel_return_url` | возвраты клиента |

⚠ Сверить: `periodicity` должен соответствовать цене оффера (годовую цену нельзя слать как MONTHLY).

### Статусы

- Контракт в вебхуке (`ContractStatusDto`, **нижний регистр**): `new`, `in-progress`, `completed`, `failed`, `cancelled`, `subscription-active`, `subscription-expired`, `subscription-cancelled`, `subscription-failed`.
- Контракт в API `/invoices` (`InvoiceStatus`, **ВЕРХНИЙ регистр**): `NEW`, `IN_PROGRESS`, `COMPLETED`, `FAILED`.
- Подписка: `ACTIVE`, `CANCELLED`, `FAILED`.
- ⚠ Сверить регистр: в вебхуке `completed`, в API `COMPLETED`. Сторонний биллинг именно на этом «никогда не видел оплату».

### Вебхуки

- Настраиваются в ЛК: URL + способ аутентификации. Basic (`BasicWebhookAuth`) или **API key вашего сервиса**, который lava.top шлёт в заголовке `X-Api-Key` (`ApiKeyWebhookAuth`). Это **ваш** ключ, а не ключ lava.top.
- Типы `eventType`:

| Событие | Когда | Особенности |
|---|---|---|
| `payment.success` | разовая покупка или первый платёж подписки | status `completed` или `subscription-active` |
| `payment.failed` | неуспех | `errorMessage` |
| `subscription.recurring.payment.success` | продление | есть `parentContractId` |
| `subscription.recurring.payment.failed` | неудачное продление | |
| `subscription.cancelled` | отмена подписки | `cancelledAt`, `willExpireAt`; `contractId` — последний контракт, не первый |
| `refund.success` | возврат | **другая структура**: `event_id`, `event_type`, `created_at`, `data{refund_id, refund_type, initiator, amount, currency, product{product_id, tier_id…}, customer_email, balance_impact, subscription_cancelled}`, **без contractId** |
| `chargeback.initiated` | чарджбэк | тоже другая структура (`event_type`, `data{chargeback_id, dispute_date, reason_category, …}`) |

- Тело основных событий: `eventType`, `product{id,title}`, `contractId`, `parentContractId`, `buyer{email}`, `amount`, `currency`, `status`, `timestamp`, `clientUtm`, `errorMessage`.
- Ответ: **2xx или 3xx** — доставлено. 4xx или 5xx — ещё **19 повторов**: 1 с, 5 с, 15 с, затем 11 раз по минуте, затем 5 раз по часу.
- ⚠ Сверить: возвраты и чарджбэки нельзя отклонять за отсутствие `contractId`, иначе пойдут 19 повторов.

### Подписки

- `GET /api/v1/subscriptions`, `GET /api/v1/subscriptions/{id}` (с `recurrentPayments`, `expiredAt`, `cancelledAt`, `terminatedAt`).
- Отмена: **`DELETE /api/v1/subscriptions?contractId=<parentContractId>&email=…`** → 204; 404 = такой подписки нет.
- `contractId` — ID конкретного платежа; `parentContractId` — контракт оформления подписки.

### Прочее

- `GET /api/v1/invoices` и `/api/v2/invoices` — список контрактов с фильтрами (по умолчанию только успешные).
- Карты: при цене в рублях — МИР/Visa/MC российских банков; при EUR/USD — иностранные (по стороннему SDK).

---

## 12. Freedom Pay (бывший PayBox)

Источники **[офиц]**:
- https://freedompay.kz/docs/merchant-api/pay
- https://freedompay.kz/docs/gateway-api/pay
- https://docs.freedompay.kz (Result notify, Create payment, recurrent, card token)
- https://freedompay.kg/docs-en/merchant-api/pay

### Хосты

- Казахстан: `https://api.freedompay.kz`. Кыргызстан: `https://api.freedompay.kg`.
- Домен `.money` в доке не встретил. ⚠ Сверить.
- Есть два протокола:
  - старый Merchant API на `init_payment.php` (форма, `pg_*`, md5);
  - Gateway API (`/g2g/payment_page/`, Sync/Async API).

### Создание платежа: POST /init_payment.php

Два способа: прямая передача от мерчанта на `init_payment.php` или через браузер клиента на `payment.php`.

Поля (из примеров):
- `pg_order_id`, `pg_merchant_id`, `pg_amount`, `pg_description`, `pg_salt` (случайная строка)
- `pg_currency` (KZT…)
- `pg_check_url`, `pg_result_url`, `pg_success_url`, `pg_failure_url`, `pg_state_url` (+ `_method`), `pg_site_url`
- `pg_payment_system` (например `EPAYWEBKZT`), `pg_lifetime` (например 86400 секунд)
- `pg_user_phone`, `pg_user_contact_email`, `pg_user_id`
- `pg_recurring_start`, `pg_recurring_lifetime`
- `pg_sig`
- Любые свои параметры без префикса `pg_` пересылаются в check_url и result_url.

Ответ XML: `pg_status` (`ok` / `rejected`), `pg_redirect_url` (куда отправить клиента), `pg_sig`.

### Подпись pg_sig

```
pg_sig = md5( "<имя_скрипта>;<значение1>;<значение2>;…;<secret_key>" )
```

- Пример: `init_payment.php;25;test;{merchant_id};23;molbulak;{secret_key}`. Первым идёт **имя скрипта** (`init_payment.php`), последним — **секретный ключ**.
- В примере значения идут в алфавитном порядке ключей (amount, description, merchant_id, order_id, salt). Порядок — вывод из примера.
- Для ответов и запросов на ваши URL имя скрипта — последняя часть вашего URL. ⚠ Сверить по доке.
- Подписаны и ответы Freedom Pay. Сообщение не подписывается (нет `pg_salt`/`pg_sig`) только если Freedom Pay не смог опознать мерчанта.

### Result URL (уведомление о результате)

- Поля: `pg_order_id`, `pg_payment_id`, `pg_amount`, **`pg_result`** (1 — успех, 0 — неуспех), **`pg_can_reject`** (1 — платёж можно откатить, например карта; 0 — безотзывный), `pg_description`, `pg_payment_date`, `pg_user_*`, `pg_recurring_profile_id` (при создании профиля), `pg_salt`, `pg_sig`.
- Ответ мерчанта — подписанный XML с `pg_status`:
  - `ok` — платёж принят
  - `rejected` — отказ, **только если `pg_can_reject=1`**; иначе платёж считается проведённым
  - `error` — ошибка разбора
- Если первый вызов Result URL не удался, платёж **не отменяется**, а в повторных вызовах отказать уже нельзя.
- Ответы на повторы должны **совпадать** с первым, даже если `pg_lifetime` истёк.

### Рекуррент

- В `init_payment` передать `pg_recurring_start=1` и `pg_recurring_lifetime`. Если срок дольше действия карты, профиль живёт до истечения карты.
- `pg_recurring_profile_id` приходит в Result URL.
- Повторное списание: `POST https://api.freedompay.kz/make_recurring_payment`.
- ⚠ Единицы `pg_recurring_lifetime` (в примере `156`) в выдержке не указаны. Вероятно, месяцы, но не подтверждено.

### Статус платежа

- Запрос статуса возвращает `pg_status` (ok/error), `pg_payment_id`, `pg_transaction_status`, `pg_can_reject`, `pg_failure_code`, `pg_failure_description`.
- Значения статуса (со страницы выплат): `partial` (новый), `pending` (ожидание плательщика или системы), `failed`, `incomplete` (истёк срок). Значение для успеха в выдержке не видно.

### Токенизация

`POST https://api.freedompay.kz/v1/merchant/{merchant_id}/card/init`.

### НЕ СОБРАНО

Формат check_url, поддержка «Мира» в интернет-эквайринге.

---

## 13. ioka (Казахстан)

Источники **[офиц]**:
- https://ioka.kz/docs/en/ioka-api/accept-payment
- `/webhooks`
- `/testing`
- `/payments-with-saved-card/*`
- https://ioka.kz/developers/api (справочник, не читал)

### Доступ

- Заголовок **`API-KEY`**.
- Тест: **`https://stage-api.ioka.kz/v2`**, тестовый доступ через аккаунт-менеджера после комплаенса.
- Прод-хост в прочитанных страницах не указан (вероятно `api.ioka.kz`). ⚠ Сверить.

### Создание заказа: POST /v2/orders

- **`amount` в минорных единицах: 500 тенге = `50000`** (1 тенге = 100 тиын).
- `capture_method`: `AUTO` (по умолчанию, одностадийный) или `MANUAL` (двухстадийный).
- Прочее: `currency` (KZT), `external_id`, `description`, `extra_info`, `due_date`, `customer_id`, `card_id`, `back_url`, `success_url`, `failure_url`, `template`.
- Ответ: `order{id, status, checkout_url, access_token, attempts (по умолчанию 10), …}`, `order_access_token`.
- Клиента перенаправляют на `checkout_url`.

### Статусы заказа

| Статус | Смысл |
|---|---|
| `UNPAID` | начальный |
| `ON_HOLD` | холд (MANUAL) |
| `PAID` | оплачен (деньги придут в течение 3 рабочих дней), можно вернуть |
| `EXPIRED` | истёк `due_date` |

Заказ успешен при переходе в `PAID` или `ON_HOLD` (в зависимости от способа списания).

### Статусы платежа

| Статус | Смысл |
|---|---|
| `PENDING` | ждёт подтверждения |
| `REQUIRES_ACTION` | 3DS |
| `APPROVED` | холд успешен. **Если не списать или не отменить за 48 часов, спишется автоматически** |
| `CAPTURED` | списано |
| `CANCELLED` | холд снят |
| `DECLINED` | отказ; придёт `error{code, message}` |

### Уведомления

- Регистрация вебхука через API (`CreateWebhook`): URL + события. В ответе приходит **секретный ключ уведомления**.
- События: `ORDER_EXPIRED`, `PAYMENT_DECLINED`, `PAYMENT_APPROVED`, `PAYMENT_CAPTURED`, `PAYMENT_CANCELED`, `CARD_APPROVED`, `CARD_DECLINED`, `TRANSFER_*`.
- Тело: `{event, order{…}, payment{id, status, approved_amount, captured_amount, refunded_amount, processing_fee, payer{pan_masked, …, customer_id, card_id}, error, acquirer, action}}`.
- **Подпись: заголовок `X-Signature`** = HMAC-SHA256 с секретным ключом уведомления от JSON-строки, в которой **все ключи (рекурсивно) отсортированы и убраны пробелы** между парами.
  - ⚠ Сверить: в Python это `json.dumps(obj, sort_keys=True, separators=(",", ":"))`. Отдельно проверить кириллицу (`ensure_ascii`) — в доке не уточнено.
- Дополнительно — IP боевой среды: **94.247.132.210**.
- Ответ: **HTTP 200 за 10 секунд**. Иначе повторы каждые **5 секунд, не более 10 раз**.

### Сохранённые карты

- Если клиент отметил «Сохранить карту», в вебхуке или `GetOrderByID` придут `payer.customer_id` и `card_id`.
- Оплата: `POST /v2/orders` с `amount`, `customer_id`, `card_id` (с вводом CVC или без, в зависимости от сценария).

### Тестовые карты

| Карта | Результат |
|---|---|
| 4111111111111111 (Visa, 3DS) | успех после 3DS; пароль ACS `12345678` |
| 5555555555555599 (MC) | успех |
| 4444444444446666 | превышен лимит |
| 4444444411111111 | недостаточно средств |

Для всех: CVV 123, срок 12/2026.

### НЕ СОБРАНО

Возврат и capture (страницы `/after-payment/*` есть), полный справочник ошибок.

---

## 14. Processing.kz

Официальную документацию **не нашёл**. Всё ниже **[не первоисточник]**: PHP-клиент kolesa-team/processing-kz, Ruby-гем processing_kz, issue savon.

- Протокол SOAP. Тестовый WSDL: `https://test.processing.kz/CNPMerchantWebServices/CNPMerchantWebService.wsdl`. Прод-адрес НЕ СОБРАН.
- **startTransaction**: `merchantId`, `terminalId`, `totalAmount`, `currencyCode` (398 = KZT), `description`, `returnURL`, `goodsList`, `languageCode` (ru/en/kz), `merchantLocalDateTime` (`dd.mm.YYYY HH:MM:SS`), `orderId`, `purchaserName`, `purchaserEmail`. Ответ: `success`, `customerReference`, `errorDescription` (+ URL платёжной формы).
- Клиент платит во фрейме Processing.kz и возвращается на `returnURL`.
- **completeTransaction**: `merchantId`, `referenceNr` (= customerReference), `transactionSuccess` (true/false), опционально `overrideAmount`, `goodsList`. Это вторая стадия: подтвердить или отменить.
- **getTransactionStatus**: `merchantId`, `referenceNr`. После оплаты статус `AUTHORISED`, после complete — **`PAID`**.
- Ruby-гем поддерживает только стандартные платежи без возвратов.
- ⚠ Сверить: единицы `totalAmount` (тенге или тиыны) не установлены.

---

## 15. Click (Узбекистан)

Источники **[офиц]**:
- https://docs.click.uz/en/click-api-request/
- https://docs.click.uz/en/?p=9 (коды ошибок)

Merchant API (статус по `merchant_trans_id`): `https://api.click.uz/v2/merchant/` (PHP-модуль Click, не первоисточник).

### Схема Shop API

Click сам вызывает ваш сервер двумя запросами:
1. **Prepare** (`action = 0`): проверка заказа и суммы.
2. **Complete** (`action = 1`): завершение. При успешном Prepare Click шлёт Complete, **повторно Complete не отправляется**.

### Поля запросов

- Prepare: `click_trans_id`, `service_id`, `click_paydoc_id`, `merchant_trans_id` (ваш ID заказа), `amount`, `action`, `error`, `error_note`, `sign_time`, `sign_string`.
- Complete: те же поля плюс `merchant_prepare_id` (ваш ID из ответа на Prepare).
- Формат `sign_time`: `YYYY-MM-DD HH:mm:ss` (по PHP-модулю).

### Подпись sign_string (MD5)

- Prepare: `md5(click_trans_id + service_id + SECRET_KEY + merchant_trans_id + amount + action + sign_time)`
- Complete: `md5(click_trans_id + service_id + SECRET_KEY + merchant_trans_id + merchant_prepare_id + amount + action + sign_time)`
- ⚠ Сверить: `amount` берётся строкой как пришла (например `1000.0` или `1000`), без переформатирования.

### Ответ (JSON)

`error` (0 — успех), `error_note`, `click_trans_id`, `merchant_trans_id`, а также `merchant_prepare_id` (для Prepare) или `merchant_confirm_id` (для Complete).

### Коды, которые возвращает ваш сервер

| Код | Смысл |
|---|---|
| 0 | успех |
| -1 | ошибка проверки подписи |
| -2 | неверная сумма |
| -3 | действие не найдено |
| -4 | уже оплачено (попытка подтвердить или отменить подтверждённую) |
| -5 | пользователь или заказ не найден (`merchant_trans_id`) |
| -6 | транзакция не найдена (`merchant_prepare_id`) |
| -7 | не удалось обновить данные пользователя |
| -8 | ошибка в запросе от Click |
| -9 | транзакция отменена (попытка подтвердить или отменить отменённую) |

Если в Complete пришёл отрицательный `error` от Click (оплата не прошла), отменить заказ у себя и ответить **-9**.

### НЕ СОБРАНО

Требование «всегда HTTP 200» в прочитанных страницах не нашёл.

---

## 16. Payme / Paycom (Узбекистан)

Источник **[офиц]**: https://developer.help.paycom.uz. Страницы методов, «Типы данных», «Схема взаимодействия», «Песочница», «Отправка чека по методу POST», Subscribe API.

### Схема

Merchant API, JSON-RPC 2.0. Payme Business сам вызывает ваш эндпоинт.

### Авторизация входящих запросов

- HTTP Basic: `Authorization: Basic base64(login:password)`. Password — ключ, выданный после добавления веб-кассы.
- В кабинете ключ `key`, в песочнице `TEST_KEY`.
- Неверная авторизация → ошибка **-32504** («недостаточно привилегий»), это проверяется в песочнице.
- Запросы приходят только с IP **185.234.113.1–185.234.113.15**.
- Рекомендации к серверу: SSL session cache 1 МБ, session timeout и keepalive 10 минут или больше.

### Типы данных

| Тип | Описание |
|---|---|
| ID | строка 24 символа |
| Timestamp | 13 цифр, миллисекунды UTC |
| Amount | целое > 0, **в тийинах** |
| Account | объект, поля задаёт мерчант (`{"order": "…"}`, `{"phone": "…"}` и т.д.) |

### Методы

| Метод | Суть | Ответ |
|---|---|---|
| CheckPerformTransaction | можно ли оплатить (amount, account) | `{allow: true}` |
| CreateTransaction | создать (id, time, amount, account); при повторе с тем же id — вернуть то же | `create_time`, `transaction`, `state: 1` (+ `receivers`) |
| PerformTransaction | провести, заказ становится «оплачен» | `transaction`, `perform_time`, `state: 2` |
| CancelTransaction | отменить созданную **или проведённую** (id, reason) | `transaction`, `cancel_time`, `state` (в примере `-2` — отмена проведённой) |
| CheckTransaction | статус | `create_time`, `perform_time`, `cancel_time`, `transaction`, `state`, `reason` |
| GetStatement | выписка за период | НЕ СОБРАНО |

Требования к CreateTransaction:
- Хранить транзакции в постоянном хранилище.
- Проверять, что account существует (иначе -31050…-31099) и что сумма совпадает со счётом (иначе -31001).
- Бронировать заказ до оплаты или отмены по таймауту; запретить изменение заказа.

### Коды ошибок

| Код | Смысл |
|---|---|
| -32700 | ошибка парсинга JSON |
| -32600 | нет обязательных полей или неверные типы |
| -32504 | недостаточно привилегий (авторизация) |
| -32400 | системная ошибка |
| -31001 | неверная сумма |
| -31003 | транзакция не найдена |
| -31007 | заказ выполнен, отменить нельзя (CancelTransaction) |
| -31008 | невозможно выполнить операцию (неверное состояние) |
| -31050…-31099 | ошибки `account`: `message` локализован (ru/uz/en), `data` — имя поля account |

- **Таймаут:** транзакция отменяется через **12 часов** (43 200 000 мс) после создания в Payme.
- Состояния транзакции: 1 создана, 2 проведена, отрицательные — отменена (-2 после проведения; -1 до проведения — стандарт, в выдержке не виден).

### Песочница

- Адрес `https://test.paycom.uz`.
- Проверяет: неверную сумму (-31001), неверный заказ (-31050…-31099), неверную авторизацию (-32504).
- **CreateTransaction, PerformTransaction и CancelTransaction отправляются дважды, и ответ на повтор должен совпадать с первым.**

### Инициализация оплаты (чек)

- POST-форма на `https://checkout.paycom.uz` (прод) или `https://test.paycom.uz` (песочница).
- Поля: `merchant` (ID кассы), `amount` (тийины), `account[поле]`, `lang` (ru/uz/en), `callback` (URL возврата с подстановками `:transaction`, `:account.{field}`).

### Subscribe API (карты, рекуррент)

- Запросы идут **от мерчанта**: `https://checkout.paycom.uz/api` (тест: `https://checkout.test.paycom.uz/api`).
- Заголовок `X-Auth` (ID кассы и ключ).
- Требуется лейбл «Powered by Payme».

### НЕ СОБРАНО

Объект `detail` для фискального чека (упоминается объект `additional`, его использование согласуется с Payme), детали GetStatement.

---

## 17. LiqPay (Украина)

Источники **[офиц]**:
- https://www.liqpay.ua/documentation/en/api/callback
- `/api/information/status/doc`
- `/api/aquiring/checkout/doc`
- `/api/aquiring/pay/doc`

### Адреса

- Checkout (форма): `https://www.liqpay.ua/api/3/checkout`.
- Server-to-server: `https://www.liqpay.ua/api/request`.

### Формирование запроса

1. JSON с параметрами (`version` = 3, `public_key`, `action`, `amount`, `currency`, `description`, `order_id`, `server_url`, `result_url`, …).
2. `data = base64(json)`.
3. `signature = base64( sha1_binary( private_key + data + private_key ) )`.
4. Отправить `data` и `signature`.

### Checkout: ключевые параметры

- `version`, `order_id` (уникален в магазине), `amount`, `currency`, `description`, `paytypes`, `server_url` (callback), `result_url` (возврат клиента).
- Подписка: `subscribe` (=1), `subscribe_date_start` (UTC, формат `YYYY-MM-DD HH:MM:SS` — по старой доке), `subscribe_periodicity` (`month`; в старой доке ещё `year`).
- `sandbox=1` — тест (по примерам).
- Значения `action`: `pay`, `hold`, `paysplit`, `subscribe`, `paydonate`, `auth`, `regular`.
- Рекуррент без карты: `card_token` + API paytoken.

### Callback

- POST на `server_url` с `data` и `signature`.
- Проверка: пересчитать `base64(sha1(private_key + data + private_key))` по **сырому значению `data`**, затем сравнить. После проверки декодировать `data`.
- Поля: `action`, `status`, `payment_id`, `order_id`, `liqpay_order_id`, `amount`, `currency`, `paytype` (card, liqpay, privat24, masterpass, moment_part, cash, invoice, qr), `err_code`, `err_description`, `err_erc`, `version`.
- Актуальный статус можно запросить в любой момент: `action=status` + `order_id`.

### Статусы

| Группа | Статусы |
|---|---|
| Финальные | `success` (успех), `failure` (неуспех), `error` (неуспех, неверные данные), `reversed` (возврат) |
| Подписка | `subscribed` (оформлена), `unsubscribed` (деактивирована) |
| Прочие | `hold_wait` (сумма заблокирована), `wait_secure` (платёж на проверке), `sandbox` (тестовый — по SDK) |
| Требуют подтверждения | есть отдельная группа (3DS/OTP и т.п.), список НЕ СОБРАН |

Не первоисточник: отмена холда и возврат списанного оба дают `reversed`; server-to-server вызовы (status, refund, hold_completion) идут с `version=3`.

### НЕ СОБРАНО

Формат `order_id` у регулярных списаний подписки, требуемый ответ на callback.

---

## 18. «Оплата по ссылке» (link.py) и 19. Тестовая касса (test_provider.py)

Внешнего API нет. Проверять только код:
- link.py — подтверждение делает продавец вручную, и только он;
- test_provider.py — в боевом режиме выключена и не может подтвердить оплату простым открытием ссылки.

---

## Общий чек-лист для сверки адаптеров

1. **Сумма и валюта** в уведомлении сверяются с заказом. Единицы:
   - копейки: Stripe, ioka (тиыны), Payme (тийины);
   - строки с дробью: Crypto Bot, ЮKassa, LIFE PAY, Robokassa;
   - decimal: PayMaster, CloudPayments.
2. **Подпись по сырым байтам**: Stripe, Crypto Bot, CloudPayments.
3. **Подпись по сериализации** с сортировкой ключей: ioka, Prodamus. Совпадение байтов JSON критично.
4. **Подпись по склейке строк**:
   - Т-Банк: булевы как `"true"`;
   - Robokassa: `OutSum` как пришёл, Пароль #2 для ResultURL;
   - Click: порядок полей;
   - Freedom Pay: имя скрипта в начале, ключ в конце.
5. **Подписи нет**: ЮKassa, LIFE PAY, PayMaster (API v2). Нужен перезапрос статуса через API и/или allowlist IP.
6. **Формат ответа**:
   - `OK` — Т-Банк
   - `OK{InvId}` — Robokassa
   - `{"code":0}` — CloudPayments
   - XML `pg_status` — Freedom Pay
   - JSON `error` — Click
   - JSON-RPC — Payme
   - `answerPreCheckoutQuery` — Telegram
7. **Идемпотентность**: повторы приходят у Stripe, Crypto Bot (`update_id` не уникален), ЮKassa (24 ч), lava.top (19 раз), ioka (10 раз), LIFE PAY (10 раз), Payme (песочница шлёт дважды), Freedom Pay (повтор = тот же ответ).
8. **Устаревшие поля и адреса**:
   - Crypto Bot `pay_url` → `bot_invoice_url`;
   - lava.top `/api/v1|v2/invoice` → `/api/v3/invoice`;
   - Т-Банк тест — DEMO-терминал на боевом хосте, а не `rest-api-test`;
   - PayMaster — ставки Vat22/Vat122 вместо 20/120.
9. **Регистр статусов**: lava.top (вебхук в нижнем, API в верхнем).
10. **Двухстадийные платежи с автосписанием**: ioka APPROVED через 48 ч списывается сам; ЮKassa и CloudPayments отменяют холд по истечении срока.
