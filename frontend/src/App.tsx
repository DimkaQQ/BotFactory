import { useCallback, useEffect, useRef, useState } from "react";

import { type BlockType, type BotBlock, type BotWithBlocks, builderApi, configureBuilderApi } from "./api/builderApi";
import "./App.css";
import { BlockList } from "./components/BlockList";
import { PublishButton } from "./components/PublishButton";
import { useTelegramWebApp } from "./hooks/useTelegramWebApp";

const AUTOSAVE_DEBOUNCE_MS = 500;

type LoadState = "loading" | "ready" | "error";

export default function App() {
  const { ready, initData, user } = useTelegramWebApp();

  const [loadState, setLoadState] = useState<LoadState>("loading");
  const [loadError, setLoadError] = useState<string | null>(null);
  const [bot, setBot] = useState<BotWithBlocks | null>(null);

  const saveTimers = useRef<Record<string, ReturnType<typeof setTimeout>>>({});

  // Bootstrap: validate initData with the backend, then load or create the
  // client's bot draft.
  useEffect(() => {
    if (!ready) return;

    configureBuilderApi(() => initData);

    (async () => {
      try {
        await builderApi.getMe();

        const bots = await builderApi.listBots();
        const draft = bots.find((b) => b.status === "draft");
        const target = draft ?? bots[0] ?? (await builderApi.createBot());

        const full = await builderApi.getBot(target.id);
        setBot(full);
        setLoadState("ready");
      } catch (err) {
        setLoadError(err instanceof Error ? err.message : "Не удалось загрузить конструктор");
        setLoadState("error");
      }
    })();
  }, [ready, initData]);

  const isDraft = bot?.status === "draft";

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
    async (blockType: BlockType) => {
      if (!bot) return;
      const defaultContent = blockType === "buttons" ? { buttons: [] } : { text: "" };
      const created = await builderApi.createBlock(bot.id, blockType, defaultContent);
      setBot((prev) => (prev ? { ...prev, blocks: [...prev.blocks, created] } : prev));
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

  const handlePublish = useCallback(
    async (token: string) => {
      if (!bot) return;
      await builderApi.publishBot(bot.id, token);
      const refreshed = await builderApi.getBot(bot.id);
      setBot(refreshed);
    },
    [bot],
  );

  if (loadState === "loading") {
    return <div className="screen screen--center">Загрузка…</div>;
  }

  if (loadState === "error") {
    return (
      <div className="screen screen--center">
        <p>😕 {loadError}</p>
      </div>
    );
  }

  if (!bot) {
    return <div className="screen screen--center">Бот не найден</div>;
  }

  return (
    <div className="screen">
      <header className="app-header">
        <h1>🛠 Конструктор бота</h1>
        {user && (
          <p className="app-header__greeting">
            Привет, {user.first_name}
            {user.last_name ? ` ${user.last_name}` : ""}!
          </p>
        )}
      </header>

      {bot.status === "active" ? (
        <div className="published-banner">
          ✅ Бот опубликован: <strong>@{bot.telegram_bot_username}</strong>
          <p>Редактирование опубликованного бота пока не поддерживается.</p>
        </div>
      ) : (
        <p className="app-hint">Собери диалог из блоков — перетаскивай, чтобы менять порядок.</p>
      )}

      <BlockList
        blocks={bot.blocks}
        onReorder={handleReorder}
        onChangeContent={handleChangeContent}
        onDelete={handleDelete}
        onAdd={handleAdd}
        disabled={!isDraft}
      />

      {isDraft && (
        <div className="app-footer">
          <PublishButton onPublish={handlePublish} disabled={bot.blocks.length === 0} />
        </div>
      )}
    </div>
  );
}
