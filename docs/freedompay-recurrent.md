# Freedom Pay: Recurrent (списание по сохранённому профилю)

Источник: официальная OpenAPI-схема, присланная владельцем 5 октября 2026 (Gateway API → Sync API → Purchase → Recurrent).

- `POST /g2g/recurrent`, `multipart/form-data`. Хосты: KZ `https://api.freedompay.kz`, UZ `https://api.freedompay.uz`,
  KG `https://api.freedompay.kg`.
- Обязательные поля: `pg_amount`, `pg_description`, `pg_merchant_id`, `pg_order_id`, `pg_recurring_profile`
  (ID профиля), `pg_salt`, `pg_sig`. Подпись — по общему правилу Overview от последнего сегмента адреса: `recurrent`.
- Ответ (XML): `pg_payment_id`, `pg_status` (`ok`), `pg_recurring_profile`, `pg_datetime`, `pg_salt`, `pg_sig`.
- В схеме не сказано: придёт ли итог списания на `pg_result_url` (мы его передаём) и означает ли `pg_status=ok` деньги
  списаны или платёж создан. Адаптер считает `ok` «создан» (pending) и ждёт уведомления — проверить живьём.
