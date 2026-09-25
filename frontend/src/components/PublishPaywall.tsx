import { useEffect, useRef, useState } from "react";

import { type PublicationInfo, ApiError, builderApi, formatAmount } from "../api/builderApi";
import { openExternal } from "../hooks/useTelegramWebApp";

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
  stripe: "зарубежная карта",
  cryptobot: "USDT или TON из Telegram",
  robokassa: "карта РФ или KZT",
  yookassa: "карта РФ",
  lavatop: "карта РФ",
  stars: "звёзды Telegram",
};

function money(currency: string): string {
  return SYMBOLS[currency] ?? currency;
}

/** Building is free; putting the bot on the air is what's paid for. Opens
 * the provider's page in a new tab and polls the payment until the callback
 * settles it — the redirect back is never what we trust. */
export function PublishPaywall({ botId, problems, info, onPaid }: Props) {
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

  return (
    <div className="paywall">
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
              Дальше — {formatAmount(info.renewal_price_minor)} {money(info.currency)} за каждые{" "}
              {info.renewal_period_days} дней работы. Первый период входит в эту оплату: следующий счёт придёт
              через {info.renewal_period_days} дней, и бот напомнит заранее.
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
        Что дальше: после оплаты бот попросит токен. Получить его — минута: открой{" "}
        <a href="https://t.me/BotFather" target="_blank" rel="noreferrer">
          @BotFather
        </a>
        , отправь ему <code>/newbot</code>, придумай имя — он пришлёт строку вида
        <code> 123456789:AAH…</code>. Её и вставишь.
      </p>

      {error && <p className="publish-form__error">{error}</p>}

      {waiting ? (
        <div className="paywall__waiting">
          <span className="btn-spinner" aria-hidden="true" />
          <span>
            Ждём подтверждение оплаты.{" "}
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
            : `Оплатить публикацию · ${formatAmount(methods[0].price_minor)} ${money(methods[0].currency)}`}
        </button>
      ) : (
        <div className="paywall__methods">
          {methods.map((method) => (
            <button
              key={method.provider}
              type="button"
              className="paywall__method"
              onClick={() => handlePay(method.provider)}
              disabled={starting}
            >
              <span className="paywall__method-title">
                {method.title}
                {METHOD_NOTE[method.provider] && (
                  <span className="paywall__method-note">{METHOD_NOTE[method.provider]}</span>
                )}
              </span>
              <span className="paywall__method-price">
                {formatAmount(method.price_minor)} {money(method.currency)}
                {method.renewal_price_minor > 0 && (
                  <span className="paywall__method-renewal">
                    затем {formatAmount(method.renewal_price_minor)} {money(method.currency)}/
                    {info.renewal_period_days} дн.
                  </span>
                )}
              </span>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
