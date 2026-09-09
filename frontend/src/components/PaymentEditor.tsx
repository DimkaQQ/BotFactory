import type { BlockContent } from "../api/builderApi";

interface Props {
  content: BlockContent;
  /** Which provider the bot is set up with — a payment block with none is
   * inert, and saying so here beats letting a customer hit a dead button. */
  provider: string | null;
  currencies: string[];
  onChange: (content: BlockContent) => void;
  onOpenSettings: () => void;
}

const FALLBACK_CURRENCIES = ["KZT", "RUB", "USD", "EUR"];

/** Editor for a payment block: what's being sold, for how much, and what
 * the button says. What happens *after* the money lands is the block's
 * plain arrow on the canvas — usually a delivery block. */
export function PaymentEditor({ content, provider, currencies, onChange, onOpenSettings }: Props) {
  const options = currencies.length > 0 ? currencies : FALLBACK_CURRENCIES;
  const currency = content.currency || options[0];

  return (
    <div className="payment-editor">
      {!provider && (
        <button type="button" className="payment-editor__warning" onClick={onOpenSettings}>
          ⚠️ Платёжный провайдер не подключён — кнопка оплаты не появится. Настроить →
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
          <span className="buttons-editor__field-label">Цена</span>
          <input
            className="payment-editor__input"
            inputMode="decimal"
            placeholder="990"
            value={content.price ?? ""}
            onChange={(e) => onChange({ ...content, price: e.target.value.replace(/[^\d.,]/g, "") })}
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

      <label className="buttons-editor__field">
        <span className="buttons-editor__field-label">Надпись на кнопке</span>
        <input
          className="payment-editor__input"
          placeholder={`Оплатить ${content.price || "990"} ${currency}`}
          value={content.button_label ?? ""}
          onChange={(e) => onChange({ ...content, button_label: e.target.value })}
        />
      </label>

      <p className="payment-editor__note">
        После оплаты бот сам продолжит сценарий по стрелке «дальше» — поставь туда блок «Выдача» с файлом или
        ссылкой.
      </p>
    </div>
  );
}
