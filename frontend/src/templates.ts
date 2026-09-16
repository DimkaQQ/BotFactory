import type { BlockContent, BlockType } from "./api/builderApi";

export interface BotTemplate {
  /** Only offered when subscriptions are enabled. */
  needsSubscriptions?: boolean;
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
        block_type: "payment",
        content: {
          text: "Стоимость — [цена]. После оплаты материал придёт сюда автоматически.",
          title: "[название продукта]",
          price: "990",
          currency: "RUB",
        },
      },
      {
        block_type: "delivery",
        content: { text: "Спасибо за покупку! Вот твой материал 🎁 (пришли сюда ссылку или файл)" },
      },
    ],
  },
  {
    id: "subscription",
    // Hidden while recurring billing is switched off server-side: the whole
    // template is a promise of monthly charging, and showing it then is the
    // same lie this product spent a while removing.
    needsSubscriptions: true,
    accent: "buttons",
    icon: "🔔",
    label: "Платная подписка",
    pitch: "Новый материал каждую неделю — тренер, коуч, закрытый канал",
    suggestedName: "Подписка",
    // The template builds the whole month, not just the sale: the payment
    // block is marked as a subscription and the three weekly videos are real
    // blocks behind real week-long pauses. It used to promise «новый видос
    // каждую неделю» on top of a bot that sent one message and never came
    // back — the copy was the feature.
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
      {
        block_type: "payment",
        content: {
          text: "Подписка стоит [цена] в месяц. После оплаты доступ откроется сразу.",
          title: "Подписка на месяц",
          price: "590",
          currency: "RUB",
          subscription: true,
          period_days: 30,
        },
      },
      { block_type: "delivery", content: { text: "Готово! Первое видео — сразу, дальше по одному каждую неделю 👀" } },
      { block_type: "video", content: { text: "Выпуск 1 — вставь ссылку на видео", media_type: "video" } },
      { block_type: "delay", content: { seconds: 7 * 24 * 3600 } },
      { block_type: "video", content: { text: "Выпуск 2 — придёт через неделю после оплаты", media_type: "video" } },
      { block_type: "delay", content: { seconds: 7 * 24 * 3600 } },
      { block_type: "video", content: { text: "Выпуск 3 — ещё через неделю", media_type: "video" } },
      { block_type: "delay", content: { seconds: 7 * 24 * 3600 } },
      { block_type: "video", content: { text: "Выпуск 4 — последний в этом месяце", media_type: "video" } },
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
        // One button, wired to the payment block. For separate time slots,
        // add a button per slot on the canvas and drag each one to its own
        // «Оплата» block titled with that time — then the sales list shows
        // which slot was booked, because the order carries the block's title.
        block_type: "buttons",
        content: {
          text: "Выбери, когда удобно — я подтвержу время в переписке.",
          buttons: [{ label: "Записаться", action_type: "text", action_value: "" }],
        },
      },
      {
        block_type: "payment",
        content: {
          text: "Сессия стоит [цена]. После оплаты я напишу тебе лично и подтвержу время.",
          title: "Личная сессия",
          price: "3000",
          currency: "RUB",
        },
      },
      {
        block_type: "delivery",
        content: {
          text:
            "Записал! Я получу уведомление с твоим именем и временем и свяжусь с тобой здесь, " +
            "чтобы подтвердить. До встречи 👋",
        },
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
    icon: "✏️",
    label: "С нуля",
    pitch: "Пустой бот — соберёшь сам из блоков",
    suggestedName: "",
    blocks: [],
  },
];
