# Как подключить приём денег платформы (запуск $49 и подписка $15)

Эти способы нужны, чтобы **вам** платили за запуск ботов. Это не кассы клиентов. Код всех трёх способов
(Stripe, Crypto Bot, Telegram Stars) уже написан и проверен тестами. Не хватает **ваших настоящих
аккаунтов**: ключи вы берёте у провайдеров и кладёте на сервер в `.env`. Ключи в чат, в репозиторий и в
скриншоты не отправлять. Если ключ засветился, сразу отзовите его в кабинете и выпустите новый.

Все изменения `.env` делаются на сервере и применяются пересозданием только `api`:

```bash
docker compose up -d --no-deps --force-recreate api bot
```

(без полного перезапуска, без `down`, без `prune`). После любой правки проверка без денег:

```bash
docker compose exec api python -m app.platform_check
```

Он читает `PLATFORM_PAYMENT_METHODS`, проверяет ключи запросом «кто я» к самому провайдеру и печатает адреса
вебхуков, которые нужно вписать в кабинеты. Деньги не двигаются, ключи не печатаются.

## 1. Stripe (карты)

Нужен аккаунт Stripe в стране, которую Stripe поддерживает. Казахстан в списке, по найденным данным, не
значится: обычно используют компанию в поддерживаемой стране (например эстонская OÜ или американская LLC
через Stripe Atlas). Условия проверяйте на сайте Stripe.

1. В Stripe Dashboard пройти активацию аккаунта («Activate»), пока приём платежей не включён, живой режим
   не заработает.
2. Developers → API keys → **Secret key** (`sk_live_…`). Не тестовый `sk_test_…`.
3. Developers → Webhooks → Add endpoint. Адрес: `https://<ваш домен>/webhook/pay/stripe`. События:
   `checkout.session.completed`, `checkout.session.async_payment_succeeded`,
   `checkout.session.async_payment_failed`, `checkout.session.expired` и (для возвратов) `charge.refunded`.
   После создания скопировать **Signing secret** (`whsec_…`). У тестового и боевого режимов секреты разные.
4. В `.env` на сервере в `PLATFORM_PAYMENT_METHODS` добавить способ:
   `{"provider":"stripe","price_minor":4900,"renewal_price_minor":1500,"currency":"USD","credentials":{"secret_key":"sk_live_…","webhook_secret":"whsec_…"}}`
5. Пересоздать `api`, запустить `python -m app.platform_check`: должно быть «ключ боевой», «аккаунт найден,
   приём платежей: включён».
6. Живой тест: опубликовать тестового бота, оплатить $49 своей картой, убедиться, что бот стал доступен, затем
   вернуть деньги в Dashboard (Payments → Refund).

## 2. Crypto Bot (USDT)

Юрлицо и KYC для приёма не нужны.

1. В Telegram открыть `@CryptoBot` → **Crypto Pay** → **Create App**, придумать название, скопировать
   **API Token**.
2. Там же My Apps → ваше приложение → **Webhooks** → включить и указать
   `https://<ваш домен>/webhook/pay/cryptobot`. (Мы всё равно перепроверяем счёт запросом в их API, подпись не
   единственная защита.)
3. В `PLATFORM_PAYMENT_METHODS` добавить способ:
   `{"provider":"cryptobot","price_minor":4900,"renewal_price_minor":1500,"currency":"USDT","credentials":{"token":"…"}}`
   Для тестовой сети (`@CryptoTestnetBot`, не настоящие деньги) добавить `"is_test":true`.
4. Пересоздать `api`, запустить `platform_check`: «приложение …, боевая сеть».
5. Живой тест: временно поставить маленькую цену, оплатить из своего кошелька, вернуть цену. Деньги копятся
   в кошельке `@CryptoBot`, оттуда выводятся на биржу или карту средствами самого `@CryptoBot`.

## 3. Telegram Stars

Ничего регистрировать и никаких ключей не нужно: счёт звёздами выставляет **мета-бот**, звёзды копятся на его
балансе.

1. Убедиться, что мета-бот работает (`META_BOT_TOKEN` в `.env`, контейнер `bot` запущен).
2. В `PLATFORM_PAYMENT_METHODS` добавить способ (число звёзд умножается на 100):
   `{"provider":"stars","price_minor":380000,"renewal_price_minor":115000,"currency":"XTR"}`
   Это 3800 ⭐ за запуск и 1150 ⭐ в месяц (покупатель платит около $0,02 за звезду, на вывод через Fragment
   приходит около $0,013, поэтому число звёзд выше, чем «в долларах»).
3. Пересоздать `api` и `bot`, запустить `platform_check`: «мета-бот отвечает».
4. Живой тест: временно поставить `price_minor: 100` (это 1 ⭐), оплатить со своего аккаунта, вернуть цену.
5. **Заранее проверить вывод.** Звёзды выводятся через Fragment в TON. По сторонним источникам есть задержка
   около 21 дня и минимум около 1000 звёзд, доступность зависит от страны. Это не официальные данные: проверьте
   в Telegram (BotFather → мини-приложение → ваш бот → Balance), доступен ли вывод именно вам, до того как
   включать способ для клиентов.

## 4. Итоговая переменная (три способа сразу)

```
PLATFORM_PAYMENT_METHODS=[{"provider":"stripe","price_minor":4900,"renewal_price_minor":1500,"currency":"USD","credentials":{"secret_key":"sk_live_…","webhook_secret":"whsec_…"}},{"provider":"cryptobot","price_minor":4900,"renewal_price_minor":1500,"currency":"USDT","credentials":{"token":"…"}},{"provider":"stars","price_minor":380000,"renewal_price_minor":115000,"currency":"XTR"}]
```

Проверить: `curl https://<домен>/api/config`, в `pricing` должны быть все способы. Если JSON с опечаткой,
публикация отвечает 503 (а не раздаёт запуск даром), `platform_check` сразу об этом скажет.
Также в `.env` должны быть `PUBLIC_BASE_URL` (настоящий домен, не `your-domain.com`), `ADMIN_TELEGRAM_IDS` и
`SUBSCRIPTIONS_ENABLED=0`.
