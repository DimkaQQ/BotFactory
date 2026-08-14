import { useEffect, useRef, useState } from "react";
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
import { ChatBubble } from "./ChatBubble";

const BLOCK_TYPES: { type: BlockType; label: string; icon: string; accent: string; hint: string }[] = [
  { type: "welcome", label: "Приветствие", icon: "👋", accent: "welcome", hint: "Первое сообщение при /start" },
  { type: "description", label: "Описание", icon: "📝", accent: "description", hint: "Расскажи о продукте" },
  { type: "buttons", label: "Кнопки", icon: "🔘", accent: "buttons", hint: "Ссылки и переходы" },
  { type: "delivery", label: "Выдача", icon: "🎁", accent: "delivery", hint: "Файл, ссылка или доступ" },
];

interface Props {
  blocks: BotBlock[];
  onReorder: (orderedIds: string[]) => void;
  onChangeContent: (blockId: string, content: BotBlock["content"]) => void;
  onDelete: (blockId: string) => void;
  onAdd: (blockType: BlockType) => Promise<string>;
  disabled?: boolean;
}

export function ChatCanvas({ blocks, onReorder, onChangeContent, onDelete, onAdd, disabled }: Props) {
  const [sheetOpen, setSheetOpen] = useState(false);
  const [activeId, setActiveId] = useState<string | null>(null);
  const canvasRef = useRef<HTMLDivElement | null>(null);

  // Tapping outside the currently-active bubble (another message, the
  // header, the composer, empty canvas space) ends editing — a single
  // "active" bubble at a time, like a real chat's compose focus.
  useEffect(() => {
    if (!activeId) return;
    function handlePointerDown(e: PointerEvent) {
      const target = e.target as HTMLElement;
      if (!target.closest(`[data-block-id="${activeId}"]`)) {
        setActiveId(null);
      }
    }
    document.addEventListener("pointerdown", handlePointerDown);
    return () => document.removeEventListener("pointerdown", handlePointerDown);
  }, [activeId]);

  const sensors = useSensors(
    // Long-press to drag (tap still edits) — no separate grip handle needed,
    // it just feels like reordering pinned messages in a real chat app.
    useSensor(PointerSensor, { activationConstraint: { delay: 220, tolerance: 6 } }),
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

  async function handleAdd(type: BlockType) {
    setSheetOpen(false);
    const newId = await onAdd(type);
    setActiveId(newId);
  }

  return (
    <>
      {!disabled && (
        <aside className="block-library" aria-label="Библиотека блоков">
          <p className="block-library__title">Добавить блок</p>
          {BLOCK_TYPES.map(({ type, label, icon, accent, hint }) => (
            <button key={type} type="button" className="block-library__item" onClick={() => handleAdd(type)}>
              <span className={`block-library__icon block-card__icon--${accent}`} aria-hidden="true">
                {icon}
              </span>
              <span className="block-library__text">
                <span className="block-library__label">{label}</span>
                <span className="block-library__hint">{hint}</span>
              </span>
            </button>
          ))}
        </aside>
      )}
      <div className="chat-canvas" ref={canvasRef}>
      {blocks.length === 0 ? (
        <div className="chat-row">
          <div className="chat-row__avatar">
            <span className="chat-avatar">🤖</span>
          </div>
          <div className="chat-row__content">
            {disabled ? (
              <div className="chat-bubble chat-bubble--ghost">
                <p className="chat-bubble__text chat-bubble__text--placeholder">Пока нет сообщений</p>
              </div>
            ) : (
              <button type="button" className="chat-bubble chat-bubble--ghost" onClick={() => setSheetOpen(true)}>
                <p className="chat-bubble__text chat-bubble__text--placeholder">Нажми, чтобы отправить первое сообщение…</p>
              </button>
            )}
          </div>
        </div>
      ) : (
        <DndContext sensors={sensors} collisionDetection={closestCenter} onDragEnd={handleDragEnd}>
          <SortableContext items={blocks.map((b) => b.id)} strategy={verticalListSortingStrategy}>
            {blocks.map((block, index) => (
              <ChatBubble
                key={block.id}
                block={block}
                isLast={index === blocks.length - 1}
                active={activeId === block.id}
                onActivate={() => setActiveId(block.id)}
                onChange={(content) => onChangeContent(block.id, content)}
                onDelete={() => onDelete(block.id)}
                disabled={disabled}
              />
            ))}
          </SortableContext>
        </DndContext>
      )}

      {!disabled && (
        <div className="chat-composer">
          <button type="button" className="chat-composer__button" onClick={() => setSheetOpen(true)}>
            <span className="chat-composer__plus">+</span>
            Добавить сообщение
          </button>
        </div>
      )}

      {sheetOpen && (
        <>
          <div className="sheet-backdrop" onClick={() => setSheetOpen(false)} />
          <div className="sheet">
            <div className="sheet__handle" />
            <p className="sheet__title">Что добавить?</p>
            <div className="block-chips">
              {BLOCK_TYPES.map(({ type, label, icon, accent }) => (
                <button key={type} type="button" className="block-chip" onClick={() => handleAdd(type)}>
                  <span className={`block-chip__icon block-card__icon--${accent}`} aria-hidden="true">
                    {icon}
                  </span>
                  {label}
                </button>
              ))}
            </div>
          </div>
        </>
      )}
      </div>
    </>
  );
}
