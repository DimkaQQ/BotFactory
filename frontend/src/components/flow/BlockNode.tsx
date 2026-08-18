import { Handle, Position } from "@xyflow/react";

import type { BotBlock } from "../../api/builderApi";
import { BLOCK_TYPE_BY_ID } from "../../blockTypes";

export interface BlockNodeData {
  block: BotBlock;
  isStart: boolean;
  onEdit: (blockId: string) => void;
  onDelete: (blockId: string) => void;
  [key: string]: unknown;
}

function preview(block: BotBlock): string {
  const c = block.content;
  switch (block.block_type) {
    case "poll":
      return c.question?.trim() || "О чём спросим?";
    case "delay":
      return `Пауза ${Math.max(0, Math.min(Number(c.seconds ?? 2), 15))} сек`;
    case "image":
    case "video":
      return c.text?.trim() || (c.media_file_id ? "Без подписи" : "Ссылка не добавлена");
    case "buttons":
      return c.text?.trim() || "Текст перед кнопками";
    default:
      return c.text?.trim() || "Пусто — нажми, чтобы написать";
  }
}

/** One node on the flow canvas — a compact card, not the full editor (that's
 * BlockEditPanel, opened on click). Buttons blocks get one source handle per
 * button (so you drag an arrow from *that specific choice*), plus a single
 * muted "default" handle every block type has, used only when nothing more
 * specific applies (see bot_dispatcher.py's chain-walk for the exact rule). */
export function BlockNode({ id, data, selected }: { id: string; data: BlockNodeData; selected?: boolean }) {
  const { block, isStart, onEdit, onDelete } = data;
  const def = BLOCK_TYPE_BY_ID[block.block_type];
  const buttons = block.block_type === "buttons" ? block.content.buttons ?? [] : [];
  const isEmpty =
    block.block_type === "buttons"
      ? !buttons.some((b) => b.label.trim() || b.action_value.trim()) && !block.content.text?.trim()
      : block.block_type === "poll"
        ? !block.content.question?.trim() || (block.content.options ?? []).filter((o) => o.trim()).length < 2
        : block.block_type === "delay"
          ? false
          : !block.content.text?.trim() && !block.content.media_file_id;

  return (
    <div className={`flow-node ${selected ? "flow-node--selected" : ""}`} onClick={() => onEdit(id)}>
      <Handle type="target" position={Position.Top} id="target" className="flow-node__handle" />

      <div className="flow-node__head">
        <span className={`flow-node__icon block-card__icon--${def.accent}`} aria-hidden="true">
          {def.icon}
        </span>
        <span className="flow-node__label">{def.label}</span>
        {isStart && <span className="flow-node__start-badge">START</span>}
        <button
          type="button"
          className="flow-node__delete"
          aria-label="Удалить блок"
          onPointerDown={(e) => e.stopPropagation()}
          onClick={(e) => {
            e.stopPropagation();
            onDelete(id);
          }}
        >
          ✕
        </button>
      </div>

      <p className={`flow-node__preview ${isEmpty ? "flow-node__preview--empty" : ""}`}>{preview(block)}</p>
      {isEmpty && block.block_type !== "delay" && <p className="flow-node__warning">⚠️ бот пропустит это сообщение</p>}

      {block.block_type === "buttons" && buttons.length > 0 && (
        <div className="flow-node__buttons">
          {buttons.map((button, i) => (
            <div key={i} className="flow-node__button-row">
              <span className="flow-node__button-label">{button.label || "…"}</span>
              <Handle
                type="source"
                position={Position.Right}
                id={`button-${i}`}
                className="flow-node__handle flow-node__handle--button"
                style={{ top: "auto", position: "relative", transform: "none", right: -14 }}
              />
            </div>
          ))}
        </div>
      )}

      <div className="flow-node__default-out">
        <span>{block.block_type === "buttons" ? "если без выбора" : "далее"}</span>
        <Handle type="source" position={Position.Bottom} id="default" className="flow-node__handle flow-node__handle--default" />
      </div>
    </div>
  );
}
