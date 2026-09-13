import { useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";

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
import { confirmDialog } from "../confirm";
import { openExternal } from "../hooks/useTelegramWebApp";
import { BLOCK_TYPE_BY_ID } from "../blockTypes";
import { orphanBlocks } from "../reachability";
import { FlowCanvas } from "./flow/FlowCanvas";
import { LivePreview } from "./LivePreview";
import { PaymentSettingsPanel } from "./PaymentSettingsPanel";
import { PublishPaywall } from "./PublishPaywall";
import { PublishButton } from "./PublishButton";
import { ThemeToggle } from "./ThemeToggle";

const AUTOSAVE_DEBOUNCE_MS = 500;

type LoadState = "loading" | "ready" | "error";
// "failed" exists so the indicator can say a save did not happen —
// showing "Сохранено" for a request that errored is how work gets lost.
type SaveStatus = "idle" | "saving" | "saved" | "failed";

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

  // The fixed footer's height decides how much room the canvas gets and how
  // much the page must reserve below it. Guessing it with a constant was
  // wrong every time it changed shape — a publish button, a paywall with one
  // method, a paywall with three — so it is measured instead.
  const footerRef = useRef<HTMLDivElement | null>(null);
  const screenRef = useRef<HTMLDivElement | null>(null);

  // Measured, never guessed — and re-measured on *every* render, because the
  // things being measured change without resizing anything: the footer swaps
  // between a publish button, an expanded token form and a paywall. Two
  // different `.app-footer` elements share this ref, so a ResizeObserver
  // attached once at mount ended up watching a detached node and `--footer-h`
  // sat at a stale 110px while the real footer was 52px — which is how the
  // publish confirm button ended up below the fold on every laptop.
  const measure = useCallback(() => {
    const footer = footerRef.current;
    const screen = screenRef.current;
    if (!footer || !screen) return;
    screen.style.setProperty("--footer-h", `${Math.ceil(footer.getBoundingClientRect().height)}px`);
    const canvas = screen.querySelector<HTMLElement>(".flow-canvas");
    if (canvas) {
      const above = canvas.getBoundingClientRect().top - screen.getBoundingClientRect().top;
      screen.style.setProperty("--above-h", `${Math.ceil(Math.max(above, 0))}px`);
    }
  }, []);

  useLayoutEffect(measure);

  // And once more for the changes React never hears about — a web font
  // landing, the browser chrome collapsing on scroll.
  useEffect(() => {
    const footer = footerRef.current;
    if (!footer) return;
    const observer = new ResizeObserver(measure);
    observer.observe(footer);
    window.addEventListener("resize", measure);
    return () => {
      observer.disconnect();
      window.removeEventListener("resize", measure);
    };
  }, [measure]);

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
    failedSaves.current.delete(key);
    if (pendingSaves.current.size === 0) {
      setSaveStatus(failedSaves.current.size > 0 ? "failed" : "saved");
    }
  }, []);

  // A save that did not happen must never show as "Сохранено". The whole
  // point of an autosave indicator is that the user trusts it and closes the
  // tab; an expired session or a restarted API would otherwise quietly eat
  // everything typed since.
  const failedSaves = useRef<Set<string>>(new Set());
  const markFailed = useCallback((key: string) => {
    failedSaves.current.add(key);
    pendingSaves.current.delete(key);
    if (pendingSaves.current.size === 0) setSaveStatus("failed");
  }, []);

  const retryFailedSaves = useCallback(async () => {
    if (!bot) return;
    setSaveStatus("saving");
    try {
      // Re-send the whole bot as it stands locally: what failed is whatever
      // the server has not got, and the client's copy is the truth here.
      // Positions and the start block are included — leaving them out meant
      // the indicator said "Сохранено" for changes still only in the browser.
      await Promise.all(
        bot.blocks.map((block) =>
          builderApi.updateBlock(bot.id, block.id, {
            content: block.content,
            next_block_id: block.next_block_id,
            position_x: block.position_x,
            position_y: block.position_y,
          }),
        ),
      );
      await builderApi.setStartBlock(bot.id, bot.start_block_id);
      if (bot.name) await builderApi.renameBot(bot.id, bot.name);
      failedSaves.current.clear();
      setSaveStatus("saved");
    } catch {
      setSaveStatus("failed");
    }
  }, [bot]);

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
          markSettled(blockId);
        } catch {
          markFailed(blockId);
        }
      }, AUTOSAVE_DEBOUNCE_MS);
    },
    [bot, markPending, markSettled, markFailed],
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
      // Kept so a failed delete can be undone on the canvas instead of the
      // block reappearing out of nowhere on the next reload.
      const before = bot.blocks;
      const startBefore = bot.start_block_id;

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
        // The block is already gone from the canvas, so failing quietly here
        // meant it silently came back on the next reload. Put it back now and
        // say so, rather than letting the canvas and the database disagree.
        setBot((current) =>
          current ? { ...current, blocks: before, start_block_id: startBefore } : current,
        );
        markFailed(blockId);
      }
    },
    [bot, markFailed],
  );

  const handleAdd = useCallback(
    async (blockType: BlockType, position: { x: number; y: number }): Promise<string> => {
      if (!bot) throw new Error("Bot not loaded");
      const defaultContent = BLOCK_TYPE_BY_ID[blockType].defaultContent();
      if (blockType === "payment") {
        // The shop's own currency, not a constant. Falls back to RUB only
        // when no cash desk is connected yet — and the block picks the real
        // one up as soon as one is, because PaymentEditor writes back
        // whatever the provider actually supports.
        const connected = paymentProviders.find((p) => p.slug === paymentSettings?.provider);
        defaultContent.currency = connected?.currencies[0] ?? "RUB";
      }
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
    [bot, paymentProviders, paymentSettings],
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
        .then(() => markSettled(`${blockId}:next`))
        .catch(() => markFailed(`${blockId}:next`));
    },
    [bot, markPending, markSettled, markFailed],
  );

  const handleSetStart = useCallback(
    (blockId: string | null) => {
      if (!bot) return;
      setBot((prev) => (prev ? { ...prev, start_block_id: blockId } : prev));
      markPending("start");
      builderApi
        .setStartBlock(bot.id, blockId)
        .then(() => markSettled("start"))
        .catch(() => markFailed("start"));
    },
    [bot, markPending, markSettled, markFailed],
  );

  const handleSetPosition = useCallback(
    (blockId: string, x: number, y: number) => {
      if (!bot) return;
      setBot((prev) =>
        prev ? { ...prev, blocks: prev.blocks.map((b) => (b.id === blockId ? { ...b, position_x: x, position_y: y } : b)) } : prev,
      );
      markPending(`${blockId}:pos`);
      builderApi
        .updateBlock(bot.id, blockId, { position_x: x, position_y: y })
        .then(() => markSettled(`${blockId}:pos`))
        .catch(() => markFailed(`${blockId}:pos`));
    },
    [bot, markPending, markSettled, markFailed],
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
          markSettled("name");
        } catch {
          markFailed("name");
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

  return (
    // The paywall card is roughly twice the height of the publish button, and
    // the footer is fixed — so the space reserved for it at the bottom of the
    // screen has to know which one is showing, or the card lands on top of the
    // "+ Добавить блок" bar and no block can be added on a phone.
    <div ref={screenRef} className="screen screen--builder">
      <header className="app-header">
        {/* One bar for "out of here" and the tools. On a phone these used to
            be two stacked 44px rows above the title — 56px of the canvas
            spent on a layout accident. */}
        <div className="app-header__bar">
          <button type="button" className="back-link" onClick={onBack}>
            ← Мои боты
          </button>
          <div className="app-header__actions">
            {!isMiniApp && <ThemeToggle />}
            {!isMiniApp && (
              <button
                type="button"
                className={`bot-payments-button ${paymentSettings?.provider ? "bot-payments-button--on" : ""}`}
                onClick={() => setPaymentPanelOpen(true)}
                title="Платёжная система, через которую бот принимает деньги"
              >
                {/* Two labels, one shown at a time by CSS: on a 390px phone
                    this bar also carries "← Мои боты", and the long form
                    squeezed the way out of the builder to 49px. */}
                💳 <span className="bot-payments-button__long">
                  {paymentSettings?.provider ? "Касса подключена" : "Подключить кассу"}
                </span>
                <span className="bot-payments-button__short">Касса</span>
              </button>
            )}
            <button
              type="button"
              className="bot-delete-button"
              onClick={handleDeleteBot}
              disabled={deleting}
              aria-label="Удалить бота"
            >
              🗑
            </button>
          </div>
        </div>
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
              <h1
                className="app-header__name"
                role="button"
                tabIndex={0}
                aria-label="Переименовать бота"
                onClick={() => setEditingName(true)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" || e.key === " ") {
                    e.preventDefault();
                    setEditingName(true);
                  }
                }}
              >
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
                  {saveStatus === "saving" ? " · Сохраняем…" : saveStatus === "failed" ? "" : " · Сохранено"}
                  {saveStatus === "failed" && (
                    <button type="button" className="save-status__retry" onClick={retryFailedSaves}>
                      · Не сохранено — повторить
                    </button>
                  )}
                </span>
              )}
            </p>
          </div>
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
          <>
            {/* Two versions on purpose. On a phone the long one ran to four
                lines — 80px of the 844 the canvas is fighting for — and half
                of it described a block library that only exists on a big
                screen. */}
            <p className="app-hint app-hint--wide">
              Блоки добавляются кнопкой «+ Добавить блок» под холстом (на большом экране — из списка слева).
              Нажми на блок, чтобы изменить его; потяни от кружка снизу или от кнопки — чтобы решить, что дальше.
            </p>
            <p className="app-hint app-hint--narrow">Нажми на блок, чтобы изменить. Потяни от кружка — что дальше.</p>
          </>
        )
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
        onPreview={bot.blocks.length > 0 ? () => setPreviewOpen(true) : undefined}
        onOpenPaymentSettings={() => setPaymentPanelOpen(true)}
        disabled={isMiniApp}
      />

      {bot.status === "draft" && (
        <div className="app-footer" ref={footerRef}>
          {publication?.required && !publication.paid ? (
            <PublishPaywall
              botId={bot.id}
              info={publication}
              onPaid={() => setPublication((prev) => (prev ? { ...prev, paid: true } : prev))}
            />
          ) : (
            <PublishButton
              onPublish={handlePublish}
              disabled={bot.blocks.length === 0}
              orphanCount={orphanBlocks(bot.blocks, bot.start_block_id).length}
            />
          )}
        </div>
      )}

      {bot.status === "active" && (
        <div className="app-footer" ref={footerRef}>
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
