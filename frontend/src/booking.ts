import type { BlockContent } from "./api/builderApi";

export type Interval = [string, string];
export type Weekly = Record<string, Interval[]>;

/** Часовой пояс устройства владельца: по нему и предлагаем расписание. */
export function localTimezone(): string {
  try {
    return Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC";
  } catch {
    return "UTC";
  }
}

export function defaultWeekly(): Weekly {
  const work: Interval[] = [["10:00", "19:00"]];
  return { "0": work, "1": work, "2": work, "3": work, "4": work, "5": [], "6": [] };
}

/** Расписание по дням недели; блок в прежнем формате (дни + одни часы) читается тоже. */
export function readWeekly(content: BlockContent): Weekly {
  if (content.weekly && typeof content.weekly === "object") {
    const out: Weekly = {};
    for (let d = 0; d < 7; d++) out[String(d)] = (content.weekly[String(d)] ?? []) as Interval[];
    return out;
  }
  if (Array.isArray(content.days)) {
    const out: Weekly = {};
    for (let d = 0; d < 7; d++) {
      out[String(d)] = content.days.includes(d) ? [[content.start ?? "10:00", content.end ?? "19:00"]] : [];
    }
    return out;
  }
  return defaultWeekly();
}

export function timezones(current: string): string[] {
  let all: string[] = [];
  try {
    all = (Intl as unknown as { supportedValuesOf?: (k: string) => string[] }).supportedValuesOf?.("timeZone") ?? [];
  } catch {
    all = [];
  }
  const base = all.length > 0 ? all : ["UTC", "Europe/Moscow", "Europe/Kyiv", "Europe/Minsk", "Asia/Almaty", "Asia/Tashkent"];
  return Array.from(new Set([current, localTimezone(), ...base]));
}

const DAYS = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"];

/** Короткая строка для карточки блока на холсте: «Пн–Пт 10:00–19:00». */
export function scheduleSummary(content: BlockContent): string {
  const weekly = readWeekly(content);
  const working = DAYS.map((_, i) => ({ i, iv: weekly[String(i)] })).filter((d) => d.iv.length > 0);
  if (working.length === 0) return "Запись закрыта: не выбрано ни одного дня";
  const first = working[0].iv[0];
  const same = working.every((d) => JSON.stringify(d.iv) === JSON.stringify(working[0].iv));
  const days = working.length === 7 ? "каждый день" : working.map((d) => DAYS[d.i]).join(", ");
  return same ? `${days} · ${first[0]}–${working[0].iv[working[0].iv.length - 1][1]}` : `${days} · часы по дням`;
}
