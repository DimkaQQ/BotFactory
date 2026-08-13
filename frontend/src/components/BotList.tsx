import { useCallback, useEffect, useState } from "react";

import { type Bot, ApiError, builderApi } from "../api/builderApi";
import { confirmDialog } from "../hooks/useTelegramWebApp";

interface Props {
  greetingName?: string;
  onOpen: (botId: string) => void;
}

const STATUS_LABEL: Record<Bot["status"], string> = {
  draft: "Черновик",
  active: "Опубликован",
  disabled: "Отключён",
};

function botTitle(bot: Bot): string {
  if (bot.name) return bot.name;
  if (bot.telegram_bot_username) return `@${bot.telegram_bot_username}`;
  return "Новый бот";
}

function blockCountLabel(count: number): string {
  if (count === 0) return "Пока пусто";
  if (count === 1) return "1 сообщение";
  if (count >= 2 && count <= 4) return `${count} сообщения`;
  return `${count} сообщений`;
}

export function BotList({ greetingName, onOpen }: Props) {
  const [bots, setBots] = useState<Bot[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);
  const [deletingId, setDeletingId] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      const list = await builderApi.listBots();
      setBots(list);
      setError(null);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Не удалось загрузить ботов");
    }
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  async function handleCreate() {
    setCreating(true);
    try {
      const bot = await builderApi.createBot();
      onOpen(bot.id);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Не удалось создать бота");
    } finally {
      setCreating(false);
    }
  }

  async function handleDelete(bot: Bot, e: React.MouseEvent) {
    e.stopPropagation();
    const confirmed = await confirmDialog(`Удалить бота ${botTitle(bot)}? Это нельзя отменить.`);
    if (!confirmed) return;

    setDeletingId(bot.id);
    const prev = bots;
    setBots((list) => list?.filter((b) => b.id !== bot.id) ?? null);
    try {
      await builderApi.deleteBot(bot.id);
    } catch (err) {
      setBots(prev ?? null); // roll back on failure
      setError(err instanceof ApiError ? err.message : "Не удалось удалить бота");
    } finally {
      setDeletingId(null);
    }
  }

  return (
    <div className="screen">
      <header className="app-header">
        <div className="app-header__top">
          <div className="app-header__icon" aria-hidden="true">
            🏭
          </div>
          <div className="app-header__titles">
            <h1>Мои боты</h1>
            {greetingName && <p className="app-header__greeting">Привет, {greetingName}!</p>}
          </div>
        </div>
      </header>

      {error && <p className="publish-form__error" style={{ marginBottom: "var(--sp-3)" }}>{error}</p>}

      {bots === null ? (
        <p className="app-hint">Загрузка…</p>
      ) : bots.length === 0 ? (
        <div className="bot-list__empty">
          <div className="block-list__empty-icon">🏭</div>
          <p className="block-list__empty-title">Ещё нет ни одного бота</p>
          <p className="block-list__empty-hint">Создай первого — это займёт пару минут</p>
        </div>
      ) : (
        <div className="bot-list">
          {bots.map((bot) => (
            <button
              type="button"
              key={bot.id}
              className="bot-card"
              onClick={() => onOpen(bot.id)}
              disabled={deletingId === bot.id}
            >
              <div className={`bot-card__icon bot-card__icon--${bot.status}`} aria-hidden="true">
                🤖
              </div>
              <div className="bot-card__info">
                <span className="bot-card__name">{botTitle(bot)}</span>
                <span className="bot-card__meta">
                  <span className={`bot-card__status bot-card__status--${bot.status}`}>{STATUS_LABEL[bot.status]}</span>
                  <span className="bot-card__dot">·</span>
                  {blockCountLabel(bot.block_count)}
                  {bot.name && bot.telegram_bot_username && (
                    <>
                      <span className="bot-card__dot">·</span>@{bot.telegram_bot_username}
                    </>
                  )}
                </span>
              </div>
              <span
                role="button"
                tabIndex={0}
                className="bot-card__delete"
                aria-label="Удалить бота"
                onClick={(e) => handleDelete(bot, e)}
              >
                🗑
              </span>
            </button>
          ))}
        </div>
      )}

      <div className="app-footer">
        <button type="button" className="publish-button" onClick={handleCreate} disabled={creating}>
          {creating ? "Создаём…" : "+ Новый бот"}
        </button>
      </div>
    </div>
  );
}
