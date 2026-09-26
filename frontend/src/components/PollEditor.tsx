import { useEffect, useState } from "react";

import { type BlockContent, type PollResult, builderApi } from "../api/builderApi";

interface Props {
  content: BlockContent;
  onChange: (content: BlockContent) => void;
  /** Нужны, чтобы показать ответы. Без них опрос можно было задать и нельзя
   * прочитать: ответы писались в таблицу, которую не читал никто — ни
   * эндпоинта на экране, ни экрана. */
  botId?: string;
  blockId?: string;
}

const MIN_OPTIONS = 2;
const MAX_OPTIONS = 10;

/** Compact inline editor for a poll block — question + option list, lives inside a chat bubble. */
export function PollEditor({ content, onChange, botId, blockId }: Props) {
  const options = content.options ?? ["", ""];
  const [answers, setAnswers] = useState<PollResult | null>(null);

  useEffect(() => {
    if (!botId || !blockId) return;
    builderApi
      .getPollResults(botId)
      .then(({ polls }) => setAnswers(polls.find((poll) => poll.block_id === blockId) ?? null))
      .catch(() => undefined);
  }, [botId, blockId]);

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

      {/* Ответы. Анонимный опрос Telegram присылает без пользователя, то
          есть ответов не будет вовсе — это надо сказать, а не показывать
          вечный ноль. */}
      {content.anonymous ? (
        <p className="poll-editor__answers-note">
          Опрос анонимный — Telegram не присылает ответы, посчитать их не получится. Сними галочку, если
          хочешь видеть результаты.
        </p>
      ) : answers && answers.answered > 0 ? (
        <div className="poll-editor__answers">
          <p className="poll-editor__answers-title">Ответили: {answers.answered}</p>
          {answers.options.map((option) => {
            const share = answers.answered > 0 ? Math.round((option.votes / answers.answered) * 100) : 0;
            return (
              <div className="poll-editor__answer" key={option.label}>
                <span className="poll-editor__answer-label">{option.label || "—"}</span>
                <span className="poll-editor__answer-bar" aria-hidden="true">
                  <span style={{ width: `${share}%` }} />
                </span>
                <span className="poll-editor__answer-count">{option.votes}</span>
              </div>
            );
          })}
        </div>
      ) : (
        <p className="poll-editor__answers-note">Ответов пока нет — они появятся здесь.</p>
      )}
    </div>
  );
}
