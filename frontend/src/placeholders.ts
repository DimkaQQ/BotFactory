import { currencyUnit } from "./api/builderApi";
import type { BotBlock } from "./api/builderApi";

const PLACEHOLDER = /\[\s*(цена|стоимость|сумма|название продукта|название|продукт)\s*\]/gi;

/** То же, что `fill_placeholders` в app/services/bot_dispatcher.py: заготовки шаблонов
 * («Стоимость — [цена]») бот заменяет ценой и названием из первого блока оплаты, а если брать
 * нечего — убирает вместе с лишним пробелом. Предпросмотр обязан показывать то же самое. */
export function fillPlaceholders(text: string, price: string, title: string): string {
  if (!text.includes("[")) return text;
  const out = text.replace(PLACEHOLDER, (_all, key: string) =>
    ["цена", "стоимость", "сумма"].includes(key.toLowerCase()) ? price : title,
  );
  return out.replace(/[ \t]{2,}/g, " ").split(" .").join(".").split(" ,").join(",");
}

/** Цена и название для подстановки: из первого блока оплаты бота. */
export function placeholderValues(blocks: BotBlock[]): { price: string; title: string } {
  const pay = [...blocks].filter((b) => b.block_type === "payment").sort((a, b) => a.order_index - b.order_index)[0];
  if (!pay) return { price: "", title: "" };
  const raw = String(pay.content.price ?? "").trim();
  const price = raw ? `${raw} ${currencyUnit(String(pay.content.currency ?? ""))}`.trim() : "";
  return { price, title: fillPlaceholders(String(pay.content.title ?? ""), "", "").trim() };
}
