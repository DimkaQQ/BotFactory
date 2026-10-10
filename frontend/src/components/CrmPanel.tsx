import { useCallback, useEffect, useRef, useState } from "react";

import {
  type Bot,
  type CalendarSlot,
  type CalendarView,
  type CrmCard,
  type CrmCustomer,
  type BlockContent,
  ApiError,
  builderApi,
  currencyUnit as unit,
  formatAmount,
} from "../api/builderApi";
import { ScheduleFields } from "./BookingEditor";
import { confirmDialog } from "../confirm";
import { useDraggablePanel } from "../hooks/useDraggablePanel";
import { useEscape } from "../hooks/useEscape";
import { plural } from "../plural";
import { UsersThree, X } from "@phosphor-icons/react";
import { CalendarCheck, CaretDown, CaretUp, GearSix, Prohibit } from "@phosphor-icons/react";


interface Props {
  bots: Bot[];
  onClose: () => void;
}

type Tab = "clients" | "calendar";

const STATE_LABEL: Record<CalendarSlot["state"], string> = {
  free: "свободно",
  past: "прошло",
  held: "ждёт оплаты",
  confirmed: "занято",
  blocked: "закрыто",
  cancelled: "отменено",
};

function shortDate(iso: string): string {
  const date = new Date(iso);
  return Number.isNaN(date.getTime()) ? "" : date.toLocaleDateString("ru", { day: "numeric", month: "short" });
}

function todayIso(): string {
  const now = new Date();
  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}-${String(now.getDate()).padStart(2, "0")}`;
}

function addDays(iso: string, days: number): string {
  const [y, m, d] = iso.split("-").map(Number);
  const date = new Date(y, m - 1, d + days);
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}-${String(date.getDate()).padStart(2, "0")}`;
}

/** Мини-CRM и календарь записи: клиенты всех ботов и расписание одного бота. */
export function CrmPanel({ bots, onClose }: Props) {
  useEscape(onClose);
  const { panelRef, handleProps: dragProps } = useDraggablePanel();
  const [tab, setTab] = useState<Tab>("clients");

  return (
    <>
      <div className="sheet-backdrop edit-panel-backdrop" onClick={onClose} />
      <div className="edit-panel overview-panel crm-panel" ref={panelRef}>
        <div
          className="edit-panel__header"
          title="Потяни, чтобы переместить окно (двойной щелчок, вернуть на место)"
          {...dragProps}
        >
          <span className="edit-panel__icon block-card__icon--poll" aria-hidden="true">
            <UsersThree size={20} aria-hidden="true" />
          </span>
          <span className="edit-panel__title">Клиенты и записи</span>
          <button type="button" className="edit-panel__close" aria-label="Закрыть" onClick={onClose}>
            <X size={18} aria-hidden="true" />
          </button>
        </div>
        <div className="edit-panel__body">
          <div className="payment-settings__modes" role="tablist" aria-label="Раздел">
            <button
              type="button"
              role="tab"
              aria-selected={tab === "clients"}
              className={`payment-settings__mode${tab === "clients" ? " payment-settings__mode--active" : ""}`}
              onClick={() => setTab("clients")}
            >
              <strong><UsersThree size={15} className="inline-icon" aria-hidden="true" /> Клиенты</strong>
              <span>Контакты и история</span>
            </button>
            <button
              type="button"
              role="tab"
              aria-selected={tab === "calendar"}
              className={`payment-settings__mode${tab === "calendar" ? " payment-settings__mode--active" : ""}`}
              onClick={() => setTab("calendar")}
            >
              <strong><CalendarCheck size={15} className="inline-icon" aria-hidden="true" /> Календарь</strong>
              <span>Записи по дням</span>
            </button>
          </div>
          {tab === "clients" ? <ClientsTab bots={bots} /> : <CalendarTab bots={bots} />}
        </div>
      </div>
    </>
  );
}

function ClientsTab({ bots }: { bots: Bot[] }) {
  const [botId, setBotId] = useState("all");
  const [q, setQ] = useState("");
  const [rows, setRows] = useState<CrmCustomer[] | null>(null);
  const [open, setOpen] = useState<{ botId: string; userId: number } | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    const timer = setTimeout(async () => {
      try {
        const res = await builderApi.crmCustomers({ botId: botId === "all" ? undefined : botId, q });
        if (!cancelled) {
          setRows(res.customers);
          setError(null);
        }
      } catch (err) {
        if (!cancelled) setError(err instanceof ApiError ? err.message : "Не удалось загрузить клиентов");
      }
    }, 250);
    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [botId, q]);

  if (open) {
    return <CustomerCard botId={open.botId} userId={open.userId} onBack={() => setOpen(null)} />;
  }

  return (
    <div className="overview-panel__list">
      <div className="overview-panel__filters">
        <label className="overview-panel__filter">
          <span className="buttons-editor__field-label">Бот</span>
          <select className="payment-editor__input" value={botId} onChange={(e) => setBotId(e.target.value)}>
            <option value="all">Все боты ({bots.length})</option>
            {bots.map((b) => (
              <option key={b.id} value={b.id}>
                {b.name || (b.telegram_bot_username ? `@${b.telegram_bot_username}` : "Без названия")}
              </option>
            ))}
          </select>
        </label>
        <label className="overview-panel__filter">
          <span className="buttons-editor__field-label">Поиск</span>
          <input
            className="payment-editor__input"
            placeholder="имя, @username, телефон"
            value={q}
            onChange={(e) => setQ(e.target.value)}
          />
        </label>
      </div>
      {error && <p className="publish-form__error">{error}</p>}
      {rows === null && !error && <p className="app-hint">Загружаем…</p>}
      {rows?.length === 0 && (
        <p className="app-hint">Пока никого нет. Клиенты появляются, когда пишут твоему боту.</p>
      )}
      {rows?.map((c) => (
        <button
          type="button"
          key={`${c.bot_id}-${c.telegram_user_id}`}
          className="overview-panel__row crm-row"
          onClick={() => setOpen({ botId: c.bot_id, userId: c.telegram_user_id })}
        >
          <div className="overview-panel__main">
            <strong>{c.name}</strong>
            <span className="overview-panel__sub">
              {c.username ? `@${c.username} · ` : ""}
              {c.phone || "телефон не оставлен"} · {c.bot_name}
            </span>
          </div>
          <div className="overview-panel__side">
            <span>{c.bookings ? `${c.bookings} ${plural(c.bookings, ["запись", "записи", "записей"])}` : ""}</span>
            <span className="overview-panel__sub">
              {(c.orders ?? []).map((o) => `${formatAmount(o.total_minor)} ${unit(o.currency)}`).join(" · ")}
            </span>
          </div>
        </button>
      ))}
    </div>
  );
}

function CustomerCard({ botId, userId, onBack }: { botId: string; userId: number; onBack: () => void }) {
  const [card, setCard] = useState<CrmCard | null>(null);
  const [name, setName] = useState("");
  const [phone, setPhone] = useState("");
  const [note, setNote] = useState("");
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    (async () => {
      try {
        const data = await builderApi.crmCustomer(botId, userId);
        setCard(data);
        setName(data.name);
        setPhone(data.phone);
        setNote(data.note);
      } catch (err) {
        setError(err instanceof ApiError ? err.message : "Не удалось загрузить клиента");
      }
    })();
  }, [botId, userId]);

  async function save() {
    try {
      await builderApi.crmUpdateCustomer(botId, userId, { contact_name: name, phone, note });
      setSaved(true);
      setTimeout(() => setSaved(false), 2000);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Не удалось сохранить");
    }
  }

  return (
    <div className="overview-panel__list">
      <button type="button" className="back-link" onClick={onBack}>
        ← Все клиенты
      </button>
      {error && <p className="publish-form__error">{error}</p>}
      {!card && !error && <p className="app-hint">Загружаем…</p>}
      {card && (
        <>
          <p className="overview-panel__sub">
            {card.bot_name} · {card.username ? (
              <a href={`https://t.me/${card.username}`} target="_blank" rel="noreferrer">
                @{card.username}
              </a>
            ) : (
              `id ${card.telegram_user_id}`
            )}{" "}
            · впервые {shortDate(card.first_seen_at)}
          </p>
          <label className="buttons-editor__field">
            <span className="buttons-editor__field-label">Имя</span>
            <input className="payment-editor__input" value={name} onChange={(e) => setName(e.target.value)} />
          </label>
          <label className="buttons-editor__field">
            <span className="buttons-editor__field-label">Телефон</span>
            <input className="payment-editor__input" value={phone} onChange={(e) => setPhone(e.target.value)} />
          </label>
          <label className="buttons-editor__field">
            <span className="buttons-editor__field-label">Заметка (видишь только ты)</span>
            <textarea
              className="chat-bubble__textarea edit-panel__textarea"
              rows={3}
              value={note}
              onChange={(e) => setNote(e.target.value)}
            />
          </label>
          <button type="button" className="payment-settings__save" onClick={save}>
            {saved ? "Сохранено" : "Сохранить"}
          </button>

          <p className="edit-panel__section-label">Записи</p>
          {card.bookings.length === 0 && <p className="app-hint">Записей нет.</p>}
          {card.bookings.map((b) => (
            <div className="overview-panel__row" key={b.id}>
              <strong>{b.label}</strong>
              <span className="overview-panel__sub">{b.status === "confirmed" ? "подтверждена" : b.status === "held" ? "ждёт оплаты" : "отменена"}</span>
            </div>
          ))}

          <p className="edit-panel__section-label">Заказы</p>
          {card.orders.length === 0 && <p className="app-hint">Заказов нет.</p>}
          {card.orders.map((o) => (
            <div className="overview-panel__row" key={o.id}>
              <div className="overview-panel__main">
                <strong>
                  №{o.invoice_no} · {o.description}
                </strong>
                {o.choices.length > 0 && <span className="orders__choices">Выбрал: {o.choices.join(" · ")}</span>}
              </div>
              <div className="overview-panel__side">
                <span>
                  {formatAmount(o.amount_minor)} {unit(o.currency)}
                </span>
                <span className="overview-panel__sub">{o.status === "paid" ? "оплачен" : "не оплачен"}</span>
              </div>
            </div>
          ))}
        </>
      )}
    </div>
  );
}

function CalendarTab({ bots }: { bots: Bot[] }) {
  const [botId, setBotId] = useState(bots[0]?.id ?? "");
  const [start, setStart] = useState(todayIso());
  const [view, setView] = useState<CalendarView | null>(null);
  const [selected, setSelected] = useState<CalendarSlot | null>(null);
  const [error, setError] = useState<string | null>(null);
  // Расписание из блока «Запись»: правится здесь же, без похода в сценарий.
  const [schedule, setSchedule] = useState<BlockContent | null>(null);
  const [hasBlock, setHasBlock] = useState(true);
  const [editing, setEditing] = useState(false);
  const [savedAt, setSavedAt] = useState(false);

  // Ответ запоздавшего запроса (быстро сменили бот или неделю) не должен затирать свежий.
  const latest = useRef(0);
  const load = useCallback(async () => {
    if (!botId) return;
    const ticket = ++latest.current;
    try {
      const data = await builderApi.calendar(botId, start, 7);
      if (ticket !== latest.current) return;
      setView(data);
      setError(null);
    } catch (err) {
      if (ticket !== latest.current) return;
      setError(err instanceof ApiError ? err.message : "Не удалось загрузить календарь");
    }
  }, [botId, start]);

  const loadSchedule = useCallback(async () => {
    if (!botId) return;
    try {
      const res = await builderApi.getBookingSchedule(botId);
      setHasBlock(res.configured);
      setSchedule(res.configured ? (res as BlockContent) : null);
    } catch {
      setSchedule(null);
    }
  }, [botId]);

  async function saveSchedule(next: BlockContent) {
    try {
      const res = await builderApi.saveBookingSchedule(botId, next);
      setSchedule(res.configured ? (res as BlockContent) : null);
      setSavedAt(true);
      setTimeout(() => setSavedAt(false), 2000);
      await load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Не удалось сохранить расписание");
    }
  }

  function toggleDay(date: string, closed: boolean) {
    if (!schedule) return;
    const exceptions = { ...(schedule.exceptions ?? {}) };
    if (closed) delete exceptions[date];
    else exceptions[date] = [];
    void saveSchedule({ ...schedule, exceptions });
  }

  useEffect(() => {
    setView(null);
    setSelected(null);
    void load();
  }, [load]);

  useEffect(() => {
    setEditing(false);
    void loadSchedule();
  }, [loadSchedule]);

  async function act(fn: () => Promise<unknown>) {
    try {
      await fn();
      setSelected(null);
      await load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Не получилось");
    }
  }

  return (
    <div className="overview-panel__list">
      <div className="overview-panel__filters">
        <label className="overview-panel__filter">
          <span className="buttons-editor__field-label">Бот</span>
          <select className="payment-editor__input" value={botId} onChange={(e) => setBotId(e.target.value)}>
            {bots.map((b) => (
              <option key={b.id} value={b.id}>
                {b.name || (b.telegram_bot_username ? `@${b.telegram_bot_username}` : "Без названия")}
              </option>
            ))}
          </select>
        </label>
        <div className="calendar__nav">
          <button type="button" onClick={() => setStart(addDays(start, -7))} aria-label="Неделей раньше">
            ←
          </button>
          <button type="button" onClick={() => setStart(todayIso())}>
            Сегодня
          </button>
          <button type="button" onClick={() => setStart(addDays(start, 7))} aria-label="Неделей позже">
            →
          </button>
        </div>
      </div>
      {error && <p className="publish-form__error">{error}</p>}
      {hasBlock && schedule && (
        <div className="calendar__schedule">
          <button type="button" className="calendar__schedule-toggle" onClick={() => setEditing(!editing)} aria-expanded={editing}>
            <GearSix size={15} className="inline-icon" aria-hidden="true" /> Расписание: дни, часы, перерывы, часовой пояс {editing ? <CaretUp size={13} className="inline-icon" aria-hidden="true" /> : <CaretDown size={13} className="inline-icon" aria-hidden="true" />}
          </button>
          {editing && (
            <>
              <ScheduleFields content={schedule} onChange={setSchedule} />
              <button type="button" className="payment-settings__save" onClick={() => void saveSchedule(schedule)}>
                {savedAt ? "Сохранено" : "Сохранить расписание"}
              </button>
            </>
          )}
        </div>
      )}
      {!hasBlock && (
        <p className="app-hint">
          В сценарии этого бота нет блока «Запись». Добавьте его: и здесь появится расписание, которое вы настроите сами.
        </p>
      )}
      {!view && !error && <p className="app-hint">Загружаем…</p>}
      {view && !view.configured && (
        <p className="app-hint">
          В этом боте нет блока «Запись», показано расписание по умолчанию. Добавь блок «Запись» в сценарий и
          настрой дни и часы.
        </p>
      )}
      {view && (
        <p className="overview-panel__sub">
          Время показано в поясе {view.tz}. Нажми на время, чтобы закрыть его или отменить запись.
        </p>
      )}
      {view?.days.map((day) => (
        <div className="calendar__day" key={day.date}>
          <div className="calendar__day-head">
            <strong>{day.label}</strong>
            {schedule && (
              <button
                type="button"
                className="calendar__day-toggle"
                onClick={() => toggleDay(day.date, Boolean((schedule.exceptions ?? {})[day.date]?.length === 0))}
              >
                {(schedule.exceptions ?? {})[day.date]?.length === 0 ? "Открыть день" : "Закрыть день"}
              </button>
            )}
          </div>
          {day.slots.length === 0 && <span className="overview-panel__sub">выходной</span>}
          <div className="calendar__slots">
            {day.slots.map((slot) => (
              <button
                type="button"
                key={slot.starts_at}
                disabled={slot.state === "past"}
                className={`calendar__slot calendar__slot--${slot.state}${selected?.starts_at === slot.starts_at ? " calendar__slot--selected" : ""}`}
                onClick={() => setSelected(slot)}
                title={slot.client ? `${slot.client}${slot.phone ? ", " + slot.phone : ""}` : STATE_LABEL[slot.state]}
              >
                {slot.time}
                {slot.client && <small>{slot.client}</small>}
              </button>
            ))}
          </div>
        </div>
      ))}
      {selected && (
        <div className="calendar__action">
          <strong>
            {selected.time} · {STATE_LABEL[selected.state]}
          </strong>
          {selected.client && (
            <span>
              {selected.client}
              {selected.phone ? ` · ${selected.phone}` : ""}
            </span>
          )}
          {selected.state === "free" && (
            <button type="button" onClick={() => act(() => builderApi.blockSlot(botId, selected.starts_at))}>
              <Prohibit size={15} className="inline-icon" aria-hidden="true" /> Закрыть это время
            </button>
          )}
          {selected.booking_id && (
            <button
              type="button"
              onClick={async () => {
                const ok = await confirmDialog(
                  selected.state === "blocked"
                    ? "Открыть это время для записи?"
                    : "Отменить запись? Клиенту придёт сообщение, время освободится.",
                );
                if (ok) void act(() => builderApi.cancelBooking(botId, selected.booking_id as string));
              }}
            >
              {selected.state === "blocked" ? "Открыть время" : "Отменить запись"}
            </button>
          )}
        </div>
      )}
    </div>
  );
}
