import { useEffect, useRef, useState } from "react";

import { type PublicationInfo, ApiError, builderApi, formatAmount } from "../api/builderApi";
import { openExternal } from "../hooks/useTelegramWebApp";
import { BotFatherSteps } from "./BotFatherSteps";
import { plural } from "../plural";

interface Props {
  botId: string;
  /** Что не так со сценарием прямо сейчас. Показывается ДО оплаты: человек
   * платил 99 $, и только потом узнавал, что касса без ключей, а кнопка
   * никуда не ведёт. */
  problems: string[];
  info: PublicationInfo;
  onPaid: () => void;
}

const POLL_MS = 3000;

/** Symbols where they read better than the code, plain code otherwise. */
const SYMBOLS: Record<string, string> = { USD: "$", EUR: "€", RUB: "₽", KZT: "₸", XTR: "⭐" };

/** Which method is yours — the same guidance the settings panel gives. */
const METHOD_NOTE: Record<string, string> = {
  stripe: "карта (кроме РФ и Беларуси)",
  cryptobot: "USDT или TON из Telegram",
  robokassa: "карта РФ или KZT",
  yookassa: "карта РФ",
  lavatop: "карта РФ",
  stars: "звёзды Telegram",
};

/** Какой способ предложить первым. По языку и часовому поясу угадываем страну:
 * из РФ карта Stripe не пройдёт (звёзды или крипта), из Казахстана и
 * Узбекистана удобнее всего карта. Это подсказка, а не ограничение: выбрать
 * можно любой. */
function recommendedProvider(providers: string[]): string | null {
  let zone = "";
  try {
    zone = Intl.DateTimeFormat().resolvedOptions().timeZone || "";
  } catch {
    /* окружение без Intl — просто не угадываем */
  }
  const lang = (typeof navigator !== "undefined" ? navigator.language : "").toLowerCase();
  const centralAsia = /^(Asia\/(Almaty|Aqtau|Aqtobe|Atyrau|Oral|Qostanay|Qyzylorda|Tashkent|Samarkand|Bishkek))$/.test(zone) ||
    lang.startsWith("kk") || lang.startsWith("uz");
  const order = centralAsia ? ["stripe", "stars", "cryptobot"] : ["stars", "cryptobot", "stripe"];
  const isRussia = /^Europe\/(Moscow|Kaliningrad|Samara|Volgograd|Kirov|Saratov|Astrakhan|Ulyanovsk)$/.test(zone) ||
    /^Asia\/(Yekaterinburg|Omsk|Novosibirsk|Krasnoyarsk|Irkutsk|Yakutsk|Vladivostok|Magadan|Kamchatka)$/.test(zone);
  if (!centralAsia && !isRussia && !lang.startsWith("ru")) return null;
  return order.find((slug) => providers.includes(slug)) ?? null;
}

function money(currency: string): string {
  return SYMBOLS[currency] ?? currency;
}

/** «$19», «€9» — знак впереди и без пробела; «990 ₽», «5 ⭐» — после. */
function price(minor: number, currency: string): string {
  const amount = formatAmount(minor);
  return currency === "USD" || currency === "EUR" ? `${money(currency)}${amount}` : `${amount}\u00a0${money(currency)}`;
}

/** Building is free; putting the bot on the air is what's paid for. Opens
 * the provider's page in a new tab and polls the payment until the callback
 * settles it — the redirect back is never what we trust. */
export function PublishPaywall({ botId, problems, info, onPaid }: Props) {
  // На телефоне панель занимала три четверти экрана и закрывала холст, поэтому
  // она свёрнута в одну строку и раскрывается по нажатию.
  const [open, setOpen] = useState(false);
  const [starting, setStarting] = useState(false);
  const [waiting, setWaiting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const paymentId = useRef<string | null>(null);
  // Kept so the link can be offered in the waiting state: the page is opened
  // after an await, which is outside the user gesture, and Safari and Firefox
  // block that — leaving the old UI insisting a tab was open when none was.
  const [checkoutUrl, setCheckoutUrl] = useState<string | null>(null);

  useEffect(() => {
    if (!waiting) return;
    const timer = setInterval(async () => {
      if (!paymentId.current) return;
      try {
        const payment = await builderApi.getPayment(paymentId.current);
        if (payment.status === "paid") {
          setWaiting(false);
          onPaid();
        } else if (payment.status === "failed") {
          setWaiting(false);
          setError("Платёж не прошёл. Попробуй ещё раз.");
        }
      } catch {
        // transient — the next tick tries again
      }
    }, POLL_MS);
    return () => clearInterval(timer);
  }, [waiting, onPaid]);

  async function handlePay(provider?: string) {
    setStarting(true);
    setError(null);
    try {
      const payment = await builderApi.startPublicationCheckout(botId, provider);
      paymentId.current = payment.id;
      if (!payment.checkout_url) {
        setError("Счёт создан, но ссылки на оплату нет. Напиши нам, мы разберёмся.");
        return;
      }
      setCheckoutUrl(payment.checkout_url);
      openExternal(payment.checkout_url);
      setWaiting(true);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Не удалось создать счёт");
    } finally {
      setStarting(false);
    }
  }

  // Several methods can be offered at once — cards abroad, a local
  // acquirer, crypto — and they are priced in different currencies, so each
  // shows its own amount rather than one converted number.
  const methods = info.methods?.length
    ? info.methods
    : [
        {
          provider: "",
          title: "Оплатить публикацию",
          price_minor: info.price_minor,
          currency: info.currency,
          renewal_price_minor: info.renewal_price_minor,
        },
      ];

  if (!open && !waiting) {
    const first = methods[0];
    return (
      <button type="button" className="paywall__collapsed" onClick={() => setOpen(true)}>
        <span>🚀 Опубликовать</span>
        <span className="paywall__collapsed-price">
          {first.price_minor > 0 ? `от ${price(first.price_minor, first.currency)} ›` : "›"}
          {problems.length > 0 && (
            <span
              className="paywall__collapsed-badge"
              title={`Замечаний перед оплатой: ${problems.length}`}
              aria-label={`Замечаний перед оплатой: ${problems.length}`}
            >
              ⚠ {problems.length}
            </span>
          )}
        </span>
      </button>
    );
  }

  const best = methods.length > 1 ? recommendedProvider(methods.map((m) => m.provider)) : null;
  const ordered = best ? [...methods].sort((a, b) => Number(b.provider === best) - Number(a.provider === best)) : methods;

  return (
    <div className="paywall paywall--open">
      <button type="button" className="paywall__fold" onClick={() => setOpen(false)}>
        Свернуть ✕
      </button>
      <div className="paywall__head">
        <span className="paywall__icon" aria-hidden="true">
          🚀
        </span>
        <div>
          <p className="paywall__title">Публикация бота</p>
          <p className="paywall__hint">
            Собирать и править сценарий можно бесплатно и сколько угодно. Оплата — за запуск этого бота в
            Telegram.
          </p>
          {/* Said here, before the money is taken, and not in a message a
              month later: "а почему с меня списали ещё раз" is the same
              conversation as a refund request. */}
          {info.renewal_price_minor > 0 && (
            <p className="paywall__terms">
              Подписка — {price(info.renewal_price_minor, info.currency)} за каждые {info.renewal_period_days}{" "}
              {plural(info.renewal_period_days, ["день", "дня", "дней"])}, и она одна на все ваши боты, сколько бы их ни
              было. Если подписки ещё нет, первый период входит в эту оплату; каждый следующий бот оплачивается только
              за запуск. Напомним заранее, до конца периода.
            </p>
          )}
        </div>
      </div>

      {problems.length > 0 && (
        <div className="paywall__problems">
          <p className="paywall__problems-title">Перед оплатой стоит поправить:</p>
          <ul>
            {problems.map((problem) => (
              <li key={problem}>{problem}</li>
            ))}
          </ul>
          <p className="paywall__problems-hint">
            Оплатить можно и так — деньги за запуск не сгорят. Но бот выйдет в Telegram с этими проблемами.
          </p>
        </div>
      )}

      <p className="paywall__next">
        Что дальше: после оплаты бот попросит токен. Получить его — минута, если делать по шагам.
      </p>
      <BotFatherSteps />

      {error && <p className="publish-form__error">{error}</p>}

      {waiting ? (
        <div className="paywall__waiting">
          <span className="btn-spinner" aria-hidden="true" />
          <span>
            Ждём подтверждение — обычно несколько секунд, страница обновится сама. Если прошло больше минуты,{" "}
            <a href="https://t.me/DragDropBot" target="_blank" rel="noreferrer">
              напиши в поддержку
            </a>
            .{" "}
            {checkoutUrl && (
              <a href={checkoutUrl} target="_blank" rel="noreferrer">
                Если страница не открылась — открой её здесь
              </a>
            )}
          </span>
        </div>
      ) : methods.length === 1 ? (
        <button
          type="button"
          className="publish-button"
          onClick={() => handlePay(methods[0].provider || undefined)}
          disabled={starting}
        >
          {starting
            ? "Готовим счёт…"
            : `Оплатить публикацию · ${price(methods[0].price_minor, methods[0].currency)}`}
        </button>
      ) : (
        <div className="paywall__methods">
          {ordered.map((method) => (
            <button
              key={method.provider}
              type="button"
              className="paywall__method"
              onClick={() => handlePay(method.provider)}
              disabled={starting}
            >
              <span className="paywall__method-title">
                {method.title}
                {method.provider === best && <span className="paywall__method-badge">Рекомендуем тебе</span>}
                {method.how && <span className="paywall__method-how">{method.how}</span>}
                {(method.who || METHOD_NOTE[method.provider]) && (
                  <span className="paywall__method-note">{method.who || METHOD_NOTE[method.provider]}</span>
                )}
              </span>
              <span className="paywall__method-price">
                {price(method.price_minor, method.currency)}
                {method.renewal_price_minor > 0 && (
                  <span className="paywall__method-renewal">
                    затем {price(method.renewal_price_minor, method.currency)}/
                    {info.renewal_period_days}&nbsp;дн.
                  </span>
                )}
                <span className="paywall__method-go" aria-hidden="true">
                  Оплатить ›
                </span>
              </span>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
