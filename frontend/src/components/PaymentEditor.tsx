import { useEffect } from "react";

import type { BlockContent, PaymentProviderInfo } from "../api/builderApi";

interface Props {
  content: BlockContent;
  /** Which provider the bot is set up with — a payment block with none is
   * inert, and saying so here beats letting a customer hit a dead button. */
  provider: string | null;
  currencies: string[];
  /** The chosen provider's catalogue entry, when it has been loaded: what it
   * needs per product, and whether it can confirm a payment by itself. */
  providerInfo?: PaymentProviderInfo | null;
  onChange: (content: BlockContent) => void;
  onOpenSettings: () => void;
}

// Only used before a provider is chosen; once one is, its own list wins.
const FALLBACK_CURRENCIES = ["RUB", "KZT", "USD", "EUR"];

/** Editor for a payment block: what's being sold, for how much, and what
 * the button says. What happens *after* the money lands is the block's
 * plain arrow on the canvas — usually a delivery block. */
export function PaymentEditor({ content, provider, currencies, providerInfo, onChange, onOpenSettings }: Props) {
  const options = currencies.length > 0 ? currencies : FALLBACK_CURRENCIES;
  const currency = content.currency && options.includes(content.currency) ? content.currency : options[0];

  // A block created before a provider was chosen keeps whatever currency it
  // defaulted to, and a `<select>` whose value is not in its options renders
  // the first one instead — so the owner read "RUB" while the block still
  // said "KZT". Write the displayed value back so the two agree.
  useEffect(() => {
    if (content.currency !== currency) {
      onChange({ ...content, currency });
    }
  }, [content, currency, onChange]);
  const isStars = currency === "XTR";
  const blockFields = providerInfo?.block_fields ?? [];

  return (
    <div className="payment-editor">
      {!provider && (
        <button type="button" className="payment-editor__warning" onClick={onOpenSettings}>
          <span>
            ⚠️ Платёжная система не подключена — бот не сможет принять деньги, и этот блок остановит сценарий.
          </span>
          <span className="payment-editor__warning-cta">Подключить кассу →</span>
        </button>
      )}

      <label className="buttons-editor__field">
        <span className="buttons-editor__field-label">Сообщение перед кнопкой</span>
        <textarea
          className="chat-bubble__textarea edit-panel__textarea"
          rows={3}
          placeholder="Гайд «Как открыть кофейню» — 40 страниц опыта"
          value={content.text ?? ""}
          onChange={(e) => onChange({ ...content, text: e.target.value })}
        />
      </label>

      <label className="buttons-editor__field">
        <span className="buttons-editor__field-label">Название товара (увидит банк в чеке)</span>
        <input
          className="payment-editor__input"
          placeholder="Гайд по кофейне"
          value={content.title ?? ""}
          onChange={(e) => onChange({ ...content, title: e.target.value })}
        />
      </label>

      <div className="payment-editor__row">
        <label className="buttons-editor__field payment-editor__price">
          <span className="buttons-editor__field-label">{isStars ? "Цена в звёздах" : "Цена"}</span>
          <input
            className="payment-editor__input"
            inputMode="decimal"
            placeholder={isStars ? "250" : "990"}
            value={content.price ?? ""}
            onChange={(e) =>
              onChange({
                ...content,
                // Stars come only in whole units — letting a "990.50" be
                // typed here would just fail later, at the checkout.
                price: e.target.value.replace(isStars ? /[^\d]/g : /[^\d.,]/g, ""),
              })
            }
          />
        </label>
        <label className="buttons-editor__field payment-editor__currency">
          <span className="buttons-editor__field-label">Валюта</span>
          <select
            className="payment-editor__input"
            value={currency}
            onChange={(e) => onChange({ ...content, currency: e.target.value })}
          >
            {options.map((code) => (
              <option key={code} value={code}>
                {code}
              </option>
            ))}
          </select>
        </label>
      </div>

      {blockFields.map((field) => (
        <label className="buttons-editor__field" key={field.key}>
          <span className="buttons-editor__field-label">{field.label}</span>
          <input
            className="payment-editor__input"
            placeholder={field.hint}
            value={(content as Record<string, unknown>)[field.key] as string ?? ""}
            onChange={(e) => onChange({ ...content, [field.key]: e.target.value })}
          />
          {field.hint && <span className="payment-editor__field-hint">{field.hint}</span>}
        </label>
      ))}

      <label className="buttons-editor__field">
        <span className="buttons-editor__field-label">Надпись на кнопке</span>
        <input
          className="payment-editor__input"
          placeholder={`Оплатить ${content.price || "990"} ${currency}`}
          value={content.button_label ?? ""}
          onChange={(e) => onChange({ ...content, button_label: e.target.value })}
        />
      </label>

      {/* Subscription — the one place in the product where the difference
          between the providers actually changes what the owner is selling,
          so it is stated in full rather than hidden behind a checkbox. */}
      <div className="payment-editor__subscription">
        <label className="payment-editor__toggle">
          <input
            type="checkbox"
            checked={Boolean(content.subscription)}
            onChange={(e) => onChange({ ...content, subscription: e.target.checked })}
          />
          <span>Это подписка — платят регулярно</span>
        </label>

        {content.subscription && (
          <>
            {isStars ? (
              <p className="payment-editor__note payment-editor__note--good">
                ⭐️ Telegram сам спишет звёзды раз в 30 дней, пока подписчик не отменит — отменяет он тоже внутри
                Telegram. Период фиксированный: 30 дней, другого Telegram не поддерживает.
              </p>
            ) : (
              <>
                <label className="buttons-editor__field payment-editor__period">
                  <span className="buttons-editor__field-label">Период доступа, дней</span>
                  <input
                    className="payment-editor__input"
                    inputMode="numeric"
                    placeholder="30"
                    value={content.period_days ?? ""}
                    onChange={(e) =>
                      onChange({ ...content, period_days: e.target.value.replace(/[^\d]/g, "") })
                    }
                  />
                </label>
                <p className="payment-editor__note payment-editor__note--manual">
                  {providerInfo ? (
                    <>
                      ⚠️ {providerInfo.title} не умеет списывать сама — так устроены все кассы, кроме Telegram
                      Stars.
                    </>
                  ) : (
                    <>⚠️ Автосписание умеет только Telegram Stars, остальные кассы — нет.</>
                  )}{" "}
                  Бот пришлёт новый счёт за 2 дня до конца периода и напомнит; доступ продлится, если счёт
                  оплатят. Если нужно именно автосписание — выбери Telegram Stars в настройках кассы.
                </p>
              </>
            )}
          </>
        )}
      </div>

      <p className="payment-editor__note">
        После оплаты бот сам продолжит сценарий по стрелке «дальше» — поставь туда блок «Выдача» с файлом или
        ссылкой.
      </p>

      {providerInfo && !providerInfo.supports_status_check && providerInfo.slug !== "stars" && (
        <p className="payment-editor__note payment-editor__note--manual">
          {providerInfo.slug === "link"
            ? "Такую оплату бот проверить не может: покупатель нажмёт «Я оплатил», а ты подтвердишь заказ — придёт сообщение в бот и появится в списке заказов. После подтверждения бот сразу выдаёт товар."
            : "Оплата подтвердится сама, когда провайдер пришлёт уведомление."}
        </p>
      )}
    </div>
  );
}
