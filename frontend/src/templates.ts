import type { BlockContent, BlockType } from "./api/builderApi";

export interface BotTemplate {
  id: string;
  icon: string;
  label: string;
  pitch: string;
  /** Which --accent-* colour the card is tinted with (same palette as the
   * block types — see index.css), so a template is recognisable by colour
   * and not just by emoji. */
  accent: string;
  suggestedName: string;
  blocks: { block_type: BlockType; content: BlockContent }[];
}

/** "5 блоков" / "1 блок" / "3 блока" — Russian plural agreement, used on
 * both the landing's template cards and the in-app picker. */
export function blocksLabel(count: number): string {
  if (count % 10 === 1 && count % 100 !== 11) return `${count} блок`;
  if ([2, 3, 4].includes(count % 10) && ![12, 13, 14].includes(count % 100)) return `${count} блока`;
  return `${count} блоков`;
}

export const BOT_TEMPLATES: BotTemplate[] = [
  {
    id: "one-time-product",
    accent: "delivery",
    icon: "📦",
    label: "Разовый продукт",
    pitch: "Гайд, курс, файл, путеводитель — купил один раз и получил",
    suggestedName: "Разовый продукт",
    blocks: [
      { block_type: "welcome", content: { text: "Привет! Здесь можно получить [название продукта] 👋" } },
      {
        block_type: "description",
        content: { text: "Расскажи, что внутри и кому это подойдёт — 2-3 предложения хватит." },
      },
      { block_type: "image", content: { media_type: "photo", media_file_id: "", text: "Как это выглядит" } },
      {
        block_type: "buttons",
        content: { buttons: [{ label: "Купить", action_type: "text", action_value: "" }] },
      },
      {
        block_type: "delivery",
        content: { text: "Спасибо за покупку! Вот твой материал 🎁 (пришли сюда ссылку или файл)" },
      },
    ],
  },
  {
    id: "subscription",
    accent: "buttons",
    icon: "🔔",
    label: "Платная подписка",
    pitch: "Новый видос/техника каждую неделю для подписчиков — тренер, коуч, канал",
    suggestedName: "Подписка",
    blocks: [
      { block_type: "welcome", content: { text: "Привет! Здесь ты будешь получать новый материал каждую неделю 🔔" } },
      {
        block_type: "description",
        content: { text: "Опиши, что именно получают подписчики и как часто выходит новый выпуск." },
      },
      {
        block_type: "buttons",
        content: { buttons: [{ label: "Оформить подписку", action_type: "text", action_value: "" }] },
      },
      { block_type: "delivery", content: { text: "Отлично! Первый материал уже готовится — жди на этой неделе 👀" } },
    ],
  },
  {
    id: "one-on-one",
    accent: "poll",
    icon: "📅",
    label: "Запись на сессию",
    pitch: "Консультация, коучинг, разбор один-на-один",
    suggestedName: "Запись на сессию",
    blocks: [
      { block_type: "welcome", content: { text: "Привет! Здесь можно записаться на личную сессию со мной 📅" } },
      {
        block_type: "description",
        content: { text: "Опиши формат: длительность, что разбираем, что получит клиент на выходе." },
      },
      {
        block_type: "buttons",
        content: { buttons: [{ label: "Записаться", action_type: "url", action_value: "https://" }] },
      },
    ],
  },
  {
    id: "promo-broadcast",
    accent: "image",
    icon: "🎉",
    label: "Акции и новости",
    pitch: "Кафе, магазин, шоурум — держи подписчиков в курсе скидок",
    suggestedName: "Акции и новости",
    blocks: [
      { block_type: "welcome", content: { text: "Привет! Подпишись, чтобы не пропускать акции и новинки 🎉" } },
      { block_type: "description", content: { text: "Расскажи о заведении или магазине в паре предложений." } },
      {
        block_type: "poll",
        content: { question: "Что вам интереснее всего?", options: ["Скидки", "Новинки", "Акции выходного дня"], anonymous: true },
      },
      {
        block_type: "buttons",
        content: { buttons: [{ label: "Наш сайт / меню", action_type: "url", action_value: "https://" }] },
      },
    ],
  },
  {
    id: "blank",
    accent: "delay",
    icon: "⬜",
    label: "С нуля",
    pitch: "Пустой бот — соберёшь сам из блоков",
    suggestedName: "",
    blocks: [],
  },
];
