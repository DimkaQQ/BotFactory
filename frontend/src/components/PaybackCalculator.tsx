import { ArrowRight } from "@phosphor-icons/react";
import { useState } from "react";

interface Props {
  launchUsd: number;
  renewalUsd: number | null;
  onStart: () => void;
}

const salesWord = (n: number) => (n === 1 ? "продажа" : n < 5 ? "продажи" : "продаж");

/** «Сколько продаж, чтобы бот окупился»: простая арифметика на цифрах из настроек
 * сервера, без обещаний дохода. Сколько товар стоит, решает сам человек, а мы лишь
 * показываем, как быстро запуск возвращается. */
export function PaybackCalculator({ launchUsd, renewalUsd, onStart }: Props) {
  const [price, setPrice] = useState(30);
  const salesForLaunch = Math.max(1, Math.ceil(launchUsd / price));
  const salesForMonth = renewalUsd ? Math.max(1, Math.ceil(renewalUsd / price)) : null;

  return (
    <div className="payback">
      <div className="payback__controls">
        <p className="payback__title">Посчитай, когда бот окупится</p>
        <p className="payback__headline">
          Запуск ${launchUsd}
          {renewalUsd ? `, дальше $${renewalUsd} в месяц` : ", дальше без доплат"}
        </p>
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
        <div className="payback__scale" aria-hidden="true">
          <span>$5</span>
          <span>$100</span>
          <span>$300</span>
        </div>
      </div>
      <div className="payback__results">
        <div className="payback__result">
          <span className="payback__big">{salesForLaunch}</span>
          <span className="payback__small">
            {salesWord(salesForLaunch)}, и запуск окупился
          </span>
          <span className="payback__sum">запуск ${launchUsd}</span>
        </div>
        {salesForMonth !== null && (
          <div className="payback__result">
            <span className="payback__big">{salesForMonth}</span>
            <span className="payback__small">{salesWord(salesForMonth)} в месяц покрывают работу бота</span>
            <span className="payback__sum">${renewalUsd} в месяц</span>
          </div>
        )}
      </div>
      <p className="payback__note">
        Бот принимает оплату и выдаёт товар сам, круглосуточно. Каждая следующая продажа уже твоя. Расчёт без
        комиссии твоей кассы.
      </p>
      <button type="button" className="payback__cta" onClick={onStart}>
        Начать бесплатно <ArrowRight size={18} aria-hidden="true" />
      </button>
    </div>
  );
}
