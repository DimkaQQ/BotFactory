import { useEffect, useRef, useState } from "react";

import type { BotBlock } from "../api/builderApi";

interface Props {
  blocks: BotBlock[];
  botName: string;
  onClose: () => void;
}

type Step = { block: BotBlock; kind: "typing" | "pause"; waitMs: number };

const CHARS_PER_SECOND = 45;
const MIN_DELAY_MS = 500;
const MAX_DELAY_MS = 1800;

/** Mirrors the backend's pacing (app/services/bot_dispatcher.py::_typing_delay)
 * so the preview genuinely shows how the real bot will feel, not just a
 * generic animation. */
function typingDelayMs(text: string): number {
  const seconds = text.length / CHARS_PER_SECOND;
  return Math.max(MIN_DELAY_MS, Math.min(seconds * 1000, MAX_DELAY_MS));
}

function stepFor(block: BotBlock, isFirst: boolean): Step {
  if (block.block_type === "delay") {
    const seconds = Math.max(0, Math.min(Number(block.content.seconds ?? 2), 15));
    return { block, kind: "pause", waitMs: seconds * 1000 };
  }
  if (isFirst) return { block, kind: "typing", waitMs: 0 };
  const text = block.content.text || block.content.question || "";
  return { block, kind: "typing", waitMs: typingDelayMs(text) };
}

export function LivePreview({ blocks, botName, onClose }: Props) {
  const steps = useRef<Step[]>(blocks.map((b, i) => stepFor(b, i === 0))).current;
  const [revealed, setRevealed] = useState<BotBlock[]>([]);
  const [pending, setPending] = useState<Step | null>(steps[0] ?? null);
  const [countdown, setCountdown] = useState<number | null>(null);
  const [done, setDone] = useState(blocks.length === 0);
  const scrollRef = useRef<HTMLDivElement | null>(null);
  const skipRef = useRef(false);

  function replay() {
    skipRef.current = false;
    setRevealed([]);
    setDone(blocks.length === 0);
    setPending(steps[0] ?? null);
  }

  useEffect(() => {
    if (!pending) return;
    let cancelled = false;

    async function run(step: Step) {
      if (step.kind === "pause") {
        const totalMs = step.waitMs;
        const startedAt = Date.now();
        while (!cancelled && !skipRef.current && Date.now() - startedAt < totalMs) {
          setCountdown(Math.max(0, Math.ceil((totalMs - (Date.now() - startedAt)) / 1000)));
          await new Promise((r) => setTimeout(r, 200));
        }
        setCountdown(null);
      } else if (step.waitMs > 0) {
        await new Promise((r) => setTimeout(r, skipRef.current ? 0 : step.waitMs));
      }
      if (cancelled) return;

      setRevealed((prev) => [...prev, step.block]);
      const idx = steps.indexOf(step);
      const next = steps[idx + 1];
      skipRef.current = false;
      setPending(next ?? null);
      if (!next) setDone(true);
    }

    run(pending);
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pending]);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [revealed, countdown]);

  const showTyping = pending && pending.kind === "typing" && (pending.waitMs > 0 || revealed.length > 0) && revealed.length < blocks.length && countdown === null;
  // The avatar belongs on the last *message* — a trailing pause renders as
  // a marker, not a bubble, so it shouldn't steal that spot.
  const lastBubbleIndex = (() => {
    for (let i = revealed.length - 1; i >= 0; i--) {
      if (revealed[i].block_type !== "delay") return i;
    }
    return -1;
  })();

  return (
    <>
      <div className="sheet-backdrop" onClick={onClose} />
      <div className="live-preview">
        <div className="live-preview__header">
          <span className="live-preview__title">▶ {botName || "Предпросмотр"}</span>
          <button type="button" className="live-preview__close" onClick={onClose} aria-label="Закрыть предпросмотр">
            ✕
          </button>
        </div>

        <div className="live-preview__body chat-canvas" ref={scrollRef}>
          {revealed.map((block, i) => (
            <PreviewBlock key={block.id} block={block} isLast={i === lastBubbleIndex && !showTyping} />
          ))}

          {countdown !== null && <div className="block-preview__caption live-preview__pause">⏱ Пауза — ещё {countdown} сек…</div>}

          {showTyping && (
            <div className="chat-row">
              <div className="chat-row__avatar">
                <span className="chat-avatar">🤖</span>
              </div>
              <div className="chat-row__content">
                <div className="chat-bubble chat-bubble--ghost live-preview__typing">
                  <span className="block-preview__dots block-preview__dots--solo">
                    <span />
                    <span />
                    <span />
                  </span>
                </div>
              </div>
            </div>
          )}

          {revealed.length === 0 && !showTyping && countdown === null && (
            <p className="app-hint">Тут пока пусто — добавь первое сообщение, чтобы увидеть предпросмотр.</p>
          )}
        </div>

        <div className="live-preview__footer">
          {done ? (
            <button type="button" className="publish-button" onClick={replay}>
              🔁 Смотреть заново
            </button>
          ) : (
            <button
              type="button"
              className="live-preview__skip"
              onClick={() => {
                skipRef.current = true;
              }}
            >
              ⏩ Пропустить паузы
            </button>
          )}
        </div>
      </div>
    </>
  );
}

function PreviewBlock({ block, isLast }: { block: BotBlock; isLast: boolean }) {
  const { content } = block;

  // No message of its own — mirrors how it renders in the editor canvas.
  if (block.block_type === "delay") {
    return <p className="live-preview__pause-marker">⏱ пауза {content.seconds ?? 2} сек — бот немного помолчал</p>;
  }

  return (
    <div className="chat-row">
      <div className="chat-row__avatar">{isLast && <span className="chat-avatar">🤖</span>}</div>
      <div className="chat-row__content">
        {block.block_type === "poll" ? (
          <div className="chat-bubble">
            <p className="chat-bubble__text">📊 {content.question || "Опрос"}</p>
            <div className="block-preview__poll live-preview__poll">
              {(content.options ?? []).map((opt, i) => (
                <span key={i} className="block-preview__bar block-preview__bar--static">
                  {opt || "…"}
                </span>
              ))}
            </div>
          </div>
        ) : (
          <div className="chat-bubble">
            {content.media_file_id && block.block_type === "image" && (
              <div className="block-preview__media live-preview__media">🖼️</div>
            )}
            {content.media_file_id && block.block_type === "video" && (
              <div className="block-preview__media block-preview__media--video live-preview__media">▶</div>
            )}
            {content.text && <p className="chat-bubble__text">{content.text}</p>}
            {(content.buttons ?? []).length > 0 && (
              <div className="chat-buttons">
                <div className="chat-buttons__preview">
                  {content.buttons!.map((btn, i) => (
                    <span key={i} className="chat-buttons__pill">
                      {btn.label || "…"}
                    </span>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
