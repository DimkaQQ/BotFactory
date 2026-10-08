import type { BlockContent, BlockType } from "./api/builderApi";
import { defaultWeekly, localTimezone } from "./booking";

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
  /** Своя разводка вместо простой цепочки: нажатие кнопки `button` блока `from`
   * ведёт к блоку `to` (номера — позиции в `blocks`). Блоки до первого блока
   * кнопок соединяются по порядку. */
  links?: { from: number; button: number; to: number }[];
  /** Стрелки «дальше»: [откуда, куда]. Если задано, простая цепочка не строится. */
  nexts?: [number, number][];
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
      { block_type: "welcome", content: { text: "Здравствуйте! Здесь можно получить [название продукта] 👋" } },
      {
        block_type: "description",
        content: { text: "[Расскажи, что внутри и кому это подойдёт — 2-3 предложения хватит.]" },
      },
      { block_type: "image", content: { media_type: "photo", media_file_id: "", text: "Как это выглядит" } },
      {
        block_type: "buttons",
        // Текст обязателен: блок кнопок без него уходит покупателю как
        // сообщение «…» — Telegram не отправляет кнопки без сообщения.
        content: {
          text: "Готовы забрать?",
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
        content: { text: "Спасибо за покупку! Вот ваш материал 🎁 [пришли сюда ссылку или файл]" },
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
        content: { text: "Здравствуйте! Здесь открывается доступ в закрытый канал 🔔" },
      },
      {
        block_type: "description",
        content: {
          text: "[Расскажи, что внутри канала и как часто там появляется новое. Это главный текст, который решает, купят или нет.]",
        },
      },
      {
        block_type: "buttons",
        content: {
          text: "Готовы присоединиться?",
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
          text: "Готово! Вот ваша персональная ссылка на вход — она одноразовая и только для вас 👇",
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
      { block_type: "welcome", content: { text: "Здравствуйте! Здесь можно записаться на личную сессию со мной 📅" } },
      {
        block_type: "description",
        content: { text: "[Опиши формат: длительность, что разбираем, что получит клиент на выходе.]" },
      },
      {
        // One button, wired to the payment block. For separate time slots,
        // add a button per slot on the canvas and drag each one to its own
        // «Оплата» block titled with that time — then the sales list shows
        // which slot was booked, because the order carries the block's title.
        block_type: "buttons",
        content: {
          text: "Выберите, когда удобно — я подтвержу время в переписке.",
          buttons: [{ label: "Записаться", action_type: "text", action_value: "" }],
        },
      },
      {
        block_type: "payment",
        content: {
          text: "Сессия стоит [цена]. После оплаты я напишу вам лично и подтвержу время.",
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
            "Записал! Я получу уведомление с вашим именем и временем и свяжусь с вами здесь, " +
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
      { block_type: "welcome", content: { text: "Здравствуйте! Подпишитесь, чтобы не пропускать акции и новинки 🎉" } },
      { block_type: "description", content: { text: "[Расскажи о заведении или магазине в паре предложений.]" } },
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
          text: "Загляните к нам:",
          buttons: [{ label: "Наш сайт / меню", action_type: "url", action_value: "" }],
        },
      },
    ],
  },
  {
    id: "quick-menu",
    accent: "buttons",
    icon: "⌨️",
    label: "Меню с быстрыми кнопками",
    pitch: "Кафе, салон, магазин: кнопки внизу экрана — цены, отзывы, адрес. Хороший пример, как это выглядит",
    suggestedName: "Меню с быстрыми кнопками",
    blocks: [
      { block_type: "welcome", content: { text: "Здравствуйте! Выберите внизу, что показать 👇" } },
      {
        block_type: "buttons",
        content: {
          keyboard: "reply",
          text: "Что вас интересует?",
          buttons: [
            { label: "💰 Цены", action_type: "text", action_value: "" },
            { label: "⭐ Отзывы", action_type: "text", action_value: "" },
            { label: "📍 Как добраться", action_type: "text", action_value: "" },
          ],
        },
      },
      { block_type: "description", content: { text: "[Цены: например, стрижка — 1500 ₽, окрашивание — 4000 ₽.]" } },
      { block_type: "description", content: { text: "[Отзывы клиентов: вставь настоящие отзывы со своего разрешения.]" } },
      { block_type: "description", content: { text: "[Адрес и часы работы: ул. Примерная, 1, ежедневно 10:00–21:00.]" } },
    ],
    nexts: [[0, 1]],
    links: [
      { from: 1, button: 0, to: 2 },
      { from: 1, button: 1, to: 3 },
      { from: 1, button: 2, to: 4 },
    ],
  },
  {
    id: "salon-booking",
    accent: "poll",
    icon: "📅",
    label: "Запись по предоплате",
    pitch: "Календарь со свободным временем, контакты клиента, предоплата и подтверждение записи",
    suggestedName: "Запись по предоплате",
    blocks: [
      { block_type: "welcome", content: { text: "Здравствуйте! Здесь можно посмотреть услуги и записаться 👇" } },
      {
        block_type: "buttons",
        content: {
          keyboard: "reply",
          text: "Что вас интересует?",
          buttons: [
            { label: "📅 Записаться", action_type: "text", action_value: "" },
            { label: "💇 Услуги и цены", action_type: "text", action_value: "" },
            { label: "📍 Адрес", action_type: "text", action_value: "" },
          ],
        },
      },
      { block_type: "description", content: { text: "[Услуги и цены: стрижка — 1500 ₽, окрашивание — 4000 ₽.]" } },
      {
        block_type: "contact",
        // Имя и @username приходят из Telegram сами; спрашиваем только телефон.
        content: { text: "Оставьте контакт, чтобы мы могли подтвердить запись.", ask_name: false, ask_phone: true },
      },
      {
        block_type: "booking",
        content: {
          text: "Выберите день:",
          weekly: defaultWeekly(),
          exceptions: {},
          slot_minutes: 60,
          horizon_days: 14,
          notice_hours: 2,
          tz: localTimezone(),
        },
      },
      {
        block_type: "payment",
        content: {
          text: "Предоплата за запись — [цена]. Она засчитывается в стоимость услуги. Время придержано на час.",
          title: "Предоплата за запись",
          price: "500",
          currency: "RUB",
          repeatable: true,
        },
      },
      {
        block_type: "delivery",
        content: { text: "Записал! Мастер напишет вам здесь, если что-то изменится. До встречи 👋" },
      },
      { block_type: "description", content: { text: "[Адрес и часы работы: ул. Примерная, 1, ежедневно 10:00–21:00.]" } },
    ],
    nexts: [
      [0, 1],
      [3, 4],
      [4, 5],
      [5, 6],
    ],
    links: [
      { from: 1, button: 0, to: 3 },
      { from: 1, button: 1, to: 2 },
      { from: 1, button: 2, to: 7 },
    ],
  },
  {
    id: "booking-free",
    accent: "poll",
    icon: "🗓",
    label: "Запись без оплаты",
    pitch: "Консультация, занятие, приём: клиент выбирает время, вы видите записи и контакты",
    suggestedName: "Онлайн-запись",
    blocks: [
      { block_type: "welcome", content: { text: "Здравствуйте! Запишу вас на удобное время 👇" } },
      {
        block_type: "buttons",
        content: {
          keyboard: "reply",
          text: "Что вас интересует?",
          buttons: [
            { label: "📅 Записаться", action_type: "text", action_value: "" },
            { label: "ℹ️ Об услуге", action_type: "text", action_value: "" },
          ],
        },
      },
      { block_type: "description", content: { text: "[Об услуге: что входит, сколько длится, сколько стоит.]" } },
      {
        block_type: "contact",
        content: { text: "", ask_name: false, ask_phone: false },
      },
      {
        block_type: "booking",
        content: {
          text: "Выберите день:",
          weekly: { ...defaultWeekly(), "0": [["10:00", "18:00"]], "1": [["10:00", "18:00"]], "2": [["10:00", "18:00"]], "3": [["10:00", "18:00"]], "4": [["10:00", "18:00"]] },
          exceptions: {},
          slot_minutes: 60,
          horizon_days: 14,
          notice_hours: 2,
          tz: localTimezone(),
        },
      },
      { block_type: "delivery", content: { text: "Ждём вас! Если планы изменятся, напишите — перенесём 🙏" } },
    ],
    nexts: [
      [0, 1],
      [3, 4],
      [4, 5],
    ],
    links: [
      { from: 1, button: 0, to: 3 },
      { from: 1, button: 1, to: 2 },
    ],
  },
  {
    id: "shop-showcase",
    accent: "image",
    icon: "🛍",
    label: "Магазин: каталог и покупка",
    pitch: "Каталог, доставка, покупка в один тап, связь с продавцом",
    suggestedName: "Магазин",
    blocks: [
      { block_type: "welcome", content: { text: "Здравствуйте! Выбирайте внизу 👇" } },
      {
        block_type: "buttons",
        content: {
          keyboard: "reply",
          text: "Чем помочь?",
          buttons: [
            { label: "🛍 Каталог", action_type: "text", action_value: "" },
            { label: "🚚 Доставка и оплата", action_type: "text", action_value: "" },
            { label: "💳 Купить", action_type: "text", action_value: "" },
            { label: "☎️ Связаться", action_type: "text", action_value: "" },
          ],
        },
      },
      { block_type: "description", content: { text: "[Каталог: перечисли товары и цены.]" } },
      { block_type: "description", content: { text: "[Доставка и оплата: сроки, стоимость, способы.]" } },
      {
        block_type: "payment",
        content: {
          text: "К оплате — [цена]. После оплаты вы получите подтверждение.",
          title: "Заказ в магазине",
          price: "1990",
          currency: "RUB",
          repeatable: true,
        },
      },
      { block_type: "delivery", content: { text: "Заказ оплачен, спасибо! Мы свяжемся с вами для отправки 📦" } },
      {
        block_type: "buttons",
        content: {
          text: "Написать продавцу:",
          buttons: [{ label: "Написать в Telegram", action_type: "url", action_value: "" }],
        },
      },
    ],
    nexts: [
      [0, 1],
      [4, 5],
    ],
    links: [
      { from: 1, button: 0, to: 2 },
      { from: 1, button: 1, to: 3 },
      { from: 1, button: 2, to: 4 },
      { from: 1, button: 3, to: 6 },
    ],
  },
  {
    id: "faq-support",
    accent: "welcome",
    icon: "❓",
    label: "Частые вопросы и поддержка",
    pitch: "Бот отвечает на типовые вопросы кнопками, сложное — передаёт вам",
    suggestedName: "Помощь",
    blocks: [
      { block_type: "welcome", content: { text: "Здравствуйте! Выберите вопрос внизу — отвечу сразу 👇" } },
      {
        block_type: "buttons",
        content: {
          keyboard: "reply",
          text: "О чём спросить?",
          buttons: [
            { label: "❓ Как заказать", action_type: "text", action_value: "" },
            { label: "🚚 Сроки", action_type: "text", action_value: "" },
            { label: "↩️ Возврат", action_type: "text", action_value: "" },
            { label: "👤 Живой человек", action_type: "text", action_value: "" },
          ],
        },
      },
      { block_type: "description", content: { text: "[Как заказать: шаги в двух-трёх предложениях.]" } },
      { block_type: "description", content: { text: "[Сроки: сколько занимает выполнение и доставка.]" } },
      { block_type: "description", content: { text: "[Возврат: условия и как оформить.]" } },
      {
        block_type: "buttons",
        content: {
          text: "Напишите нам — ответим в рабочее время:",
          buttons: [{ label: "Написать в Telegram", action_type: "url", action_value: "" }],
        },
      },
    ],
    nexts: [[0, 1]],
    links: [
      { from: 1, button: 0, to: 2 },
      { from: 1, button: 1, to: 3 },
      { from: 1, button: 2, to: 4 },
      { from: 1, button: 3, to: 5 },
    ],
  },
  {
    id: "lead-magnet",
    accent: "delivery",
    icon: "🧲",
    label: "Бесплатный подарок и продажа",
    pitch: "Дай полезное бесплатно, потом предложи платный продукт",
    suggestedName: "Подарок и продукт",
    blocks: [
      { block_type: "welcome", content: { text: "Здравствуйте! Дарю [название подарка] — забирайте 🎁" } },
      { block_type: "delivery", content: { text: "Держите подарок! [пришли сюда ссылку или файл]" } },
      { block_type: "description", content: { text: "[Расскажи, что ещё есть в полной версии и чем она полезна.]" } },
      {
        block_type: "buttons",
        content: {
          text: "Хотите полную версию?",
          buttons: [{ label: "Да, хочу", action_type: "text", action_value: "" }],
        },
      },
      {
        block_type: "payment",
        content: {
          text: "Полная версия — [цена]. Придёт сюда сразу после оплаты.",
          title: "Полная версия",
          price: "990",
          currency: "RUB",
        },
      },
      { block_type: "delivery", content: { text: "Спасибо за покупку! [пришли сюда ссылку или файл]" } },
    ],
  },
  {
    id: "course-lessons",
    accent: "video",
    icon: "🎓",
    label: "Мини-курс по дням",
    pitch: "Купил — получает урок сразу, следующий через сутки",
    suggestedName: "Мини-курс",
    blocks: [
      { block_type: "welcome", content: { text: "Здравствуйте! Это мини-курс: один урок в день 🎓" } },
      { block_type: "description", content: { text: "[Программа курса: чему научится человек за эти дни.]" } },
      {
        block_type: "buttons",
        content: {
          text: "Готовы начать?",
          buttons: [{ label: "Записаться на курс", action_type: "text", action_value: "" }],
        },
      },
      {
        block_type: "payment",
        content: {
          text: "Курс стоит [цена]. Первый урок придёт сразу после оплаты.",
          title: "Мини-курс",
          price: "2900",
          currency: "RUB",
        },
      },
      { block_type: "delivery", content: { text: "Урок 1. [пришли сюда ссылку или файл]" } },
      { block_type: "delay", content: { seconds: 86400 } },
      { block_type: "delivery", content: { text: "Урок 2. [пришли сюда ссылку или файл]" } },
      { block_type: "delay", content: { seconds: 86400 } },
      { block_type: "delivery", content: { text: "Урок 3. [пришли сюда ссылку или файл]" } },
    ],
  },
  {
    id: "event-tickets",
    accent: "success",
    icon: "🎟",
    label: "Мероприятие: билеты",
    pitch: "Вебинар, мастер-класс, встреча: описание, билет, ссылка после оплаты",
    suggestedName: "Билеты на мероприятие",
    blocks: [
      { block_type: "welcome", content: { text: "Здравствуйте! Здесь можно купить билет на [название мероприятия] 🎟" } },
      { block_type: "description", content: { text: "[Когда, где и о чём мероприятие, кто ведущий.]" } },
      {
        block_type: "buttons",
        content: {
          text: "Забронировать место?",
          buttons: [{ label: "Купить билет", action_type: "text", action_value: "" }],
        },
      },
      {
        block_type: "payment",
        content: {
          text: "Билет — [цена]. После оплаты пришлю ссылку и напомню накануне.",
          title: "Билет на мероприятие",
          price: "1500",
          currency: "RUB",
          repeatable: true,
        },
      },
      { block_type: "delivery", content: { text: "Вы в списке! [пришли сюда ссылку на вход или адрес]" } },
    ],
  },
  {
    id: "donations",
    accent: "success",
    icon: "💛",
    label: "Поддержать автора",
    pitch: "Блогер, автор, проект: «спасибо» одним нажатием",
    suggestedName: "Поддержать автора",
    blocks: [
      { block_type: "welcome", content: { text: "Здравствуйте! Если мои материалы помогли — можно поддержать 💛" } },
      { block_type: "description", content: { text: "[На что пойдут деньги: расскажи честно и коротко.]" } },
      {
        block_type: "payment",
        content: {
          text: "Спасибо, что хотите поддержать!",
          title: "Поддержка автора",
          price: "300",
          currency: "RUB",
          repeatable: true,
        },
      },
      { block_type: "delivery", content: { text: "Спасибо огромное! Это очень важно 🙏" } },
    ],
  },
  {
    id: "feedback-quiz",
    accent: "poll",
    icon: "📊",
    label: "Опрос клиентов",
    pitch: "Узнай, что нравится и чего не хватает, — два вопроса и благодарность",
    suggestedName: "Опрос клиентов",
    blocks: [
      { block_type: "welcome", content: { text: "Здравствуйте! Два быстрых вопроса — это поможет сделать лучше 🙏" } },
      {
        block_type: "poll",
        content: { question: "Как вам наш сервис?", options: ["Отлично", "Нормально", "Можно лучше"], anonymous: false },
      },
      {
        block_type: "poll",
        content: { question: "Что улучшить в первую очередь?", options: ["Цены", "Скорость", "Ассортимент", "Другое"], anonymous: false },
      },
      { block_type: "description", content: { text: "Спасибо за ответы! Они уже учтены 💛" } },
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
