import { Handle, Position } from "@xyflow/react";

import { useWideScreen } from "../../hooks/useWideScreen";
import { Play } from "@phosphor-icons/react";

/** The synthetic entry-point node — not a real block, just an arrow source
 * pointing at whichever block is `bot.start_block_id`. Its own position on
 * the canvas is local-only (FlowCanvas seeds it once and never persists it —
 * there's no backend field for "where does the ▶ Старт pseudo-node sit"). */
export function StartNode() {
  const wide = useWideScreen();
  return (
    <div className="flow-node flow-node--start">
      <span className="flow-node--start__icon" aria-hidden="true">
        <Play size={14} aria-hidden="true" />
      </span>
      <span className="flow-node--start__label">Старт</span>
      <Handle type="source" position={wide ? Position.Right : Position.Bottom} id="default" className="flow-node__handle flow-node__handle--default" />
    </div>
  );
}
