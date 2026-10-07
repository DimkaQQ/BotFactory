import type { BlockContent } from "../api/builderApi";

interface Props {
  content: BlockContent;
  onChange: (content: BlockContent) => void;
}

const WEEK = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"];
const TZ = [
  ["Asia/Almaty", "Алматы, Астана"],
  ["Europe/Moscow", "Москва"],
  ["Asia/Tashkent", "Ташкент"],
  ["Europe/Kyiv", "Киев"],
  ["Europe/Minsk", "Минск"],
  ["Asia/Yekaterinburg", "Екатеринбург"],
  ["Asia/Novosibirsk", "Новосибирск"],
  ["UTC", "UTC"],
] as const;

/** Расписание записи: рабочие дни и часы, длина слота, горизонт, часовой пояс. */
export function BookingEditor({ content, onChange }: Props) {
  const days = content.days ?? [0, 1, 2, 3, 4];
  const set = (patch: Partial<BlockContent>) => onChange({ ...content, ...patch });

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
        onChange={(e) => set({ text: e.target.value })}
      />

      <p className="edit-panel__section-label">Рабочие дни</p>
      <div className="booking-editor__days">
        {WEEK.map((label, index) => (
          <label key={label} className={`booking-editor__day${days.includes(index) ? " booking-editor__day--on" : ""}`}>
            <input
              type="checkbox"
              checked={days.includes(index)}
              onChange={(e) =>
                set({ days: (e.target.checked ? [...days, index] : days.filter((d) => d !== index)).sort() })
              }
            />
            {label}
          </label>
        ))}
      </div>

      <div className="booking-editor__grid">
        <label className="buttons-editor__field">
          <span className="buttons-editor__field-label">Начало работы</span>
          <input
            className="payment-editor__input"
            type="time"
            value={content.start ?? "10:00"}
            onChange={(e) => set({ start: e.target.value })}
          />
        </label>
        <label className="buttons-editor__field">
          <span className="buttons-editor__field-label">Конец работы</span>
          <input
            className="payment-editor__input"
            type="time"
            value={content.end ?? "19:00"}
            onChange={(e) => set({ end: e.target.value })}
          />
        </label>
        <label className="buttons-editor__field">
          <span className="buttons-editor__field-label">Длина записи</span>
          <select
            className="payment-editor__input"
            value={content.slot_minutes ?? 60}
            onChange={(e) => set({ slot_minutes: Number(e.target.value) })}
          >
            {[15, 30, 45, 60, 90, 120, 180].map((m) => (
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
          <span className="buttons-editor__field-label">Часовой пояс</span>
          <select
            className="payment-editor__input"
            value={content.tz ?? "Asia/Almaty"}
            onChange={(e) => set({ tz: e.target.value })}
          >
            {TZ.map(([value, label]) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </select>
        </label>
      </div>
      <p className="app-hint">
        Календарь один на бота: два блока «Запись» делят одно время. Закрыть перерыв или выходной можно в разделе
        «Клиенты и записи» → «Календарь».
      </p>
    </div>
  );
}

/** Какие контакты спросить. Данные из Telegram (имя, @username) приходят сами. */
export function ContactEditor({ content, onChange }: Props) {
  const set = (patch: Partial<BlockContent>) => onChange({ ...content, ...patch });
  return (
    <div className="booking-editor" onClick={(e) => e.stopPropagation()}>
      <p className="payment-settings__hint">
        Имя и @username бот берёт из Telegram сам, клиенту ничего вводить не нужно. Поставьте галочки только на то,
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
