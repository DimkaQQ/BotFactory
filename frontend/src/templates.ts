import type { BlockContent, BlockType } from "./api/builderApi";

export interface BotTemplate {
  id: string;
  icon: string;
  label: string;
  pitch: string;
  suggestedName: string;
  blocks: { block_type: BlockType; content: BlockContent }[];
}

export const BOT_TEMPLATES: BotTemplate[] = [
  {
    id: "one-time-product",
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
      {
        block_type: "buttons",
        content: { buttons: [{ label: "Купить", action_type: "text", action_value: "Хочу купить" }] },
      },
      {
        block_type: "delivery",
        content: { text: "Спасибо за покупку! Вот твой материал 🎁 (пришли сюда ссылку или файл)" },
      },
    ],
  },
  {
    id: "subscription",
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
        content: { buttons: [{ label: "Оформить подписку", action_type: "text", action_value: "Хочу подписку" }] },
      },
      { block_type: "delivery", content: { text: "Отлично! Первый материал уже готовится — жди на этой неделе 👀" } },
    ],
  },
  {
    id: "one-on-one",
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
    icon: "🎉",
    label: "Акции и новости",
    pitch: "Кафе, магазин, шоурум — держи подписчиков в курсе скидок",
    suggestedName: "Акции и новости",
    blocks: [
      { block_type: "welcome", content: { text: "Привет! Подпишись, чтобы не пропускать акции и новинки 🎉" } },
      { block_type: "description", content: { text: "Расскажи о заведении или магазине в паре предложений." } },
      {
        block_type: "buttons",
        content: { buttons: [{ label: "Наш сайт / меню", action_type: "url", action_value: "https://" }] },
      },
    ],
  },
  {
    id: "blank",
    icon: "⬜",
    label: "С нуля",
    pitch: "Пустой бот — соберёшь сам из блоков",
    suggestedName: "",
    blocks: [],
  },
];
