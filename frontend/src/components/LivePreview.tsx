import { useEffect, useMemo, useRef, useState } from "react";

import type { BotBlock, BotWithBlocks } from "../api/builderApi";

interface Props {
  bot: BotWithBlocks;
  botName: string;
  onClose: () => void;
}

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

function hasBranches(block: BotBlock): boolean {
  return block.block_type === "buttons" && (block.content.buttons ?? []).some((b) => (b.target_block_id || "").trim());
}

/** Walks the same graph the real bot walks (start_block_id → next_block_id,
 * pausing at any buttons block with a configured branch) instead of just
 * replaying the flat block list — tapping a button here actually picks the
 * path, exactly like a real Telegram chat with this bot would. */
export function LivePreview({ bot, botName, onClose }: Props) {
  const blocksById = useMemo(() => new Map(bot.blocks.map((b) => [b.id, b])), [bot.blocks]);

  const [revealed, setRevealed] = useState<BotBlock[]>([]);
  const [currentId, setCurrentId] = useState<string | null>(bot.start_block_id);
  const [countdown, setCountdown] = useState<number | null>(null);
  const [showTyping, setShowTyping] = useState(false);
  const [waitingForTap, setWaitingForTap] = useState(false);
  const [done, setDone] = useState(!bot.start_block_id);
  const scrollRef = useRef<HTMLDivElement | null>(null);
  const skipRef = useRef(false);
  // Same cycle guard as the backend (_walk_chain's `visited` set) — a demo
  // shouldn't be able to spin forever on a loop with no branch point either.
  const visitedRef = useRef<Set<string>>(new Set());

  function replay() {
    skipRef.current = false;
    visitedRef.current = new Set();
    setRevealed([]);
    setWaitingForTap(false);
    setDone(!bot.start_block_id);
    setCurrentId(bot.start_block_id);
  }

  useEffect(() => {
    if (!currentId) return;
    if (visitedRef.current.has(currentId)) {
      setDone(true);
      return;
    }
    const block = blocksById.get(currentId);
    if (!block) {
      setDone(true);
      return;
    }
    visitedRef.current.add(currentId);

    let cancelled = false;
    const isFirst = revealed.length === 0;

    (async () => {
      if (block.block_type === "delay") {
        const seconds = Math.max(0, Math.min(Number(block.content.seconds ?? 2), 15));
        const totalMs = seconds * 1000;
        const startedAt = Date.now();
        while (!cancelled && !skipRef.current && Date.now() - startedAt < totalMs) {
          setCountdown(Math.max(0, Math.ceil((totalMs - (Date.now() - startedAt)) / 1000)));
          await new Promise((r) => setTimeout(r, 200));
        }
        setCountdown(null);
        skipRef.current = false;
      } else if (!isFirst) {
        setShowTyping(true);
        const text = block.content.text || block.content.question || "";
        await new Promise((r) => setTimeout(r, text ? typingDelayMs(text) : MIN_DELAY_MS));
        setShowTyping(false);
      }
      if (cancelled) return;

      setRevealed((prev) => [...prev, block]);

      if (hasBranches(block)) {
        setWaitingForTap(true);
      } else if (block.next_block_id) {
        setCurrentId(block.next_block_id);
      } else {
        setDone(true);
      }
    })();

    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [currentId]);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [revealed, countdown]);

  function handlePick(block: BotBlock, index: number) {
    const target = (block.content.buttons?.[index]?.target_block_id || "").trim();
    if (!target) return; // this button isn't wired to anything — real bot just re-answers the tap and stays put
    setWaitingForTap(false);
    setCurrentId(target);
  }

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
            <PreviewBlock
              key={`${block.id}-${i}`}
              block={block}
              isLast={i === lastBubbleIndex && !showTyping}
              interactive={i === revealed.length - 1 && waitingForTap}
              onPick={(index) => handlePick(block, index)}
            />
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
            <p className="app-hint">
              {bot.start_block_id ? "Тут пока пусто…" : "У бота ещё нет стартового блока — потяни стрелку от «▶ Старт» к первому сообщению."}
            </p>
          )}
        </div>

        <div className="live-preview__footer">
          {done ? (
            <button type="button" className="publish-button" onClick={replay}>
              🔁 Смотреть заново
            </button>
          ) : waitingForTap ? (
            <p className="live-preview__hint">👆 Нажми на кнопку выше, чтобы продолжить</p>
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

function PreviewBlock({
  block,
  isLast,
  interactive,
  onPick,
}: {
  block: BotBlock;
  isLast: boolean;
  interactive: boolean;
  onPick: (index: number) => void;
}) {
  const { content } = block;

  if (block.block_type === "payment") {
    const label = content.button_label?.trim() || `Оплатить ${content.price || "…"} ${content.currency || ""}`.trim();
    return (
      <div className="chat-row">
        <div className="chat-row__avatar">{isLast && <span className="chat-avatar">🤖</span>}</div>
        <div className="chat-row__content">
          <div className="chat-bubble">
            {content.text && <p className="chat-bubble__text">{content.text}</p>}
            <div className="chat-buttons">
              <div className="chat-buttons__preview">
                <span className="chat-buttons__pill">💳 {label}</span>
              </div>
            </div>
          </div>
          <p className="live-preview__pause-marker">в боте здесь откроется страница оплаты</p>
        </div>
      </div>
    );
  }

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
                  {content.buttons!.map((btn, i) =>
                    interactive ? (
                      <button key={i} type="button" className="chat-buttons__pill chat-buttons__pill--tappable" onClick={() => onPick(i)}>
                        {btn.label || "…"}
                      </button>
                    ) : (
                      <span key={i} className="chat-buttons__pill">
                        {btn.label || "…"}
                      </span>
                    ),
                  )}
                </div>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
