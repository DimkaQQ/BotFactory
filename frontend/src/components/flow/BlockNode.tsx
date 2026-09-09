import { memo } from "react";
import { Handle, Position } from "@xyflow/react";

import type { BotBlock } from "../../api/builderApi";
import { BLOCK_TYPE_BY_ID } from "../../blockTypes";
import { useFlowActions } from "./flowActions";

export interface BlockNodeData {
  block: BotBlock;
  isStart: boolean;
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

/** One block's card on the flow canvas — a compact summary, not the full
 * editor (that's BlockEditPanel, opened on click).
 *
 * A buttons block gets one arrow socket per button, because an arrow from
 * *that specific button* is what "tapping it goes here" means. Every block
 * also has the plain bottom socket, which is what happens when nothing more
 * specific applies — for a buttons block with branches that's never, so the
 * card says so instead of leaving a dead handle looking clickable (the rule
 * itself lives in bot_dispatcher.py's chain-walk). */
function BlockNodeComponent({ id, data, selected }: { id: string; data: BlockNodeData; selected?: boolean }) {
  const { block, isStart } = data;
  const { onEdit, onDelete } = useFlowActions();
  const def = BLOCK_TYPE_BY_ID[block.block_type];
  const isButtons = block.block_type === "buttons";
  const buttons = isButtons ? block.content.buttons ?? [] : [];
  const hasBranch = buttons.some((b) => (b.target_block_id || "").trim());
  const isEmpty = isButtons
    ? !buttons.some((b) => b.label.trim() || b.action_value.trim()) && !block.content.text?.trim()
    : block.block_type === "poll"
      ? !block.content.question?.trim() || (block.content.options ?? []).filter((o) => o.trim()).length < 2
      : block.block_type === "delay"
        ? false
        : !block.content.text?.trim() && !block.content.media_file_id;

  return (
    <div className={`flow-node ${selected ? "flow-node--selected" : ""}`} onClick={() => onEdit(id)}>
      <Handle
        type="target"
        position={Position.Top}
        id="target"
        className="flow-node__handle"
        title="Сюда приходят стрелки от других блоков"
      />

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

      {isButtons && buttons.length > 0 && (
        <div className="flow-node__buttons">
          <p className="flow-node__buttons-caption">Куда ведёт нажатие:</p>
          {buttons.map((button, index) => {
            const wired = !!(button.target_block_id || "").trim();
            const isUrl = button.action_type === "url";
            return (
              <div
                key={index}
                className={`flow-node__button-row ${wired ? "flow-node__button-row--wired" : ""}`}
                title={
                  isUrl
                    ? `«${button.label || "…"}» — кнопка-ссылка: откроет сайт, ветка ей не нужна`
                    : wired
                      ? `«${button.label || "…"}» ведёт к другому блоку. Стрелку можно перетянуть или удалить.`
                      : `Потяни от кружка справа к блоку, который должен открыться после нажатия «${button.label || "…"}»`
                }
              >
                <span className="flow-node__button-label">{button.label || "…"}</span>
                {isUrl ? (
                  <span className="flow-node__button-tag">🔗 ссылка</span>
                ) : (
                  <span className={`flow-node__button-tag ${wired ? "" : "flow-node__button-tag--todo"}`}>
                    {wired ? "ведёт" : "тяни"} →
                  </span>
                )}
                {/* A URL button can't branch (Telegram just opens the link), so
                    it only keeps a socket if an arrow was already drawn from
                    it — otherwise the edge would have nowhere to attach and
                    would silently disappear from the canvas. */}
                {(!isUrl || wired) && (
                  <Handle
                    type="source"
                    position={Position.Right}
                    id={`button-${index}`}
                    className={`flow-node__handle flow-node__handle--button ${wired ? "" : "flow-node__handle--todo"}`}
                    style={{ top: "auto", position: "relative", transform: "none", right: -14 }}
                  />
                )}
              </div>
            );
          })}
        </div>
      )}

      <div className={`flow-node__default-out ${isButtons && hasBranch ? "flow-node__default-out--idle" : ""}`}>
        <span
          title={
            isButtons && hasBranch
              ? "У кнопок есть ветки — бот остановится и будет ждать нажатия. Эта стрелка сработает, только если убрать все ветки."
              : "Потяни отсюда к блоку, который придёт следующим"
          }
        >
          {isButtons && hasBranch ? "ждёт нажатия" : "дальше"}
        </span>
        <Handle type="source" position={Position.Bottom} id="default" className="flow-node__handle flow-node__handle--default" />
      </div>
    </div>
  );
}

export const BlockNode = memo(BlockNodeComponent);
