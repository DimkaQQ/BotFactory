import { useCallback, useEffect, useRef, useState } from "react";

import {
  type BlockType,
  type BotBlock,
  type BotWithBlocks,
  type PaymentProviderInfo,
  type PaymentSettings,
  type PublicationInfo,
  ApiError,
  builderApi,
} from "../api/builderApi";
import { confirmDialog, openExternal } from "../hooks/useTelegramWebApp";
import { BLOCK_TYPE_BY_ID } from "../blockTypes";
import { FlowCanvas } from "./flow/FlowCanvas";
import { LivePreview } from "./LivePreview";
import { PaymentSettingsPanel } from "./PaymentSettingsPanel";
import { PublishPaywall } from "./PublishPaywall";
import { PublishButton } from "./PublishButton";

const AUTOSAVE_DEBOUNCE_MS = 500;

type LoadState = "loading" | "ready" | "error";
type SaveStatus = "idle" | "saving" | "saved";

interface Props {
  botId: string;
  isMiniApp?: boolean;
  onBack: () => void;
  onDeleted: () => void;
}

export function BotBuilder({ botId, isMiniApp, onBack, onDeleted }: Props) {
  const [loadState, setLoadState] = useState<LoadState>("loading");
  const [loadError, setLoadError] = useState<string | null>(null);
  const [bot, setBot] = useState<BotWithBlocks | null>(null);
  const [deleting, setDeleting] = useState(false);
  const [editingName, setEditingName] = useState(false);
  const [saveStatus, setSaveStatus] = useState<SaveStatus>("idle");
  const [previewOpen, setPreviewOpen] = useState(false);
  const [paymentPanelOpen, setPaymentPanelOpen] = useState(false);
  const [paymentSettings, setPaymentSettings] = useState<PaymentSettings | null>(null);
  const [paymentProviders, setPaymentProviders] = useState<PaymentProviderInfo[]>([]);
  const [publication, setPublication] = useState<PublicationInfo | null>(null);

  const saveTimers = useRef<Record<string, ReturnType<typeof setTimeout>>>({});
  const nameTimer = useRef<ReturnType<typeof setTimeout>>();

  // Tracks which fields (block ids, "name", "reorder") currently have an
  // autosave in flight, so the "Сохраняем… / Сохранено" indicator in the
  // header reflects reality even with several fields mid-edit at once —
  // repeated keystrokes on the same field are a no-op (Set), and the
  // status only flips back to "saved" once every field has settled.
  const pendingSaves = useRef<Set<string>>(new Set());
  const markPending = useCallback((key: string) => {
    pendingSaves.current.add(key);
    setSaveStatus("saving");
  }, []);
  const markSettled = useCallback((key: string) => {
    pendingSaves.current.delete(key);
    if (pendingSaves.current.size === 0) setSaveStatus("saved");
  }, []);

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

    // Payment setup and the publication paywall are secondary — a failure
    // here leaves the constructor perfectly usable, so it never touches
    // loadState.
    (async () => {
      try {
        const [providers, settings, publicationInfo] = await Promise.all([
          builderApi.listPaymentProviders(),
          builderApi.getPaymentSettings(botId),
          builderApi.getPublicationInfo(botId),
        ]);
        setPaymentProviders(providers.providers);
        setPaymentSettings(settings);
        setPublication(publicationInfo);
      } catch {
        // leaves payments unconfigured in the UI; nothing else breaks
      }
    })();
  }, [botId]);

  const handleChangeContent = useCallback(
    (blockId: string, content: BotBlock["content"]) => {
      if (!bot) return;
      setBot((prev) =>
        prev ? { ...prev, blocks: prev.blocks.map((b) => (b.id === blockId ? { ...b, content } : b)) } : prev,
      );

      markPending(blockId);
      clearTimeout(saveTimers.current[blockId]);
      saveTimers.current[blockId] = setTimeout(async () => {
        try {
          await builderApi.updateBlock(bot.id, blockId, { content });
        } catch {
          // best-effort autosave; a subsequent edit will retry
        } finally {
          markSettled(blockId);
        }
      }, AUTOSAVE_DEBOUNCE_MS);
    },
    [bot, markPending, markSettled],
  );

  const handleDelete = useCallback(
    async (blockId: string) => {
      if (!bot) return;
      // Removing a node can orphan two kinds of arrow pointing *at* it: the
      // backend already nulls next_block_id/start_block_id on delete (real
      // FKs, ON DELETE SET NULL) but a button's target_block_id lives inside
      // JSONB content, so it's on us to clear it here — otherwise the arrow
      // just silently stops resolving to anything on the canvas.
      const affected = bot.blocks.filter(
        (b) => b.block_type === "buttons" && (b.content.buttons ?? []).some((btn) => btn.target_block_id === blockId),
      );

      setBot((prev) =>
        prev
          ? {
              ...prev,
              start_block_id: prev.start_block_id === blockId ? null : prev.start_block_id,
              blocks: prev.blocks
                .filter((b) => b.id !== blockId)
                .map((b) =>
                  b.block_type === "buttons" && (b.content.buttons ?? []).some((btn) => btn.target_block_id === blockId)
                    ? {
                        ...b,
                        content: {
                          ...b.content,
                          buttons: (b.content.buttons ?? []).map((btn) =>
                            btn.target_block_id === blockId ? { ...btn, target_block_id: null } : btn,
                          ),
                        },
                      }
                    : b,
                ),
            }
          : prev,
      );
      try {
        await builderApi.deleteBlock(bot.id, blockId);
        await Promise.all(
          affected.map((b) =>
            builderApi.updateBlock(bot.id, b.id, {
              content: {
                ...b.content,
                buttons: (b.content.buttons ?? []).map((btn) =>
                  btn.target_block_id === blockId ? { ...btn, target_block_id: null } : btn,
                ),
              },
            }),
          ),
        );
      } catch {
        // block stays removed locally; a reload will resync if this failed
      }
    },
    [bot],
  );

  const handleAdd = useCallback(
    async (blockType: BlockType, position: { x: number; y: number }): Promise<string> => {
      if (!bot) throw new Error("Bot not loaded");
      const defaultContent = BLOCK_TYPE_BY_ID[blockType].defaultContent();
      const created = await builderApi.createBlock(bot.id, blockType, defaultContent, position);
      setBot((prev) =>
        prev
          ? {
              ...prev,
              blocks: [...prev.blocks, created],
              start_block_id: prev.start_block_id ?? created.id,
            }
          : prev,
      );
      return created.id;
    },
    [bot],
  );

  // Graph edges — a plain arrow (next_block_id), a per-button branch (lives
  // in content, so it rides the same debounced content autosave), and the
  // "▶ Старт" pseudo-edge (bot.start_block_id). All three are optimistic:
  // the canvas already shows the new arrow before the PATCH lands.
  const handleSetNext = useCallback(
    (blockId: string, nextBlockId: string | null) => {
      if (!bot) return;
      setBot((prev) =>
        prev ? { ...prev, blocks: prev.blocks.map((b) => (b.id === blockId ? { ...b, next_block_id: nextBlockId } : b)) } : prev,
      );
      markPending(`${blockId}:next`);
      builderApi
        .updateBlock(bot.id, blockId, { next_block_id: nextBlockId })
        .catch(() => {
          /* optimistic update already applied; ignore transient failures */
        })
        .finally(() => markSettled(`${blockId}:next`));
    },
    [bot, markPending, markSettled],
  );

  const handleSetStart = useCallback(
    (blockId: string | null) => {
      if (!bot) return;
      setBot((prev) => (prev ? { ...prev, start_block_id: blockId } : prev));
      markPending("start");
      builderApi
        .setStartBlock(bot.id, blockId)
        .catch(() => {
          /* optimistic update already applied; ignore transient failures */
        })
        .finally(() => markSettled("start"));
    },
    [bot, markPending, markSettled],
  );

  const handleSetPosition = useCallback(
    (blockId: string, x: number, y: number) => {
      if (!bot) return;
      setBot((prev) =>
        prev ? { ...prev, blocks: prev.blocks.map((b) => (b.id === blockId ? { ...b, position_x: x, position_y: y } : b)) } : prev,
      );
      builderApi.updateBlock(bot.id, blockId, { position_x: x, position_y: y }).catch(() => {
        /* best-effort; the node just snaps back to its last saved spot on reload */
      });
    },
    [bot],
  );

  const handleNameChange = useCallback(
    (name: string) => {
      if (!bot) return;
      setBot((prev) => (prev ? { ...prev, name } : prev));

      markPending("name");
      clearTimeout(nameTimer.current);
      nameTimer.current = setTimeout(async () => {
        try {
          await builderApi.renameBot(bot.id, name);
        } catch {
          // best-effort; a subsequent edit will retry
        } finally {
          markSettled("name");
        }
      }, AUTOSAVE_DEBOUNCE_MS);
    },
    [bot, markPending, markSettled],
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

  const showsPaywall = bot.status === "draft" && Boolean(publication?.required) && !publication?.paid;

  return (
    // The paywall card is roughly twice the height of the publish button, and
    // the footer is fixed — so the space reserved for it at the bottom of the
    // screen has to know which one is showing, or the card lands on top of the
    // "+ Добавить блок" bar and no block can be added on a phone.
    <div className={`screen screen--builder${showsPaywall ? " screen--builder-paywall" : ""}`}>
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
                <span className="app-header__name-text">
                  {bot.name || (bot.telegram_bot_username ? `@${bot.telegram_bot_username}` : "Новый бот")}
                </span>
                <span className="app-header__edit-hint" aria-hidden="true">
                  ✎
                </span>
              </h1>
            )}
            <p className="app-header__greeting">
              {bot.status === "active" ? "Опубликован — изменения применяются сразу" : "Черновик"}
              {bot.name && bot.telegram_bot_username ? ` · @${bot.telegram_bot_username}` : ""}
              {!isMiniApp && saveStatus !== "idle" && (
                <span className={`save-status save-status--${saveStatus}`}>
                  {saveStatus === "saving" ? " · Сохраняем…" : " · Сохранено"}
                </span>
              )}
            </p>
          </div>
          {!isMiniApp && (
            <button
              type="button"
              className={`bot-payments-button ${paymentSettings?.provider ? "bot-payments-button--on" : ""}`}
              onClick={() => setPaymentPanelOpen(true)}
              title="Платёжная система, через которую бот принимает деньги"
            >
              💳 {paymentSettings?.provider ? "Касса подключена" : "Подключить кассу"}
            </button>
          )}
          <button type="button" className="bot-delete-button" onClick={handleDeleteBot} disabled={deleting} aria-label="Удалить бота">
            🗑
          </button>
        </div>
      </header>

      {isMiniApp && (
        <div className="miniapp-banner">
          <p>📱 Здесь виден сценарий и кнопка публикации. Редактировать — в браузере, с телефона тоже удобно.</p>
          <button type="button" onClick={() => openExternal(`${window.location.origin}/`)}>
            Открыть в браузере →
          </button>
        </div>
      )}

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
        !isMiniApp && (
          <p className="app-hint">
            Блоки добавляются кнопкой «+ Добавить блок» под холстом (на большом экране — из списка слева).
            Нажми на блок, чтобы изменить его; потяни от кружка снизу или от кнопки — чтобы решить, что дальше.
          </p>
        )
      )}

      {bot.blocks.length > 0 && (
        <button type="button" className="chat-canvas__preview-btn" onClick={() => setPreviewOpen(true)}>
          ▶ Смотреть, как в реальности
        </button>
      )}

      <FlowCanvas
        bot={bot}
        onChangeContent={handleChangeContent}
        onDelete={handleDelete}
        onAdd={handleAdd}
        onSetNext={handleSetNext}
        onSetStart={handleSetStart}
        onSetPosition={handleSetPosition}
        paymentProvider={paymentSettings?.provider ?? null}
        paymentCurrencies={paymentProviders.find((p) => p.slug === paymentSettings?.provider)?.currencies ?? []}
        paymentProviderInfo={paymentProviders.find((p) => p.slug === paymentSettings?.provider) ?? null}
        onOpenPaymentSettings={() => setPaymentPanelOpen(true)}
        disabled={isMiniApp}
      />

      {bot.status === "draft" && (
        <div className="app-footer">
          {publication?.required && !publication.paid ? (
            <PublishPaywall
              botId={bot.id}
              info={publication}
              onPaid={() => setPublication((prev) => (prev ? { ...prev, paid: true } : prev))}
            />
          ) : (
            <PublishButton onPublish={handlePublish} disabled={bot.blocks.length === 0} />
          )}
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

      {paymentPanelOpen && (
        <PaymentSettingsPanel
          botId={bot.id}
          onClose={() => setPaymentPanelOpen(false)}
          onSaved={(settings) => setPaymentSettings(settings)}
        />
      )}

      {previewOpen && <LivePreview bot={bot} botName={bot.name || bot.telegram_bot_username || ""} onClose={() => setPreviewOpen(false)} />}
    </div>
  );
}
