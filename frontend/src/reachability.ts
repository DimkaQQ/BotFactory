import type { BotBlock } from "./api/builderApi";

/**
 * Which blocks the bot can actually reach from /start.
 *
 * A block dragged in from the library lands unconnected — that is how the
 * canvas works, and it is correct while you are still wiring things up. What
 * was wrong is that nothing ever said so: someone building four weekly
 * videos could connect none of them, publish, and ship a bot that sends one
 * message. The graph was already on screen and the answer was one traversal
 * away.
 *
 * Mirrors the engine's own walk (app/services/bot_dispatcher.walk_chain):
 * the plain `next_block_id` arrow, plus every button's `target_block_id`.
 */
export function reachableBlockIds(blocks: BotBlock[], startBlockId: string | null): Set<string> {
  const byId = new Map(blocks.map((block) => [block.id, block]));
  const seen = new Set<string>();
  if (!startBlockId || !byId.has(startBlockId)) return seen;

  const queue = [startBlockId];
  while (queue.length > 0) {
    const id = queue.pop()!;
    // Guards against a deliberate loop in the graph, which is a legitimate
    // pattern and would otherwise spin here.
    if (seen.has(id)) continue;
    seen.add(id);

    const block = byId.get(id);
    if (!block) continue;

    if (block.next_block_id) queue.push(block.next_block_id);
    for (const button of block.content.buttons ?? []) {
      const target = (button.target_block_id ?? "").trim();
      if (target) queue.push(target);
    }
  }
  return seen;
}

/** The blocks nobody will ever see, in canvas order. */
export function orphanBlocks(blocks: BotBlock[], startBlockId: string | null): BotBlock[] {
  const reachable = reachableBlockIds(blocks, startBlockId);
  return blocks.filter((block) => !reachable.has(block.id));
}
