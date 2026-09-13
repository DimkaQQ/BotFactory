import { useState } from "react";

import { ApiError, builderApi } from "../api/builderApi";
import { confirmDialog } from "../confirm";

interface Props {
  botId: string;
  blockId: string;
  /** Only a published bot has a token to send with. */
  published: boolean;
}

/**
 * "Отправить этот блок всем" — the thing «рассылка» has always meant.
 *
 * Lives on the block, not in a separate screen, because the block *is* the
 * message: whatever this node says on the canvas is exactly what lands in
 * everyone's chat, and there is no second place to keep it in sync with.
 */
export function BroadcastButton({ botId, blockId, published }: Props) {
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<string | null>(null);

  async function send(audience: "all" | "subscribers") {
    const who = audience === "all" ? "всем, кто писал боту" : "только активным подписчикам";
    // Irreversible and outward-facing: once it is queued, those messages are
    // going to real people's phones.
    if (!(await confirmDialog(`Отправить это сообщение ${who}? Отменить будет нельзя.`))) return;

    setBusy(true);
    setResult(null);
    try {
      const { queued } = await builderApi.broadcast(botId, blockId, audience);
      setResult(queued === 0 ? "Пока некому — у бота ещё нет подписчиков." : `Отправляем ${queued} чел.`);
    } catch (err) {
      setResult(err instanceof ApiError ? err.message : "Не удалось отправить");
    } finally {
      setBusy(false);
    }
  }

  if (!published) {
    return <p className="app-hint">Рассылку можно отправить после публикации бота.</p>;
  }

  return (
    <div className="broadcast">
      <div className="broadcast__row">
        <button type="button" className="broadcast__button" disabled={busy} onClick={() => send("all")}>
          Отправить всем
        </button>
        <button
          type="button"
          className="broadcast__button broadcast__button--quiet"
          disabled={busy}
          onClick={() => send("subscribers")}
        >
          Только подписчикам
        </button>
      </div>
      {result && <p className="app-hint broadcast__result">{result}</p>}
    </div>
  );
}
