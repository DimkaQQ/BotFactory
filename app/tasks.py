"""Фоновые задачи сервиса: всё, что должно идти само, без запроса от человека.

Их запускает либо отдельный процесс `python -m app.worker` (боевая сборка),
либо сам api, если `RUN_BACKGROUND=true` (простая установка в один процесс).
Каждая задача безопасна при нескольких запусках одновременно: захват работы
идёт условным UPDATE, поэтому два воркера не сделают одно дело дважды.
"""

from app.services import (
    background,
    bot_registry,
    housekeeping,
    media_gc,
    payment_service,
    platform_billing,
    scheduler,
    subscription_service,
)


def start_background_tasks() -> None:
    # Brings bots published before webhook secrets existed up to date, so the
    # webhook route can refuse anything that arrives without one.
    background.spawn(bot_registry.refresh_all_webhooks(), name="refresh-all-webhooks")
    # Anything a previous run was paid for but never handed over — the
    # provider was already acknowledged, so nothing else would ever retry.
    background.spawn(payment_service.redeliver_undelivered(), name="redeliver-undelivered")
    # And keep looking: a delivery can also fail mid-flight (Telegram 5xx, a
    # rate limit), and until this existed the only retry was the next deploy.
    background.spawn(payment_service.redeliver_forever(), name="redeliver-forever", daemon=True)
    # Conversations that were told to continue later — a long "Пауза", a
    # renewal reminder. Run once at boot before the loop starts, because
    # everything that came due while the process was down is due *now*.
    background.spawn(scheduler.run_due(), name="scheduled-steps-catchup")
    background.spawn(scheduler.run_forever(), name="scheduled-steps", daemon=True)
    # And close out periods that ran out while nobody was watching. Separate
    # from the queue above on purpose: access must end when the period ends
    # even if no step survived to say so.
    background.spawn(subscription_service.expire_due(), name="subscriptions-catchup")
    background.spawn(subscription_service.expire_forever(), name="subscriptions-expiry", daemon=True)
    # What the bot owners owe *us*: remind while a period is running out,
    # take the bot off the air once the grace period has run out too. Same
    # shape as above and for the same reason — a period that ended during a
    # deploy ended, whether or not anything was running to notice.
    # Загруженные файлы, на которые больше никто не ссылается: они
    # переживали и блок, и бота, и клиента, а каталог лежит на том же томе,
    # что и база.
    background.spawn(media_gc.sweep_forever(), name="media-gc", daemon=True)
    # Напоминания о записи за сутки и за 2 часа; уборка старых нажатий кнопок,
    # записей и слепков ключей кассы.
    background.spawn(housekeeping.run_forever(), name="housekeeping", daemon=True)
    background.spawn(platform_billing.sweep_once(), name="billing-catchup")
    background.spawn(platform_billing.sweep_forever(), name="billing-sweep", daemon=True)
