import { useEffect, useRef } from "react";

import type { BlockContent, BotBlock, ButtonAction } from "../api/builderApi";
import { BLOCK_TYPE_BY_ID } from "../blockTypes";

interface Props {
  content: BlockContent;
  onChange: (content: BlockContent) => void;
  /** Every block of this bot — used to name the block a button leads to
   * ("ведёт к: 🎁 Выдача") instead of showing a raw uuid or nothing at all. */
  blocks?: BotBlock[];
}

function emptyButton(): ButtonAction {
  return { label: "", action_type: "text", action_value: "" };
}

const URL_SCHEME_RE = /^[a-zA-Z][a-zA-Z0-9+.-]*:\/\//;

/** Editor for a buttons block's button list. Each button is one card: what
 * it says, and what tapping it does — either "opens a link" (Telegram's own
 * URL button) or "continues the scenario", which is the arrow drawn from
 * that button on the canvas. */
export function ButtonsEditor({ content, onChange, blocks = [] }: Props) {
  const buttons = content.buttons ?? [];

  function updateButton(index: number, patch: Partial<ButtonAction>) {
    const next = buttons.map((b, i) => (i === index ? { ...b, ...patch } : b));
    onChange({ ...content, buttons: next });
  }

  /** Switching what a button does also drops a value that no longer means
   * anything: action_value is the URL for a link button and unused for a
   * scenario button, so carrying leftovers across the switch is how "Хочу
   * купить" ends up sitting in a field labelled "Адрес ссылки". */
  function setMode(index: number, mode: ButtonAction["action_type"]) {
    const current = buttons[index];
    if (!current || current.action_type === mode) return;
    const keepUrl = mode === "url" && URL_SCHEME_RE.test((current.action_value || "").trim());
    updateButton(index, { action_type: mode, action_value: keepUrl ? current.action_value : "" });
  }

  function removeButton(index: number) {
    onChange({ ...content, buttons: buttons.filter((_, i) => i !== index) });
  }

  function addButton() {
    onChange({ ...content, buttons: [...buttons, emptyButton()] });
  }

  return (
    <div className="buttons-editor" onClick={(e) => e.stopPropagation()}>
      {buttons.map((button, index) => (
        <ButtonRow
          key={index}
          button={button}
          index={index}
          blocks={blocks}
          onUpdate={updateButton}
          onSetMode={setMode}
          onRemove={removeButton}
        />
      ))}
      <button type="button" className="buttons-editor__add" onClick={addButton}>
        + Добавить кнопку
      </button>
    </div>
  );
}

interface RowProps {
  button: ButtonAction;
  index: number;
  blocks: BotBlock[];
  onUpdate: (index: number, patch: Partial<ButtonAction>) => void;
  onSetMode: (index: number, mode: ButtonAction["action_type"]) => void;
  onRemove: (index: number) => void;
}

function targetSummary(block: BotBlock): string {
  const def = BLOCK_TYPE_BY_ID[block.block_type];
  const text = (block.content.text || block.content.question || "").trim();
  return `${def.icon} ${def.label}${text ? ` — ${text.slice(0, 28)}${text.length > 28 ? "…" : ""}` : ""}`;
}

function ButtonRow({ button, index, blocks, onUpdate, onSetMode, onRemove }: RowProps) {
  const valueRef = useRef<HTMLInputElement | null>(null);
  const actionType = useRef(button.action_type);
  actionType.current = button.action_type;

  const isUrl = button.action_type === "url";
  const targetId = (button.target_block_id || "").trim();
  const target = targetId ? blocks.find((b) => b.id === targetId) : undefined;

  // A native listener, not React's onBlur — a holdover from when this
  // editor lived inline in a chat bubble, where the bubble's own
  // pointerdown-based outside-tap handler fired *before* the browser
  // resolved this field's blur, and React's synthetic onBlur lost that
  // race. It now lives in BlockEditPanel instead (a plain click-outside
  // backdrop, no such race), but the native listener is still correct —
  // just no longer load-bearing — so it stays rather than being ripped
  // out mid-migration.
  useEffect(() => {
    const el = valueRef.current;
    if (!el) return;

    function handleBlur() {
      if (actionType.current !== "url") return;
      const trimmed = el!.value.trim();
      if (trimmed && !URL_SCHEME_RE.test(trimmed)) {
        onUpdate(index, { action_value: `https://${trimmed}` });
      }
    }

    el.addEventListener("blur", handleBlur);
    return () => el.removeEventListener("blur", handleBlur);
  }, [index, onUpdate]);

  return (
    <div className="buttons-editor__item">
      <div className="buttons-editor__item-head">
        <span className="buttons-editor__item-n">Кнопка {index + 1}</span>
        <button type="button" className="buttons-editor__remove" onClick={() => onRemove(index)} aria-label="Удалить кнопку">
          ✕
        </button>
      </div>

      <label className="buttons-editor__field">
        <span className="buttons-editor__field-label">Что написано на кнопке</span>
        <input
          className="buttons-editor__label"
          placeholder="Например: Купить"
          value={button.label}
          onChange={(e) => onUpdate(index, { label: e.target.value })}
        />
      </label>

      <div className="buttons-editor__field">
        <span className="buttons-editor__field-label">Что будет, когда клиент нажмёт</span>
        <div className="buttons-editor__modes" role="radiogroup">
          <button
            type="button"
            role="radio"
            aria-checked={!isUrl}
            className={`buttons-editor__mode ${!isUrl ? "buttons-editor__mode--active" : ""}`}
            onClick={() => onSetMode(index, "text")}
          >
            <span className="buttons-editor__mode-title">➜ Продолжить сценарий</span>
            <span className="buttons-editor__mode-hint">бот пришлёт следующий блок</span>
          </button>
          <button
            type="button"
            role="radio"
            aria-checked={isUrl}
            className={`buttons-editor__mode ${isUrl ? "buttons-editor__mode--active" : ""}`}
            onClick={() => onSetMode(index, "url")}
          >
            <span className="buttons-editor__mode-title">🔗 Открыть ссылку</span>
            <span className="buttons-editor__mode-hint">сайт, оплата, запись</span>
          </button>
        </div>
      </div>

      {isUrl ? (
        <label className="buttons-editor__field">
          <span className="buttons-editor__field-label">Адрес ссылки</span>
          <input
            ref={valueRef}
            className="buttons-editor__value"
            placeholder="https://…"
            value={button.action_value}
            onChange={(e) => onUpdate(index, { action_value: e.target.value })}
          />
        </label>
      ) : target ? (
        <p className="buttons-editor__target">
          <span className="buttons-editor__target-label">Ведёт к блоку:</span> {targetSummary(target)}
        </p>
      ) : (
        <p className="buttons-editor__target buttons-editor__target--empty">
          Пока никуда не ведёт — потяни стрелку от этой кнопки на холсте к нужному блоку
        </p>
      )}
    </div>
  );
}
