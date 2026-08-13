import type { BlockContent, ButtonAction } from "../api/builderApi";

interface Props {
  content: BlockContent;
  onChange: (content: BlockContent) => void;
}

function emptyButton(): ButtonAction {
  return { label: "", action_type: "text", action_value: "" };
}

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
        <div className="buttons-editor__item" key={index}>
          <div className="buttons-editor__item-row">
            <input
              className="buttons-editor__label"
              placeholder="Текст кнопки"
              value={button.label}
              onChange={(e) => updateButton(index, { label: e.target.value })}
            />
            <button type="button" className="buttons-editor__remove" onClick={() => removeButton(index)} aria-label="Удалить кнопку">
              ✕
            </button>
          </div>
          <div className="buttons-editor__item-row">
            <select
              className="buttons-editor__type"
              value={button.action_type}
              onChange={(e) => updateButton(index, { action_type: e.target.value as ButtonAction["action_type"] })}
            >
              <option value="text">Текст</option>
              <option value="url">Ссылка</option>
            </select>
            <input
              className="buttons-editor__value"
              placeholder={button.action_type === "url" ? "https://…" : "Что ответить"}
              value={button.action_value}
              onChange={(e) => updateButton(index, { action_value: e.target.value })}
            />
          </div>
        </div>
      ))}
      <button type="button" className="buttons-editor__add" onClick={addButton}>
        + Добавить кнопку
      </button>
    </div>
  );
}
