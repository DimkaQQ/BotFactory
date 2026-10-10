import type { BlockContent, BlockType } from "./api/builderApi";
import { defaultWeekly, localTimezone } from "./booking";

export interface BlockTypeDef {
  type: BlockType;
  label: string;
  icon: string;
  accent: string;
  hint: string;
  defaultContent: () => BlockContent;
}

/** Single source of truth for every block type the constructor offers —
 * used by the sidebar/sheet picker, the hover preview flyout, and the
 * default content a freshly-added block starts with. */
export const BLOCK_TYPES: BlockTypeDef[] = [
  {
    type: "welcome",
    label: "Приветствие",
    icon: "👋",
    accent: "welcome",
    hint: "Первое сообщение при /start",
    defaultContent: () => ({ text: "" }),
  },
  {
    type: "description",
    label: "Текст",
    icon: "📝",
    accent: "description",
    hint: "Любое сообщение: расскажи о продукте",
    defaultContent: () => ({ text: "" }),
  },
  {
    type: "image",
    label: "Изображение",
    icon: "🖼️",
    accent: "image",
    hint: "Фото со ссылкой и подписью",
    defaultContent: () => ({ media_type: "photo", media_file_id: "", text: "" }),
  },
  {
    type: "video",
    label: "Видео",
    icon: "🎬",
    accent: "video",
    hint: "Видео со ссылкой и подписью",
    defaultContent: () => ({ media_type: "video", media_file_id: "", text: "" }),
  },
  {
    type: "buttons",
    label: "Кнопки",
    icon: "🔘",
    accent: "buttons",
    hint: "Ссылки и переходы",
    defaultContent: () => ({ buttons: [] }),
  },
  {
    type: "poll",
    label: "Опрос",
    icon: "📊",
    accent: "poll",
    hint: "Вопрос с вариантами ответа",
    // Не анонимный по умолчанию. У анонимного опроса Telegram не присылает
    // ответы вовсе: в них нет пользователя,, то есть блок, который
    // продаётся как способ «узнать, чего хотят подписчики», не собирал бы
    // ничего. Анонимность остаётся выбором, но выбором осознанным.
    defaultContent: () => ({ question: "", options: ["", ""], anonymous: false }),
  },
  {
    type: "delivery",
    label: "Выдача",
    icon: "🎁",
    accent: "delivery",
    hint: "Файл, ссылка или доступ",
    defaultContent: () => ({ text: "" }),
  },
  {
    type: "payment",
    label: "Оплата",
    icon: "💳",
    accent: "success",
    hint: "Кнопка оплаты: выдача после платежа",
    // No currency here on purpose: a new payment block takes the one the
    // connected cash desk actually charges in (see BotBuilder.handleAdd).
    // A hardcoded "KZT" meant a shop on ЮKassa typed 990, got a block
    // priced in tenge, and either hit a refusal at checkout or, on a
    // provider that takes both, charged 990 ₸ ≈ 170 ₽ for a 990 ₽ guide.
    // RUB, not KZT: this product is Russian-language and CIS-first, and
    // it is the same value PaymentEditor falls back to, so the canvas
    // and the editor agree from the first render. Once a cash desk is
    // connected, BotBuilder.handleAdd uses *its* currency instead.
    defaultContent: () => ({ text: "", title: "", price: "", currency: "RUB", button_label: "" }),
  },
  {
    type: "contact",
    label: "Контакты",
    icon: "📇",
    accent: "welcome",
    hint: "Спросить имя и телефон: Telegram приходит сам",
    defaultContent: () => ({ text: "", ask_name: false, ask_phone: true }),
  },
  {
    type: "booking",
    label: "Запись",
    icon: "📅",
    accent: "poll",
    hint: "Клиент выбирает день и время в календаре",
    defaultContent: () => ({
      text: "Выберите день:",
      weekly: defaultWeekly(),
      exceptions: {},
      slot_minutes: 60,
      horizon_days: 14,
      notice_hours: 2,
      tz: localTimezone(),
    }),
  },
  {
    type: "delay",
    label: "Пауза",
    icon: "⏱",
    accent: "delay",
    hint: "Задержка перед следующим шагом",
    defaultContent: () => ({ seconds: 3 }),
  },
];

export const BLOCK_TYPE_BY_ID: Record<BlockType, BlockTypeDef> = Object.fromEntries(
  BLOCK_TYPES.map((def) => [def.type, def]),
) as Record<BlockType, BlockTypeDef>;
