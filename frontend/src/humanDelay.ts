/** "1 неделя", "3 дня", "5 сек" — a pause as a person would say it.
 *
 * Shared between the canvas node label and the block editor so the two can
 * never disagree about what a stored number of seconds means. Both used to
 * clamp it at fifteen, which is why a week-long pause read "Пауза 15 сек"
 * on the canvas. */
const STEPS: { limit: number; unit: number; forms: [string, string, string] }[] = [
  { limit: 7 * 24 * 3600, unit: 7 * 24 * 3600, forms: ["неделя", "недели", "недель"] },
  { limit: 24 * 3600, unit: 24 * 3600, forms: ["день", "дня", "дней"] },
  { limit: 3600, unit: 3600, forms: ["час", "часа", "часов"] },
  { limit: 60, unit: 60, forms: ["минута", "минуты", "минут"] },
];

/** Russian needs three forms, and "1 дней" in a product about writing to
 * customers reads as carelessness. */
function plural(n: number, forms: [string, string, string]): string {
  const mod100 = n % 100;
  if (mod100 >= 11 && mod100 <= 14) return forms[2];
  const mod10 = n % 10;
  if (mod10 === 1) return forms[0];
  if (mod10 >= 2 && mod10 <= 4) return forms[1];
  return forms[2];
}

export function humanDelay(seconds: number): string {
  const value = Math.max(0, Math.round(seconds || 0));
  for (const step of STEPS) {
    if (value >= step.limit && value % step.unit === 0) {
      const n = value / step.unit;
      return `${n} ${plural(n, step.forms)}`;
    }
  }
  // Anything that doesn't divide evenly stays in the largest whole unit it
  // fits into, rounded — "90 минут" beats "5400 сек" on a node label.
  for (const step of STEPS) {
    if (value >= step.limit) {
      const n = Math.round(value / step.unit);
      return `~${n} ${plural(n, step.forms)}`;
    }
  }
  return `${value} сек`;
}
