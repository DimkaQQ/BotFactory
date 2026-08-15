import { useState } from "react";

interface Props {
  disabled?: boolean;
  onPublish: (token: string) => Promise<void>;
}

export function PublishButton({ disabled, onPublish }: Props) {
  const [open, setOpen] = useState(false);
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
    <form className="publish-form" onSubmit={handleSubmit}>
      <p className="publish-form__hint">
        Вставь токен бота от <a href="https://t.me/BotFather" target="_blank" rel="noreferrer">@BotFather</a>
      </p>
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
