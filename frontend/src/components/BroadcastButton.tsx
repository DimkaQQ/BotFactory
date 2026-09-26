import { useCallback, useEffect, useState } from "react";

import { type BroadcastRow, ApiError, builderApi } from "../api/builderApi";
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
  // Чем рассылка закончилась. Эндпоинт был написан и не вызывался ни одной
  // строчкой фронтенда: владелец видел «Отправляем 340 чел.» и тишину, а
  // шаги могли упасть все до одного.
  const [report, setReport] = useState<BroadcastRow | null>(null);

  const refreshReport = useCallback(async () => {
    try {
      const { broadcasts } = await builderApi.listBroadcasts(botId);
      setReport(broadcasts.find((row) => row.block_id === blockId) ?? null);
    } catch {
      // Отчёт — дополнение, а не условие работы кнопки.
    }
  }, [botId, blockId]);

  useEffect(() => {
    void refreshReport();
  }, [refreshReport]);

  // Пока есть ожидающие, обновляем сами: рассылка идёт минутами, и владелец
  // не должен гадать, закончилась ли она.
  useEffect(() => {
    if (!report || report.waiting === 0) return;
    const timer = setInterval(() => void refreshReport(), 5000);
    return () => clearInterval(timer);
  }, [report, refreshReport]);

  async function send(audience: "all" | "subscribers") {
    const who = audience === "all" ? "всем, кто писал боту" : "только активным подписчикам";

    // Сколько именно человек — до того, как нажать. «Всем» без числа может
    // означать и троих, и три тысячи, а отменить отправку нельзя.
    let howMany = "";
    try {
      const report = await builderApi.listSubscribers(botId);
      // Считаем ровно так же, как отбирает сервер: он пропускает
      // заблокировавших бота и попросивших не писать. Раньше здесь была
      // длина всего списка — диалог спрашивал «(5 чел.)», а уходило трём.
      const reachable = report.people.filter((person) => !person.blocked && !person.unsubscribed);
      const count = audience === "all" ? reachable.length : report.active_count;
      howMany = ` (${count} чел.)`;
    } catch {
      // Не смогли посчитать — спрашиваем без числа, но спрашиваем.
    }

    // Irreversible and outward-facing: once it is queued, those messages are
    // going to real people's phones.
    const ok = await confirmDialog(
      `Отправить это сообщение ${who}${howMany}? Отменить будет нельзя.`,
      "Отправить",
    );
    if (!ok) return;

    setBusy(true);
    setResult(null);
    try {
      const { queued } = await builderApi.broadcast(botId, blockId, audience);
      setResult(queued === 0 ? "Пока некому — у бота ещё нет подписчиков." : `Отправляем ${queued} чел.`);
      if (queued > 0) void refreshReport();
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

      {/* Чем всё закончилось. «Отправляем 340 чел.» — это про очередь, а не
          про доставку: шаги могли упасть все до одного, и на трёхстах
          учениках этого не заметить никак. */}
      {report && (
        <p className={`broadcast__report${report.failed > 0 ? " broadcast__report--bad" : ""}`}>
          {report.waiting > 0
            ? `Отправлено ${report.sent} из ${report.total}, в очереди ещё ${report.waiting}…`
            : `Дошло ${report.sent} из ${report.total}`}
          {report.failed > 0 && ` · не доставлено ${report.failed}`}
          {report.cancelled > 0 && ` · отменено ${report.cancelled}`}
        </p>
      )}
    </div>
  );
}
