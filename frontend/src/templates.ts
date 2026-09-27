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
        // Текст обязателен: блок кнопок без него уходит покупателю как
        // сообщение «…» — Telegram не отправляет кнопки без сообщения.
        content: {
          text: "Готов забрать?",
          buttons: [{ label: "Купить", action_type: "text", action_value: "" }],
        },
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
    pitch: "Доступ в закрытый канал или чат за деньги в месяц",
    suggestedName: "Подписка",
    // Закрытый чат, а не капельная выдача видео. Прошлая версия была именно
    // капельницей: четыре выпуска с недельными паузами и ни слова про
    // доступ куда-либо, — а человек, который берёт этот шаблон, почти всегда
    // продаёт вход в свой канал. Ему приходилось выкинуть семь блоков из
    // двенадцати и собрать своё, то есть шаблон мешал, а не помогал. Выдачу
    // по расписанию собрать по-прежнему можно: «Пауза» и «Видео» лежат в
    // списке блоков слева.
    blocks: [
      {
        block_type: "welcome",
        content: { text: "Привет! Здесь открывается доступ в закрытый канал 🔔" },
      },
      {
        block_type: "description",
        content: {
          text: "Расскажи, что внутри канала и как часто там появляется новое. Это главный текст, который решает, купят или нет.",
        },
      },
      {
        block_type: "buttons",
        content: {
          text: "Готов присоединиться?",
          buttons: [{ label: "Оформить подписку", action_type: "text", action_value: "" }],
        },
      },
      {
        block_type: "payment",
        content: {
          text: "Подписка стоит [цена] в месяц. После оплаты бот сразу пришлёт ссылку на вход.",
          title: "Доступ в закрытый канал",
          price: "590",
          currency: "RUB",
          subscription: true,
          period_days: 30,
        },
      },
      {
        // Пустой group_chat_id, но с подсказкой: доступ выдаётся именно
        // отсюда, и без этого поля шаблон снова стал бы «просто сообщением».
        block_type: "delivery",
        content: {
          text: "Готово! Вот твоя персональная ссылка на вход — она одноразовая и только для тебя 👇",
          group_chat_id: "",
        },
      },
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
          // Услугу покупают не один раз. Без этого второй визит того же
          // клиента не продавался бы вовсе: бот сказал бы «уже оплачено» и
          // выдал сессию бесплатно.
          repeatable: true,
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
        // Не анонимный: у анонимного опроса Telegram не присылает ответы
        // вовсе (в них нет пользователя), то есть шаблон, который продан как
        // «узнать, чего хотят подписчики», не собирал бы ничего.
        content: { question: "Что вам интереснее всего?", options: ["Скидки", "Новинки", "Акции выходного дня"] },
      },
      {
        block_type: "buttons",
        // Адрес пустой, а не «https://»: такой Telegram отвергает целиком,
        // и вместе с кнопкой пропадало всё сообщение. Пустой ловит
        // чек-лист перед публикацией.
        content: {
          text: "Загляни к нам:",
          buttons: [{ label: "Наш сайт / меню", action_type: "url", action_value: "" }],
        },
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
