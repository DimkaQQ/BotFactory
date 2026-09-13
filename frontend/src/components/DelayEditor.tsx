import type { BlockContent } from "../api/builderApi";
import { humanDelay } from "../humanDelay";

/** The inline ceiling in the engine (scheduler.INLINE_PAUSE_SECONDS). Below
 * it the bot simply waits inside the conversation; above it the rest of the
 * chain is queued and resumes later. Named here so the copy can tell the
 * truth about which of the two is about to happen. */
const INLINE_CEILING = 15;

const MINUTE = 60;
const HOUR = 60 * MINUTE;
const DAY = 24 * HOUR;
const WEEK = 7 * DAY;

const UNITS = [
  { id: "seconds", label: "сек", factor: 1 },
  { id: "minutes", label: "мин", factor: MINUTE },
  { id: "hours", label: "часов", factor: HOUR },
  { id: "days", label: "дней", factor: DAY },
  { id: "weeks", label: "недель", factor: WEEK },
] as const;

type UnitId = (typeof UNITS)[number]["id"];

/** Seconds → the largest unit that divides evenly, so 604800 comes back as
 * "1 неделя" and not "604800 секунд". */
function split(seconds: number): { amount: number; unit: UnitId } {
  for (const unit of [...UNITS].reverse()) {
    if (seconds >= unit.factor && seconds % unit.factor === 0) {
      return { amount: seconds / unit.factor, unit: unit.id };
    }
  }
  return { amount: Math.max(1, Math.round(seconds || 2)), unit: "seconds" };
}

const PRESETS: { label: string; seconds: number }[] = [
  { label: "2 сек", seconds: 2 },
  { label: "5 сек", seconds: 5 },
  { label: "1 час", seconds: HOUR },
  { label: "1 день", seconds: DAY },
  { label: "3 дня", seconds: 3 * DAY },
  { label: "1 неделя", seconds: WEEK },
  { label: "2 недели", seconds: 2 * WEEK },
  { label: "1 месяц", seconds: 30 * DAY },
];

interface Props {
  content: BlockContent;
  onChange: (content: BlockContent) => void;
}

/**
 * How long the bot waits before the next block.
 *
 * This used to offer 1–10 seconds and nothing else, which made it look like
 * a typing-rhythm effect and hid the fact that the engine could not send
 * anything later at all. It is now the front end of the scheduler: a pause
 * measured in days is what turns a chain of video blocks into "3–4 видео в
 * течение месяца", which is the single most-requested thing a subscription
 * bot has to do.
 */
export function DelayEditor({ content, onChange }: Props) {
  const seconds = Math.max(1, Number(content.seconds ?? 2) || 2);
  const { amount, unit } = split(seconds);
  const scheduled = seconds > INLINE_CEILING;

  function set(nextAmount: number, nextUnit: UnitId) {
    const nextFactor = UNITS.find((u) => u.id === nextUnit)?.factor ?? 1;
    onChange({ ...content, seconds: Math.max(1, Math.round(nextAmount)) * nextFactor });
  }

  return (
    <div className="delay-editor">
      <div className="delay-editor__row">
        <input
          className="payment-editor__input delay-editor__amount"
          type="number"
          min={1}
          max={999}
          value={amount}
          onChange={(e) => set(Number(e.target.value) || 1, unit)}
          aria-label="Сколько ждать"
        />
        <select
          className="payment-editor__input delay-editor__unit"
          value={unit}
          onChange={(e) => set(amount, e.target.value as UnitId)}
          aria-label="Единица времени"
        >
          {UNITS.map((u) => (
            <option key={u.id} value={u.id}>
              {u.label}
            </option>
          ))}
        </select>
      </div>

      <div className="delay-editor__presets">
        {PRESETS.map((preset) => (
          <button
            key={preset.seconds}
            type="button"
            className={`chat-delay__preset ${seconds === preset.seconds ? "chat-delay__preset--active" : ""}`}
            onClick={() => onChange({ ...content, seconds: preset.seconds })}
          >
            {preset.label}
          </button>
        ))}
      </div>

      {/* The two behaviours are genuinely different and the owner has to know
          which one they just picked: one happens inside the conversation,
          the other outlives it. */}
      <p className="app-hint delay-editor__note">
        {scheduled
          ? `⏳ Через ${humanDelay(seconds)} бот вернётся сам и продолжит с следующего блока — даже если человек закроет чат.`
          : "⌛️ Короткая пауза прямо в диалоге — чтобы сообщения не сыпались сразу. Для «пришли материал через неделю» поставь часы или дни."}
      </p>
    </div>
  );
}
