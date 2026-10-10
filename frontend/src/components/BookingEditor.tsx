import type { BlockContent } from "../api/builderApi";
import { type Interval, localTimezone, readWeekly, timezones } from "../booking";
import { X } from "@phosphor-icons/react";

interface Props {
  content: BlockContent;
  onChange: (content: BlockContent) => void;
  /** Без поля «Что написать клиенту»: в календаре правится только расписание. */
  scheduleOnly?: boolean;
}

const WEEK = ["Понедельник", "Вторник", "Среда", "Четверг", "Пятница", "Суббота", "Воскресенье"];

function IntervalList({
  intervals,
  onChange,
}: {
  intervals: Interval[];
  onChange: (next: Interval[]) => void;
}) {
  return (
    <div className="schedule__intervals">
      {intervals.map((interval, index) => (
        <div className="schedule__interval" key={index}>
          <input
            className="payment-editor__input"
            type="time"
            aria-label="С"
            value={interval[0]}
            onChange={(e) => onChange(intervals.map((it, i) => (i === index ? [e.target.value, it[1]] : it)))}
          />
          <span aria-hidden="true">—</span>
          <input
            className="payment-editor__input"
            type="time"
            aria-label="До"
            value={interval[1]}
            onChange={(e) => onChange(intervals.map((it, i) => (i === index ? [it[0], e.target.value] : it)))}
          />
          <button
            type="button"
            className="schedule__remove"
            aria-label="Убрать промежуток"
            onClick={() => onChange(intervals.filter((_, i) => i !== index))}
          >
            <X size={18} aria-hidden="true" />
          </button>
        </div>
      ))}
      <button
        type="button"
        className="schedule__add"
        onClick={() => onChange([...intervals, intervals.length ? [intervals[intervals.length - 1][1], "19:00"] : ["10:00", "19:00"]])}
      >
        + промежуток
      </button>
    </div>
  );
}

/** Расписание записи: часы по каждому дню недели (можно с перерывом), особые даты,
 * длина записи, часовой пояс. Всё задаёт владелец — ничего не привязано к городу. */
export function ScheduleFields({ content, onChange }: Props) {
  const weekly = readWeekly(content);
  const exceptions = (content.exceptions ?? {}) as Record<string, Interval[]>;
  const tz = content.tz || localTimezone();
  const set = (patch: Partial<BlockContent>) => onChange({ ...content, ...patch });
  const setDay = (day: number, intervals: Interval[]) =>
    set({ weekly: { ...weekly, [String(day)]: intervals }, days: undefined, start: undefined, end: undefined });
  const setException = (date: string, intervals: Interval[] | null) => {
    const next = { ...exceptions };
    if (intervals === null) delete next[date];
    else next[date] = intervals;
    set({ exceptions: next });
  };

  return (
    <div className="schedule">
      <p className="edit-panel__section-label">Рабочие дни и часы</p>
      {WEEK.map((label, day) => {
        const intervals = weekly[String(day)];
        const on = intervals.length > 0;
        return (
          <div className={`schedule__day${on ? " schedule__day--on" : ""}`} key={label}>
            <label className="schedule__day-head">
              <input
                type="checkbox"
                checked={on}
                onChange={(e) => setDay(day, e.target.checked ? [["10:00", "19:00"]] : [])}
              />
              <strong>{label}</strong>
              {!on && <span className="overview-panel__sub">выходной</span>}
            </label>
            {on && (
              <>
                <IntervalList intervals={intervals} onChange={(next) => setDay(day, next)} />
                <button
                  type="button"
                  className="schedule__copy"
                  onClick={() => {
                    const all = { ...weekly };
                    WEEK.forEach((_, d) => {
                      if (all[String(d)].length > 0) all[String(d)] = intervals.map((i) => [...i] as Interval);
                    });
                    set({ weekly: all, days: undefined, start: undefined, end: undefined });
                  }}
                >
                  Те же часы — на все рабочие дни
                </button>
              </>
            )}
          </div>
        );
      })}

      <p className="edit-panel__section-label">Особые даты</p>
      <p className="app-hint">Отпуск, праздник или короткий день: для этой даты расписание недели не действует.</p>
      {Object.entries(exceptions)
        .sort(([a], [b]) => a.localeCompare(b))
        .map(([date, intervals]) => (
          <div className="schedule__day schedule__day--on" key={date}>
            <div className="schedule__exception-head">
              <input
                className="payment-editor__input"
                type="date"
                value={date}
                onChange={(e) => {
                  if (!e.target.value || e.target.value === date) return;
                  const next = { ...exceptions };
                  delete next[date];
                  next[e.target.value] = intervals;
                  set({ exceptions: next });
                }}
              />
              <select
                className="payment-editor__input"
                value={intervals.length === 0 ? "closed" : "custom"}
                onChange={(e) => setException(date, e.target.value === "closed" ? [] : [["10:00", "19:00"]])}
              >
                <option value="closed">Закрыто весь день</option>
                <option value="custom">Свои часы</option>
              </select>
              <button type="button" className="schedule__remove" aria-label="Убрать дату" onClick={() => setException(date, null)}>
                <X size={18} aria-hidden="true" />
              </button>
            </div>
            {intervals.length > 0 && <IntervalList intervals={intervals} onChange={(next) => setException(date, next)} />}
          </div>
        ))}
      <button
        type="button"
        className="schedule__add"
        onClick={() => {
          const d = new Date();
          d.setDate(d.getDate() + 1);
          const iso = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
          let key = iso;
          while (exceptions[key]) {
            d.setDate(d.getDate() + 1);
            key = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
          }
          setException(key, []);
        }}
      >
        + особая дата
      </button>

      <p className="edit-panel__section-label">Параметры</p>
      <div className="booking-editor__grid">
        <label className="buttons-editor__field">
          <span className="buttons-editor__field-label">Длина записи</span>
          <select
            className="payment-editor__input"
            value={content.slot_minutes ?? 60}
            onChange={(e) => set({ slot_minutes: Number(e.target.value) })}
          >
            {[15, 20, 30, 45, 60, 90, 120, 180, 240].map((m) => (
              <option key={m} value={m}>
                {m} мин
              </option>
            ))}
          </select>
        </label>
        <label className="buttons-editor__field">
          <span className="buttons-editor__field-label">Открыть запись на</span>
          <select
            className="payment-editor__input"
            value={content.horizon_days ?? 14}
            onChange={(e) => set({ horizon_days: Number(e.target.value) })}
          >
            {[7, 14, 21, 30, 60].map((d) => (
              <option key={d} value={d}>
                {d} дней вперёд
              </option>
            ))}
          </select>
        </label>
        <label className="buttons-editor__field">
          <span className="buttons-editor__field-label">Не позже чем за</span>
          <select
            className="payment-editor__input"
            value={content.notice_hours ?? 2}
            onChange={(e) => set({ notice_hours: Number(e.target.value) })}
          >
            {[0, 1, 2, 4, 12, 24, 48].map((h) => (
              <option key={h} value={h}>
                {h === 0 ? "без ограничения" : `${h} ч до начала`}
              </option>
            ))}
          </select>
        </label>
        <label className="buttons-editor__field">
          <span className="buttons-editor__field-label">Часовой пояс расписания</span>
          <select className="payment-editor__input" value={tz} onChange={(e) => set({ tz: e.target.value })}>
            {timezones(tz).map((zone) => (
              <option key={zone} value={zone}>
                {zone}
              </option>
            ))}
          </select>
        </label>
      </div>
      <p className="app-hint">Время в расписании — по выбранному часовому поясу. Клиенту показываются те же часы.</p>
      <label className="payment-settings__test">
        <input
          type="checkbox"
          checked={content.reminders !== false}
          onChange={(e) => set({ reminders: e.target.checked })}
        />
        <span>Напоминать клиенту о записи за сутки и за 2 часа</span>
      </label>
    </div>
  );
}

/** Редактор блока «Запись»: текст клиенту и расписание. */
export function BookingEditor({ content, onChange }: Props) {
  return (
    <div className="booking-editor" onClick={(e) => e.stopPropagation()}>
      <p className="payment-settings__hint">
        Клиент выбирает свободный день и время. Занятое время бот не показывает. Если после этого блока идёт оплата,
        время придерживается на час и подтверждается после оплаты; если оплаты нет — запись подтверждается сразу.
      </p>
      <p className="edit-panel__section-label">Что написать клиенту</p>
      <textarea
        className="chat-bubble__textarea edit-panel__textarea"
        value={content.text ?? ""}
        placeholder="Выберите день:"
        rows={2}
        onChange={(e) => onChange({ ...content, text: e.target.value })}
      />
      <ScheduleFields content={content} onChange={onChange} />
      <p className="app-hint">
        Календарь один на бота: два блока «Запись» делят одно время. Закрыть отдельное время или день можно в разделе
        «Клиенты» → «Календарь».
      </p>
    </div>
  );
}
export function ContactEditor({ content, onChange }: Props) {
  const set = (patch: Partial<BlockContent>) => onChange({ ...content, ...patch });
  return (
    <div className="booking-editor" onClick={(e) => e.stopPropagation()}>
      <p className="payment-settings__hint">
        Имя и @username бот берёт из Telegram сам, клиенту ничего вводить не нужно. Поставь галочки только на то,
        что нужно дополнительно. Уже оставленное клиентом второй раз не спрашивается.
      </p>
      <label className="payment-settings__test">
        <input type="checkbox" checked={Boolean(content.ask_phone)} onChange={(e) => set({ ask_phone: e.target.checked })} />
        <span>Спросить телефон (кнопка «Отправить мой номер» или вручную)</span>
      </label>
      <label className="payment-settings__test">
        <input type="checkbox" checked={Boolean(content.ask_name)} onChange={(e) => set({ ask_name: e.target.checked })} />
        <span>Спросить, как к клиенту обращаться</span>
      </label>
      <p className="edit-panel__section-label">Что написать перед вопросом (необязательно)</p>
      <textarea
        className="chat-bubble__textarea edit-panel__textarea"
        value={content.text ?? ""}
        placeholder="Оставьте контакты, чтобы мы могли подтвердить запись"
        rows={2}
        onChange={(e) => set({ text: e.target.value })}
      />
      {!content.ask_phone && !content.ask_name && (
        <p className="app-hint">Ничего не отмечено: бот ничего не спросит и пойдёт дальше, останутся данные из Telegram.</p>
      )}
    </div>
  );
}
