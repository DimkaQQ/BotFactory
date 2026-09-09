import { useEffect, useRef, useState } from "react";

import { type PublicationInfo, ApiError, builderApi, formatAmount } from "../api/builderApi";
import { openExternal } from "../hooks/useTelegramWebApp";

interface Props {
  botId: string;
  info: PublicationInfo;
  onPaid: () => void;
}

const POLL_MS = 3000;

/** Building is free; putting the bot on the air is what's paid for. Opens
 * the provider's page in a new tab and polls the payment until the callback
 * settles it — the redirect back is never what we trust. */
export function PublishPaywall({ botId, info, onPaid }: Props) {
  const [starting, setStarting] = useState(false);
  const [waiting, setWaiting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const paymentId = useRef<string | null>(null);

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

  async function handlePay() {
    setStarting(true);
    setError(null);
    try {
      const payment = await builderApi.startPublicationCheckout(botId);
      paymentId.current = payment.id;
      if (payment.checkout_url) {
        openExternal(payment.checkout_url);
        setWaiting(true);
      }
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Не удалось создать счёт");
    } finally {
      setStarting(false);
    }
  }

  return (
    <div className="paywall">
      <div className="paywall__head">
        <span className="paywall__icon" aria-hidden="true">
          🚀
        </span>
        <div>
          <p className="paywall__title">Публикация — {formatAmount(info.price_minor)} {info.currency}</p>
          <p className="paywall__hint">
            Собирать и править сценарий можно бесплатно и сколько угодно. Оплата — один раз за запуск этого бота
            в Telegram.
          </p>
        </div>
      </div>

      {error && <p className="publish-form__error">{error}</p>}

      {waiting ? (
        <div className="paywall__waiting">
          <span className="btn-spinner" aria-hidden="true" />
          Ждём подтверждение оплаты… Страница оплаты открыта в соседней вкладке.
        </div>
      ) : (
        <button type="button" className="publish-button" onClick={handlePay} disabled={starting}>
          {starting ? "Готовим счёт…" : `Оплатить публикацию · ${formatAmount(info.price_minor)} ${info.currency}`}
        </button>
      )}
    </div>
  );
}
