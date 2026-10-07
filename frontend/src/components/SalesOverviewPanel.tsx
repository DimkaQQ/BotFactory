import { useEffect, useMemo, useState } from "react";

import {
  type Bot,
  type ButtonStats,
  type Order,
  ApiError,
  builderApi,
  currencyUnit as unit,
  formatAmount,
} from "../api/builderApi";
import { useDraggablePanel } from "../hooks/useDraggablePanel";
import { useEscape } from "../hooks/useEscape";
import { plural } from "../plural";

interface Props {
  bots: Bot[];
  onClose: () => void;
}

type Tab = "sales" | "clicks";
type Row = Order & { botName: string };
type ClickRow = ButtonStats["buttons"][number] & { botName: string };

const STATUS: Record<Order["status"], string> = {
  paid: "оплачен",
  pending: "не оплачен",
  failed: "не прошёл",
  refunded: "возврат",
};

function when(iso: string): string {
  const date = new Date(iso);
  return Number.isNaN(date.getTime())
    ? ""
    : date.toLocaleString("ru", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });
}

/** Продажи и нажатия по всем ботам сразу — с выбором одного бота. */
export function SalesOverviewPanel({ bots, onClose }: Props) {
  useEscape(onClose);
  const { panelRef, handleProps: dragProps } = useDraggablePanel();
  const [tab, setTab] = useState<Tab>("sales");
  const [botId, setBotId] = useState<string>("all");
  const [days, setDays] = useState(30);
  const [orders, setOrders] = useState<Row[] | null>(null);
  const [clicks, setClicks] = useState<ClickRow[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  const selected = useMemo(() => (botId === "all" ? bots : bots.filter((b) => b.id === botId)), [bots, botId]);
  const nameOf = (b: Bot) => b.name || (b.telegram_bot_username ? `@${b.telegram_bot_username}` : "Без названия");

  useEffect(() => {
    let cancelled = false;
    setOrders(null);
    setClicks(null);
    setError(null);
    (async () => {
      try {
        const [orderReports, clickReports] = await Promise.all([
          Promise.all(selected.map((b) => builderApi.listOrders(b.id))),
          Promise.all(selected.map((b) => builderApi.buttonStats(b.id, days))),
        ]);
        if (cancelled) return;
        setOrders(
          orderReports
            .flatMap((report, i) => report.orders.map((o) => ({ ...o, botName: nameOf(selected[i]) })))
            .sort((a, b) => (a.created_at < b.created_at ? 1 : -1)),
        );
        setClicks(
          clickReports
            .flatMap((report, i) => report.buttons.map((c) => ({ ...c, botName: nameOf(selected[i]) })))
            .sort((a, b) => b.clicks - a.clicks),
        );
      } catch (err) {
        if (!cancelled) setError(err instanceof ApiError ? err.message : "Не удалось загрузить данные");
      }
    })();
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [botId, days, bots]);

  const totals = useMemo(() => {
    const byCurrency = new Map<string, { count: number; total: number }>();
    for (const o of orders ?? []) {
      if (o.status !== "paid") continue;
      const cur = byCurrency.get(o.currency) ?? { count: 0, total: 0 };
      byCurrency.set(o.currency, { count: cur.count + 1, total: cur.total + o.amount_minor });
    }
    return [...byCurrency.entries()];
  }, [orders]);

  const maxClicks = Math.max(1, ...(clicks ?? []).map((c) => c.clicks));

  return (
    <>
      <div className="sheet-backdrop edit-panel-backdrop" onClick={onClose} />
      <div className="edit-panel overview-panel" ref={panelRef}>
        <div
          className="edit-panel__header"
          title="Потяни, чтобы переместить окно (двойной щелчок — вернуть на место)"
          {...dragProps}
        >
          <span className="edit-panel__icon block-card__icon--success" aria-hidden="true">
            💰
          </span>
          <span className="edit-panel__title">Продажи и кнопки</span>
          <button type="button" className="edit-panel__close" aria-label="Закрыть" onClick={onClose}>
            ✕
          </button>
        </div>
        <div className="edit-panel__body">
          <div className="overview-panel__filters">
            <label className="overview-panel__filter">
              <span className="buttons-editor__field-label">Бот</span>
              <select className="payment-editor__input" value={botId} onChange={(e) => setBotId(e.target.value)}>
                <option value="all">Все боты ({bots.length})</option>
                {bots.map((b) => (
                  <option key={b.id} value={b.id}>
                    {nameOf(b)}
                  </option>
                ))}
              </select>
            </label>
            {tab === "clicks" && (
              <label className="overview-panel__filter">
                <span className="buttons-editor__field-label">Период</span>
                <select
                  className="payment-editor__input"
                  value={days}
                  onChange={(e) => setDays(Number(e.target.value))}
                >
                  <option value={7}>7 дней</option>
                  <option value={30}>30 дней</option>
                  <option value={90}>90 дней</option>
                </select>
              </label>
            )}
          </div>

          <div className="payment-settings__modes" role="tablist" aria-label="Раздел">
            <button
              type="button"
              role="tab"
              aria-selected={tab === "sales"}
              className={`payment-settings__mode${tab === "sales" ? " payment-settings__mode--active" : ""}`}
              onClick={() => setTab("sales")}
            >
              <strong>💰 Продажи</strong>
              <span>Заказы и выручка</span>
            </button>
            <button
              type="button"
              role="tab"
              aria-selected={tab === "clicks"}
              className={`payment-settings__mode${tab === "clicks" ? " payment-settings__mode--active" : ""}`}
              onClick={() => setTab("clicks")}
            >
              <strong>👆 Нажатия кнопок</strong>
              <span>Что выбирают чаще</span>
            </button>
          </div>

          {error && <p className="publish-form__error">{error}</p>}
          {!error && (orders === null || clicks === null) && <p className="app-hint">Загружаем…</p>}

          {tab === "sales" && orders !== null && (
            <div className="overview-panel__list">
              {totals.length > 0 && (
                <p className="overview-panel__totals">
                  {totals.map(([cur, v]) => `${v.count} · ${formatAmount(v.total)} ${unit(cur)}`).join("   ")}
                </p>
              )}
              {orders.length === 0 && <p className="app-hint">Заказов пока нет.</p>}
              {orders.slice(0, 100).map((o) => (
                <div className="overview-panel__row" key={o.id}>
                  <div className="overview-panel__main">
                    <strong>
                      №{o.invoice_no} · {o.description}
                    </strong>
                    <span className="overview-panel__sub">
                      {o.botName}
                      {o.buyer ? ` · ${o.buyer.title}` : ""} · {when(o.created_at)}
                    </span>
                    {o.choices && o.choices.length > 0 && (
                      <span className="orders__choices">Выбрал: {o.choices.join(" · ")}</span>
                    )}
                  </div>
                  <div className="overview-panel__side">
                    <span>
                      {formatAmount(o.amount_minor)} {unit(o.currency)}
                    </span>
                    <span className={`overview-panel__status overview-panel__status--${o.status}`}>
                      {STATUS[o.status]}
                    </span>
                  </div>
                </div>
              ))}
            </div>
          )}

          {tab === "clicks" && clicks !== null && (
            <div className="overview-panel__list">
              {clicks.length === 0 && (
                <p className="app-hint">За этот период нажатий пока нет. Они появятся, когда покупатели начнут нажимать кнопки.</p>
              )}
              {clicks.map((c, i) => (
                <div className="overview-panel__row overview-panel__row--click" key={`${c.block_id}-${c.label}-${i}`}>
                  <div className="overview-panel__main">
                    <strong>{c.label}</strong>
                    <span className="overview-panel__sub">
                      {c.botName} · «{c.block}»
                    </span>
                    <span className="overview-panel__bar">
                      <span style={{ width: `${Math.round((c.clicks / maxClicks) * 100)}%` }} />
                    </span>
                  </div>
                  <div className="overview-panel__side">
                    <span>{c.clicks} {plural(c.clicks, ["нажатие", "нажатия", "нажатий"])}</span>
                    <span className="overview-panel__sub">{c.people} чел.</span>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </>
  );
}
