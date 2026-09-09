import { createContext, useContext } from "react";

export interface FlowActions {
  onEdit: (blockId: string) => void;
  onDelete: (blockId: string) => void;
}

/** Node callbacks travel through context rather than through each node's
 * `data`, so `data` can stay reference-stable between renders. That's what
 * lets React Flow skip re-rendering every other node while one block's text
 * is being typed — previously every keystroke rebuilt the data object of
 * every node on the canvas. The provider's value is ref-backed and never
 * changes identity, so consuming it costs nothing. */
export const FlowActionsContext = createContext<FlowActions>({ onEdit: () => {}, onDelete: () => {} });

export function useFlowActions(): FlowActions {
  return useContext(FlowActionsContext);
}
