import { useEffect } from "react";

import type { BlockContent, PaymentProviderInfo } from "../api/builderApi";

interface Props {
  /** Only used to keep this block's radio group to itself. */
  blockId?: string;
  content: BlockContent;
  /** Which provider the bot is set up with — a payment block with none is
   * inert, and saying so here beats letting a customer hit a dead button. */
  provider: string | null;
  currencies: string[];
  /** The chosen provider's catalogue entry, when it has been loaded: what it
   * needs per product, and whether it can confirm a payment by itself. */
  providerInfo?: PaymentProviderInfo | null;
  /** Чего не хватает в настройках кассы, если чего-то не хватает. */
  missingFields?: string[];
  /** Whether the constructor offers subscriptions at all right now. */
  subscriptionsEnabled?: boolean;
  onChange: (content: BlockContent) => void;
  onOpenSettings: () => void;
}

// Only used before a provider is chosen; once one is, its own list wins.
const FALLBACK_CURRENCIES = ["RUB", "KZT", "USD", "EUR"];

/** Editor for a payment block: what's being sold, for how much, and what
 * the button says. What happens *after* the money lands is the block's
 * plain arrow on the canvas — usually a delivery block. */
function PeriodField({
  content,
  onChange,
}: {
  content: BlockContent;
  onChange: (content: BlockContent) => void;
}) {
  return (
    <label className="buttons-editor__field payment-editor__period">
      <span className="buttons-editor__field-label">Период доступа, дней</span>
      <input
        className="payment-editor__input"
        inputMode="numeric"
        placeholder="30"
        value={content.period_days ?? ""}
        onChange={(e) => onChange({ ...content, period_days: e.target.value.replace(/[^\d]/g, "") })}
      />
    </label>
  );
}

export function PaymentEditor({
  blockId,
  content,
  provider,
  currencies,
  providerInfo,
  missingFields,
  subscriptionsEnabled,
  onChange,
  onOpenSettings,
}: Props) {
  // Radio groups are keyed by `name`; without the block's own id two payment
  // blocks open in turn would share one group, and picking a mode on the
  // second would silently clear it on the first.
  const blockKey = blockId ?? "payment";
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
  // What this particular gateway can do about the next period. Three
  // genuinely different answers, and the owner is choosing a business
  // model here, not a checkbox.
  const recurring = providerInfo?.recurring ?? "none";
  const blockFields = providerInfo?.block_fields ?? [];

  return (
    <div className="payment-editor">
      {/* Предупреждение снимается только когда касса РЕАЛЬНО готова. Раньше
          оно гасло от одного выбора провайдера — то есть ровно там, где
          владелец переставал видеть проблему, она и начиналась. */}
      {!provider ? (
        <button type="button" className="payment-editor__warning" onClick={onOpenSettings}>
          <span>
            ⚠️ Платёжная система не подключена — бот не сможет принять деньги, и этот блок остановит сценарий.
          </span>
          <span className="payment-editor__warning-cta">Подключить кассу →</span>
        </button>
      ) : missingFields && missingFields.length > 0 ? (
        <button type="button" className="payment-editor__warning" onClick={onOpenSettings}>
          <span>
            ⚠️ В кассе не заполнено: {missingFields.join(", ")}. Оплата не откроется, покупатель увидит
            ошибку.
          </span>
          <span className="payment-editor__warning-cta">Дозаполнить →</span>
        </button>
      ) : null}

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

      {/* Цена «0» проходила все проверки редактора и рисовалась на холсте
          как «— 0 RUB»; узнавал об этом только покупатель, получив общую
          ошибку. Продавец — никогда. */}
      {content.price !== undefined && !(Number(String(content.price).replace(",", ".")) > 0) && (
        <p className="payment-editor__note payment-editor__note--manual">
          ⚠️ Без цены бот не сможет выставить счёт — покупатель увидит ошибку вместо оплаты.
        </p>
      )}

      <label className="buttons-editor__field">
        <span className="buttons-editor__field-label">Надпись на кнопке</span>
        <input
          className="payment-editor__input"
          placeholder={`Оплатить ${content.price || "990"} ${currency}`}
          value={content.button_label ?? ""}
          onChange={(e) => onChange({ ...content, button_label: e.target.value })}
        />
      </label>

      {/* Покупают один раз или каждый раз заново. Выбор обязателен именно
          здесь: по умолчанию бот считает товар разовым и вернувшемуся
          покупателю говорит «уже оплачено» — для гайда это правильно, а для
          консультации значит, что продавец работает бесплатно. */}
      <div className="payment-editor__repeat">
        <span className="buttons-editor__field-label">Как часто это покупают</span>
        <label className="payment-editor__toggle">
          <input
            type="radio"
            name={`repeat-${blockKey}`}
            checked={!content.repeatable}
            onChange={() => onChange({ ...content, repeatable: false })}
          />
          <span>Покупают один раз — потом бот просто выдаёт купленное</span>
        </label>
        <label className="payment-editor__toggle">
          <input
            type="radio"
            name={`repeat-${blockKey}`}
            checked={Boolean(content.repeatable)}
            onChange={() => onChange({ ...content, repeatable: true })}
          />
          <span>Покупают снова и снова — каждый раз новый счёт</span>
        </label>
        <p className="payment-editor__field-hint">
          {content.repeatable
            ? "Подходит для услуг, записи, донатов и повторных заказов: тот же человек сможет купить ещё раз."
            : "Подходит для гайда, курса, файла: вернувшийся покупатель получит купленное снова, но платить второй раз не будет."}
        </p>
      </div>

      {/* Subscription — the one place in the product where the difference
          between the providers actually changes what the owner is selling,
          so it is stated in full rather than hidden behind a checkbox.

          Hidden entirely while the feature is switched off server-side: a
          control that saves a flag the engine then ignores is worse than no
          control. The engine strips the flag too (payment_service
          ._purchase_terms), so a block saved while it was on is sold as an
          ordinary one-off purchase. */}
      {subscriptionsEnabled && (
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
            {recurring === "gateway" ? (
              <>
                {/* Stars is locked to Telegram's own 30-day cycle; every
                    other gateway-run subscription takes the period we ask
                    for, so hiding the field would silently pin it to 30. */}
                {!isStars && <PeriodField content={content} onChange={onChange} />}
                <p className="payment-editor__note payment-editor__note--good">
                  {isStars
                    ? "⭐️ Telegram сам спишет звёзды раз в 30 дней, пока подписчик не отменит — отменяет он тоже внутри Telegram. Период фиксированный: 30 дней, другого Telegram не поддерживает."
                    : `✅ ${providerInfo?.title ?? "Касса"} сама ведёт подписку: спишет следующий период без участия покупателя, сама повторит попытку при отказе карты и даст ему страницу, где отписаться.`}
                </p>
                {providerInfo?.slug === "prodamus" && (
                  <p className="payment-editor__note payment-editor__note--manual">
                    ⚠️ Цену и периодичность задаёт карточка подписки в кабинете Prodamus — поле «Цена» выше на
                    подписку не влияет, и первый платёж может отличаться от регулярного. «Период доступа» здесь
                    отвечает только за то, до какого числа бот держит доступ открытым, поэтому поставь тот же
                    интервал, что в карточке. И учти: первый платёж Prodamus не считает автосписанием —
                    интервал 30 дней и 5 автосписаний это 6 месяцев доступа, а не 5.
                  </p>
                )}
              </>
            ) : recurring === "token" ? (
              <>
                <PeriodField content={content} onChange={onChange} />
                <p className="payment-editor__note payment-editor__note--good">
                  ✅ Первая оплата сохранит карту, дальше бот сам списывает в конце каждого периода. Если карта
                  откажет — подписчику придёт сообщение, а доступ закроется в конце оплаченного срока.
                  {providerInfo?.slug === "yookassa" &&
                    " В ЮKassa автоплатежи включает менеджер — если их нет, бот перейдёт на счета."}
                  {providerInfo?.slug === "ioka" &&
                    " В ioka карта сохраняется, только если покупатель отметит это на странице оплаты — кто не отметил, тому бот пришлёт счёт."}
                  {providerInfo?.slug === "freedompay" &&
                    " Во Freedom Pay рекуррент включает менеджер — если его нет, бот перейдёт на счета."}
                </p>
              </>
            ) : (
              <>
                <PeriodField content={content} onChange={onChange} />
                <p className="payment-editor__note payment-editor__note--manual">
                  {/* "Мы не умеем", не "касса не умеет": у половины этих
                      шлюзов рекуррент есть, просто мы его ещё не подключили,
                      и врать про чужой продукт незачем. */}
                  ⚠️ Автосписание через {providerInfo?.title ?? "эту кассу"} бот пока не умеет. Он пришлёт новый
                  счёт за 2 дня до конца периода и напомнит; доступ продлится, если счёт оплатят. Списывают
                  сами двенадцать касс — они помечены 🔁 в списке.
                </p>
              </>
            )}
          </>
        )}
      </div>
      )}

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
