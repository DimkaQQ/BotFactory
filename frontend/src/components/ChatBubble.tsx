import { useEffect, useRef, useState } from "react";
import { useSortable } from "@dnd-kit/sortable";
import { CSS } from "@dnd-kit/utilities";

import type { BotBlock } from "../api/builderApi";
import { ButtonsEditor } from "./ButtonsEditor";
import { MediaEditor } from "./MediaEditor";
import { PollEditor } from "./PollEditor";

const PLACEHOLDER: Record<BotBlock["block_type"], string> = {
  welcome: "Привет! Рады видеть тебя здесь 👋",
  description: "Расскажи, чем занимается твой бизнес…",
  image: "Добавь ссылку на изображение и подпись",
  video: "Добавь ссылку на видео и подпись",
  buttons: "Текст перед кнопками (необязательно)",
  poll: "О чём спросим?",
  delivery: "Вот твой файл / ссылка / инструкция",
  delay: "",
};

const DELAY_PRESETS = [1, 2, 3, 5, 8, 10];

function autoResize(el: HTMLTextAreaElement | null) {
  if (!el) return;
  el.style.height = "auto";
  el.style.height = `${el.scrollHeight}px`;
}

interface Props {
  block: BotBlock;
  isLast: boolean;
  active: boolean;
  staggerIndex?: number;
  removing?: boolean;
  onActivate: () => void;
  onChange: (content: BotBlock["content"]) => void;
  onDelete: () => void;
  disabled?: boolean;
}

export function ChatBubble({ block, isLast, active, staggerIndex, removing, onActivate, onChange, onDelete, disabled }: Props) {
  const textareaRef = useRef<HTMLTextAreaElement | null>(null);

  const { attributes, listeners, setNodeRef, transform, transition, isDragging } = useSortable({
    id: block.id,
    disabled: disabled || active,
  });

  const style = {
    transform: CSS.Transform.toString(transform),
    transition,
    opacity: isDragging ? 0.55 : 1,
    // Each row fades in with a small stagger on first mount — makes the
    // canvas feel alive instead of the whole list just appearing at once.
    // (Only affects a freshly-created DOM node; React never replays it on
    // existing bubbles when the list re-renders.)
    "--stagger": staggerIndex ?? 0,
  } as React.CSSProperties;

  useEffect(() => {
    if (active && block.block_type !== "delay") {
      autoResize(textareaRef.current);
      textareaRef.current?.focus();
    }
  }, [active, block.block_type]);

  // Hooks must run unconditionally (before the early "delay" return below),
  // even though only the image/video branch further down actually uses this.
  const [imgBroken, setImgBroken] = useState(false);
  const mediaUrlForReset = block.content.media_file_id;
  useEffect(() => setImgBroken(false), [mediaUrlForReset]);

  const deleteButton = !disabled && (
    <button
      type="button"
      className="chat-bubble__delete"
      aria-label="Удалить"
      onPointerDown={(e) => e.stopPropagation()}
      onClick={(e) => {
        e.stopPropagation();
        onDelete();
      }}
    >
      ✕
    </button>
  );

  // A pause has no message of its own — render it as a slim system pill
  // instead of a chat bubble, so it reads as "the bot waits here" rather
  // than "the bot says this".
  if (block.block_type === "delay") {
    const seconds = Math.max(0, Math.min(Number(block.content.seconds ?? 2), 15));
    return (
      <div
        ref={setNodeRef}
        style={style}
        className={`chat-row chat-row--delay ${removing ? "chat-row--removing" : ""}`}
        data-block-id={block.id}
      >
        <div
          className={`chat-delay ${active ? "chat-delay--editing" : ""}`}
          {...(!disabled && !active ? attributes : {})}
          {...(!disabled && !active ? listeners : {})}
          onClick={() => !disabled && !active && onActivate()}
        >
          {deleteButton}
          <span className="chat-delay__icon" aria-hidden="true">
            ⏱
          </span>
          {active ? (
            <div className="chat-delay__control" onPointerDown={(e) => e.stopPropagation()}>
              {DELAY_PRESETS.map((s) => (
                <button
                  key={s}
                  type="button"
                  className={`chat-delay__preset ${seconds === s ? "chat-delay__preset--active" : ""}`}
                  onClick={() => onChange({ ...block.content, seconds: s })}
                >
                  {s}с
                </button>
              ))}
            </div>
          ) : (
            <span className="chat-delay__label">Пауза {seconds} сек — дальше бот немного помолчит</span>
          )}
        </div>
      </div>
    );
  }

  const buttons = block.content.buttons ?? [];
  const hasText = !!block.content.text?.trim();
  const isButtonsBlock = block.block_type === "buttons";
  const isMediaBlock = block.block_type === "image" || block.block_type === "video";
  const isPollBlock = block.block_type === "poll";
  const mediaUrl = block.content.media_file_id;
  const pollOptions = (block.content.options ?? []).filter((o) => o.trim());
  const hasRealButton = buttons.some((b) => b.label.trim() || b.action_value.trim());

  // Mirrors the backend's "nothing to send" guard (bot_dispatcher.py) —
  // a block that would silently vanish from the real bot used to just...
  // silently vanish, with no clue why. Flag it here instead.
  const isEmptyInBot = isMediaBlock
    ? !mediaUrl && !hasText
    : isButtonsBlock
      ? !hasRealButton && !hasText
      : isPollBlock
        ? !block.content.question?.trim() || pollOptions.length < 2
        : !hasText;

  return (
    <div ref={setNodeRef} style={style} className={`chat-row ${removing ? "chat-row--removing" : ""}`} data-block-id={block.id}>
      <div className="chat-row__avatar">{isLast && <span className="chat-avatar">🤖</span>}</div>

      <div className="chat-row__content">
        <div
          className={`chat-bubble ${active ? "chat-bubble--editing" : ""}`}
          {...(!disabled && !active ? attributes : {})}
          {...(!disabled && !active ? listeners : {})}
          onClick={() => !disabled && !active && onActivate()}
        >
          {deleteButton}

          {active ? (
            isMediaBlock ? (
              <MediaEditor kind={block.block_type as "image" | "video"} content={block.content} onChange={onChange} />
            ) : isPollBlock ? (
              <PollEditor content={block.content} onChange={onChange} />
            ) : (
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
            )
          ) : isMediaBlock ? (
            <>
              {mediaUrl ? (
                block.block_type === "image" ? (
                  imgBroken ? (
                    <div className="chat-bubble__media-thumb chat-bubble__media-thumb--empty">⚠️</div>
                  ) : (
                    <img className="chat-bubble__media-thumb" src={mediaUrl} alt="" onError={() => setImgBroken(true)} />
                  )
                ) : (
                  <div className="chat-bubble__media-thumb chat-bubble__media-thumb--video">▶</div>
                )
              ) : (
                <div className="chat-bubble__media-thumb chat-bubble__media-thumb--empty">
                  {block.block_type === "image" ? "🖼️" : "🎬"}
                </div>
              )}
              <p className={`chat-bubble__text ${hasText ? "" : "chat-bubble__text--placeholder"}`}>
                {hasText ? block.content.text : PLACEHOLDER[block.block_type]}
              </p>
            </>
          ) : isPollBlock ? (
            <>
              <p className={`chat-bubble__text ${block.content.question?.trim() ? "" : "chat-bubble__text--placeholder"}`}>
                {block.content.question?.trim() ? `📊 ${block.content.question}` : PLACEHOLDER.poll}
              </p>
              {pollOptions.length > 0 && (
                <div className="poll-preview">
                  {pollOptions.map((option, i) => (
                    <span key={i} className="poll-preview__option">
                      {option}
                    </span>
                  ))}
                </div>
              )}
            </>
          ) : (
            <p className={`chat-bubble__text ${hasText ? "" : "chat-bubble__text--placeholder"}`}>
              {hasText ? block.content.text : PLACEHOLDER[block.block_type]}
            </p>
          )}
        </div>

        {!active && isEmptyInBot && (
          <p className="chat-bubble__empty-warning">⚠️ Пусто — бот пропустит это сообщение</p>
        )}

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
