import { useSortable } from "@dnd-kit/sortable";
import { CSS } from "@dnd-kit/utilities";

import type { BotBlock } from "../api/builderApi";
import { BlockEditor } from "./BlockEditor";

const BLOCK_LABELS: Record<BotBlock["block_type"], string> = {
  welcome: "👋 Приветствие",
  description: "📝 Описание",
  buttons: "🔘 Кнопки",
  delivery: "🎁 Выдача",
};

function summarize(block: BotBlock): string {
  if (block.block_type === "buttons") {
    const count = block.content.buttons?.length ?? 0;
    return count ? `${count} кнопок(и)` : "Кнопки не заданы";
  }
  const text = block.content.text?.trim();
  return text ? (text.length > 60 ? `${text.slice(0, 60)}…` : text) : "Пусто — нажми, чтобы заполнить";
}

interface Props {
  block: BotBlock;
  expanded: boolean;
  onToggle: () => void;
  onChange: (content: BotBlock["content"]) => void;
  onDelete: () => void;
  disabled?: boolean;
}

export function BlockCard({ block, expanded, onToggle, onChange, onDelete, disabled }: Props) {
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } = useSortable({
    id: block.id,
    disabled,
  });

  const style = {
    transform: CSS.Transform.toString(transform),
    transition,
    opacity: isDragging ? 0.6 : 1,
  };

  return (
    <div ref={setNodeRef} style={style} className="block-card">
      <div className="block-card__header">
        {!disabled && (
          <button type="button" className="block-card__handle" aria-label="Перетащить" {...attributes} {...listeners}>
            ⠿
          </button>
        )}
        <button type="button" className="block-card__title" onClick={onToggle}>
          <span className="block-card__label">{BLOCK_LABELS[block.block_type]}</span>
          <span className="block-card__summary">{summarize(block)}</span>
        </button>
        {!disabled && (
          <button type="button" className="block-card__delete" aria-label="Удалить блок" onClick={onDelete}>
            🗑
          </button>
        )}
      </div>

      {expanded && (
        <div className="block-card__body">
          <BlockEditor blockType={block.block_type} content={block.content} onChange={onChange} />
        </div>
      )}
    </div>
  );
}
