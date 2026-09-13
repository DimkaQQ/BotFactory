import { useEffect, useRef, useState } from "react";

interface Props {
  disabled?: boolean;
  /** Blocks nothing on the canvas leads to. Not an error — a half-wired
   * scenario is a normal thing to have open — but shipping one silently is
   * how a bot that was meant to send four videos sends one. */
  orphanCount?: number;
  onPublish: (token: string) => Promise<void>;
}

export function PublishButton({ disabled, orphanCount = 0, onPublish }: Props) {
  const [open, setOpen] = useState(false);
  const formRef = useRef<HTMLFormElement | null>(null);

  // The form is three rows taller than the button it replaces, and on a
  // laptop that pushed its own submit button below the fold — you pasted the
  // token and the thing that publishes it was off-screen, with nothing
  // saying so. Cheaper and far more robust than trying to make every
  // viewport's chrome budget add up exactly.
  useEffect(() => {
    if (open) formRef.current?.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }, [open]);
  const [token, setToken] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!token.trim()) return;
    setSubmitting(true);
    setError(null);
    try {
      await onPublish(token.trim());
      setOpen(false);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Не удалось опубликовать бота");
    } finally {
      setSubmitting(false);
    }
  }

  if (!open) {
    return (
      <button type="button" className="publish-button" disabled={disabled} onClick={() => setOpen(true)}>
        🚀 Опубликовать
      </button>
    );
  }

  return (
    <form className="publish-form" ref={formRef} onSubmit={handleSubmit}>
      <p className="publish-form__hint">
        Вставь токен бота от <a href="https://t.me/BotFather" target="_blank" rel="noreferrer">@BotFather</a>
      </p>
      {orphanCount > 0 && (
        <p className="publish-form__warning">
          ⚠️ {orphanCount === 1 ? "Один блок ни с чем не соединён" : `Блоков ни с чем не соединено: ${orphanCount}`}
          {" — "}бот их не покажет. Опубликовать можно, но сначала проверь стрелки на холсте.
        </p>
      )}
      <input
        className="publish-form__input"
        placeholder="123456789:AA...your-token"
        value={token}
        onChange={(e) => setToken(e.target.value)}
        autoFocus
      />
      {error && <p className="publish-form__error">{error}</p>}
      <div className="publish-form__actions">
        <button type="button" onClick={() => setOpen(false)} disabled={submitting}>
          Отмена
        </button>
        <button type="submit" disabled={submitting || !token.trim()}>
          {submitting && <span className="btn-spinner" aria-hidden="true" />}
          {submitting ? "Публикуем…" : "Опубликовать"}
        </button>
      </div>
    </form>
  );
}
