import { useEffect, useMemo, useRef, useState } from "react";

import { type BotBlock, type BotWithBlocks, currencyUnit } from "../api/builderApi";
import { useDialogA11y } from "../hooks/useDialogA11y";
import { useEscape } from "../hooks/useEscape";
import { scrollBehavior } from "../motion";
import { fillPlaceholders, placeholderValues } from "../placeholders";

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

/** The same rule the dispatcher applies, and for the same reason: a button
 * that opens a URL sends Telegram nothing when it is tapped, so the real bot
 * cannot branch on it and walks straight past. A preview that stopped there
 * would offer a path the live bot can never take. */
function hasBranches(block: BotBlock): boolean {
  if (block.block_type !== "buttons" || block.content.keyboard === "remove") return false;
  return (block.content.buttons ?? []).some(
    (b) => (b.target_block_id || "").trim() && b.action_type !== "url",
  );
}

/** Блоки, на которых настоящий бот останавливается и ждёт покупателя: оплата (цепочка идёт дальше
 * только после подтверждения денег) и запись (дальше — после выбора дня и времени). Предпросмотр
 * обязан остановиться там же, иначе «выдача» покажется до оплаты. */
function waitsForBuyer(block: BotBlock): string | null {
  if (block.block_type === "payment") return "Здесь бот ждёт оплату. Выдача придёт только после неё.";
  if (block.block_type === "booking") return "Здесь клиент выбирает день и время. Дальше — после его выбора.";
  return null;
}

/** Walks the same graph the real bot walks (start_block_id → next_block_id,
 * pausing at any buttons block with a configured branch) instead of just
 * replaying the flat block list — tapping a button here actually picks the
 * path, exactly like a real Telegram chat with this bot would. */
export function LivePreview({ bot, botName, onClose }: Props) {
  useEscape(onClose);
  const dialogRef = useRef<HTMLDivElement | null>(null);
  useDialogA11y(dialogRef, ".live-preview__title");

  // Заготовки «[цена]» и «[название продукта]» бот подставляет сам — предпросмотр тоже.
  const fill = useMemo(() => {
    const { price, title } = placeholderValues(bot.blocks);
    return (text: string) => fillPlaceholders(text, price, title).trim();
  }, [bot.blocks]);
  const blocksById = useMemo(() => new Map(bot.blocks.map((b) => [b.id, b])), [bot.blocks]);

  const [revealed, setRevealed] = useState<BotBlock[]>([]);
  const [currentId, setCurrentId] = useState<string | null>(bot.start_block_id);
  const [countdown, setCountdown] = useState<number | null>(null);
  const [showTyping, setShowTyping] = useState(false);
  const [waitingForTap, setWaitingForTap] = useState(false);
  const [done, setDone] = useState(!bot.start_block_id);
  // Блок оплаты/записи: бот ждёт покупателя; `next` — куда пойдёт сценарий после этого.
  const [gate, setGate] = useState<{ hint: string; next: string | null } | null>(null);
  // Номер шага: переход на тот же блок (кнопка «повторить», «Смотреть заново» со стартового) тоже
  // должен запустить показ заново, а `currentId` в таком случае не меняется.
  const [step, setStep] = useState(0);
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
    setGate(null);
    setDone(!bot.start_block_id);
    setCurrentId(bot.start_block_id);
    setStep((n) => n + 1);
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

      const gateHint = waitsForBuyer(block);
      if (hasBranches(block)) {
        setWaitingForTap(true);
      } else if (gateHint) {
        setGate({ hint: gateHint, next: block.next_block_id });
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
  }, [currentId, step]);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: scrollBehavior() });
  }, [revealed, countdown]);

  function handlePick(block: BotBlock, index: number) {
    const target = (block.content.buttons?.[index]?.target_block_id || "").trim();
    if (!target) return; // this button isn't wired to anything — real bot just re-answers the tap and stays put
    // Каждое нажатие в настоящем боте начинает новый обход: меню, куда ведёт «Назад», должно
    // показываться снова, а не считаться петлёй.
    visitedRef.current = new Set();
    setWaitingForTap(false);
    setCurrentId(target);
    setStep((n) => n + 1);
  }

  function continueAfterGate() {
    if (!gate) return;
    const next = gate.next;
    setGate(null);
    if (next) {
      setCurrentId(next);
      setStep((n) => n + 1);
    } else {
      setDone(true);
    }
  }

  // Быстрые кнопки живут внизу экрана, а не в сообщении, и остаются, пока их
  // не заменит другая клавиатура — как в Telegram.
  const lastKeyboardBlock =
    [...revealed]
      .reverse()
      .find((b) => b.block_type === "buttons" && (b.content.keyboard === "reply" || b.content.keyboard === "remove")) ?? null;
  const replyBlock = lastKeyboardBlock?.content.keyboard === "reply" ? lastKeyboardBlock : null;

  function handleReplyPick(block: BotBlock, index: number) {
    const button = block.content.buttons?.[index];
    const target = (button?.target_block_id || "").trim();
    if (!target || button?.action_type === "url") return;
    visitedRef.current = new Set();
    setDone(false);
    setGate(null);
    setWaitingForTap(false);
    setCurrentId(target);
    setStep((n) => n + 1);
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
      <div className="live-preview" ref={dialogRef}>
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
              fill={fill}
              isLast={i === lastBubbleIndex && !showTyping}
              interactive={i === revealed.length - 1 && waitingForTap && block.content.keyboard !== "reply"}
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

        {replyBlock && (
          <div className="live-preview__keyboard" aria-label="Быстрые кнопки">
            {(replyBlock.content.buttons ?? [])
              .map((btn, i) => ({ btn, i }))
              .filter(({ btn }) => (btn.label || "").trim())
              .map(({ btn, i }) => (
                <button key={i} type="button" className="live-preview__key" onClick={() => handleReplyPick(replyBlock, i)}>
                  {btn.label}
                </button>
              ))}
          </div>
        )}

        <div className="live-preview__footer">
          {done ? (
            <button type="button" className="publish-button" onClick={replay}>
              🔁 Смотреть заново
            </button>
          ) : gate ? (
            <>
              <p className="live-preview__hint">{gate.hint}</p>
              <button type="button" className="live-preview__skip" onClick={continueAfterGate}>
                {gate.next ? "Показать, что придёт дальше" : "Завершить"}
              </button>
            </>
          ) : waitingForTap ? (
            <p className="live-preview__hint">
              {replyBlock && replyBlock === revealed[revealed.length - 1]
                ? "👇 Нажми на быструю кнопку внизу, чтобы продолжить"
                : "👆 Нажми на кнопку выше, чтобы продолжить"}
            </p>
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
  fill,
  isLast,
  interactive,
  onPick,
}: {
  block: BotBlock;
  fill: (text: string) => string;
  isLast: boolean;
  interactive: boolean;
  onPick: (index: number) => void;
}) {
  const { content } = block;

  if (block.block_type === "payment") {
    // Знак валюты, а не код: живой бот присылает «Оплатить 990 ₽», и
    // предпросмотр, который обещал «990 RUB», показывал не ту кнопку,
    // которую увидит покупатель.
    const label =
      content.button_label?.trim() ||
      `Оплатить ${content.price || "…"} ${currencyUnit(content.currency || "")}`.trim();
    return (
      <div className="chat-row">
        <div className="chat-row__avatar">{isLast && <span className="chat-avatar">🤖</span>}</div>
        <div className="chat-row__content">
          <div className="chat-bubble">
            {(content.text || content.title) && <p className="chat-bubble__text">{fill(content.text || content.title || "")}</p>}
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
        ) : block.block_type === "booking" ? (
          <div className="chat-bubble">
            <p className="chat-bubble__text">{content.text || "Выберите день:"}</p>
            <div className="chat-buttons">
              <div className="chat-buttons__preview">
                {["Чт 8 окт", "Пт 9 окт", "Сб 10 окт"].map((d) => (
                  <span key={d} className="chat-buttons__pill">
                    {d}
                  </span>
                ))}
              </div>
            </div>
            <p className="block-preview__caption">В боте клиент выберет день и свободное время, затем сценарий пойдёт дальше.</p>
          </div>
        ) : block.block_type === "contact" ? (
          <div className="chat-bubble">
            <p className="chat-bubble__text">
              {content.ask_name || content.ask_phone
                ? `${content.text ? content.text + "\n\n" : ""}${content.ask_name ? "Как к вам обращаться? " : ""}${content.ask_phone ? "Оставьте номер телефона." : ""}`
                : "Ничего не спрашиваем: имя и @username берём из Telegram."}
            </p>
            {content.ask_phone && (
              <div className="chat-buttons">
                <div className="chat-buttons__preview">
                  <span className="chat-buttons__pill">📱 Отправить мой номер</span>
                </div>
              </div>
            )}
          </div>
        ) : (
          <div className="chat-bubble">
            {content.media_file_id && block.block_type === "image" && (
              <div className="block-preview__media live-preview__media">🖼️</div>
            )}
            {content.media_file_id && block.block_type === "video" && (
              <div className="block-preview__media block-preview__media--video live-preview__media">▶</div>
            )}
            {content.text && fill(content.text) && <p className="chat-bubble__text">{fill(content.text)}</p>}
            {(content.buttons ?? []).length > 0 && content.keyboard !== "reply" && content.keyboard !== "remove" && (
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
