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

/**
 * Петля из стрелок «дальше», по которой бот пойдёт по кругу.
 *
 * Движок такую петлю переживает — он помнит пройденное и останавливается, —
 * но останавливается МОЛЧА: покупатель видит оборванный разговор, владелец
 * не узнаёт ничего. Для соседней беды (больше пятидесяти блоков подряд)
 * владельцу уходит предупреждение, а для петли не уходило ничего. Если
 * петля окажется перед блоком оплаты, ученики просто не дойдут до кнопки
 * «купить», и это будет выглядеть как отсутствие спроса.
 *
 * Считаются только стрелки «дальше»: ветвление кнопками, которое сходится
 * обратно, — нормальный приём, там человек нажимает и выбирает сам.
 */
export function loopedBlocks(blocks: BotBlock[], startBlockId: string | null): BotBlock[] {
  const byId = new Map(blocks.map((block) => [block.id, block]));
  const looped = new Set<string>();

  for (const start of blocks) {
    const path: string[] = [];
    const onPath = new Set<string>();
    let current: string | null = start.id;

    while (current && byId.has(current)) {
      if (onPath.has(current)) {
        // Нашли витой участок: всё от первого появления и до конца пути.
        for (const id of path.slice(path.indexOf(current))) looped.add(id);
        break;
      }
      onPath.add(current);
      path.push(current);
      current = byId.get(current)!.next_block_id ?? null;
    }
  }

  // Порядок холста, и только то, до чего бот вообще дойдёт: петля в
  // неподключённой ветке — это не то, о чём стоит кричать, про неё уже
  // сказано «не подключён».
  const reachable = reachableBlockIds(blocks, startBlockId);
  return blocks.filter((block) => looped.has(block.id) && reachable.has(block.id));
}
