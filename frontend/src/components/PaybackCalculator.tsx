import { useState } from "react";

interface Props {
  launchUsd: number;
  renewalUsd: number | null;
  onStart: () => void;
}

/** «Сколько продаж, чтобы бот окупился» — простая арифметика на цифрах из
 * настроек сервера, без обещаний дохода: сколько товар стоит, решает сам
 * человек, а мы лишь показываем, как быстро запуск возвращается. */
export function PaybackCalculator({ launchUsd, renewalUsd, onStart }: Props) {
  const [price, setPrice] = useState(30);
  const salesForLaunch = Math.max(1, Math.ceil(launchUsd / price));
  const salesForMonth = renewalUsd ? Math.max(1, Math.ceil(renewalUsd / price)) : null;

  return (
    <div className="payback">
      <p className="payback__title">Посчитай, когда бот окупится</p>
      <label className="payback__label" htmlFor="payback-price">
        Твой товар или услуга стоит
        <strong> ${price}</strong>
      </label>
      <input
        id="payback-price"
        className="payback__range"
        type="range"
        min={5}
        max={300}
        step={5}
        value={price}
        onChange={(event) => setPrice(Number(event.target.value))}
      />
      <div className="payback__results">
        <div className="payback__result">
          <span className="payback__big">{salesForLaunch}</span>
          <span className="payback__small">
            {salesForLaunch === 1 ? "продажа" : salesForLaunch < 5 ? "продажи" : "продаж"} — и запуск окупился
          </span>
        </div>
        {salesForMonth !== null && (
          <div className="payback__result">
            <span className="payback__big">{salesForMonth}</span>
            <span className="payback__small">
              {salesForMonth === 1 ? "продажа" : salesForMonth < 5 ? "продажи" : "продаж"} в месяц покрывают работу
              бота
            </span>
          </div>
        )}
      </div>
      <p className="payback__note">
        Бот принимает оплату и выдаёт товар сам, круглосуточно — каждая следующая продажа уже твоя. Расчёт без
        комиссии твоей кассы.
      </p>
      <button type="button" className="payback__cta" onClick={onStart}>
        Собрать бота бесплатно →
      </button>
    </div>
  );
}
