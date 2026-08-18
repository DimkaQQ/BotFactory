import type { BotBlock } from "../../api/builderApi";
import { BLOCK_TYPE_BY_ID } from "../../blockTypes";
import { ButtonsEditor } from "../ButtonsEditor";
import { MediaEditor } from "../MediaEditor";
import { PollEditor } from "../PollEditor";

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

interface Props {
  block: BotBlock;
  onChange: (content: BotBlock["content"]) => void;
  onDelete: () => void;
  onClose: () => void;
}

/** The block's full editor, opened on the side (desktop) / as a bottom sheet
 * (mobile) when its node is clicked on the flow canvas — this is where
 * MediaEditor/PollEditor/ButtonsEditor now live, having moved out of the old
 * inline chat-bubble editor they were built for. */
export function BlockEditPanel({ block, onChange, onDelete, onClose }: Props) {
  const def = BLOCK_TYPE_BY_ID[block.block_type];
  const isMediaBlock = block.block_type === "image" || block.block_type === "video";
  const isPollBlock = block.block_type === "poll";
  const isButtonsBlock = block.block_type === "buttons";
  const isDelayBlock = block.block_type === "delay";
  const seconds = Math.max(0, Math.min(Number(block.content.seconds ?? 2), 15));

  return (
    <>
      <div className="sheet-backdrop edit-panel-backdrop" onClick={onClose} />
      <div className="edit-panel">
        <div className="edit-panel__header">
          <span className={`edit-panel__icon block-card__icon--${def.accent}`} aria-hidden="true">
            {def.icon}
          </span>
          <span className="edit-panel__title">{def.label}</span>
          <button type="button" className="edit-panel__delete" aria-label="Удалить блок" onClick={onDelete}>
            🗑
          </button>
          <button type="button" className="edit-panel__close" aria-label="Закрыть" onClick={onClose}>
            ✕
          </button>
        </div>

        <div className="edit-panel__body">
          {isDelayBlock ? (
            <div className="chat-delay__control edit-panel__delay">
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
          ) : isMediaBlock ? (
            <MediaEditor kind={block.block_type as "image" | "video"} content={block.content} onChange={onChange} />
          ) : isPollBlock ? (
            <PollEditor content={block.content} onChange={onChange} />
          ) : (
            <textarea
              className="chat-bubble__textarea edit-panel__textarea"
              autoFocus
              value={block.content.text ?? ""}
              placeholder={PLACEHOLDER[block.block_type]}
              onChange={(e) => onChange({ ...block.content, text: e.target.value })}
              rows={4}
            />
          )}

          {isButtonsBlock && (
            <div className="edit-panel__buttons">
              <p className="edit-panel__section-label">Кнопки</p>
              <ButtonsEditor content={block.content} onChange={onChange} />
              <p className="app-hint edit-panel__hint">
                Потяни стрелку от кнопки на канвасе, чтобы решить, куда она ведёт.
              </p>
            </div>
          )}
        </div>
      </div>
    </>
  );
}
