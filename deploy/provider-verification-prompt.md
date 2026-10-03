# Задание для сверки касс с официальной документацией

Скопируй блок ниже целиком другому ассистенту, у которого есть доступ в интернет и к репозиторию.

---

Репозиторий: Bot Factory (Python, FastAPI). Платёжные адаптеры лежат в `app/services/payments/` (по файлу на провайдера, общий контракт — `base.py`). Нужно для КАЖДОГО провайдера из списка найти ОФИЦИАЛЬНУЮ документацию, сверить с кодом адаптера и вернуть расхождения. Код не правь — только отчёт. Не выдумывай: если страницу не нашёл или не открыл, так и пиши «не проверено», цитируй только то, что реально прочитал, и давай ссылку.

Что сверять у каждого: адрес API (прод и тест), способ авторизации, поля запроса создания платежа (единицы суммы: рубли/копейки, тенге/тиыны, сумы/тийины; валюта; описание; return/callback URL; метаданные; чек 54-ФЗ — обязателен ли), формат ответа и поле со ссылкой на оплату, как приходит уведомление об оплате (формат, подпись/хеш, порядок и состав полей, алгоритм, регистр, что именно ответить провайдеру), статусы платежа (какие значит «оплачено», «отказ», «возврат»), возвраты, повторы уведомлений, идемпотентность, рекуррентные платежи (токен карты, подписка), тестовый режим, поддерживаемые карты (особенно «Мир»). Для каждого расхождения: файл:строка у нас, цитата из документации, ссылка, критичность (блокер / важное / мелочь).

## Список провайдеров (файл адаптера → что искать)

**Касса для оплаты запуска платформе (самое важное)**
1. **Stripe** — `stripe.py`. Checkout Session (mode payment и subscription), подпись вебхука `Stripe-Signature`, события `checkout.session.completed / async_payment_succeeded / async_payment_failed / expired`, `invoice.paid` для подписок, возвраты и `charge.*`, валюты без дробной части, KZT в Checkout, Adaptive Pricing.
2. **Crypto Bot (Crypto Pay API, @CryptoBot)** — `cryptobot.py`. `createInvoice`, `getInvoices`, подпись `crypto-pay-api-signature`, поля ссылки (`bot_invoice_url`, `web_app_invoice_url`, `pay_url`), тестовая сеть (`@CryptoTestnetBot`), единицы суммы.
3. **Telegram Stars (XTR)** — `telegram_stars.py`, `meta_bot/handlers/payments.py`. Bot API: `createInvoiceLink`, `pre_checkout_query` (10 секунд), `successful_payment`, подписки (`subscription_period` 2592000, лимит цены), возврат `refundStarPayment`, `editUserStarSubscription`, продления.

**Россия**
4. **ЮKassa (YooKassa)** — `yookassa.py`. API v3 платежей, Basic-авторизация, `Idempotence-Key`, чек (`receipt`, 54-ФЗ), статусы (`pending`, `waiting_for_capture`, `succeeded`, `canceled`), уведомления (проверка по IP или перезапрос), возвраты, сохранение карты и автоплатежи, тестовый магазин.
5. **Т-Банк (Tinkoff Acquiring)** — `tbank.py`. `Init`, `GetState`, подпись `Token` (какие поля входят, регистр булевых), `Receipt`, уведомления и ответ `OK`, статусы, актуальный домен API.
6. **CloudPayments** — `cloudpayments.py`. `orders/create` (поле со ссылкой), `payments/find`, `Content-HMAC`/`X-Content-HMAC`, уведомления Check/Pay/Fail, откуда берётся `Token` для рекуррентов, `Subscriptions`.
7. **PayMaster** — `paymaster.py`. REST v2, `Idempotency-Key`, поле токена карты (`paymentToken`?), статусы, `receipt`, `callbackUrl`.
8. **Robokassa** — `robokassa.py`. Формулы подписи (Password1/Password2, `Shp_*`, `SuccessUrl2/FailUrl2` в подписи), `Receipt` (54-ФЗ), `IsTest` и тестовые пароли, ответ `OK{InvId}`, рекуррент `/Merchant/Recurring`.
9. **LIFE PAY** — `lifepay.py`. `/v1/bill`, подпись callback, коды статусов, СБП и интернет-эквайринг.
10. **Prodamus** — `prodamus.py`. Подпись HMAC-SHA256 (сериализация JSON, экранирование `/`), заголовок `Sign`, `products` (поля `tax`/`sno` для фискализации), подписки, статусы `payment_status`.
11. **lava.top** — `lavatop.py`. Swagger API, `offerId`, `contractId`, авторизация вебхука, вебхуки возвратов и чарджбэков (без `contractId`?), статусы, `periodicity`.

**Казахстан / Узбекистан / Кыргызстан**
12. **Freedom Pay (бывший PayBox)** — `freedompay.py`. `init_payment`, подпись `pg_sig` (имя скрипта в строке подписи), правильный домен API (`api.freedompay.kz` или `.money`), `pg_recurring_*` (единицы `pg_recurring_lifetime`), ответ на Result URL, **принимает ли интернет-эквайринг карты «Мир»** (только с прямой ссылкой).
13. **ioka** — `ioka.py`. Заказы и платежи, `API-KEY`, единицы суммы (тиыны?), список статусов, подпись вебхука, оплата сохранённой картой, тестовый хост.
14. **Processing.kz** — `processingkz.py`. SOAP/WSDL (`startTransaction`, `getTransactionStatus`, `completeTransaction`), двухстадийная оплата, единицы суммы, хосты prod/test.
15. **Click (Узбекистан)** — `click.py`. Prepare/Complete, формула подписи, коды ошибок (`-1`…`-9`, особенно `-2` сумма, `-4` уже оплачено, `-9` отменено), ответ всегда HTTP 200.
16. **Payme / Paycom (Узбекистан)** — `payme.py`. Merchant API (JSON-RPC): Basic-авторизация, методы `CheckPerformTransaction`, `CreateTransaction`, `PerformTransaction`, `CancelTransaction`, `CheckTransaction`, `GetStatement`, коды ошибок (`-31007`, `-31008`, `-31050`, `-31099`), таймаут 12 часов, `detail` для фискального чека, тестовый кабинет.

**Украина**
17. **LiqPay** — `liqpay.py`. `data` + `signature` (`base64(sha1(private+data+private))`), список статусов (`success`, `sandbox`, `subscribed`, `wait_secure`, `reversed`, `failure`), подписки и продления, формат `order_id` у регулярных списаний.

**Без внешнего API**
18. **«Оплата по ссылке»** — `link.py`: продавец подтверждает вручную; сверять нечего, проверить только логику подтверждения.
19. **Тестовая касса (`test`)** — `test_provider.py`: только для разработки, подтверждает при открытии ссылки; в бою выключена.

## Формат ответа

Таблица «провайдер → вердикт (совпадает / есть расхождения / не удалось проверить)», затем расхождения по критичности с цитатами и ссылками, затем список того, что не удалось открыть и почему.
