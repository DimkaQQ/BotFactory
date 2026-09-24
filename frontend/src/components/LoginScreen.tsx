import { useEffect, useRef, useState } from "react";

import {
  type BlockType,
  type PublicConfig,
  type TelegramLoginPayload,
  ApiError,
  builderApi,
  configureSessionAuth,
} from "../api/builderApi";
import { BLOCK_TYPES } from "../blockTypes";
import { BOT_TEMPLATES, blocksLabel } from "../templates";
import { HeroMockup } from "./HeroMockup";
import { LandingDemo } from "./LandingDemo";
import { ThemeToggle } from "./ThemeToggle";

interface Props {
  onLoggedIn: () => void;
}

declare global {
  interface Window {
    onTelegramAuth?: (user: TelegramLoginPayload) => void;
  }
}

// Marketing copy per block type — distinct from the short editor hint in
// blockTypes.ts (which is instructional, "what to type here"). This is the
// sell: why a client would want that block in their bot at all.
const FEATURE_SELL: Record<BlockType, string> = {
  welcome: "Гость пишет /start и сразу чувствует, что его здесь ждали — а не отвечает тишина.",
  description: "Расскажи о продукте своими словами — никаких полей формы и ограничений.",
  image: "Товар лицом: фото прямо в переписке. Вставил ссылку — готово, без загрузки файлов.",
  video: "Покажи, а не рассказывай — обзор или демо конвертирует лучше любого текста.",
  buttons: "«Купить» или «Записаться» в один тап — и стрелкой отправь клиента по нужной ветке сценария.",
  poll: "Узнай, чего хотят подписчики — нативный опрос Telegram, без сторонних форм.",
  delivery: "Обещал — доставь: файл, ссылка или доступ приходят мгновенно после оплаты.",
  payment: "Кнопка оплаты прямо в переписке — деньги идут тебе на счёт, а бот сам выдаёт товар после платежа.",
  delay: "Пауза между репликами — будто отвечает живой человек, а не скрипт.",
};

/** Who this is for, in their own words rather than in ours. Each one is a
 * job somebody is already doing by hand in their own Telegram. */
const AUDIENCES = [
  {
    icon: "📘",
    title: "Гайды, курсы, файлы",
    text: "Покупатель нажимает «Купить», платит — и файл приходит через секунду. В три часа ночи, в выходной, без тебя.",
  },
  {
    icon: "📅",
    title: "Услуги и запись",
    text: "Клиент выбирает услугу и время кнопками, бот записывает и подтверждает. Конец переписке «а когда вам удобно».",
  },
  {
    icon: "🔐",
    title: "Закрытый доступ",
    text: "Оплатил — бот сам пустил в канал или в группу. Не оплатил — не пустил. Никаких списков в блокноте.",
  },
];

/** The heart of the pitch: everything except going live costs nothing. Laid
 * out as four green tiles and one deliberately different fifth — hiding the
 * paid step here would just move the surprise to the publish button. */
const FREE_STEPS = [
  { icon: "🔑", title: "Регистрация", text: "Вход через Telegram. Без пароля, без карты, без формы на десять полей." },
  { icon: "🧩", title: "Сборка", text: "Сколько угодно ботов, сколько угодно правок. Ничего не блокируется на полпути." },
  { icon: "💾", title: "Хранение", text: "Собранный сценарий лежит в аккаунте и ждёт. Можно вернуться через месяц." },
  { icon: "▶", title: "Предпросмотр", text: "Пройди весь диалог сам — с кнопками и той же скоростью печати, что у живого бота." },
];

const STEPS = [
  {
    n: "1",
    title: "Выбери сценарий",
    text: "Готовые шаблоны под разные задачи — продажа файла, запись на услугу, рассылка — или начни с чистого листа.",
  },
  {
    n: "2",
    title: "Собери на холсте — блоки и стрелки",
    text: "Перетаскивай блоки, тяни стрелки от кнопок — сам решаешь, куда ведёт каждый выбор клиента. Как логическая схема, только работающая.",
  },
  {
    n: "3",
    title: "Проверь и запусти",
    text: "Пройди диалог в предпросмотре, вставь токен от @BotFather — и бот в эфире. Правки применяются сразу, без повторной публикации.",
  },
];

const FAQ = [
  {
    q: "Сколько это стоит?",
    a: "Собрать, сохранить, переделать и протестировать бота — бесплатно и без ограничений по времени. Платный только запуск в Telegram: разовая плата за старт, дальше — за каждый период работы бота. Обе цифры видно на кнопке публикации, до того как что-то спишется.",
  },
  {
    q: "Кому идут деньги моих покупателей?",
    a: "Тебе, напрямую на твой счёт в твоей кассе. Ключи от кассы твои, и мы их только шифруем и храним, чтобы бот мог выставить счёт. Через нас деньги покупателей не проходят вообще.",
  },
  {
    q: "Нужен ли свой бот в Telegram?",
    a: "Да, и он делается за минуту у @BotFather — это официальный бот Telegram, который выдаёт токен. Всё остальное берём на себя мы: вебхуки, сервер, доставка сообщений.",
  },
  {
    q: "Надо что-то устанавливать или где-то арендовать сервер?",
    a: "Нет. Бот живёт у нас и работает круглосуточно. Компьютер можно выключить — бот продолжит продавать.",
  },
  {
    q: "Можно менять сценарий после запуска?",
    a: "Да, и повторная публикация для этого не нужна: правки в тексте и в связях применяются сразу, на живом боте.",
  },
];

/** Standalone web entry point (outside the Telegram Mini App) — the full
 * marketing landing page, ending in a login via the Telegram Login Widget,
 * which hands us a signed payload we exchange for a session token (see
 * app/routers/auth.py). */
export function LoginScreen({ onLoggedIn }: Props) {
  const widgetRef = useRef<HTMLDivElement | null>(null);
  const heroRef = useRef<HTMLDivElement | null>(null);
  const [config, setConfig] = useState<PublicConfig | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [widgetFailed, setWidgetFailed] = useState(false);
  const [loading, setLoading] = useState(false);

  const botUsername = config?.meta_bot_username || null;

  useEffect(() => {
    builderApi
      .getPublicConfig()
      .then(setConfig)
      .catch(() => setError("Не удалось связаться с сервером"));
  }, []);

  useEffect(() => {
    if (!botUsername || !widgetRef.current) return;

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
    const timer = setTimeout(() => {
      if (!widgetRef.current?.querySelector("iframe")) setWidgetFailed(true);
    }, 4000);

    return () => {
      clearTimeout(timer);
      delete window.onTelegramAuth;
    };
  }, [botUsername, onLoggedIn]);

  function scrollToLogin() {
    heroRef.current?.scrollIntoView({ behavior: "smooth", block: "center" });
  }

  const loginWidget = (
    <div className="login-card">
      <p className="login-card__title">Войти через Telegram</p>
      {loading ? (
        <p className="app-hint">Входим…</p>
      ) : botUsername ? (
        <>
          <div ref={widgetRef} className="login-widget" hidden={widgetFailed} />
          {widgetFailed && (
            <div className="login-card__fallback">
              <p className="app-hint">
                Кнопка входа Telegram не загрузилась — её мог заблокировать браузер или расширение.
                Открой бота, он пришлёт ссылку для входа.
              </p>
              <a
                className="publish-button"
                href={`https://t.me/${botUsername}`}
                target="_blank"
                rel="noreferrer"
              >
                Открыть @{botUsername}
              </a>
            </div>
          )}
        </>
      ) : !error ? (
        <p className="app-hint">Загрузка…</p>
      ) : null}
      {error && <p className="publish-form__error">{error}</p>}
      <p className="login-card__trust">Регистрация и сборка — бесплатно · Платный только запуск</p>
    </div>
  );

  // Subscriptions are built but switched off, so the landing must not sell
  // one: a template promised here and missing in the picker is the worst
  // kind of broken promise — the one made before the person signs up.
  const templates = BOT_TEMPLATES.filter((t) => t.id !== "blank" && !t.needsSubscriptions);

  // Counted from the list that is actually rendered, falling back on the
  // server's own total — a headline that says "17 касс" above a list of
  // twelve is worse than no number.
  const gatewayCount =
    config?.payment_regions?.reduce((total, region) => total + region.gateways.length, 0) ||
    config?.gateway_count ||
    0;

  return (
    <div className="screen screen--login">
      {/* The landing has no header bar to hang it off, so the theme control
          floats in the corner — the one place it is reachable before login. */}
      <ThemeToggle className="theme-toggle--floating" />

      {/* ===== Hero ===== */}
      <section className="landing-hero" ref={heroRef}>
        <div className="login-hero">
          <div className="login-hero__pitch">
            <div className="landing-eyebrow">
              <span aria-hidden="true">🏭</span> Bot Factory
            </div>
            <h1 className="login-title">Бот, который сам продаёт и сам выдаёт</h1>
            <p className="login-hero__lead">
              Собери сценарий на холсте — блоки и стрелки, как схему. Клиент нажимает кнопку, платит, и бот тут
              же отдаёт файл, ссылку или доступ. Без кода, без разработчика, без ожидания.
            </p>
            <ul className="landing-promise" aria-label="Что бесплатно">
              <li>
                <span aria-hidden="true">✓</span> Собирать — бесплатно
              </li>
              <li>
                <span aria-hidden="true">✓</span> Хранить — бесплатно
              </li>
              <li>
                <span aria-hidden="true">✓</span> Тестировать — бесплатно
              </li>
            </ul>
          </div>

          {loginWidget}
        </div>

        <div className="landing-hero__visual">
          <HeroMockup />
        </div>
      </section>

      {/* ===== Who it's for ===== */}
      <section className="landing-section">
        <div className="landing-section__head">
          <p className="landing-section__eyebrow">Для кого</p>
          <h2 className="landing-section__title">Если ты уже продаёшь в личке — бот делает это за тебя</h2>
          <p className="landing-section__lead">
            Всё то же самое, что ты сейчас делаешь руками: ответить, выставить счёт, проверить оплату, прислать
            файл. Только круглосуточно и без «извини, не увидел сообщение».
          </p>
        </div>
        <div className="landing-audiences">
          {AUDIENCES.map((item) => (
            <div key={item.title} className="landing-audience">
              <span className="landing-audience__icon" aria-hidden="true">
                {item.icon}
              </span>
              <p className="landing-audience__title">{item.title}</p>
              <p className="landing-audience__text">{item.text}</p>
            </div>
          ))}
        </div>
      </section>

      {/* ===== The free promise — the centre of the pitch ===== */}
      <section className="landing-section landing-section--tint">
        <div className="landing-section__head">
          <p className="landing-section__eyebrow">Честно про деньги</p>
          <h2 className="landing-section__title">Платный только запуск. Всё до него — бесплатно</h2>
          <p className="landing-section__lead">
            Никакого пробного периода, который кончится, и никакой карты «просто для проверки». Собирай, ломай,
            переделывай и передумывай сколько хочешь — это ничего не стоит. Деньги начинаются там, где бот
            выходит в Telegram и начинает работать на тебя.
          </p>
        </div>
        <div className="landing-free">
          {FREE_STEPS.map((step) => (
            <div key={step.title} className="landing-free__tile">
              <span className="landing-free__icon" aria-hidden="true">
                {step.icon}
              </span>
              <p className="landing-free__title">
                {step.title} <span className="landing-free__tag">бесплатно</span>
              </p>
              <p className="landing-free__text">{step.text}</p>
            </div>
          ))}
          <div className="landing-free__tile landing-free__tile--paid">
            <span className="landing-free__icon" aria-hidden="true">
              🚀
            </span>
            <p className="landing-free__title">
              Запуск и работа в Telegram{" "}
              <span className="landing-free__tag landing-free__tag--paid">платно</span>
            </p>
            <p className="landing-free__text">
              Здесь начинаются деньги: разовая плата за старт и дальше за каждый период, пока бот работает.
              Обе цифры увидишь на кнопке публикации — когда бот уже собран и ты уже посмотрел, как он
              работает.
            </p>
          </div>
        </div>
      </section>

      {/* ===== How it works ===== */}
      <section className="landing-section">
        <div className="landing-section__head">
          <p className="landing-section__eyebrow">Как это работает</p>
          <h2 className="landing-section__title">От пустого экрана до работающего бота за один присест</h2>
        </div>
        <div className="landing-steps">
          {STEPS.map((step) => (
            <div key={step.n} className="landing-step">
              <span className="landing-step__n">{step.n}</span>
              <p className="landing-step__title">{step.title}</p>
              <p className="landing-step__text">{step.text}</p>
            </div>
          ))}
        </div>
      </section>

      {/* ===== Feature grid — sells every block type ===== */}
      <section className="landing-section landing-section--tint">
        <div className="landing-section__head">
          <p className="landing-section__eyebrow">Библиотека блоков</p>
          <h2 className="landing-section__title">Каждый блок — рабочий инструмент, а не украшение</h2>
          <p className="landing-section__lead">
            Девять типов блоков, из которых складывается любой сценарий — от простого приветствия до приёма
            оплаты и паузы для реалистичного темпа.
          </p>
        </div>
        <div className="landing-features">
          {BLOCK_TYPES.map((block) => (
            <div key={block.type} className="landing-feature-card">
              <span className={`landing-feature-card__icon block-card__icon--${block.accent}`} aria-hidden="true">
                {block.icon}
              </span>
              <p className="landing-feature-card__title">{block.label}</p>
              <p className="landing-feature-card__text">{FEATURE_SELL[block.type]}</p>
            </div>
          ))}
        </div>
      </section>

      {/* ===== Acquirers — the list is served, not written here ===== */}
      {/* Optional-chained rather than trusted: this page is the only door
          into the product, and an API that answers without these fields —
          an older deployment, a cached response — used to take the whole
          landing down with it, login widget included. */}
      {config?.payment_regions?.length ? (
        <section className="landing-section">
          <div className="landing-section__head">
            <p className="landing-section__eyebrow">Приём оплаты</p>
            <h2 className="landing-section__title">
              Деньги идут тебе напрямую — {gatewayCount} касс на выбор
            </h2>
            <p className="landing-section__lead">
              Ключи от кассы твои, счёт твой, деньги падают тебе. Мы не посредник и денег твоих покупателей не
              касаемся — бот только выставляет счёт и ждёт, когда касса подтвердит оплату.
            </p>
          </div>
          <div className="landing-gateways">
            {config.payment_regions.map((region) => (
              <div key={region.slug} className="landing-gateway-group">
                <p className="landing-gateway-group__title">{region.title}</p>
                <ul className="landing-gateway-group__list">
                  {region.gateways.map((name) => (
                    <li key={name}>{name}</li>
                  ))}
                </ul>
              </div>
            ))}
          </div>
          <p className="landing-gateways__note">
            Своей кассы и компании ещё нет? Telegram Stars и Crypto Bot работают без юрлица и без эквайринга —
            начать можно сегодня, а подключить банк потом.
          </p>
        </section>
      ) : null}

      {/* ===== Live preview callout ===== */}
      <section className="landing-callout">
        <div className="landing-callout__text">
          <p className="landing-section__eyebrow">▶ Смотреть, как в реальности</p>
          <h2 className="landing-section__title">Прежде чем показать клиенту — пройди сценарий сам</h2>
          <p className="landing-section__lead">
            Кнопка предпросмотра проигрывает весь диалог с той же скоростью печати, что и у настоящего бота — а
            на развилках можно реально нажимать кнопки и проверять, куда ведёт каждая ветка. Никаких сюрпризов
            после публикации.
          </p>
        </div>
        <div className="landing-callout__demo">
          <LandingDemo />
        </div>
      </section>

      {/* ===== Templates showcase ===== */}
      <section className="landing-section">
        <div className="landing-section__head">
          <p className="landing-section__eyebrow">Готовые сценарии</p>
          <h2 className="landing-section__title">Не с чистого листа — с рабочей заготовки</h2>
          <p className="landing-section__lead">
            Выбираешь шаблон — блоки уже расставлены и связаны стрелками. Остаётся вписать свой текст и
            опубликовать.
          </p>
        </div>
        <div className="landing-templates">
          {templates.map((template) => (
            <div key={template.id} className={`landing-template-card landing-template-card--${template.accent}`}>
              <span className="landing-template-card__icon" aria-hidden="true">
                {template.icon}
              </span>
              <p className="landing-template-card__title">{template.label}</p>
              <p className="landing-template-card__text">{template.pitch}</p>
              <span className="landing-template-card__meta">
                <span className="landing-template-card__count">{blocksLabel(template.blocks.length)}</span>
                готово к правкам
              </span>
            </div>
          ))}
        </div>
      </section>

      {/* ===== FAQ — the questions that otherwise become support tickets or
              silent closes of the tab. <details> so it works without JS and
              is keyboard-navigable for free. ===== */}
      <section className="landing-section landing-section--tint">
        <div className="landing-section__head">
          <p className="landing-section__eyebrow">Вопросы</p>
          <h2 className="landing-section__title">То, что спрашивают до регистрации</h2>
        </div>
        <div className="landing-faq">
          {FAQ.map((item) => (
            <details key={item.q} className="landing-faq__item">
              <summary className="landing-faq__q">{item.q}</summary>
              <p className="landing-faq__a">{item.a}</p>
            </details>
          ))}
        </div>
      </section>

      {/* ===== Final CTA ===== */}
      <section className="landing-cta">
        <h2 className="landing-cta__title">Собери первого бота прямо сейчас</h2>
        <p className="landing-cta__text">
          Вход через Telegram — без пароля и без карты. Платить — только если решишь запустить бота.
        </p>
        <button type="button" className="landing-cta__button" onClick={scrollToLogin}>
          Начать бесплатно ↑
        </button>
      </section>
    </div>
  );
}
