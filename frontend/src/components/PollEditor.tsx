import type { BlockContent } from "../api/builderApi";

interface Props {
  content: BlockContent;
  onChange: (content: BlockContent) => void;
}

const MIN_OPTIONS = 2;
const MAX_OPTIONS = 10;

/** Compact inline editor for a poll block — question + option list, lives inside a chat bubble. */
export function PollEditor({ content, onChange }: Props) {
  const options = content.options ?? ["", ""];

  function updateOption(index: number, value: string) {
    onChange({ ...content, options: options.map((o, i) => (i === index ? value : o)) });
  }

  function removeOption(index: number) {
    onChange({ ...content, options: options.filter((_, i) => i !== index) });
  }

  function addOption() {
    if (options.length >= MAX_OPTIONS) return;
    onChange({ ...content, options: [...options, ""] });
  }

  return (
    <div className="poll-editor" onClick={(e) => e.stopPropagation()}>
      <textarea
        className="poll-editor__question"
        placeholder="Вопрос опроса"
        value={content.question ?? ""}
        onChange={(e) => onChange({ ...content, question: e.target.value })}
        onPointerDown={(e) => e.stopPropagation()}
        rows={1}
      />
      {options.map((option, index) => (
        <div className="poll-editor__option" key={index}>
          <span className="poll-editor__bullet" aria-hidden="true">
            {index + 1}
          </span>
          <input
            placeholder={`Вариант ${index + 1}`}
            value={option}
            onChange={(e) => updateOption(index, e.target.value)}
          />
          {options.length > MIN_OPTIONS && (
            <button type="button" className="poll-editor__remove" onClick={() => removeOption(index)} aria-label="Удалить вариант">
              ✕
            </button>
          )}
        </div>
      ))}
      {options.length < MAX_OPTIONS && (
        <button type="button" className="buttons-editor__add" onClick={addOption}>
          + Добавить вариант
        </button>
      )}
    </div>
  );
}
