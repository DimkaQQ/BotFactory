import { useCallback, useEffect, useRef, useState } from "react";

import { type BlockType, type BotBlock, type BotWithBlocks, ApiError, builderApi } from "../api/builderApi";
import { confirmDialog } from "../hooks/useTelegramWebApp";
import { ChatCanvas } from "./ChatCanvas";
import { PublishButton } from "./PublishButton";

const AUTOSAVE_DEBOUNCE_MS = 500;

type LoadState = "loading" | "ready" | "error";

interface Props {
  botId: string;
  onBack: () => void;
  onDeleted: () => void;
}

export function BotBuilder({ botId, onBack, onDeleted }: Props) {
  const [loadState, setLoadState] = useState<LoadState>("loading");
  const [loadError, setLoadError] = useState<string | null>(null);
  const [bot, setBot] = useState<BotWithBlocks | null>(null);
  const [deleting, setDeleting] = useState(false);
  const [editingName, setEditingName] = useState(false);

  const saveTimers = useRef<Record<string, ReturnType<typeof setTimeout>>>({});
  const nameTimer = useRef<ReturnType<typeof setTimeout>>();

  useEffect(() => {
    setLoadState("loading");
    (async () => {
      try {
        const full = await builderApi.getBot(botId);
        setBot(full);
        setLoadState("ready");
      } catch (err) {
        setLoadError(err instanceof ApiError ? err.message : "Не удалось загрузить бота");
        setLoadState("error");
      }
    })();
  }, [botId]);

  const handleChangeContent = useCallback(
    (blockId: string, content: BotBlock["content"]) => {
      if (!bot) return;
      setBot((prev) =>
        prev ? { ...prev, blocks: prev.blocks.map((b) => (b.id === blockId ? { ...b, content } : b)) } : prev,
      );

      clearTimeout(saveTimers.current[blockId]);
      saveTimers.current[blockId] = setTimeout(async () => {
        try {
          await builderApi.updateBlock(bot.id, blockId, { content });
        } catch {
          // best-effort autosave; a subsequent edit will retry
        }
      }, AUTOSAVE_DEBOUNCE_MS);
    },
    [bot],
  );

  const handleDelete = useCallback(
    async (blockId: string) => {
      if (!bot) return;
      setBot((prev) => (prev ? { ...prev, blocks: prev.blocks.filter((b) => b.id !== blockId) } : prev));
      try {
        await builderApi.deleteBlock(bot.id, blockId);
      } catch {
        // block stays removed locally; a reload will resync if this failed
      }
    },
    [bot],
  );

  const handleAdd = useCallback(
    async (blockType: BlockType): Promise<string> => {
      if (!bot) throw new Error("Bot not loaded");
      const defaultContent = blockType === "buttons" ? { buttons: [] } : { text: "" };
      const created = await builderApi.createBlock(bot.id, blockType, defaultContent);
      setBot((prev) => (prev ? { ...prev, blocks: [...prev.blocks, created] } : prev));
      return created.id;
    },
    [bot],
  );

  const handleReorder = useCallback(
    (orderedIds: string[]) => {
      if (!bot) return;
      const byId = new Map(bot.blocks.map((b) => [b.id, b]));
      const reordered = orderedIds.map((id, index) => ({ ...byId.get(id)!, order_index: index }));
      setBot((prev) => (prev ? { ...prev, blocks: reordered } : prev));

      builderApi
        .reorderBlocks(
          bot.id,
          orderedIds.map((id, index) => ({ id, order_index: index })),
        )
        .catch(() => {
          /* optimistic update already applied; ignore transient failures */
        });
    },
    [bot],
  );

  const handleNameChange = useCallback(
    (name: string) => {
      if (!bot) return;
      setBot((prev) => (prev ? { ...prev, name } : prev));

      clearTimeout(nameTimer.current);
      nameTimer.current = setTimeout(async () => {
        try {
          await builderApi.renameBot(bot.id, name);
        } catch {
          // best-effort; a subsequent edit will retry
        }
      }, AUTOSAVE_DEBOUNCE_MS);
    },
    [bot],
  );

  const handlePublish = useCallback(
    async (token: string) => {
      if (!bot) return;
      await builderApi.publishBot(bot.id, token);
      const refreshed = await builderApi.getBot(bot.id);
      setBot(refreshed);
    },
    [bot],
  );

  async function handleDeleteBot() {
    if (!bot) return;
    const label = bot.telegram_bot_username ? `@${bot.telegram_bot_username}` : "этого бота";
    const confirmed = await confirmDialog(`Удалить ${label}? Это нельзя отменить.`);
    if (!confirmed) return;

    setDeleting(true);
    try {
      await builderApi.deleteBot(bot.id);
      onDeleted();
    } catch (err) {
      setLoadError(err instanceof ApiError ? err.message : "Не удалось удалить бота");
      setDeleting(false);
    }
  }

  if (loadState === "loading") {
    return (
      <div className="screen screen--center">
        <div className="state-icon">🛠</div>
        <p>Загружаем бота…</p>
      </div>
    );
  }

  if (loadState === "error" || !bot) {
    return (
      <div className="screen screen--center">
        <div className="state-icon">😕</div>
        <p>{loadError ?? "Бот не найден"}</p>
        <button type="button" className="back-link" onClick={onBack}>
          ← Назад к списку
        </button>
      </div>
    );
  }

  return (
    <div className="screen">
      <header className="app-header">
        <button type="button" className="back-link" onClick={onBack}>
          ← Мои боты
        </button>
        <div className="app-header__top">
          <div className="app-header__icon" aria-hidden="true">
            🛠
          </div>
          <div className="app-header__titles">
            {editingName ? (
              <input
                className="app-header__name-input"
                autoFocus
                value={bot.name ?? ""}
                placeholder={bot.telegram_bot_username ? `@${bot.telegram_bot_username}` : "Название бота"}
                onChange={(e) => handleNameChange(e.target.value)}
                onBlur={() => setEditingName(false)}
                onKeyDown={(e) => e.key === "Enter" && (e.target as HTMLInputElement).blur()}
              />
            ) : (
              <h1 className="app-header__name" onClick={() => setEditingName(true)}>
                {bot.name || (bot.telegram_bot_username ? `@${bot.telegram_bot_username}` : "Новый бот")}
                <span className="app-header__edit-hint" aria-hidden="true">
                  ✎
                </span>
              </h1>
            )}
            <p className="app-header__greeting">
              {bot.status === "active" ? "Опубликован — изменения применяются сразу" : "Черновик"}
              {bot.name && bot.telegram_bot_username ? ` · @${bot.telegram_bot_username}` : ""}
            </p>
          </div>
          <button type="button" className="bot-delete-button" onClick={handleDeleteBot} disabled={deleting} aria-label="Удалить бота">
            🗑
          </button>
        </div>
      </header>

      {bot.status === "active" ? (
        <div className="published-banner">
          <div className="published-banner__badge" aria-hidden="true">
            ✓
          </div>
          <div>
            <p className="published-banner__title">
              Бот работает: <strong>@{bot.telegram_bot_username}</strong>
            </p>
            <p className="published-banner__hint">Правки в сообщениях применяются сразу, без повторной публикации.</p>
          </div>
        </div>
      ) : (
        <p className="app-hint">Так и будет выглядеть переписка. Нажми на сообщение, чтобы изменить, зажми — чтобы переставить.</p>
      )}

      <ChatCanvas
        blocks={bot.blocks}
        onReorder={handleReorder}
        onChangeContent={handleChangeContent}
        onDelete={handleDelete}
        onAdd={handleAdd}
      />

      {bot.status === "draft" && (
        <div className="app-footer">
          <PublishButton onPublish={handlePublish} disabled={bot.blocks.length === 0} />
        </div>
      )}

      {bot.status === "active" && (
        <div className="app-footer">
          <a
            className="publish-button publish-button--link"
            href={`https://t.me/${bot.telegram_bot_username}`}
            target="_blank"
            rel="noreferrer"
          >
            Открыть @{bot.telegram_bot_username} →
          </a>
        </div>
      )}
    </div>
  );
}
