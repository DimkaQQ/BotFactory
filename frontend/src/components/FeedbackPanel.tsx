import { useEffect, useState } from "react";

import { type MySuggestion, ApiError, builderApi } from "../api/builderApi";
import { useDraggablePanel } from "../hooks/useDraggablePanel";
import { useEscape } from "../hooks/useEscape";

const CATEGORIES: [string, string][] = [
  ["idea", "💡 Идея"],
  ["bug", "🐞 Ошибка"],
  ["question", "❓ Вопрос"],
];

/** Обратная связь: клиент пишет идею, оператор видит её сразу в Telegram. */
export function FeedbackPanel({ onClose }: { onClose: () => void }) {
  useEscape(onClose);
  const { panelRef, handleProps: dragProps } = useDraggablePanel();
  const [category, setCategory] = useState("idea");
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [sent, setSent] = useState(false);
  const [mine, setMine] = useState<MySuggestion[]>([]);

  useEffect(() => {
    builderApi
      .mySuggestions()
      .then((r) => setMine(r.suggestions))
      .catch(() => undefined);
  }, []);

  async function send() {
    setBusy(true);
    setError(null);
    setSent(false);
    try {
      const item = await builderApi.sendSuggestion(text.trim(), category);
      setMine((prev) => [item, ...prev]);
      setText("");
      setSent(true);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Не получилось отправить. Попробуйте ещё раз.");
    } finally {
      setBusy(false);
    }
  }

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
            💡
          </span>
          <span className="edit-panel__title">Идеи и обратная связь</span>
          <button type="button" className="edit-panel__close" aria-label="Закрыть" onClick={onClose}>
            ✕
          </button>
        </div>
        <div className="edit-panel__body">
          <p className="payment-editor__hint">
            Чего не хватает в конструкторе? Что неудобно? Напишите — сообщение сразу приходит разработчику. Полезное
            добавляем быстро и сообщаем вам.
          </p>
          <div className="overview-panel__filters">
            {CATEGORIES.map(([key, label]) => (
              <button
                key={key}
                type="button"
                className={`overview-panel__filter${category === key ? " is-active" : ""}`}
                onClick={() => setCategory(key)}
              >
                {label}
              </button>
            ))}
          </div>
          <textarea
            className="payment-editor__input"
            rows={5}
            maxLength={2000}
            placeholder="Опишите своими словами…"
            value={text}
            onChange={(e) => setText(e.target.value)}
          />
          {error && <p className="payment-editor__error">{error}</p>}
          {sent && <p className="payment-editor__hint">Спасибо! Отправлено.</p>}
          <button
            type="button"
            className="bot-payments-button"
            disabled={busy || text.trim().length < 10}
            onClick={send}
          >
            {busy ? "Отправляем…" : "Отправить"}
          </button>
          {mine.length > 0 && (
            <>
              <h3 className="buttons-editor__field-label">Мои обращения</h3>
              <ul className="overview-panel__list">
                {mine.map((i) => (
                  <li key={i.id}>
                    <div>{i.text}</div>
                    <small>{i.done ? "✅ " : ""}{i.status}</small>
                  </li>
                ))}
              </ul>
            </>
          )}
        </div>
      </div>
    </>
  );
}
