import { useEffect, useRef } from "react";
import { useSortable } from "@dnd-kit/sortable";
import { CSS } from "@dnd-kit/utilities";

import type { BotBlock } from "../api/builderApi";
import { ButtonsEditor } from "./ButtonsEditor";

const PLACEHOLDER: Record<BotBlock["block_type"], string> = {
  welcome: "Привет! Рады видеть тебя здесь 👋",
  description: "Расскажи, чем занимается твой бизнес…",
  buttons: "Текст перед кнопками (необязательно)",
  delivery: "Вот твой файл / ссылка / инструкция",
};

function autoResize(el: HTMLTextAreaElement | null) {
  if (!el) return;
  el.style.height = "auto";
  el.style.height = `${el.scrollHeight}px`;
}

interface Props {
  block: BotBlock;
  isLast: boolean;
  active: boolean;
  onActivate: () => void;
  onChange: (content: BotBlock["content"]) => void;
  onDelete: () => void;
  disabled?: boolean;
}

export function ChatBubble({ block, isLast, active, onActivate, onChange, onDelete, disabled }: Props) {
  const textareaRef = useRef<HTMLTextAreaElement | null>(null);

  const { attributes, listeners, setNodeRef, transform, transition, isDragging } = useSortable({
    id: block.id,
    disabled: disabled || active,
  });

  const style = {
    transform: CSS.Transform.toString(transform),
    transition,
    opacity: isDragging ? 0.55 : 1,
  };

  useEffect(() => {
    if (active) {
      autoResize(textareaRef.current);
      textareaRef.current?.focus();
    }
  }, [active]);

  const buttons = block.content.buttons ?? [];
  const hasText = !!block.content.text?.trim();
  const isButtonsBlock = block.block_type === "buttons";

  return (
    <div ref={setNodeRef} style={style} className="chat-row" data-block-id={block.id}>
      <div className="chat-row__avatar">{isLast && <span className="chat-avatar">🤖</span>}</div>

      <div className="chat-row__content">
        <div
          className={`chat-bubble ${active ? "chat-bubble--editing" : ""}`}
          {...(!disabled && !active ? attributes : {})}
          {...(!disabled && !active ? listeners : {})}
          onClick={() => !disabled && !active && onActivate()}
        >
          {!disabled && (
            <button
              type="button"
              className="chat-bubble__delete"
              aria-label="Удалить сообщение"
              onPointerDown={(e) => e.stopPropagation()}
              onClick={(e) => {
                e.stopPropagation();
                onDelete();
              }}
            >
              ✕
            </button>
          )}

          {active ? (
            <textarea
              ref={textareaRef}
              className="chat-bubble__textarea"
              value={block.content.text ?? ""}
              placeholder={PLACEHOLDER[block.block_type]}
              onPointerDown={(e) => e.stopPropagation()}
              onChange={(e) => {
                onChange({ ...block.content, text: e.target.value });
                autoResize(e.target);
              }}
              rows={1}
            />
          ) : (
            <p className={`chat-bubble__text ${hasText ? "" : "chat-bubble__text--placeholder"}`}>
              {hasText ? block.content.text : PLACEHOLDER[block.block_type]}
            </p>
          )}
        </div>

        {isButtonsBlock && (
          <div className="chat-buttons" onPointerDown={(e) => e.stopPropagation()}>
            {active ? (
              <ButtonsEditor content={block.content} onChange={onChange} />
            ) : buttons.length > 0 ? (
              <div className="chat-buttons__preview" onClick={() => !disabled && onActivate()}>
                {buttons.map((button, i) => (
                  <span key={i} className="chat-buttons__pill">
                    {button.label || "…"}
                  </span>
                ))}
              </div>
            ) : (
              <button type="button" className="chat-buttons__ghost" onClick={() => !disabled && onActivate()}>
                + Добавить кнопку
              </button>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
