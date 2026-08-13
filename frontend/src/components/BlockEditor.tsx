import type { BlockContent, BlockType, ButtonAction } from "../api/builderApi";

interface Props {
  blockType: BlockType;
  content: BlockContent;
  onChange: (content: BlockContent) => void;
}

const TEXT_PLACEHOLDERS: Record<string, string> = {
  welcome: "Привет! Рады видеть тебя здесь 👋",
  description: "Расскажи, чем занимается твой бизнес…",
  delivery: "Вот твой файл / ссылка / инструкция",
};

function TextBlockEditor({ blockType, content, onChange }: Props) {
  return (
    <textarea
      className="block-editor__textarea"
      placeholder={TEXT_PLACEHOLDERS[blockType]}
      value={content.text ?? ""}
      onChange={(e) => onChange({ ...content, text: e.target.value })}
      rows={4}
    />
  );
}

function emptyButton(): ButtonAction {
  return { label: "", action_type: "text", action_value: "" };
}

function ButtonsBlockEditor({ content, onChange }: Props) {
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
    <div className="buttons-editor">
      {buttons.map((button, index) => (
        <div className="buttons-editor__row" key={index}>
          <input
            className="buttons-editor__label"
            placeholder="Текст кнопки"
            value={button.label}
            onChange={(e) => updateButton(index, { label: e.target.value })}
          />
          <select
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
          <button type="button" className="buttons-editor__remove" onClick={() => removeButton(index)} aria-label="Удалить кнопку">
            ✕
          </button>
        </div>
      ))}
      <button type="button" className="buttons-editor__add" onClick={addButton}>
        + Добавить кнопку
      </button>
    </div>
  );
}

export function BlockEditor(props: Props) {
  if (props.blockType === "buttons") {
    return <ButtonsBlockEditor {...props} />;
  }
  return <TextBlockEditor {...props} />;
}
