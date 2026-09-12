import { useEffect, useRef, useState } from "react";

import { type BlockType, type TelegramLoginPayload, ApiError, builderApi, configureSessionAuth } from "../api/builderApi";
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

const STEPS = [
  {
    n: "1",
    title: "Выбери сценарий",
    text: "Четыре готовых шаблона под разные модели — разовая продажа, подписка, запись на сессию, рассылка — или начни с чистого листа.",
  },
  {
    n: "2",
    title: "Собери на холсте — блоки и стрелки",
    text: "Как в Human Resource Machine: перетаскивай блоки, тяни стрелки от кнопок — сам решаешь, куда ведёт каждый выбор клиента.",
  },
  {
    n: "3",
    title: "Опубликуй за 2 минуты",
    text: "Вставь токен от @BotFather — бот заработает мгновенно. Правки в сценарии применяются сразу, без повторной публикации.",
  },
];

/** Standalone web entry point (outside the Telegram Mini App) — the full
 * marketing landing page, ending in a login via the Telegram Login Widget,
 * which hands us a signed payload we exchange for a session token (see
 * app/routers/auth.py). */
export function LoginScreen({ onLoggedIn }: Props) {
  const widgetRef = useRef<HTMLDivElement | null>(null);
  const heroRef = useRef<HTMLDivElement | null>(null);
  const [botUsername, setBotUsername] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [widgetFailed, setWidgetFailed] = useState(false);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    builderApi
      .getPublicConfig()
      .then((cfg) => setBotUsername(cfg.meta_bot_username || null))
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
      <p className="login-card__trust">Бесплатно · Без кода · Публикация за 2 минуты</p>
    </div>
  );

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
            <h1 className="login-title">Telegram-бот, который продаёт, пока ты спишь</h1>
            <p className="login-hero__lead">
              Собирай сценарий на визуальном холсте — блоки и стрелки, ветвления по нажатой кнопке, как в
              настоящей логической схеме. Без кода, без разработчиков, без ожидания.
            </p>
            <ul className="login-hero__features">
              <li>👋 Готовые шаблоны — товар, подписка, запись, рассылка</li>
              <li>🧩 Визуальный конструктор — тяни стрелки от кнопок, задавай ветвления</li>
              <li>🤖 Управляй несколькими ботами из одного аккаунта</li>
            </ul>
          </div>

          {loginWidget}
        </div>

        <div className="landing-hero__visual">
          <HeroMockup />
        </div>
      </section>

      {/* ===== Feature grid — sells every block type ===== */}
      <section className="landing-section">
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

      {/* ===== How it works ===== */}
      <section className="landing-section landing-section--tint">
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
          {BOT_TEMPLATES.filter((t) => t.id !== "blank").map((template) => (
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

      {/* ===== Final CTA ===== */}
      <section className="landing-cta">
        <h2 className="landing-cta__title">Собери первого бота прямо сейчас</h2>
        <p className="landing-cta__text">Вход через Telegram — без пароля, без формы регистрации.</p>
        <button type="button" className="landing-cta__button" onClick={scrollToLogin}>
          Начать бесплатно ↑
        </button>
      </section>
    </div>
  );
}
