import { useEffect, useRef, useState } from "react";

import { builderApi } from "../api/builderApi";
import { BotFatherSteps } from "./BotFatherSteps";

interface Props {
  disabled?: boolean;
  /** Blocks nothing on the canvas leads to. Not an error — a half-wired
   * scenario is a normal thing to have open — but shipping one silently is
   * how a bot that was meant to send four videos sends one. */
  orphanCount?: number;
  /** Что не так со сценарием. Тот же список, что показывает пейволл до
   * оплаты: он исчезал вместе с пейволлом, и последний клик перед выходом к
   * живым покупателям оставался без единой проверки. */
  problems?: string[];
  onPublish: (token: string) => Promise<void>;
}

export function PublishButton({ disabled, orphanCount = 0, problems = [], onPublish }: Props) {
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
  // Шаг 1 запуска: человек должен нажать Start у мета-бота (уведомления о
  // продажах идут туда). Пока Telegram не разрешил писать — токен не просим.
  const [meta, setMeta] = useState<{ reachable: boolean; username: string; url: string } | null>(null);
  const [checking, setChecking] = useState(false);

  async function checkMeta() {
    setChecking(true);
    try {
      setMeta(await builderApi.metaBotStatus());
    } catch {
      setMeta(null); // не удалось проверить — не мешаем, сервер проверит при публикации
    } finally {
      setChecking(false);
    }
  }

  useEffect(() => {
    if (open) void checkMeta();
  }, [open]);
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
    <form className="publish-form publish-form--sheet" ref={formRef} onSubmit={handleSubmit}>
      {meta && !meta.reachable ? (
        <div className="publish-form__meta">
          <p className="publish-form__hint">
            <strong>Шаг 1.</strong> Открой {meta.username ? `@${meta.username}` : "нашего бота"} в Telegram и нажми{" "}
            <b>Start</b> — сюда придут уведомления о продажах и сообщение о запуске.
          </p>
          <div className="publish-form__actions">
            {meta.url && (
              <a className="publish-form__link-button" href={meta.url} target="_blank" rel="noreferrer">
                Открыть в Telegram
              </a>
            )}
            <button type="button" onClick={checkMeta} disabled={checking}>
              {checking ? "Проверяем…" : "Я нажал Start — проверить"}
            </button>
          </div>
          <p className="publish-form__hint">Когда Start нажат, здесь появится шаг 2 — токен бота.</p>
          <div className="publish-form__actions">
            <button type="button" onClick={() => setOpen(false)}>
              Отмена
            </button>
          </div>
        </div>
      ) : (
        <>
      <p className="publish-form__hint">
        <strong>Шаг 2.</strong> Вставь токен бота от <a href="https://t.me/BotFather" target="_blank" rel="noreferrer">@BotFather</a>
      </p>
      <BotFatherSteps />
      {problems.length > 0 && (
        <div className="paywall__problems">
          <p className="paywall__problems-title">Перед публикацией стоит поправить:</p>
          <ul>
            {problems.map((problem) => (
              <li key={problem}>{problem}</li>
            ))}
          </ul>
        </div>
      )}
      {problems.length === 0 && orphanCount > 0 && (
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
        </>
      )}
    </form>
  );
}
