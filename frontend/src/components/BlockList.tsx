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

const BLOCK_TYPES: { type: BlockType; label: string }[] = [
  { type: "welcome", label: "👋 Приветствие" },
  { type: "description", label: "📝 Описание" },
  { type: "buttons", label: "🔘 Кнопки" },
  { type: "delivery", label: "🎁 Выдача" },
];

interface Props {
  blocks: BotBlock[];
  onReorder: (orderedIds: string[]) => void;
  onChangeContent: (blockId: string, content: BotBlock["content"]) => void;
  onDelete: (blockId: string) => void;
  onAdd: (blockType: BlockType) => void;
  disabled?: boolean;
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

  return (
    <div className="block-list">
      {blocks.length === 0 && <p className="block-list__empty">Блоков пока нет — добавь первый ниже.</p>}

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
              {BLOCK_TYPES.map(({ type, label }) => (
                <button
                  key={type}
                  type="button"
                  className="block-list__add-option"
                  onClick={() => {
                    onAdd(type);
                    setAddMenuOpen(false);
                  }}
                >
                  {label}
                </button>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
