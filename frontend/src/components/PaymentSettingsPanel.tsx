import { useEffect, useState } from "react";

import {
  type Order,
  type OrdersReport,
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

/** One line per provider, so choosing does not require having integrated one
 * before. The full `hint` only appears after the tile is clicked. */
const SHORT: Record<string, string> = {
  stars: "цифровые товары в Telegram",
  yookassa: "карты РФ · нужно ИП/ООО",
  tbank: "карты РФ и СБП · нужно ИП/ООО",
  cloudpayments: "карты РФ и Казахстана",
  prodamus: "карты РФ · для самозанятых",
  robokassa: "карты РФ и KZT",
  paymaster: "карты РФ",
  lifepay: "СБП и карты РФ · онлайн-касса",
  lavatop: "карты РФ, покупатель платит из-за рубежа",
  freedompay: "Казахстан, Узбекистан, Кыргызстан",
  ioka: "Казахстан · тенге, рубли, доллары",
  processingkz: "Казахстан · через банк-эквайер",
  click: "Узбекистан · Click",
  payme: "Узбекистан · Payme",
  liqpay: "Украина · ПриватБанк",
  stripe: "зарубежные карты · нужна компания вне РФ и РК",
  cryptobot: "USDT, TON · без юрлица",
  link: "любая своя ссылка · подтверждаешь вручную",
  test: "только для проверки сценария",
};

const STATUS_LABEL: Record<Order["status"], string> = {
  paid: "оплачен",
  // Unpaid orders matter as much as paid ones: "ten people opened checkout
  // and nobody paid" is the most useful thing a seller can learn.
  pending: "не оплачен",
  failed: "не прошёл",
  refunded: "возврат",
};

/** "1 заказ" / "2 заказа" / "5 заказов" — the two-form version printed
 * "2 заказов". */
function ordersLabel(count: number): string {
  if (count % 10 === 1 && count % 100 !== 11) return `${count} заказ`;
  if ([2, 3, 4].includes(count % 10) && ![12, 13, 14].includes(count % 100)) return `${count} заказа`;
  return `${count} заказов`;
}

function unit(currency: string): string {
  return currency === "XTR" ? "⭐" : currency;
}

function when(iso: string): string {
  const date = new Date(iso);
  return Number.isNaN(date.getTime())
    ? ""
    : date.toLocaleString("ru", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });
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
  const [totals, setTotals] = useState<OrdersReport["totals"]>([]);
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
            .catch(() => ({ orders: [] as Order[], totals: [], paid_count: 0, paid_total_minor: 0 })),
        ]);
        setProviders(list.providers);
        setSettings(current);
        setSlug(current.provider ?? "");
        setIsTest(current.is_test);
        setOrders(sales.orders);
        setTotals(sales.totals ?? []);
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
      setTotals(refreshed.totals ?? []);
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
                      className={`payment-settings__provider ${slug === provider.slug ? "payment-settings__provider--active" : ""}${
                        provider.slug === "test" ? " payment-settings__provider--test" : ""
                      }`}
                      onClick={() => setSlug(provider.slug)}
                    >
                      <span className="payment-settings__provider-title">{provider.title}</span>
                      {SHORT[provider.slug] && (
                        <span className="payment-settings__provider-note">{SHORT[provider.slug]}</span>
                      )}
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
                          {formatAmount(order.amount_minor)} {unit(order.currency)}
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
                          onClick={() => {
                            if (window.confirm(`Отклонить заказ №${order.invoice_no}? Покупателю придёт сообщение, что оплату не видно.`)) {
                              decide(order, false);
                            }
                          }}
                        >
                          Не пришло
                        </button>
                      </div>
                    </div>
                  ))}
                </div>
              )}

              {(totals.length > 0 || orders.length > 0) && (
                <div className="orders orders--summary">
                  <span className="buttons-editor__field-label">Продажи</span>

                  {totals.length === 0 ? (
                    <p className="orders__lead">
                      Оплаченных заказов пока нет. Здесь появятся все продажи этого бота.
                    </p>
                  ) : (
                    <div className="orders__totals">
                      {totals.map((total) => (
                        <span className="orders__total" key={total.currency}>
                          <span className="orders__total-value">
                            {formatAmount(total.total_minor)} {unit(total.currency)}
                          </span>
                          <span className="orders__total-label">{ordersLabel(total.count)}</span>
                        </span>
                      ))}
                    </div>
                  )}

                  <ul className="orders__log">
                    {orders.slice(0, 12).map((order) => (
                      <li className={`orders__log-row orders__log-row--${order.status}`} key={order.id}>
                        <span className="orders__log-main">
                          <span className="orders__log-title">
                            №{order.invoice_no} · {order.description}
                          </span>
                          <span className="orders__log-meta">
                            {STATUS_LABEL[order.status]} · {when(order.paid_at ?? order.created_at)}
                          </span>
                        </span>
                        <span className="orders__log-amount">
                          {formatAmount(order.amount_minor)} {unit(order.currency)}
                        </span>
                      </li>
                    ))}
                  </ul>
                </div>
              )}

            </>
          )}
        </div>
      </div>
    </>
  );
}
