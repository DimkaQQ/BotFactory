# Открытые вопросы по кассам: ответы и решения

Сборка: 3 октября 2026. В каждом пункте: что выяснено (со ссылкой), что решаем и что сделать в коде.

---

## 1. Prodamus: экранировать ли `/` при подписи

**Ответ: да, экранировать.** Пробный запрос к demo.payform.ru не нужен.

Источник: официальный репозиторий Prodamus https://github.com/PRODAMUS/integration-expert, файл `references/hmac.md`.

### Канон для webhook (заголовок `Sign`) и для `signature` в `do=pay`

1. Все значения рекурсивно привести к строкам, как PHP `strval`:
   - `True` → `"1"`, `False` → `""`, `None` → `""`.
2. Рекурсивно отсортировать словари по ключам. Порядок в списках не трогать.
3. Сериализовать как PHP `json_encode($data, JSON_UNESCAPED_UNICODE)`:
   - кириллица остаётся как есть;
   - пробелов нет;
   - **`/` превращается в `\/`**.
4. Посчитать `hmac_sha256(secret, json).hexdigest()`.
5. Сравнить с заголовком `Sign` через `hmac.compare_digest`, без учёта регистра.
6. Перед проверкой удалить из тела поля `signature`, `sign`, `_payform_sign`.

Я прогнал официальные тест-векторы в Python:
- вариант с `\/` даёт эталонную подпись в обоих векторах;
- вариант без экранирования ломает вектор 2, где в данных есть URL.

```python
import hashlib, hmac, json

def _s(v):
    if isinstance(v, dict): return {str(k): _s(x) for k, x in v.items()}
    if isinstance(v, (list, tuple)): return [_s(x) for x in v]
    if isinstance(v, bool): return "1" if v else ""
    if v is None: return ""
    return str(v)

def _k(v):
    if isinstance(v, dict): return {k: _k(v[k]) for k in sorted(v)}
    if isinstance(v, list): return [_k(x) for x in v]
    return v

def prodamus_sign(data: dict, secret: str) -> str:
    j = json.dumps(_k(_s(data)), ensure_ascii=False, separators=(",", ":"))
    j = j.replace("/", "\\/")
    return hmac.new(secret.encode(), j.encode(), hashlib.sha256).hexdigest()

def prodamus_verify(data: dict, secret: str, sign: str) -> bool:
    clean = {k: v for k, v in data.items() if k not in ("signature", "sign", "_payform_sign")}
    return hmac.compare_digest(prodamus_sign(clean, secret).lower(), (sign or "").lower())

# Тест-векторы из репозитория Prodamus (secret = "test_secret_key"):
# v1 -> a0c2f61457c981288d7687765a069d5e8db5b6998706115fb0c0de0988620609
# v2 (с кириллицей и URL) -> ca54bade5070ec36f00dd966aea69bd84f5bdc89632b8f3d25c93f57340628c5
```

### Ещё факты из того же репозитория

- **Ключ подписи.** Если интеграции выдан `sys`, webhook может быть подписан сервисным ключом (он выдаётся вместе с `sys`), а не секретом страницы. Нужна настройка `webhook_secret` с фолбэком на `secret_key`. Если подпись не сходится, первым делом проверить ключ, потом алгоритм.
- **Формат webhook.** Приходит как form-urlencoded или multipart, парсер должен понимать оба.
- **Ответ.** Строго **HTTP 200**: даже 202 считается недоставкой. Ошибка подписи — 400 или 403.
- **Поля webhook:**
  - `order_num` — эхо нашего `order_id` (сопоставлять по нему);
  - `order_id` — внутренний номер Prodamus;
  - `sum` — строка вида `1000.00`;
  - `currency` — `rub`;
  - `receipt_url` — ссылка на чек;
  - **`is_test=1`** — тестовый платёж: в бою ответить 200 и не обрабатывать.
- **Статусы:**
  - `success` — оплачено;
  - `order_canceled` — отменил покупатель;
  - `order_denied` — отказ банка (рассрочка);
  - неизвестный статус — ответить 200 и записать в лог, не 400 (иначе будут бесконечные повторы).
- **`do=link`.** Подпись опциональна. Если её передавать, считается **другой** схемой (query-string канонизация). JSON-схему к `do=link` не применять.
- **Подписки.**
  - Маршрутизировать по `subscription[profile_id]`, а не по `subscription[id]`: это ID тарифа, он общий для всех покупателей.
  - Ключ идемпотентности: `profile_id + payment_num`.
  - Отмена: `POST https://{payform}/rest/setActivity/`.
- **Финальная проверка.** На первом живом прогоне сохранить сырое тело и заголовок `Sign` реального webhook и сделать из них регрессионный тест.

---

## 2. Чеки 54-ФЗ

### Что выяснено

| Касса | Что говорит дока | Формат позиции |
|---|---|---|
| **Т-Банк** | `Receipt` **обязателен, если подключена онлайн-касса** (страницы Confirm и Cancel) | `Receipt{Email/Phone, Taxation, Items[{Name≤128, Price (коп.), Quantity, Amount = Price×Qty (коп.), Tax, PaymentMethod, PaymentObject}], Payments?}`. Сумма `Items.Amount` должна равняться `Amount` платежа. Не больше 100 позиций. **`Tax`: none, vat0, vat5, vat7, vat10, vat22, vat105, vat107, vat110, vat122 — `vat20` в списке уже нет.** `PaymentMethod` по умолчанию `full_payment`. Объект `Receipt` в Token не входит |
| **ЮKassa** | При подключённых чеках без `receipt` будет ошибка. Если чек отправляется отдельно (`POST /v3/receipts`), `receipt` в платёж не класть. При частичном capture передать новый `receipt` | `receipt{customer{email/phone}, items[{description, quantity, amount{value,currency}, vat_code, payment_mode, payment_subject}]}` (имена полей сверить с /developers/54fz) |
| **Robokassa** | `Receipt` (JSON, urlencode) входит в подпись между InvId и Паролем #1 | `{"sno":"osn", "items":[{"name","quantity","sum","tax","payment_method","payment_object"}]}`. `tax`: none, vat0, vat5, vat7, vat10, vat20, vat22, vat105, vat107, vat110, vat120, vat122. Второй (итоговый) чек: `ws.roboxchange.com/RoboFiscal/Receipt/Attach` |
| **PayMaster** | `receipt` в `/invoices`, `/payments`, `/confirm`, `/refunds` или отдельно `POST /receipts` | `items[{name, quantity, price, vatType, paymentSubject, paymentMethod}]`, `client{email/phone}`. `vatType`: None, Vat0, Vat5, Vat7, Vat10, **Vat22**, Vat105, Vat107, Vat110, **Vat122** |
| **Prodamus** | Чек формирует Prodamus по `products` | у позиции решить `tax`, `payment_object`, `payment_method` (для предоплаты — `full_prepayment`); сумма должна сходиться: `sum == Σ(price×qty)` |

### Решение

**Не просить продавца отключать чеки.** Для российского продавца с онлайн-кассой чек обязателен по закону. Мы не можем советовать его отключить, и касса всё равно потребует чек.

**Генерировать чек автоматически по флагу в настройках кассы продавца.**

1. В `base.py` добавить общую модель `Receipt`:
   - `items[{name, qty, price: Decimal, vat, payment_method="full_prepayment", payment_object="service"}]`
   - `customer_email` / `customer_phone`
   - `tax_system` (`osn` / `usn_income` / …)
2. В настройках кассы продавца добавить поля:
   - `fiscalization_enabled: bool`
   - `tax_system`
   - `default_vat`
3. Каждый адаптер переводит общую модель в свой формат (таблица выше). Если `fiscalization_enabled=False`, чек не передаётся.
4. Для оплаты запуска на платформе — одна позиция «Запуск бота …», `payment_object=service`, `full_prepayment`.
5. Ставки НДС хранить в общем enum с **vat22 и vat122**, плюс маппинг для каждой кассы. Т-Банк и PayMaster уже не принимают 20/120.
   - ⚠ Числовые `vat_code` ЮKassa для 22% я не проверял — сверить по справочнику значений перед релизом.
6. Если касса вернула ошибку «нужен чек», показать продавцу понятный текст: «включите фискализацию в настройках кассы и укажите СНО».

---

## 3. Robokassa: тестовые пароли

Источник: https://docs.robokassa.ru/ru/testing-mode.

### Что выяснено

- Для теста нужны **отдельные** Пароль #1 и #2. Алгоритм хеша тот же, что в бою.
- В запросе обязателен `IsTest=1`. Если параметра нет, он равен 0 или пустой, платёж создаётся **боевой**.

### Решение

1. В настройки Robokassa добавить `test_password1`, `test_password2`, `test_mode: bool`.
2. При создании ссылки в тест-режиме подписывать `test_password1` и добавлять `IsTest=1`.
3. При проверке ResultURL выбирать пароль по режиму магазина, а не перебирать оба.
   - Если перебирать, тестовая подпись может провести боевой заказ.
   - В боевом режиме уведомление с `IsTest=1` отклонять.
4. Recurring и Split в тест-режиме не использовать: Split с `IsTest` несовместим.

---

## 4. Payme: таймаут, повтор после отмены, -31007, GetStatement, тест

Источники:
- `developer.help.paycom.uz/metody-merchant-api/*`
- «Типы данных»
- «Песочница»

### Состояния и причины

- Состояния: `1` создана, `2` проведена, `-1` отменена до проведения, `-2` отменена после проведения.
- Причина `4` — отмена по таймауту.

### Логика методов

| Метод | Правило |
|---|---|
| CheckPerformTransaction | Заказ существует, сумма совпадает (иначе -31001), заказ не оплачен. Если у заказа уже есть **другая** транзакция в состоянии 1 — ошибка из диапазона -31050…-31099 («заказ ожидает оплаты»). Иначе `{allow: true}` |
| CreateTransaction, тот же `id` | Если state ≠ 1 — **-31008**. Если state = 1 и прошло больше 12 ч (43 200 000 мс) от `params.time` — перевести в -1 с reason=4 и вернуть **-31008**. Иначе вернуть **тот же** ответ (`create_time`, `transaction`, `state: 1`) |
| CreateTransaction, новый `id` | Те же проверки, что в Check. Если у заказа есть активная (state 1) транзакция с другим id — ошибка -31050…-31099. **После отмены (-1 или -2) заказ освобождается, новая транзакция с новым id разрешена** |
| PerformTransaction | Нет транзакции — -31003. state 1 и больше 12 ч — отменить (-1, reason 4) и вернуть **-31008**. state 1 — провести (state 2, `perform_time`) и отметить заказ оплаченным. state 2 — вернуть тот же ответ. Иначе -31008 |
| CancelTransaction | Нет транзакции — -31003. state 1 — перевести в -1, сохранить `reason`. state 2 — если услуга уже оказана и возврат невозможен, **-31007**; иначе -2 и откатить заказ. Уже отменена — вернуть тот же ответ |
| CheckTransaction | Вернуть `create_time`, `perform_time`, `cancel_time` (0, если не было), `transaction`, `state`, `reason` |
| **GetStatement** (обязателен) | Транзакции, у которых `from ≤ time ≤ to` по **времени создания в Payme** (`params.time` из CreateTransaction). Только успешно созданные, по возрастанию. Поля как у транзакции: id, time, amount, account, create_time, perform_time, cancel_time, transaction, state, reason, receivers |

### Решение по -31007

Для оплаты запуска бота услуга считается оказанной, как только платформа запустила бота. Значит, после запуска отвечать -31007, до запуска — разрешать отмену (-2) и откатывать заказ.

### Тест

- Песочница `https://test.paycom.uz`, ключ `TEST_KEY` (в бою — ключ кассы).
- Форма оплаты: `test.paycom.uz` в тесте, `checkout.paycom.uz` в бою.
- Неверная авторизация — -32504.
- Create, Perform и Cancel песочница шлёт **дважды**, ответы должны совпасть.
- Входящие запросы приходят с IP 185.234.113.1–15.

---

## 5. Freedom Pay: метод result URL, Кыргызстан, `pg_can_reject`

Источники:
- https://freedompay.kz/docs/merchant-api/pay
- https://freedompay.kg/docs-en/merchant-api/pay
- https://freedompay.kz/docs-en/gateway-api/pay

### Что выяснено

- **`pg_request_method`** = `GET`, `POST` или `XML` — каким способом Freedom Pay вызывает наши check URL и result URL. При `XML` всё приходит POST-ом в одном параметре `pg_xml`.
- Отдельно есть `pg_success_url_method`, `pg_failure_url_method`, `pg_state_url_method` (GET/POST) для редиректов клиента.
- Пустой `pg_result_url` значит, что уведомлений о результате не будет.
- **Хосты:**
  - KZ: `https://api.freedompay.kz`;
  - **KG: `https://api.freedompay.kg`** (те же `init_payment.php` и подпись);
  - тестовый хост Gateway API: `https://test-api.freedompay.kz`.
- **Повторы result URL:** если наш сервер недоступен или ответил не 200, повтор каждые полчаса в течение 2 часов, даже после истечения `pg_lifetime`.
- **`pg_can_reject`:** 1 — платёж можно откатить (карты), 0 — безотзывный.
  - Ответить `rejected` можно только при 1, иначе платёж всё равно проведён.
  - Если первый вызов не удался, в повторных отказать уже нельзя.
  - Ответ на повтор должен совпадать с первым.

### Решение

1. В `init_payment` всегда явно передавать `pg_request_method=POST` и парсить form-data. Поддержку `XML` не делать.
2. Хост выбирать по стране магазина: настройка `country: kz|kg` → `api.freedompay.kz` или `api.freedompay.kg`. Секрет и merchant_id у каждой страны свои.
3. Логика ответа на result URL:
   - `pg_result=1`, заказ валиден, сумма совпала → `ok`, отметить оплату.
   - `pg_result=1`, но заказ уже оплачен иначе, отменён или сумма не та:
     - если `pg_can_reject=1` → `rejected` и понятный `pg_description`;
     - если `pg_can_reject=0` → `ok`, пометить «нужен ручной возврат» и уведомить продавца.
   - `pg_result=0` → `ok` (получение подтверждаем), заказ отметить неоплаченным.
4. Сохранять отправленный ответ по `pg_payment_id` и на повтор отдавать **его же** байт в байт.
5. Ответ подписывать: `pg_salt` + `pg_sig`. Имя скрипта в подписи — последний сегмент пути нашего result URL.
   - ⚠ Это правило из старой доки PayBox, в выдержках этой сессии не подтверждено. Проверить одним тестовым платежом.

---

## 6. lava.top: `periodicity` из оффера

Источник: https://gate.lava.top/docs/documentation.yaml (OpenAPI 1.22.0).

### Что выяснено

- У оффера есть `prices[]`, и у каждой цены — `amount`, `currency`, **`periodicity`**: `ONE_TIME`, `MONTHLY`, `PERIOD_90_DAYS`, `PERIOD_180_DAYS`, `PERIOD_YEAR`.
- `GET /api/v2/products?showAllSubscriptionPeriods=true` показывает цены с периодом больше месяца. По умолчанию их скрывают.

### Решение

1. Не вычислять период из числа дней.
2. При настройке тарифа продавец выбирает оффер. Мы сохраняем `offerId` + `currency` + `periodicity` прямо из `prices[]` этого оффера.
3. При создании счёта передавать сохранённый `periodicity`.
4. Перед созданием проверять, что у оффера есть цена с такой парой `currency + periodicity`. Если нет — ошибка «у оффера нет цены за этот период», без молчаливой подмены на MONTHLY.
5. Отмену подписки делать через `DELETE /api/v1/subscriptions?contractId=<parentContractId>&email=…` (204 — отменена, 404 — уже нет).

---

## 7. LiqPay: `subscribed`, `regular`, 90 дней, `sandbox`

Источники:
- https://www.liqpay.ua/documentation/en/api/callback
- `/api/aquiring/checkout/doc`

### Что выяснено

- `subscribe_periodicity` в официальной доке: только **`month`** и **`year`**. Периода 90 дней нет.
- `action` в callback: `subscribe` (оформление), **`regular` (регулярное списание)**, `pay`, `hold` и др.
- Статусы:
  - `subscribed` — подписка оформлена;
  - `unsubscribed` — подписка деактивирована;
  - `success` — успешный платёж;
  - `failure` / `error` — неуспех;
  - `reversed` — возврат;
  - `sandbox` — тестовый платёж.

### Решение

1. **90 дней не округлять до месяца**: это списание в 3 раза чаще, чем продавец продал. Для LiqPay разрешить только тарифы `month` и `year`, а тариф на 90 или 180 дней при выборе LiqPay блокировать с понятной ошибкой.
2. Обработка callback:
   - `action=subscribe` + `status=subscribed` → подписка активна. Первый платёж считать оплаченным только если по нему пришёл успех; сверить на тестовом платеже, приходит ли отдельный `success`.
   - `action=regular` + `status=success` → продление: продлить доступ на период и сохранить `payment_id` (идемпотентность по `payment_id`).
   - `action=regular` + `failure`/`error` → продление не прошло: уведомить продавца, доступ до конца оплаченного периода.
   - `status=unsubscribed` → подписка отменена.
3. **`sandbox` в боевом режиме не принимать как оплату.**
   - Магазин в боевом режиме + `status=sandbox` → ответить 200, записать в лог, заказ не трогать.
   - `sandbox=1` в запрос добавлять только при `test_mode` магазина.

---

## 8. Processing.kz: единицы суммы, боевой хост, сверка до complete

Официальной документации в открытом доступе нет. Всё ниже из SDK (PHP kolesa-team, Ruby processing_kz).

### Что выяснено

- Тестовый WSDL: `https://test.processing.kz/CNPMerchantWebServices/CNPMerchantWebService.wsdl`. Боевого адреса нет ни в одном открытом источнике.
- Единицы `totalAmount` не установлены.
- В ответе `getTransactionStatus` есть поля `amountRequested`, `amountAuthorized`, `amountRefunded` (по Ruby-гему).
- Статусы: после оплаты `AUTHORISED`, после complete — `PAID`.

### Решение

1. Боевой WSDL и единицы суммы запросить у менеджера Processing.kz. До ответа держать адаптер выключенным для боевых магазинов, только тест.
2. Единицы определить одним тестовым платежом на test-хосте: создать на `100`, посмотреть сумму на платёжной странице (100 ₸ или 1 ₸).
3. **Сверка перед `completeTransaction`:**
   - Вызвать `getTransactionStatus`. Проверить `status == AUTHORISED` и `amountAuthorized == ожидаемой сумме` в тех же единицах.
   - Если всё сходится → `completeTransaction(transactionSuccess=true)`.
   - Если нет → `completeTransaction(transactionSuccess=false)` (снять холд) и пометить заказ.
   - После complete ещё раз проверить, что статус `PAID`.
4. Не вызывать complete по одному возврату клиента на `returnURL`: только после проверки статуса.

---

## 9. CloudPayments: откуда брать токен карты

Источник: https://developers.cloudpayments.ru.

### Ответ

Токен приходит в поле **`Token` Pay-уведомления** (и в ответе API на оплату по криптограмме). Чтобы он вообще был:

1. **Виджет:** параметр `tokenize: true` (или включено принудительное сохранение в ЛК), плюс `userInfo.accountId` — наш ID пользователя.
2. **API:** `SaveCard: true` при включённой настройке «Сохранение токена карты» в ЛК; если там стоит «сохранять принудительно», параметр игнорируется.
3. Сохранять пару `(AccountId, Token)` из Pay-уведомления со статусом `Completed`. Из `Authorized` — только после Confirm.
4. Повторное списание: `POST /payments/tokens/charge` с `Amount`, `AccountId` (тот же), `Token`, `TrInitiatorCode=0` (инициатор — мы), **`PaymentScheduled=1`** для подписки по расписанию.
5. Токен работает **только на том терминале (Public ID), где получен**. При смене терминала продавцом токены пропадают.
6. Альтернатива своему планировщику — подписка CloudPayments (`subscriptions/create` или объект `recurrent` в виджете). Тогда продления приходят уведомлениями **Recurrent** и Pay, и токен нам хранить не нужно.

**Решение:** для подписок на платформе использовать подписки CloudPayments и не хранить токены. Токен брать из Pay только для оплаты в один клик.

---

## Что ещё нужно руками (без этого не закрыть)

1. **Processing.kz** — боевой WSDL и единицы суммы у менеджера.
2. **Freedom Pay** — один тестовый платёж, чтобы проверить имя скрипта в подписи ответа на result URL.
3. **LiqPay** — один тестовый платёж подписки, чтобы увидеть, приходит ли отдельный `success` вместе с `subscribed`.
4. **ЮKassa** — сверить числовые `vat_code` для ставки 22%.
5. **Prodamus** — сохранить первый живой webhook как регрессионный тест подписи.
