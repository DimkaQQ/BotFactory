import { useEffect, useRef, useState } from "react";

import { type BillingState, ApiError, builderApi, formatAmount } from "../api/builderApi";
import { openExternal } from "../hooks/useTelegramWebApp";

interface Props {
  botId: string;
  billing: BillingState;
  /** The bot went back on the air — the page reloads it, because the status
   * it shows everywhere else has just changed too. */
  onRenewed: () => void;
}

const POLL_MS = 3000;
const SYMBOLS: Record<string, string> = { USD: "$", EUR: "€", RUB: "₽", KZT: "₸", USDT: "USDT", XTR: "⭐" };

/** How close to the end is worth interrupting someone over. Matches the
 * lead time the reminder in Telegram uses, so the two never disagree. */
const NAG_DAYS = 5;

function money(currency: string): string {
  return SYMBOLS[currency] ?? currency;
}

function day(iso: string | null): string {
  if (!iso) return "";
  return new Date(iso).toLocaleDateString("ru-RU", { day: "numeric", month: "long" });
}

/** "Оплачено до 18 октября" while there is nothing to do about it, and null
 * once there is — from then on the banner below says it, louder. */
export function paidUntilLabel(billing: BillingState): string | null {
  if (billing.state !== "active" || (billing.days_left ?? 0) <= NAG_DAYS) return null;
  return `Оплачено до ${day(billing.paid_until)}`;
}

/** What the bot's owner owes us, and the one button that settles it.
 *
 * Deliberately not a modal: a bot that is still working must not be covered
 * by a payment dialogue, and one that has stopped needs the rest of the
 * constructor reachable so its owner can see that nothing was deleted. */
export function BillingBanner({ botId, billing, onRenewed }: Props) {
  const [starting, setStarting] = useState(false);
  const [waiting, setWaiting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const paymentId = useRef<string | null>(null);
  const [checkoutUrl, setCheckoutUrl] = useState<string | null>(null);

  useEffect(() => {
    if (!waiting) return;
    const timer = setInterval(async () => {
      if (!paymentId.current) return;
      try {
        const payment = await builderApi.getPayment(paymentId.current);
        if (payment.status === "paid") {
          setWaiting(false);
          onRenewed();
        } else if (payment.status === "failed") {
          setWaiting(false);
          setError("Платёж не прошёл. Попробуй ещё раз.");
        }
      } catch {
        // transient — the next tick tries again
      }
    }, POLL_MS);
    return () => clearInterval(timer);
  }, [waiting, onRenewed]);

  async function handleRenew() {
    setStarting(true);
    setError(null);
    try {
      const payment = await builderApi.startRenewalCheckout(botId);
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

  // Paid and nowhere near the end: no banner at all. The date is a few words
  // in the "бот работает" line instead (see `paidUntilLabel`) — nobody needs
  // a box telling them once a day that everything is fine.
  if (paidUntilLabel(billing) !== null || billing.state === "off") return null;

  const price = `${formatAmount(billing.price_minor)} ${money(billing.currency)}`;
  const tone =
    billing.state === "suspended" ? "billing--stopped" : billing.state === "grace" ? "billing--warn" : "billing--soon";

  return (
    <div className={`billing ${tone}`}>
      <div className="billing__text">
        {billing.state === "active" && (
          <>
            <p className="billing__title">
              Оплаченный период заканчивается{billing.days_left === 0 ? " сегодня" : ` через ${billing.days_left} дн.`}
            </p>
            <p className="billing__hint">Продли сейчас — бот продолжит работать без перерыва.</p>
          </>
        )}
        {billing.state === "grace" && (
          <>
            <p className="billing__title">Период закончился {day(billing.paid_until)}</p>
            <p className="billing__hint">
              Бот пока работает — до {day(billing.grace_until)}, потом уйдёт с эфира. Сценарий, настройки и
              заказы останутся на месте.
            </p>
          </>
        )}
        {/* The banner above already says the bot is off; repeating it here
            would spend the loudest box on the page on a fact the owner has
            just read. This one is for what to do about it. */}
        {billing.state === "suspended" && (
          <>
            <p className="billing__title">Период не продлён с {day(billing.paid_until)}</p>
            <p className="billing__hint">
              Оплати продление — бот вернётся в строй сразу же, с тем же сценарием и той же кассой.
            </p>
          </>
        )}
      </div>

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
      ) : (
        <button type="button" className="publish-button" onClick={handleRenew} disabled={starting}>
          {starting ? "Готовим счёт…" : `Продлить на ${billing.period_days} дней · ${price}`}
        </button>
      )}
    </div>
  );
}
