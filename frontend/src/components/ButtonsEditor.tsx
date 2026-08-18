import { useEffect, useRef } from "react";

import type { BlockContent, ButtonAction } from "../api/builderApi";

interface Props {
  content: BlockContent;
  onChange: (content: BlockContent) => void;
}

function emptyButton(): ButtonAction {
  return { label: "", action_type: "text", action_value: "" };
}

const URL_SCHEME_RE = /^[a-zA-Z][a-zA-Z0-9+.-]*:\/\//;

/** Compact inline editor for a buttons block's button list — lives inside a chat bubble. */
export function ButtonsEditor({ content, onChange }: Props) {
  const buttons = content.buttons ?? [];

  function updateButton(index: number, patch: Partial<ButtonAction>) {
    const next = buttons.map((b, i) => (i === index ? { ...b, ...patch } : b));
    onChange({ ...content, buttons: next });
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
        <ButtonRow key={index} button={button} index={index} onUpdate={updateButton} onRemove={removeButton} />
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
  onUpdate: (index: number, patch: Partial<ButtonAction>) => void;
  onRemove: (index: number) => void;
}

function ButtonRow({ button, index, onUpdate, onRemove }: RowProps) {
  const valueRef = useRef<HTMLInputElement | null>(null);
  const actionType = useRef(button.action_type);
  actionType.current = button.action_type;

  // A native listener, not React's onBlur: the outside-tap that ends
  // editing (ChatCanvas) has to listen on "pointerdown" rather than
  // "click" (pointerdown-vs-click self-closing-activation tradeoff is
  // its own story — see ChatCanvas), which fires *before* the browser
  // resolves the resulting blur. A React synthetic onBlur here would
  // lose that race and never fire; a native listener on the element
  // itself doesn't, because it isn't routed through React's batched
  // event dispatch at all.
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
      <div className="buttons-editor__item-row">
        <input
          className="buttons-editor__label"
          placeholder="Текст кнопки"
          value={button.label}
          onChange={(e) => onUpdate(index, { label: e.target.value })}
        />
        <button type="button" className="buttons-editor__remove" onClick={() => onRemove(index)} aria-label="Удалить кнопку">
          ✕
        </button>
      </div>
      <div className="buttons-editor__item-row">
        <select
          className="buttons-editor__type"
          value={button.action_type}
          onChange={(e) => onUpdate(index, { action_type: e.target.value as ButtonAction["action_type"] })}
        >
          <option value="text">Текст</option>
          <option value="url">Ссылка</option>
        </select>
        <input
          ref={valueRef}
          className="buttons-editor__value"
          placeholder={button.action_type === "url" ? "https://…" : "Что ответить"}
          value={button.action_value}
          onChange={(e) => onUpdate(index, { action_value: e.target.value })}
        />
      </div>
    </div>
  );
}
