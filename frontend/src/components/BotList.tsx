import { useCallback, useEffect, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";

import { type Bot, ApiError, builderApi } from "../api/builderApi";
import { confirmDialog, openExternal } from "../hooks/useTelegramWebApp";
import { useSwipeToDismiss } from "../hooks/useSwipeToDismiss";
import { useEscape } from "../hooks/useEscape";
import { BOT_TEMPLATES, blocksLabel } from "../templates";

const EASE_OUT = [0.16, 1, 0.3, 1] as const;

interface Props {
  greetingName?: string;
  isMiniApp?: boolean;
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
  return blocksLabel(count);
}

export function BotList({ greetingName, isMiniApp, onOpen }: Props) {
  const [bots, setBots] = useState<Bot[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [creatingTemplateId, setCreatingTemplateId] = useState<string | null>(null);
  const [deletingId, setDeletingId] = useState<string | null>(null);
  const [pickerOpen, setPickerOpen] = useState(false);
  useEscape(() => setPickerOpen(false), pickerOpen);
  const { sheetRef, handleProps } = useSwipeToDismiss(() => {
    if (!creatingTemplateId) setPickerOpen(false);
  });

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

  async function handlePickTemplate(templateId: string) {
    const template = BOT_TEMPLATES.find((t) => t.id === templateId);
    if (!template) return;

    setCreatingTemplateId(templateId);
    try {
      const bot = await builderApi.createBot();
      if (template.suggestedName) {
        await builderApi.renameBot(bot.id, template.suggestedName);
      }
      // Sequential on purpose — order_index falls back to "append", so
      // blocks must land in template order, not race each other.
      // Laid out as a column, stepping right after a buttons block so its
      // branch arrow reads as a branch instead of looping back on itself.
      const created = [];
      let x = 80;
      // Clear of the "▶ Старт" pseudo-node, which sits at (40, 40).
      let y = 170;
      for (const [index, block] of template.blocks.entries()) {
        if (template.blocks[index - 1]?.block_type === "buttons") x += 280;
        created.push(await builderApi.createBlock(bot.id, block.block_type, block.content, { x, y }));
        y += 190;
      }

      // Then wire them into an actual chain. A template arriving as a pile
      // of disconnected blocks would send nothing but its first message —
      // and it's also how someone learns what the arrows are for: the first
      // bot they open already shows a working one.
      for (let i = 0; i < created.length - 1; i++) {
        const current = created[i];
        const next = created[i + 1];
        const buttons = current.content.buttons ?? [];
        // A buttons block stops and waits for a tap, so its "next" is the
        // button's own branch, not the plain arrow (see bot_dispatcher.py).
        const branchIndex = buttons.findIndex((b) => b.action_type !== "url");
        if (current.block_type === "buttons" && branchIndex !== -1) {
          await builderApi.updateBlock(bot.id, current.id, {
            content: {
              ...current.content,
              buttons: buttons.map((b, index) => (index === branchIndex ? { ...b, target_block_id: next.id } : b)),
            },
          });
        } else {
          await builderApi.updateBlock(bot.id, current.id, { next_block_id: next.id });
        }
      }
      setPickerOpen(false);
      onOpen(bot.id);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Не удалось создать бота");
    } finally {
      setCreatingTemplateId(null);
    }
  }

  function handleCreateClick() {
    if (isMiniApp) {
      // Building/editing a bot is a full drag-and-drop canvas — awkward
      // inside Telegram's WebView. Send the user to the real browser
      // instead of opening the in-app template picker.
      openExternal(`${window.location.origin}/`);
      return;
    }
    setPickerOpen(true);
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
    <div className="screen screen--list">
      <header className="app-header">
        <div className="app-header__top">
          <div className="app-header__icon" aria-hidden="true">
            🏭
          </div>
          <div className="app-header__titles">
            <h1>Мои боты</h1>
            {greetingName && <p className="app-header__greeting">Привет, {greetingName}!</p>}
          </div>
          {!isMiniApp && (
            <button type="button" className="header-create-button" onClick={handleCreateClick}>
              + Новый бот
            </button>
          )}
        </div>
        {isMiniApp && (
          <p className="app-hint" style={{ marginTop: "var(--sp-3)" }}>
            📱 Здесь виден статус и кнопка публикации. Собирать бота — в браузере: открой {window.location.host},
            с телефона это тоже работает.
          </p>
        )}
      </header>

      {error && <p className="publish-form__error" style={{ marginBottom: "var(--sp-3)" }}>{error}</p>}

      {bots === null ? (
        <div className="bot-list" aria-hidden="true">
          {[0, 1, 2].map((i) => (
            <div key={i} className="bot-card bot-card--skeleton" style={{ animationDelay: `${i * 80}ms` }}>
              <div className="skeleton-block skeleton-block--icon" />
              <div className="bot-card__info">
                <div className="skeleton-block" style={{ width: "62%", height: 14 }} />
                <div className="skeleton-block" style={{ width: "40%", height: 11, marginTop: 6 }} />
              </div>
            </div>
          ))}
        </div>
      ) : (
        <div className="bot-list">
          {/* Empty-state and cards share one AnimatePresence so deleting the
              last bot crossfades into "no bots yet" instead of the whole
              list container getting swapped out mid-exit-animation. */}
          <AnimatePresence initial={false} mode="popLayout">
            {bots.length === 0 && (
              <motion.div
                key="empty"
                className="bot-list__empty"
                initial={{ opacity: 0, y: 8 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0 }}
                transition={{ duration: 0.3, ease: EASE_OUT }}
              >
                {/* Points at the header's "+ Новый бот" — the one control on
                    an otherwise empty screen, and the one thing a first-time
                    visitor has to find. Desktop only: below 960px that button
                    is hidden and the footer button takes over. */}
                {!isMiniApp && (
                  <div className="empty-arrow" aria-hidden="true">
                    <span className="empty-arrow__label">или сюда</span>
                    <svg viewBox="0 0 160 132" fill="none">
                      <path
                        d="M8 126C44 118 104 104 124 30"
                        stroke="currentColor"
                        strokeWidth="2.5"
                        strokeLinecap="round"
                        strokeDasharray="7 9"
                      />
                      <path d="M109 49L124 26L139 50" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" />
                    </svg>
                  </div>
                )}

                <div className="empty-state">
                  <div className="empty-state__icon" aria-hidden="true">
                    🏭
                  </div>
                  <p className="empty-state__title">Здесь появятся твои боты</p>
                  <p className="empty-state__hint">
                    {isMiniApp
                      ? "Собери первого в браузере — там визуальный холст с блоками и стрелками"
                      : "Возьми готовый сценарий: блоки уже расставлены и связаны — останется вписать свой текст"}
                  </p>

                  {!isMiniApp && (
                    <>
                      <button type="button" className="empty-state__cta" onClick={handleCreateClick}>
                        ✨ Собрать первого бота
                      </button>
                      <ol className="empty-state__steps">
                        <li>
                          <span>1</span> Выбери сценарий
                        </li>
                        <li>
                          <span>2</span> Правь блоки на холсте
                        </li>
                        <li>
                          <span>3</span> Вставь токен — готово
                        </li>
                      </ol>
                    </>
                  )}
                </div>
              </motion.div>
            )}
            {bots.map((bot, index) => (
              <motion.button
                type="button"
                key={bot.id}
                layout
                className="bot-card"
                onClick={() => onOpen(bot.id)}
                disabled={deletingId === bot.id}
                initial={{ opacity: 0, y: 14, scale: 0.96 }}
                animate={{ opacity: 1, y: 0, scale: 1 }}
                exit={{ opacity: 0, scale: 0.9, transition: { duration: 0.16, ease: "easeIn" } }}
                transition={{ duration: 0.32, delay: index * 0.04, ease: EASE_OUT }}
                whileHover={{ y: -3, transition: { duration: 0.15, ease: EASE_OUT } }}
                whileTap={{ scale: 0.98 }}
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
              </motion.button>
            ))}
          </AnimatePresence>
        </div>
      )}

      <div className="app-footer">
        <button type="button" className="publish-button" onClick={handleCreateClick}>
          {isMiniApp ? "Открыть в браузере →" : "+ Новый бот"}
        </button>
      </div>

      {pickerOpen && (
        <>
          <div className="sheet-backdrop" onClick={() => !creatingTemplateId && setPickerOpen(false)} />
          <div className="sheet sheet--picker" ref={sheetRef}>
            <div className="sheet__handle" {...handleProps} />
            <div className="sheet__head">
              <div className="sheet__head-text">
                <p className="sheet__title">С чего начнём?</p>
                <p className="sheet__subtitle">
                  Шаблон — это готовый сценарий: блоки уже расставлены и связаны стрелками. Любой можно
                  переписать под себя.
                </p>
              </div>
              <button
                type="button"
                className="sheet__close"
                aria-label="Закрыть"
                onClick={() => !creatingTemplateId && setPickerOpen(false)}
              >
                ✕
              </button>
            </div>
            <div className="template-list">
              {BOT_TEMPLATES.map((template) => (
                <button
                  key={template.id}
                  type="button"
                  className={`template-card template-card--${template.accent}`}
                  onClick={() => handlePickTemplate(template.id)}
                  disabled={creatingTemplateId !== null}
                >
                  <span className="template-card__icon" aria-hidden="true">
                    {template.icon}
                  </span>
                  <span className="template-card__text">
                    <span className="template-card__label">{template.label}</span>
                    <span className="template-card__pitch">{template.pitch}</span>
                    <span className="template-card__badge">
                      {template.blocks.length > 0 ? blocksLabel(template.blocks.length) : "чистый холст"}
                    </span>
                  </span>
                  {creatingTemplateId === template.id ? (
                    <span className="template-card__spinner" aria-hidden="true" />
                  ) : (
                    <span className="template-card__go" aria-hidden="true">
                      →
                    </span>
                  )}
                </button>
              ))}
            </div>
          </div>
        </>
      )}
    </div>
  );
}
