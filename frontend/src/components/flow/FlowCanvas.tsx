import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Background, Controls, type Edge, type Node, ReactFlow, ReactFlowProvider, useNodesState } from "@xyflow/react";
import "@xyflow/react/dist/style.css";

import type { BlockType, BotBlock, BotWithBlocks } from "../../api/builderApi";
import { BLOCK_TYPES } from "../../blockTypes";
import { BlockEditPanel } from "./BlockEditPanel";
import { BlockNode, type BlockNodeData } from "./BlockNode";
import { FlowActionsContext, type FlowActions } from "./flowActions";
import { StartNode } from "./StartNode";

const START_ID = "__start__";
const START_POSITION = { x: 40, y: 40 };

/** Which model field a dropped/deleted arrow maps back to — carried on the
 * edge itself so onConnect/onEdgesDelete don't need to re-derive it from
 * ids and handle-name string parsing in two places. */
type EdgeKind = { kind: "start" } | { kind: "default"; blockId: string } | { kind: "button"; blockId: string; index: number };

interface Props {
  bot: BotWithBlocks;
  onChangeContent: (blockId: string, content: BotBlock["content"]) => void;
  onDelete: (blockId: string) => void;
  onAdd: (blockType: BlockType, position: { x: number; y: number }) => Promise<string>;
  onSetNext: (blockId: string, nextBlockId: string | null) => void;
  onSetStart: (blockId: string | null) => void;
  onSetPosition: (blockId: string, x: number, y: number) => void;
  paymentProvider: string | null;
  paymentCurrencies: string[];
  onOpenPaymentSettings: () => void;
  disabled?: boolean;
}

// Node data is heterogeneous (the start node carries none) — kept loose
// (`Node<any>` rather than a strict union) so BlockNode/StartNode each own
// their own data shape instead of the canvas fighting React Flow's generics
// to describe both at once.
type FlowNode = Node<any>;

const nodeTypes = { block: BlockNode, start: StartNode };

function blockNode(block: BotBlock, isStart: boolean): FlowNode {
  return {
    id: block.id,
    type: "block",
    position: { x: block.position_x, y: block.position_y },
    data: { block, isStart } satisfies BlockNodeData,
  };
}

export function FlowCanvas(props: Props) {
  // React Flow's own state (drag position, viewport) needs to live above
  // remounts, hence the provider wrapper — everything else is in Inner.
  return (
    <ReactFlowProvider>
      <Inner {...props} />
    </ReactFlowProvider>
  );
}

function Inner({
  bot,
  onChangeContent,
  onDelete,
  onAdd,
  onSetNext,
  onSetStart,
  onSetPosition,
  paymentProvider,
  paymentCurrencies,
  onOpenPaymentSettings,
  disabled,
}: Props) {
  const [editingId, setEditingId] = useState<string | null>(null);
  const [sheetOpen, setSheetOpen] = useState(false);

  const blocksById = useMemo(() => new Map(bot.blocks.map((b) => [b.id, b])), [bot.blocks]);

  const [nodes, setNodes, onNodesChange] = useNodesState<FlowNode>([
    { id: START_ID, type: "start", position: START_POSITION, data: {} },
    ...bot.blocks.map((b) => blockNode(b, b.id === bot.start_block_id)),
  ]);

  // Reconcile nodes with the current block list on every bot change, without
  // ever touching an existing node's `position` — that's the live/dragged
  // value, seeded from block.position_x/y only at creation time. Overwriting
  // it on every keystroke-triggered re-render would fight drags and the
  // async round trip after a drop.
  //
  // Untouched blocks keep their exact node object. BotBuilder replaces only
  // the block being edited (the rest keep reference identity), so typing in
  // one block leaves every other node byte-identical and React Flow skips
  // re-rendering it — the difference between a canvas that keeps up with
  // typing and one that redraws itself on every keystroke.
  useEffect(() => {
    setNodes((current) => {
      const byId = new Map(current.map((n) => [n.id, n]));
      const startNode = byId.get(START_ID) ?? { id: START_ID, type: "start", position: START_POSITION, data: {} };
      const next: FlowNode[] = [startNode];
      let changed = current.length !== bot.blocks.length + 1 || current[0] !== startNode;

      for (const block of bot.blocks) {
        const existing = byId.get(block.id);
        const isStart = block.id === bot.start_block_id;
        if (existing && existing.data.block === block && existing.data.isStart === isStart) {
          next.push(existing);
        } else if (existing) {
          next.push({ ...existing, data: { block, isStart } satisfies BlockNodeData });
          changed = true;
        } else {
          next.push(blockNode(block, isStart));
          changed = true;
        }
      }

      return changed ? next : current;
    });
  }, [bot.blocks, bot.start_block_id, setNodes]);

  const edges = useMemo<Edge[]>(() => {
    const out: Edge[] = [];
    if (bot.start_block_id && blocksById.has(bot.start_block_id)) {
      out.push({
        id: "start-edge",
        source: START_ID,
        sourceHandle: "default",
        target: bot.start_block_id,
        data: { kind: "start" } satisfies EdgeKind,
      });
    }
    for (const block of bot.blocks) {
      if (block.next_block_id && blocksById.has(block.next_block_id)) {
        out.push({
          id: `${block.id}-default`,
          source: block.id,
          sourceHandle: "default",
          target: block.next_block_id,
          className: block.block_type === "buttons" ? "flow-edge--muted" : undefined,
          data: { kind: "default", blockId: block.id } satisfies EdgeKind,
        });
      }
      if (block.block_type === "buttons") {
        (block.content.buttons ?? []).forEach((button, index) => {
          const target = (button.target_block_id || "").trim();
          if (target && blocksById.has(target)) {
            out.push({
              id: `${block.id}-button-${index}`,
              source: block.id,
              sourceHandle: `button-${index}`,
              target,
              data: { kind: "button", blockId: block.id, index } satisfies EdgeKind,
            });
          }
        });
      }
    }
    return out;
  }, [bot.blocks, bot.start_block_id, blocksById]);

  const editingBlock = editingId ? (blocksById.get(editingId) ?? null) : null;

  const handleEdit = useCallback((blockId: string) => setEditingId(blockId), []);
  const handleDelete = useCallback(
    (blockId: string) => {
      setEditingId((cur) => (cur === blockId ? null : cur));
      onDelete(blockId);
    },
    [onDelete],
  );

  // The node callbacks reach BlockNode through context, not through node
  // data, and this object never changes identity — the latest handlers are
  // read off a ref at call time. That keeps `data` stable across renders
  // (see the reconcile effect) instead of invalidating every node whenever
  // a handler was recreated.
  const latest = useRef({ handleEdit, handleDelete, disabled });
  latest.current = { handleEdit, handleDelete, disabled };
  const actions = useMemo<FlowActions>(
    () => ({
      onEdit: (blockId) => {
        if (!latest.current.disabled) latest.current.handleEdit(blockId);
      },
      onDelete: (blockId) => latest.current.handleDelete(blockId),
    }),
    [],
  );

  function handleConnect(connection: { source: string | null; sourceHandle: string | null; target: string | null }) {
    if (!connection.source || !connection.target || connection.source === connection.target) return;
    if (connection.source === START_ID) {
      onSetStart(connection.target);
    } else if (connection.sourceHandle?.startsWith("button-")) {
      const index = Number(connection.sourceHandle.slice("button-".length));
      const block = blocksById.get(connection.source);
      if (!block) return;
      const buttons = (block.content.buttons ?? []).map((b, i) => (i === index ? { ...b, target_block_id: connection.target } : b));
      onChangeContent(connection.source, { ...block.content, buttons });
    } else {
      onSetNext(connection.source, connection.target);
    }
  }

  function handleEdgesDelete(deleted: Edge[]) {
    for (const edge of deleted) {
      const info = edge.data as EdgeKind | undefined;
      if (!info) continue;
      if (info.kind === "start") onSetStart(null);
      else if (info.kind === "default") onSetNext(info.blockId, null);
      else {
        const block = blocksById.get(info.blockId);
        if (!block) continue;
        const buttons = (block.content.buttons ?? []).map((b, i) => (i === info.index ? { ...b, target_block_id: null } : b));
        onChangeContent(info.blockId, { ...block.content, buttons });
      }
    }
  }

  function handleNodeDragStop(_: unknown, node: FlowNode) {
    if (node.id === START_ID) return;
    onSetPosition(node.id, node.position.x, node.position.y);
  }

  async function handleAdd(type: BlockType) {
    setSheetOpen(false);
    // Cascade new nodes so they don't all land in the same spot — a rough
    // grid, not a real layout algorithm; the user drags from there.
    const count = bot.blocks.length;
    const position = { x: 360 + (count % 3) * 260, y: 40 + Math.floor(count / 3) * 220 };
    const newId = await onAdd(type, position);
    setEditingId(newId);
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

      <div className="flow-canvas">
        <FlowActionsContext.Provider value={actions}>
          <ReactFlow
            nodes={nodes}
            edges={edges}
            onNodesChange={onNodesChange}
            onConnect={disabled ? undefined : handleConnect}
            onEdgesDelete={disabled ? undefined : handleEdgesDelete}
            onNodeDragStop={disabled ? undefined : handleNodeDragStop}
            nodeTypes={nodeTypes}
            nodesDraggable={!disabled}
            nodesConnectable={!disabled}
            elementsSelectable={!disabled}
            deleteKeyCode={disabled ? null : ["Backspace", "Delete"]}
            fitView
            fitViewOptions={{ padding: 0.3, maxZoom: 1 }}
            proOptions={{ hideAttribution: true }}
          >
            <Background gap={24} size={1.5} />
            <Controls showInteractive={false} />
          </ReactFlow>
        </FlowActionsContext.Provider>

        {!disabled && bot.blocks.length === 0 && (
          <div className="flow-canvas__empty">
            <p>Пока пусто — добавь первый блок слева, и от него потянется стрелка «▶ Старт».</p>
          </div>
        )}
      </div>

      {sheetOpen && (
        <>
          <div className="sheet-backdrop" onClick={() => setSheetOpen(false)} />
          <div className="sheet">
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

      {!disabled && (
        <div className="chat-composer flow-canvas__composer">
          <button type="button" className="chat-composer__button" onClick={() => setSheetOpen(true)}>
            <span className="chat-composer__plus">+</span>
            Добавить блок
          </button>
        </div>
      )}

      {editingBlock && (
        <BlockEditPanel
          block={editingBlock}
          botId={bot.id}
          blocks={bot.blocks}
          paymentProvider={paymentProvider}
          paymentCurrencies={paymentCurrencies}
          onOpenPaymentSettings={onOpenPaymentSettings}
          onChange={(content) => onChangeContent(editingBlock.id, content)}
          onDelete={() => handleDelete(editingBlock.id)}
          onClose={() => setEditingId(null)}
        />
      )}
    </>
  );
}
