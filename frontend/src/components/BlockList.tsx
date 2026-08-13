import { useState } from "react";
import {
  DndContext,
  type DragEndEvent,
  KeyboardSensor,
  PointerSensor,
  closestCenter,
  useSensor,
  useSensors,
} from "@dnd-kit/core";
import { SortableContext, sortableKeyboardCoordinates, verticalListSortingStrategy } from "@dnd-kit/sortable";

import type { BlockType, BotBlock } from "../api/builderApi";
import { BlockCard } from "./BlockCard";

const BLOCK_TYPES: { type: BlockType; label: string; icon: string; accent: string }[] = [
  { type: "welcome", label: "Приветствие", icon: "👋", accent: "welcome" },
  { type: "description", label: "Описание", icon: "📝", accent: "description" },
  { type: "buttons", label: "Кнопки", icon: "🔘", accent: "buttons" },
  { type: "delivery", label: "Выдача", icon: "🎁", accent: "delivery" },
];

interface Props {
  blocks: BotBlock[];
  onReorder: (orderedIds: string[]) => void;
  onChangeContent: (blockId: string, content: BotBlock["content"]) => void;
  onDelete: (blockId: string) => void;
  onAdd: (blockType: BlockType) => void;
  disabled?: boolean;
}

function BlockTypeChips({ onAdd }: { onAdd: (type: BlockType) => void }) {
  return (
    <div className="block-chips">
      {BLOCK_TYPES.map(({ type, label, icon, accent }) => (
        <button key={type} type="button" className="block-chip" onClick={() => onAdd(type)}>
          <span className={`block-chip__icon block-card__icon--${accent}`} aria-hidden="true">
            {icon}
          </span>
          {label}
        </button>
      ))}
    </div>
  );
}

export function BlockList({ blocks, onReorder, onChangeContent, onDelete, onAdd, disabled }: Props) {
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [addMenuOpen, setAddMenuOpen] = useState(false);

  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 4 } }),
    useSensor(KeyboardSensor, { coordinateGetter: sortableKeyboardCoordinates }),
  );

  function handleDragEnd(event: DragEndEvent) {
    const { active, over } = event;
    if (!over || active.id === over.id) return;

    const oldIndex = blocks.findIndex((b) => b.id === active.id);
    const newIndex = blocks.findIndex((b) => b.id === over.id);
    if (oldIndex === -1 || newIndex === -1) return;

    const reordered = [...blocks];
    const [moved] = reordered.splice(oldIndex, 1);
    reordered.splice(newIndex, 0, moved);
    onReorder(reordered.map((b) => b.id));
  }

  function handleAdd(type: BlockType) {
    onAdd(type);
    setAddMenuOpen(false);
  }

  if (blocks.length === 0 && !disabled) {
    return (
      <div className="block-list">
        <div className="block-list__empty">
          <div className="block-list__empty-icon">🧩</div>
          <p className="block-list__empty-title">Пока пусто</p>
          <p className="block-list__empty-hint">Выбери, с чего начать — остальное добавишь потом</p>
        </div>
        <BlockTypeChips onAdd={handleAdd} />
      </div>
    );
  }

  return (
    <div className="block-list">
      <DndContext sensors={sensors} collisionDetection={closestCenter} onDragEnd={handleDragEnd}>
        <SortableContext items={blocks.map((b) => b.id)} strategy={verticalListSortingStrategy}>
          {blocks.map((block) => (
            <BlockCard
              key={block.id}
              block={block}
              expanded={expandedId === block.id}
              onToggle={() => setExpandedId(expandedId === block.id ? null : block.id)}
              onChange={(content) => onChangeContent(block.id, content)}
              onDelete={() => onDelete(block.id)}
              disabled={disabled}
            />
          ))}
        </SortableContext>
      </DndContext>

      {!disabled && (
        <div className="block-list__add">
          <button type="button" className="block-list__add-button" onClick={() => setAddMenuOpen((v) => !v)}>
            + Добавить блок
          </button>
          {addMenuOpen && (
            <div className="block-list__add-menu">
              <BlockTypeChips onAdd={handleAdd} />
            </div>
          )}
        </div>
      )}
    </div>
  );
}
