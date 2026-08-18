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
import { BLOCK_TYPES } from "../blockTypes";
import { useSwipeToDismiss } from "../hooks/useSwipeToDismiss";
import { BlockPreviewFlyout } from "./BlockPreviewFlyout";
import { ChatBubble } from "./ChatBubble";
import { LivePreview } from "./LivePreview";

interface Props {
  blocks: BotBlock[];
  botName?: string;
  onReorder: (orderedIds: string[]) => void;
  onChangeContent: (blockId: string, content: BotBlock["content"]) => void;
  onDelete: (blockId: string) => void;
  onAdd: (blockType: BlockType) => Promise<string>;
  disabled?: boolean;
}

const DELETE_ANIM_MS = 220;

export function ChatCanvas({ blocks, botName, onReorder, onChangeContent, onDelete, onAdd, disabled }: Props) {
  const [sheetOpen, setSheetOpen] = useState(false);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [hoveredType, setHoveredType] = useState<BlockType | null>(null);
  const [previewOpen, setPreviewOpen] = useState(false);
  const [removingIds, setRemovingIds] = useState<Set<string>>(new Set());
  const canvasRef = useRef<HTMLDivElement | null>(null);
  const { sheetRef, handleProps } = useSwipeToDismiss(() => setSheetOpen(false));

  // Play a shrink-and-fade before the bubble actually leaves the list,
  // instead of it just vanishing — the delete button feels like it did
  // something, not like the DOM silently snapped shut.
  function handleDeleteBlock(blockId: string) {
    setRemovingIds((prev) => new Set(prev).add(blockId));
    setTimeout(() => {
      onDelete(blockId);
      setRemovingIds((prev) => {
        const next = new Set(prev);
        next.delete(blockId);
        return next;
      });
    }, DELETE_ANIM_MS);
  }

  // Tapping outside the currently-active bubble (another message, the
  // header, the composer, empty canvas space) ends editing — a single
  // "active" bubble at a time, like a real chat's compose focus.
  //
  // Deliberately "pointerdown", not "click": a document-level "click"
  // listener registered *as a result of* a click (e.g. the same click
  // that activates a bubble via its own onClick) can still catch that
  // very click on its way further up the bubble chain and immediately
  // deactivate what it just activated — the classic self-closing
  // "outside click" bug. pointerdown doesn't have this problem here since
  // activation itself fires on "click", one step later.
  //
  // The tradeoff: pointerdown fires *before* the browser resolves any
  // resulting blur/focus shift, so a field inside the bubble this closes
  // can't reliably use a React onBlur to react to that — see
  // ButtonsEditor's URL-normalizing blur handler, which is attached as a
  // native listener via a ref for exactly this reason instead.
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
    setHoveredType(null);
    const newId = await onAdd(type);
    setActiveId(newId);
  }

  return (
    <>
      {!disabled && (
        <aside className="block-library" aria-label="Библиотека блоков">
          <p className="block-library__title">Добавить блок</p>
          {BLOCK_TYPES.map(({ type, label, icon, accent, hint }) => (
            <button
              key={type}
              type="button"
              className="block-library__item"
              onClick={() => handleAdd(type)}
              onMouseEnter={() => setHoveredType(type)}
              onMouseLeave={() => setHoveredType((cur) => (cur === type ? null : cur))}
              onFocus={() => setHoveredType(type)}
              onBlur={() => setHoveredType((cur) => (cur === type ? null : cur))}
            >
              <span className={`block-library__icon block-card__icon--${accent}`} aria-hidden="true">
                {icon}
              </span>
              <span className="block-library__text">
                <span className="block-library__label">{label}</span>
                <span className="block-library__hint">{hint}</span>
              </span>
            </button>
          ))}
          {hoveredType && (
            <div className="block-preview-flyout">
              <BlockPreviewFlyout type={hoveredType} />
            </div>
          )}
        </aside>
      )}
      <div className="chat-canvas" ref={canvasRef}>
      {blocks.length > 0 && (
        <button type="button" className="chat-canvas__preview-btn" onClick={() => setPreviewOpen(true)}>
          ▶ Смотреть, как в реальности
        </button>
      )}
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
                staggerIndex={index}
                isLast={index === blocks.length - 1}
                active={activeId === block.id}
                removing={removingIds.has(block.id)}
                onActivate={() => setActiveId(block.id)}
                onChange={(content) => onChangeContent(block.id, content)}
                onDelete={() => handleDeleteBlock(block.id)}
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
          <div className="sheet" ref={sheetRef}>
            <div className="sheet__handle" {...handleProps} />
            <p className="sheet__title">Что добавить?</p>
            <div className="block-chips">
              {BLOCK_TYPES.map(({ type, label, icon, accent, hint }) => (
                <button key={type} type="button" className="block-chip" onClick={() => handleAdd(type)}>
                  <span className={`block-chip__icon block-card__icon--${accent}`} aria-hidden="true">
                    {icon}
                  </span>
                  <span className="block-chip__text">
                    <span className="block-chip__label">{label}</span>
                    <span className="block-chip__hint">{hint}</span>
                  </span>
                </button>
              ))}
            </div>
          </div>
        </>
      )}
      </div>

      {previewOpen && <LivePreview blocks={blocks} botName={botName ?? ""} onClose={() => setPreviewOpen(false)} />}
    </>
  );
}
