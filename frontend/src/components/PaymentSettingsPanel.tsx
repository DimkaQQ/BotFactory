import { useEffect, useState } from "react";

import {
  type Order,
  type PaymentProviderInfo,
  type PaymentSettings,
  ApiError,
  builderApi,
  formatAmount,
} from "../api/builderApi";
import { useEscape } from "../hooks/useEscape";

interface Props {
  botId: string;
  onClose: () => void;
  onSaved: (settings: PaymentSettings) => void;
}

/** Per-bot payment provider setup. The form is rendered from whatever
 * GET /payments/providers returns, so adding a provider on the backend
 * makes it appear here with no frontend change. */
export function PaymentSettingsPanel({ botId, onClose, onSaved }: Props) {
  useEscape(onClose);

  const [providers, setProviders] = useState<PaymentProviderInfo[] | null>(null);
  const [settings, setSettings] = useState<PaymentSettings | null>(null);
  const [slug, setSlug] = useState<string>("");
  const [isTest, setIsTest] = useState(true);
  const [values, setValues] = useState<Record<string, string>>({});
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [orders, setOrders] = useState<Order[]>([]);
  const [sales, setSales] = useState<{ count: number; totalMinor: number } | null>(null);
  const [busyOrder, setBusyOrder] = useState<string | null>(null);

  useEffect(() => {
    (async () => {
      try {
        const [list, current, sales] = await Promise.all([
          builderApi.listPaymentProviders(),
          builderApi.getPaymentSettings(botId),
          // A bot with no sales yet is the normal case, so a failure here
          // must not take the settings form down with it.
          builderApi
            .listOrders(botId)
            .catch(() => ({ orders: [] as Order[], paid_count: 0, paid_total_minor: 0 })),
        ]);
        setProviders(list.providers);
        setSettings(current);
        setSlug(current.provider ?? "");
        setIsTest(current.is_test);
        setOrders(sales.orders);
        if ("paid_count" in sales) {
          setSales({ count: sales.paid_count, totalMinor: sales.paid_total_minor });
        }
      } catch (err) {
        setError(err instanceof ApiError ? err.message : "Не удалось загрузить настройки оплаты");
      }
    })();
  }, [botId]);

  const active = providers?.find((p) => p.slug === slug) ?? null;
  // Orders where the buyer says they paid on a provider nothing can verify —
  // these are stuck until the owner says yes or no, so they go on top.
  const awaiting = orders.filter((o) => o.needs_confirmation);

  async function decide(order: Order, confirmed: boolean) {
    setBusyOrder(order.id);
    setError(null);
    try {
      if (confirmed) {
        await builderApi.confirmOrder(botId, order.id);
      } else {
        await builderApi.rejectOrder(botId, order.id);
      }
      const refreshed = await builderApi.listOrders(botId);
      setOrders(refreshed.orders);
      setSales({ count: refreshed.paid_count, totalMinor: refreshed.paid_total_minor });
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Не удалось обновить заказ");
    } finally {
      setBusyOrder(null);
    }
  }

  async function handleSave() {
    setSaving(true);
    setError(null);
    try {
      const next = await builderApi.savePaymentSettings(botId, {
        provider: slug || null,
        is_test: isTest,
        credentials: values,
      });
      setSettings(next);
      setValues({});
      setSaved(true);
      onSaved(next);
      setTimeout(() => setSaved(false), 2500);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Не удалось сохранить");
    } finally {
      setSaving(false);
    }
  }

  return (
    <>
      <div className="sheet-backdrop edit-panel-backdrop" onClick={onClose} />
      <div className="edit-panel">
        <div className="edit-panel__header">
          <span className="edit-panel__icon block-card__icon--delivery" aria-hidden="true">
            💳
          </span>
          <span className="edit-panel__title">Приём оплаты</span>
          <button type="button" className="edit-panel__close" aria-label="Закрыть" onClick={onClose}>
            ✕
          </button>
        </div>

        <div className="edit-panel__body">
          {providers === null ? (
            <p className="app-hint">Загружаем…</p>
          ) : (
            <>
              <p className="payment-settings__lead">
                Деньги идут напрямую тебе на счёт в платёжной системе — мы только формируем ссылку на оплату и
                ждём подтверждение.
              </p>

              <div className="buttons-editor__field">
                <span className="buttons-editor__field-label">Платёжная система</span>
                <div className="payment-settings__providers">
                  {providers.map((provider) => (
                    <button
                      key={provider.slug}
                      type="button"
                      className={`payment-settings__provider ${slug === provider.slug ? "payment-settings__provider--active" : ""}`}
                      onClick={() => setSlug(provider.slug)}
                    >
                      {provider.title}
                    </button>
                  ))}
                </div>
                <button
                  type="button"
                  className={`payment-settings__none ${slug === "" ? "payment-settings__none--active" : ""}`}
                  onClick={() => setSlug("")}
                >
                  Без оплаты — бот ничего не продаёт
                </button>
              </div>

              {active && (
                <>
                  <p className="payment-settings__hint">{active.hint}</p>

                  {active.fields.map((field) => {
                    const filled = settings?.provider === active.slug && settings.filled_fields.includes(field.key);
                    return (
                      <label key={field.key} className="buttons-editor__field">
                        <span className="buttons-editor__field-label">
                          {field.label}
                          {filled && <span className="payment-settings__filled"> · сохранено</span>}
                        </span>
                        <input
                          className="payment-editor__input"
                          type={field.secret ? "password" : "text"}
                          autoComplete="off"
                          placeholder={filled ? "•••••••• (оставь пустым, чтобы не менять)" : field.hint}
                          value={values[field.key] ?? ""}
                          onChange={(e) => setValues((prev) => ({ ...prev, [field.key]: e.target.value }))}
                        />
                      </label>
                    );
                  })}

                  {active.uses_callback && (
                    <label className="payment-settings__test">
                      <input type="checkbox" checked={isTest} onChange={(e) => setIsTest(e.target.checked)} />
                      <span>
                        Тестовый режим — платежи не настоящие. Сними галочку, когда проверишь сценарий и будешь
                        готов принимать деньги.
                      </span>
                    </label>
                  )}

                  {settings?.callback_url && settings.provider === active.slug && active.uses_callback && (
                    <div className="payment-settings__callback">
                      <span className="buttons-editor__field-label">
                        Этот адрес нужно указать в кабинете платёжной системы как уведомление об оплате
                      </span>
                      <code>{settings.callback_url}</code>
                    </div>
                  )}
                </>
              )}

              {error && <p className="publish-form__error">{error}</p>}

              <button type="button" className="payment-settings__save" onClick={handleSave} disabled={saving}>
                {saving ? "Сохраняем…" : saved ? "✓ Сохранено" : "Сохранить"}
              </button>

              {sales && sales.count > 0 && (
                <div className="orders orders--summary">
                  <span className="buttons-editor__field-label">Продажи</span>
                  <div className="orders__totals">
                    <span className="orders__total-value">{formatAmount(sales.totalMinor)}</span>
                    <span className="orders__total-label">
                      за {sales.count} {sales.count === 1 ? "оплаченный заказ" : "оплаченных заказов"}
                    </span>
                  </div>
                  <ul className="orders__log">
                    {orders
                      .filter((o) => o.status === "paid")
                      .slice(0, 8)
                      .map((order) => (
                        <li className="orders__log-row" key={order.id}>
                          <span className="orders__log-title">
                            №{order.invoice_no} · {order.description}
                          </span>
                          <span className="orders__log-amount">
                            {formatAmount(order.amount_minor)} {order.currency === "XTR" ? "⭐" : order.currency}
                          </span>
                        </li>
                      ))}
                  </ul>
                </div>
              )}

              {awaiting.length > 0 && (
                <div className="orders">
                  <span className="buttons-editor__field-label">Ждут подтверждения</span>
                  <p className="orders__lead">
                    Покупатель нажал «Я оплатил». Проверь, пришли ли деньги — после подтверждения бот сразу
                    выдаст товар.
                  </p>
                  {awaiting.map((order) => (
                    <div className="orders__item" key={order.id}>
                      <div className="orders__info">
                        <span className="orders__title">
                          №{order.invoice_no} · {order.description}
                        </span>
                        <span className="orders__amount">
                          {formatAmount(order.amount_minor)} {order.currency === "XTR" ? "⭐" : order.currency}
                        </span>
                      </div>
                      <div className="orders__actions">
                        <button
                          type="button"
                          className="orders__confirm"
                          disabled={busyOrder === order.id}
                          onClick={() => decide(order, true)}
                        >
                          ✅ Оплачен
                        </button>
                        <button
                          type="button"
                          className="orders__reject"
                          disabled={busyOrder === order.id}
                          onClick={() => decide(order, false)}
                        >
                          ✖️
                        </button>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </>
          )}
        </div>
      </div>
    </>
  );
}
