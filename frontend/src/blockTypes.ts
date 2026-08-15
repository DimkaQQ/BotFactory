import type { BlockContent, BlockType } from "./api/builderApi";

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
    hint: "Любое сообщение — расскажи о продукте",
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
    defaultContent: () => ({ question: "", options: ["", ""], anonymous: true }),
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
