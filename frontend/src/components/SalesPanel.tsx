import { useEffect, useState } from "react";

import {
  type Order,
  type OrdersReport,
  type SubscribersReport,
  ApiError,
  builderApi,
  formatAmount,
} from "../api/builderApi";
import { confirmDialog } from "../confirm";
import { useEscape } from "../hooks/useEscape";

interface Props {
  botId: string;
  onClose: () => void;
  /** Выручка показана ещё и в шапке конструктора — после возврата или
   * подтверждения она обязана измениться там тоже. */
  onOrdersChanged?: (report: OrdersReport) => void;
}

const SUB_STATUS: Record<string, string> = {
  active: "активна",
  expired: "закончилась",
  cancelled: "отменена",
};

const STATUS_LABEL: Record<Order["status"], string> = {
  paid: "оплачен",
  // Неоплаченные важны не меньше оплаченных: «десять человек открыли счёт и
  // никто не заплатил» — самое полезное, что продавец может тут узнать.
  pending: "не оплачен",
  failed: "не прошёл",
  refunded: "возврат",
};

/** «1 заказ» / «2 заказа» / «5 заказов». */
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

/** Продажи бота: заказы, ожидающие подтверждения, выручка, подписки.
 *
 * Своим экраном, а не разделом в настройках кассы: попасть сюда можно было
 * только через кнопку «Приём оплаты», проскроллив семнадцать плиток
 * платёжных систем. Настройки кассы трогают один раз, а продажи смотрят
 * каждый день.
 */
export function SalesPanel({ botId, onClose, onOrdersChanged }: Props) {
  useEscape(onClose);
  const [orders, setOrders] = useState<Order[] | null>(null);
  const [totals, setTotals] = useState<OrdersReport["totals"]>([]);
  const [subs, setSubs] = useState<SubscribersReport | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [busyOrder, setBusyOrder] = useState<string | null>(null);

  useEffect(() => {
    (async () => {
      try {
        const [sales, audience] = await Promise.all([
          builderApi.listOrders(botId),
          // Бот без подписчиков — обычное дело в первый день, и это не
          // повод не показать заказы.
          builderApi
            .listSubscribers(botId)
            .catch(() => ({ subscriptions: [], people: [], active_count: 0 }) as SubscribersReport),
        ]);
        setOrders(sales.orders);
        setTotals(sales.totals ?? []);
        setSubs(audience);
      } catch (err) {
        setError(err instanceof ApiError ? err.message : "Не удалось загрузить продажи");
        setOrders([]);
      }
    })();
  }, [botId]);

  async function refreshOrders() {
    const refreshed = await builderApi.listOrders(botId);
    setOrders(refreshed.orders);
    setTotals(refreshed.totals ?? []);
    onOrdersChanged?.(refreshed);
  }

  async function decide(order: Order, confirmed: boolean) {
    setBusyOrder(order.id);
    setError(null);
    try {
      if (confirmed) {
        await builderApi.confirmOrder(botId, order.id);
      } else {
        await builderApi.rejectOrder(botId, order.id);
      }
      await refreshOrders();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Не удалось обновить заказ");
    } finally {
      setBusyOrder(null);
    }
  }

  async function refund(order: Order) {
    setBusyOrder(order.id);
    setError(null);
    try {
      await builderApi.refundOrder(botId, order.id);
      await refreshOrders();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Не удалось оформить возврат");
    } finally {
      setBusyOrder(null);
    }
  }

  async function redeliver(order: Order) {
    setBusyOrder(order.id);
    setError(null);
    setNotice(null);
    try {
      await builderApi.redeliverOrder(botId, order.id);
      // Выдача уходит фоном, с настоящими паузами между сообщениями —
      // ответ «готово» здесь означал бы не то, что случилось.
      setNotice(
        `Заказ №${order.invoice_no} отправляем заново. Через минуту обнови экран: ` +
          `если пометка «товар не выдан» осталась, значит выдача снова не прошла.`,
      );
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Не удалось отправить заново");
    } finally {
      setBusyOrder(null);
    }
  }

  // Заказы, где покупатель говорит, что заплатил, а проверить это некому —
  // они висят, пока владелец не скажет да или нет. Поэтому наверх.
  const awaiting = (orders ?? []).filter((o) => o.needs_confirmation);

  return (
    <>
      <div className="sheet-backdrop edit-panel-backdrop" onClick={onClose} />
      <div className="edit-panel">
        <div className="edit-panel__header">
          <span className="edit-panel__icon block-card__icon--payment" aria-hidden="true">
            💰
          </span>
          <span className="edit-panel__title">Продажи</span>
          <button type="button" className="edit-panel__close" aria-label="Закрыть" onClick={onClose}>
            ✕
          </button>
        </div>

        <div className="edit-panel__body">
          {orders === null ? (
            <p className="app-hint">Загружаем…</p>
          ) : (
            <>
              {error && <p className="publish-form__error">{error}</p>}
              {notice && <p className="orders__notice">{notice}</p>}
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
                    {order.buyer && (
                      <span className="orders__buyer">
                        {order.buyer.username ? (
                          <a
                            href={`https://t.me/${order.buyer.username}`}
                            target="_blank"
                            rel="noreferrer"
                          >
                            {order.buyer.title}
                          </a>
                        ) : (
                          order.buyer.title
                        )}
                      </span>
                    )}
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
                        void confirmDialog(
                          `Отклонить заказ №${order.invoice_no}? Покупателю придёт сообщение, что оплату не видно.`,
                        ).then((ok) => {
                          if (ok) decide(order, false);
                        });
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
              <span className="buttons-editor__field-label">
                Продажи
                {/* Сверять три сотни строк глазами по панели — это тот
                    самый вечер в неделю, ради которого бота и покупают. */}
                <button
                  type="button"
                  className="orders__export"
                  onClick={() => {
                    void builderApi
                      .downloadOrdersCsv(botId, "prodazhi.csv")
                      .catch((err) =>
                        setError(err instanceof ApiError ? err.message : "Не удалось выгрузить"),
                      );
                  }}
                >
                  ⬇ Выгрузить в таблицу
                </button>
              </span>

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
                        {order.buyer && ` · ${order.buyer.title}`}
                        {/* Оплачено — ещё не значит доставлено, и это
                            единственное место, где продавец может об
                            этом узнать сам. */}
                        {order.status === "paid" && !order.delivered && (
                          <span className="orders__undelivered">
                            {order.delivery_gave_up
                              ? " · ⛔️ товар не выдан"
                              : " · ⏳ товар ещё не доставлен"}
                          </span>
                        )}
                      </span>
                    </span>
                    <span className="orders__log-amount">
                      {formatAmount(order.amount_minor)} {unit(order.currency)}
                    </span>
                    {/* Журнал честно писал «товар не выдан» — и на этом
                        всё: отправить ещё раз было нельзя, оставался
                        только возврат. Почти всегда чинится за минуту:
                        укоротить текст, заменить картинку — и провести
                        выдачу заново. */}
                    {order.status === "paid" && !order.delivered && (
                      <button
                        type="button"
                        className="orders__redeliver"
                        disabled={busyOrder === order.id}
                        title="Отправить покупателю ещё раз"
                        onClick={() => void redeliver(order)}
                      >
                        {busyOrder === order.id ? "…" : "↻"}
                      </button>
                    )}
                    {order.status === "paid" && (
                      <button
                        type="button"
                        className="orders__refund"
                        disabled={busyOrder === order.id}
                        title="Пометить возврат и закрыть доступ"
                        onClick={() => {
                          void confirmDialog(
                            `Оформить возврат по заказу №${order.invoice_no}?\n\n` +
                              `Деньги вернёшь сам в кабинете кассы — через нас они не проходили. ` +
                              `Бот пометит заказ возвращённым, скажет покупателю и закроет доступ ` +
                              `в закрытый чат, если он выдавался.`,
                            "Оформить возврат",
                          ).then((ok) => {
                            if (ok) void refund(order);
                          });
                        }}
                      >
                        ↩︎
                      </button>
                    )}
                  </li>
                ))}
              </ul>
            </div>
          )}

          {subs && subs.subscriptions.length > 0 && (
            <div className="orders orders--subs">
              <span className="buttons-editor__field-label">
                Подписки · активных: {subs.active_count}
              </span>
              <ul className="orders__log">
                {subs.subscriptions.slice(0, 20).map((sub) => (
                  <li className={`orders__log-row orders__log-row--${sub.status}`} key={sub.id}>
                    <span className="orders__log-main">
                      <span className="orders__log-title">
                        {sub.buyer?.username ? (
                          <a href={`https://t.me/${sub.buyer.username}`} target="_blank" rel="noreferrer">
                            {sub.buyer.title}
                          </a>
                        ) : (
                          (sub.buyer?.title ?? `id ${sub.telegram_user_id}`)
                        )}
                        {" · "}
                        {sub.title}
                      </span>
                      <span className="orders__log-meta">
                        {SUB_STATUS[sub.status]}
                        {sub.status === "active" && ` до ${when(sub.current_period_end)}`}
                        {" · "}
                        {sub.periods_paid === 1 ? "1-й период" : `${sub.periods_paid}-й период`}
                        {" · "}
                        {sub.billing_mode === "auto" ? "списывает Telegram" : "по счёту"}
                      </span>
                    </span>
                    <span className="orders__log-amount">
                      {formatAmount(sub.amount_minor)} {unit(sub.currency)}
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
