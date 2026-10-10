import { useEffect, useRef, useState } from "react";
import {
  ArrowRight,
  BookOpenText,
  CalendarCheck,
  Check,
  FloppyDisk,
  LockKey,
  Play,
  ShieldCheck,
  Lifebuoy,
  Wallet,
  PuzzlePiece,
  UserCirclePlus,
  Plus,
  Eye,
} from "@phosphor-icons/react";

import {
  type BlockType,
  type PublicConfig,
  type TelegramLoginPayload,
  ApiError,
  builderApi,
  configureSessionAuth,
} from "../api/builderApi";
import { BLOCK_TYPES } from "../blockTypes";
import { BlockIcon, BrandMark, TemplateIcon } from "../icons";
import { BOT_TEMPLATES, blocksLabel } from "../templates";
import { HeroMockup } from "./HeroMockup";
import { LandingDemo } from "./LandingDemo";
import { LaunchOffer } from "./LaunchOffer";
import { PaybackCalculator } from "./PaybackCalculator";
import { SiteFooter } from "./SiteFooter";
import { ThemeToggle } from "./ThemeToggle";
import { BranchMini, ContactsMini, PayMini, RemindMini, SlotsMini } from "./landing/Minis";
import { Reveal } from "./landing/Reveal";
import { plural } from "../plural";
import { scrollBehavior } from "../motion";
import "../landing.css";

interface Props {
  onLoggedIn: () => void;
}

declare global {
  interface Window {
    onTelegramAuth?: (user: TelegramLoginPayload) => void;
  }
}

/** Короткие продающие подписи к типам блоков (для строки «Все блоки»). */
const FEATURE_SELL: Record<BlockType, string> = {
  welcome: "Гость пишет /start и сразу чувствует, что его ждали.",
  description: "Расскажи о продукте своими словами, без полей формы.",
  image: "Фото товара прямо в переписке. Вставил ссылку, и готово.",
  video: "Покажи, а не рассказывай: демо конвертирует лучше текста.",
  buttons: "«Купить» или «Записаться» в один тап, с развилкой по сценарию.",
  poll: "Нативный опрос Telegram, без сторонних форм.",
  delivery: "Файл, ссылка или доступ приходят сразу после оплаты.",
  payment: "Кнопка оплаты в переписке, товар выдаётся после платежа.",
  booking: "Клиент сам выбирает свободный день и время.",
  contact: "Имя и телефон клиента остаются у тебя в списке.",
  delay: "Пауза между репликами, как у живого человека.",
};

const AUDIENCES = [
  {
    Icon: BookOpenText,
    title: "Гайды, курсы, файлы",
    text: "Покупатель нажимает «Купить», платит, и файл приходит через секунду. В три часа ночи, в выходной, без тебя.",
  },
  {
    Icon: CalendarCheck,
    title: "Платные консультации и записи",
    text: "Клиент выбирает услугу и время, платит, а ты сразу получаешь сообщение, кто записался. Договориться можно тут же в чате.",
  },
  {
    Icon: LockKey,
    title: "Закрытый доступ",
    text: "Оплатил: бот сам пустил в канал или группу. Не оплатил: не пустил. Никаких списков в блокноте.",
  },
];

const FREE_STEPS = [
  { Icon: UserCirclePlus, title: "Регистрация", text: "Вход через Telegram. Без пароля, без карты, без формы на десять полей." },
  { Icon: PuzzlePiece, title: "Сборка", text: "До 20 ботов и сколько угодно правок. Ничего не блокируется на полпути." },
  { Icon: FloppyDisk, title: "Хранение", text: "Собранный сценарий ждёт в аккаунте. Можно вернуться через месяц." },
  { Icon: Eye, title: "Предпросмотр", text: "Пройди весь диалог сам: с кнопками и той же скоростью печати, что у живого бота." },
];

/** Только то, что действительно так устроено в коде. У каждого пункта есть проверяемая механика. */
const TRUST = [
  {
    Icon: Wallet,
    title: "Деньги идут не через нас",
    text: "Покупатель платит в твою кассу, на твой счёт. Мы выставляем ссылку на оплату и ждём подтверждения от кассы.",
  },
  {
    Icon: ShieldCheck,
    title: "Товар только после оплаты",
    text: "Файл или доступ уходят, когда оплату подтвердила касса или ты сам. Кнопки «я оплатил» недостаточно.",
  },
  {
    Icon: LockKey,
    title: "Ключи хранятся зашифрованными",
    text: "Токен бота и ключи кассы шифруются до записи в базу и нигде не показываются: ни в интерфейсе, ни в логах.",
  },
  {
    Icon: Lifebuoy,
    title: "Не продлил, и ничего не пропало",
    text: "Если период закончился, бот сначала предупредит, потом уйдёт с эфира. Сценарий, касса и заказы остаются, а после оплаты бот возвращается в эфир сам.",
  },
];

const STEPS = [
  {
    title: "Выбери сценарий",
    text: "Готовые шаблоны под разные задачи: продажа файла, запись на услугу, рассылка. Или начни с чистого листа.",
  },
  {
    title: "Собери на холсте",
    text: "Перетаскивай блоки и тяни стрелки от кнопок. Ты сам решаешь, куда ведёт каждый выбор клиента.",
  },
  {
    title: "Проверь и запусти",
    text: "Пройди диалог в предпросмотре, вставь токен от @BotFather и оплати запуск: бот в эфире. Правки применяются сразу, без повторной публикации.",
  },
];

const FAQ = [
  {
    q: "Нужно ли уметь программировать?",
    a: "Нет. Бот собирается из блоков, как схема: приветствие, текст, картинка, кнопки, оплата, выдача. Блоки соединяются стрелками, и это весь «код».",
  },
  {
    q: "Что увидит мой покупатель?",
    a: "Обычный чат в Telegram. Он пишет /start, получает сообщения с кнопками, нажимает «Купить», платит на странице твоей кассы, и бот присылает покупку. Никаких приложений и регистраций.",
  },
  {
    q: "Сколько это стоит?",
    a: "Собрать, сохранить, переделать и протестировать бота бесплатно и без ограничений по времени. Платный только запуск в Telegram: разовая плата за старт, дальше плата за каждый период работы бота. Обе цифры видно на кнопке публикации, до того как что-то спишется.",
  },
  {
    q: "Кому идут деньги моих покупателей?",
    a: "Тебе, напрямую на твой счёт в твоей кассе. Ключи от кассы твои, мы их только шифруем и храним, чтобы бот мог выставить счёт. Через нас деньги покупателей не проходят вообще.",
  },
  {
    q: "Нужен ли свой бот в Telegram?",
    a: "Да, и он делается за минуту у @BotFather, это официальный бот Telegram, который выдаёт токен. Всё остальное берём на себя мы: вебхуки, сервер, доставка сообщений.",
  },
  {
    q: "Надо что-то устанавливать или арендовать сервер?",
    a: "Нет. Бот живёт у нас и работает круглосуточно. Компьютер можно выключить, бот продолжит продавать.",
  },
  {
    q: "Что будет, если я перестану платить за подписку?",
    a: "Боты работают ещё несколько дней после конца оплаченного периода, пока тебе напоминают. Потом они уходят с эфира, но ничего не удаляется: сценарии, касса и история заказов остаются. Оплатил подписку, и все боты возвращаются сами.",
  },
  {
    q: "Спишут ли деньги сами, без моего ведома?",
    a: "Нет. Карту мы не сохраняем и автоматически ничего не списываем. Перед концом периода пришлём напоминание с кнопкой «Продлить»: захочешь, продлишь. Не захочешь, просто не плати, бот уйдёт с эфира, ничего не удалится.",
  },
  {
    q: "Можно ли вернуть деньги, если не получилось?",
    a: "Если бот не запустился по нашей вине или платёж прошёл дважды, вернём. Условия возврата в документе «Условия возврата» внизу страницы. Деньги твоих покупателей идут на твою кассу, их ты возвращаешь сам.",
  },
  {
    q: "Нужен ли мне ИП или компания, чтобы принимать оплату?",
    a: "Не всегда. Без юрлица можно принимать Telegram Stars и криптовалюту через Crypto Bot, а для кассы вроде ЮKassa или Stripe нужен статус, который требует сама касса. Какие кассы доступны в твоей стране, видно в конструкторе.",
  },
  {
    q: "Могу ли я получить чек или акт для бухгалтерии?",
    a: "Напиши в поддержку (кнопка внизу страницы): подтвердим оплату и подскажем, как получить документы для бухгалтерии.",
  },
  {
    q: "Можно менять сценарий после запуска?",
    a: "Да, и повторная публикация для этого не нужна: правки в тексте и в связях применяются сразу, на живом боте.",
  },
];

/** Standalone web entry point (outside the Telegram Mini App): the marketing landing page,
 * ending in a login via the Telegram Login Widget, which hands us a signed payload we exchange
 * for a session token (see app/routers/auth.py). */
export function LoginScreen({ onLoggedIn }: Props) {
  const widgetRef = useRef<HTMLDivElement | null>(null);
  const heroRef = useRef<HTMLDivElement | null>(null);
  const finalRef = useRef<HTMLElement | null>(null);
  const [config, setConfig] = useState<PublicConfig | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [widgetFailed, setWidgetFailed] = useState(false);
  const [loading, setLoading] = useState(false);
  // Виджет Telegram: пока он не нарисовался, вместо пустоты показываем кнопку-заглушку.
  const [widgetReady, setWidgetReady] = useState(false);
  // Дошли до финального блока: липкая кнопка внизу экрана больше не нужна.
  const [nearEnd, setNearEnd] = useState(false);
  // Липкая кнопка внизу экрана на телефоне: появляется, когда форма входа из
  // героя уже уехала вверх,, чтобы на длинной странице путь к входу всегда
  // был под большим пальцем.
  const [stickyCta, setStickyCta] = useState(false);

  const botUsername = config?.meta_bot_username || null;

  useEffect(() => {
    builderApi
      .getPublicConfig()
      .then(setConfig)
      .catch(() => setError("Не удалось связаться с сервером"));
  }, []);

  useEffect(() => {
    // После ошибки входа контейнер виджета создаётся заново, нужно собрать его снова.
    if (loading || !botUsername || !widgetRef.current) return;

    window.onTelegramAuth = async (user) => {
      setLoading(true);
      setError(null);
      try {
        const { token } = await builderApi.loginWithTelegram(user);
        configureSessionAuth(token);
        onLoggedIn();
      } catch (err) {
        setError(err instanceof ApiError ? err.message : "Не удалось войти");
        setLoading(false);
      }
    };

    const script = document.createElement("script");
    script.src = "https://telegram.org/js/telegram-widget.js?22";
    script.async = true;
    script.setAttribute("data-telegram-login", botUsername);
    script.setAttribute("data-size", "large");
    script.setAttribute("data-radius", "12");
    script.setAttribute("data-onauth", "onTelegramAuth(user)");
    script.setAttribute("data-request-access", "write");
    script.onerror = () => setWidgetFailed(true);
    widgetRef.current.innerHTML = "";
    widgetRef.current.appendChild(script);

    // The widget is the only way into the product, and it is a third-party
    // script: an ad blocker, a corporate proxy or a bad day at telegram.org
    // left the card showing a heading and nothing else, with no error and no
    // way forward. If nothing has rendered by now, offer the bot directly.
    const poll = setInterval(() => {
      if (widgetRef.current?.querySelector("iframe")) {
        setWidgetReady(true);
        clearInterval(poll);
      }
    }, 250);
    const timer = setTimeout(() => {
      if (!widgetRef.current?.querySelector("iframe")) setWidgetFailed(true);
    }, 4000);

    return () => {
      clearTimeout(timer);
      clearInterval(poll);
      delete window.onTelegramAuth;
    };
  }, [botUsername, onLoggedIn, loading]);

  useEffect(() => {
    const hero = heroRef.current;
    if (!hero || typeof IntersectionObserver === "undefined") return;
    const observer = new IntersectionObserver(([entry]) => setStickyCta(!entry.isIntersecting), { threshold: 0 });
    observer.observe(hero);
    return () => observer.disconnect();
  }, []);

  useEffect(() => {
    const node = finalRef.current;
    if (!node || typeof IntersectionObserver === "undefined") return;
    const observer = new IntersectionObserver(([entry]) => setNearEnd(entry.isIntersecting), { threshold: 0 });
    observer.observe(node);
    return () => observer.disconnect();
  }, []);

  function scrollToLogin() {
    const hero = heroRef.current;
    hero?.scrollIntoView({ behavior: scrollBehavior(), block: "center" });
    // Фокус на блок входа, чтобы клавиатура и скринридер оказались там же, куда прокрутили.
    hero?.querySelector<HTMLElement>(".lp-login")?.focus({ preventScroll: true });
  }

  const legalLinks = {
    offer: config?.legal_docs?.find((d) => d.path === "/legal/offer")?.path,
    privacy: config?.legal_docs?.find((d) => d.path === "/legal/privacy")?.path,
  };

  const loginWidget = (
    <div className="lp-login" tabIndex={-1}>
      <p className="lp-login__title">Войти через Telegram</p>
      {loading ? (
        <p className="lp-login__hint">Входим…</p>
      ) : botUsername ? (
        <>
          {!widgetReady && !widgetFailed && (
            <a className="lp-btn lp-btn--primary lp-login__skeleton" href={`https://t.me/${botUsername}`} target="_blank" rel="noreferrer">
              Войти через Telegram
            </a>
          )}
          <div ref={widgetRef} className="login-widget" hidden={widgetFailed || !widgetReady} />
          {widgetFailed && (
            <div className="lp-login__fallback">
              <p className="lp-login__hint">
                Кнопка входа Telegram не загрузилась, её мог заблокировать браузер или расширение. Открой бота и
                нажми «Открыть конструктор»: он работает прямо внутри Telegram.
              </p>
              <a className="lp-btn lp-btn--primary" href={`https://t.me/${botUsername}`} target="_blank" rel="noreferrer">
                Открыть @{botUsername}
              </a>
            </div>
          )}
        </>
      ) : config ? (
        <p className="lp-login__hint">
          Вход через Telegram временно недоступен. Попробуйте позже
          {config.support_telegram ? (
            <>
              {" "}
              или напишите в{" "}
              <a href={`https://t.me/${config.support_telegram}`} target="_blank" rel="noreferrer">
                поддержку
              </a>
            </>
          ) : null}
          .
        </p>
      ) : !error ? (
        <p className="lp-login__hint">Загрузка…</p>
      ) : null}
      {error && <p className="lp-login__error">{error}</p>}
      {/* Согласие стоит у кнопки, а не в подвале: виджет Telegram единственный способ войти,
          и «вход = принятие условий» должно быть написано там, где человек его нажимает.
          Пока документов нет, строки нет тоже. */}
      {legalLinks.offer && legalLinks.privacy && (
        <p className="lp-login__consent">
          Входя, вы принимаете{" "}
          <a href={legalLinks.offer} target="_blank" rel="noreferrer">
            оферту
          </a>{" "}
          и{" "}
          <a href={legalLinks.privacy} target="_blank" rel="noreferrer">
            политику конфиденциальности
          </a>
          .
        </p>
      )}
    </div>
  );

  // Subscriptions are built but switched off, so the landing must not sell
  // one: a template promised here and missing in the picker is the worst
  // kind of broken promise, the one made before the person signs up.
  const templates = BOT_TEMPLATES.filter((t) => t.id !== "blank" && !t.needsSubscriptions);

  // Counted from the list that is actually rendered, falling back on the
  // server's own total: a headline that says "17 касс" above a list of
  // twelve is worse than no number.
  const pricing = config?.pricing ?? [];

  // Плоский список без деления по странам: просто какие кассы есть.
  const gatewayNames = Array.from(new Set(config?.payment_regions?.flatMap((region) => region.gateways) ?? []));
  const gatewayCount = gatewayNames.length || config?.gateway_count || 0;

  return (
    <div className="screen screen--login lp">
      <a className="lp-skip" href="#main">К содержанию</a>
      {/* Шапка одной строкой и не выше 72px: «Войти» и цена всегда под рукой. Тема здесь же:
          это единственное место, где её можно сменить до входа. */}
      <header className="lp-nav">
        <a className="lp-nav__brand" href="#top" aria-label="Bot Factory, наверх">
          <BrandMark size={30} /> <span>Bot Factory</span>
        </a>
        <nav className="lp-nav__links" aria-label="Разделы страницы">
          <a href="#how">Как работает</a>
          <a href="#features">Возможности</a>
          <a href="#pay">Оплата</a>
          <a href="#price">Цена</a>
          <a href="#faq">Вопросы</a>
        </nav>
        <ThemeToggle />
        <button type="button" className="lp-btn lp-btn--primary lp-nav__cta" onClick={scrollToLogin}>
          Начать бесплатно
        </button>
      </header>

      <main id="main">
      {/* ===== Hero ===== */}
      <section className="lp-hero" id="top" ref={heroRef}>
        <div className="lp-hero__copy">
          <h1 className="lp-hero__title">Бот, который сам продаёт и сам выдаёт</h1>
          <p className="lp-hero__lead">
            Собери диалог из блоков и стрелок. Покупатель платит в твою кассу, бот выдаёт товар.
          </p>
          {loginWidget}
          <a className="lp-hero__more" href="#how">
            Как это работает <ArrowRight size={16} aria-hidden="true" />
          </a>
        </div>
        <div className="lp-hero__visual">
          <HeroMockup />
        </div>
      </section>

      {/* ===== Три факта сразу под героем ===== */}
      <ul className="lp-facts" aria-label="Коротко">
        <li>
          <Check size={18} weight="bold" aria-hidden="true" />
          Собирать, хранить и тестировать бесплатно, без срока
        </li>
        <li>
          <Check size={18} weight="bold" aria-hidden="true" />
          Деньги покупателей идут сразу в твою кассу
        </li>
        <li>
          <Check size={18} weight="bold" aria-hidden="true" />
          Платишь только за бота в эфире
        </li>
      </ul>

      {/* ===== Для кого ===== */}
      <section className="lp-section lp-who">
        <Reveal className="lp-who__head">
          <h2 className="lp-h2">Если ты уже продаёшь в личке, бот делает это за тебя</h2>
          <p className="lp-lead">
            Всё то же, что ты делаешь руками: ответить, выставить счёт, проверить оплату, прислать файл. Только
            круглосуточно.
          </p>
        </Reveal>
        <ul className="lp-who__list">
          {AUDIENCES.map(({ Icon, title, text }, i) => (
            <Reveal as="li" key={title} delay={i * 0.08} className="lp-who__row">
              <span className="lp-who__icon" aria-hidden="true">
                <Icon size={26} />
              </span>
              <div>
                <h3 className="lp-h3">{title}</h3>
                <p>{text}</p>
              </div>
            </Reveal>
          ))}
        </ul>
      </section>

      {/* ===== Как работает + живое демо ===== */}
      <section className="lp-section lp-how" id="how">
        <div className="lp-how__steps">
          <Reveal>
            <h2 className="lp-h2">От пустого экрана до работающего бота за один присест</h2>
          </Reveal>
          <ol className="lp-timeline">
            {STEPS.map((step, i) => (
              <Reveal as="li" key={step.title} delay={i * 0.08} className="lp-timeline__item">
                <span className="lp-timeline__n" aria-hidden="true">
                  {i + 1}
                </span>
                <div>
                  <h3 className="lp-h3">{step.title}</h3>
                  <p>{step.text}</p>
                </div>
              </Reveal>
            ))}
          </ol>
          <p className="lp-how__note">
            <Play size={16} weight="fill" aria-hidden="true" /> Справа настоящее демо. Кнопки живые: нажми, и диалог
            пойдёт по твоей ветке.
          </p>
        </div>
        <Reveal className="lp-how__demo" delay={0.1}>
          <LandingDemo />
        </Reveal>
      </section>

      {/* ===== Возможности: витрина разной формы ===== */}
      <section className="lp-section" id="features">
        <Reveal>
          <h2 className="lp-h2 lp-h2--wide">Каждый блок рабочий инструмент, а не украшение</h2>
        </Reveal>
        <div className="lp-bento">
          <Reveal className="lp-cell lp-cell--pay">
            <div className="lp-cell__text">
              <h3 className="lp-h3">Оплата в чате, выдача после платежа</h3>
              <p>
                Кнопка оплаты прямо в переписке. Деньги идут на твой счёт, а файл, ссылка или доступ приходят сразу
                после подтверждения кассы.
              </p>
            </div>
            <PayMini />
          </Reveal>
          <Reveal className="lp-cell lp-cell--slots" delay={0.06}>
            <div className="lp-cell__text">
              <h3 className="lp-h3">Запись по календарю</h3>
              <p>Клиент сам выбирает свободное время. Бот не запишет двоих на одно и напомнит клиенту заранее.</p>
            </div>
            <SlotsMini />
          </Reveal>
          <Reveal className="lp-cell lp-cell--contacts" delay={0.04}>
            <div className="lp-cell__text">
              <h3 className="lp-h3">Клиенты и контакты</h3>
              <p>Имя, Telegram и телефон остаются у тебя в списке. Если хватает Telegram, ничего вводить не нужно.</p>
            </div>
            <ContactsMini />
          </Reveal>
          <Reveal className="lp-cell lp-cell--branch" delay={0.08}>
            <div className="lp-cell__text">
              <h3 className="lp-h3">Кнопки и ветки</h3>
              <p>Стрелкой от каждой кнопки выбираешь, куда пойдёт клиент дальше.</p>
            </div>
            <BranchMini />
          </Reveal>
          <Reveal className="lp-cell lp-cell--remind" delay={0.12}>
            <div className="lp-cell__text">
              <h3 className="lp-h3">Напоминания, паузы и рассылка</h3>
              <p>Бот отвечает с паузами, как живой человек, напоминает о записи и пишет подписчикам по твоей команде.</p>
            </div>
            <RemindMini />
          </Reveal>
        </div>
        <ul className="lp-blocks" aria-label="Все типы блоков">
          {BLOCK_TYPES.map((block) => (
            <li key={block.type} title={FEATURE_SELL[block.type]}>
              <BlockIcon type={block.type} size={16} /> {block.label}
            </li>
          ))}
        </ul>
      </section>

      {/* ===== Кассы: список приходит с сервера ===== */}
      {/* Optional-chained, а не «доверено»: эта страница единственная дверь в продукт, и ответ API
          без этих полей (старая выкладка, кэш) не должен ронять весь лендинг вместе с входом. */}
      {gatewayNames.length ? (
        <section className="lp-section lp-pay" id="pay">
          <Reveal className="lp-pay__head">
            <h2 className="lp-h2">
              Деньги идут напрямую тебе. Касс на выбор: {gatewayCount}
              <span className="lp-sr"> {plural(gatewayCount, ["касса", "кассы", "касс"])}</span>
            </h2>
            <p className="lp-lead">
              Ключи от кассы твои, счёт твой. Мы не посредник: бот выставляет счёт и ждёт, когда касса подтвердит оплату.
            </p>
          </Reveal>
          <div className="lp-pay__gateways">
            <ul className="lp-gateways">
              {gatewayNames.map((name) => (
                <li key={name}>{name.replace(/\s*⭐️?/u, "")}</li>
              ))}
            </ul>
            <p className="lp-note">
              Своей кассы и компании ещё нет? Telegram Stars и Crypto Bot работают без юрлица и без эквайринга. Начать
              можно сегодня, а подключить банк потом.
            </p>
          </div>
        </section>
      ) : null}

      {/* ===== Шаблоны: лента с прокруткой ===== */}
      <section className="lp-section lp-templates">
        <Reveal>
          <h2 className="lp-h2 lp-h2--wide">Не с чистого листа, а с рабочей заготовки</h2>
          <p className="lp-lead">Блоки уже расставлены и связаны. Остаётся вписать свой текст и опубликовать.</p>
        </Reveal>
        <ul className="lp-tpl-strip" aria-label="Готовые сценарии">
          {templates.map((template) => (
            <li
              key={template.id}
              className="lp-tpl"
              style={{ "--tpl": `var(--accent-${template.accent})` } as React.CSSProperties}
            >
              <span className="lp-tpl__icon" aria-hidden="true">
                <TemplateIcon id={template.id} size={22} />
              </span>
              <h3 className="lp-tpl__title">{template.label}</h3>
              <p className="lp-tpl__text">{template.pitch}</p>
              <span className="lp-tpl__meta">{blocksLabel(template.blocks.length)}, готово к правкам</span>
            </li>
          ))}
        </ul>
      </section>

      {/* ===== Цена: цифры приходят с сервера ===== */}
      <section className="lp-section lp-price" id="price">
        <Reveal>
          <h2 className="lp-h2 lp-h2--wide">
            {pricing.length ? "Собирать бесплатно, платишь за запуск и работу бота" : "Сейчас запуск бота бесплатный"}
          </h2>
          <p className="lp-lead">
            {pricing.length
              ? "Заказывать бота у разработчика долго и дорого. Здесь ты собираешь сам за вечер. Платишь один раз за запуск каждого бота и одну общую подписку за все боты. Собирать и проверять можно бесплатно и без срока."
              : "Собирать, сохранять, проверять и запускать бота можно без оплаты. Если условия изменятся, цена будет видна на кнопке публикации до того, как что-то спишется."}
          </p>
        </Reveal>

        <div className="lp-price__grid">
          <Reveal className="lp-price__free">
            <h3 className="lp-h3">Бесплатно и без срока</h3>
            <ul>
              {FREE_STEPS.map(({ Icon, title, text }) => (
                <li key={title}>
                  <span className="lp-price__icon" aria-hidden="true">
                    <Icon size={20} />
                  </span>
                  <div>
                    <strong>{title}</strong>
                    <p>{text}</p>
                  </div>
                </li>
              ))}
            </ul>
          </Reveal>

          <Reveal className="lp-price__paid" delay={0.08}>
            <h3 className="lp-h3">Запуск в Telegram</h3>
            {pricing.length > 0 && config?.launch_offer_ends_at && config.launch_offer_regular_price ? (
              <LaunchOffer endsAt={config.launch_offer_ends_at} regularPrice={config.launch_offer_regular_price} />
            ) : null}
            {pricing.length > 0 ? (
              <div className="lp-prices">
                {pricing.map((price) => (
                  <div key={price.method} className="lp-prices__item">
                    <p className="lp-prices__method">{price.method}</p>
                    <p className="lp-prices__amount">{price.launch}</p>
                    <p className="lp-prices__label">один раз, за запуск каждого бота</p>
                    {price.who && <p className="lp-prices__who">{price.who}</p>}
                    <p className="lp-prices__renewal">
                      {price.renewal
                        ? `Плюс одна подписка ${price.renewal} за каждые ${config?.renewal_period_days ?? 30} дн. на все ваши боты сразу`
                        : "Дальше без доплат, бот работает без продлений"}
                    </p>
                  </div>
                ))}
              </div>
            ) : (
              <div className="lp-prices"><div className="lp-prices__item"><p className="lp-prices__amount">Запуск бесплатно</p><p className="lp-prices__label">Если условия изменятся, цена появится здесь и на кнопке публикации до того, как что-то спишется.</p></div></div>
            )}
            <p className="lp-note">
              Деньги твоих покупателей сюда не входят: они идут напрямую в твою кассу, без нашей комиссии.
              {pricing.some((p) => p.renewal) && config?.renewal_grace_days
                ? ` Не продлили вовремя: бот ещё ${config.renewal_grace_days} дн. работает, пока тебе напоминают. Ничего не удаляется.`
                : ""}
            </p>
          </Reveal>
        </div>

        {config?.launch_usd ? (
          <Reveal>
            <PaybackCalculator
              launchUsd={config.launch_usd}
              renewalUsd={config.renewal_usd ?? null}
              onStart={scrollToLogin}
            />
          </Reveal>
        ) : null}
      </section>

      {/* ===== Доверие: без карточек, строки с линиями ===== */}
      <section className="lp-section lp-trust">
        <Reveal>
          <h2 className="lp-h2 lp-h2--wide">Что именно мы делаем, чтобы тебе можно было доверять</h2>
        </Reveal>
        <ul className="lp-trust__grid">
          {TRUST.map(({ Icon, title, text }, i) => (
            <Reveal as="li" key={title} delay={i * 0.06} className="lp-trust__item">
              <span className="lp-trust__icon" aria-hidden="true">
                <Icon size={24} />
              </span>
              <h3 className="lp-h3">{title}</h3>
              <p>{text}</p>
            </Reveal>
          ))}
        </ul>
      </section>

      {/* ===== FAQ: <details> работает без JS и с клавиатуры ===== */}
      <section className="lp-section lp-faq" id="faq">
        <Reveal className="lp-faq__head">
          <h2 className="lp-h2">То, что спрашивают до регистрации</h2>
          <p className="lp-lead">Не нашли ответ? Поддержка в Telegram есть в самом низу страницы.</p>
        </Reveal>
        <div className="lp-faq__list">
          {FAQ.map((item) => (
            <details key={item.q} className="lp-faq__item">
              <summary className="lp-faq__q">
                <span>{item.q}</span>
                <Plus size={18} aria-hidden="true" className="lp-faq__plus" />
              </summary>
              <p className="lp-faq__a">{item.a}</p>
            </details>
          ))}
        </div>
      </section>

      {/* ===== Финальный призыв ===== */}
      <section className="lp-final" ref={finalRef}>
        <h2 className="lp-final__title">Собери первого бота сегодня</h2>
        <p className="lp-final__text">
          Вход через Telegram, без пароля и без карты. Платить нужно, только если решишь запустить бота.
        </p>
        <button type="button" className="lp-btn lp-btn--light" onClick={scrollToLogin}>
          Начать бесплатно <ArrowRight size={18} aria-hidden="true" />
        </button>
      </section>
      </main>

      {/* ===== Подвал ===== */}
      <SiteFooter config={config} />

      {stickyCta && !nearEnd && (
        <div className="lp-sticky">
          <button type="button" className="lp-btn lp-btn--primary" onClick={scrollToLogin}>
            Начать бесплатно
          </button>
        </div>
      )}
    </div>
  );
}
