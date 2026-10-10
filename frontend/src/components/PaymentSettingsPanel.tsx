import { useEffect, useState } from "react";

import {
  type PaymentProviderInfo,
  type PaymentSettings,
  ApiError,
  builderApi,
} from "../api/builderApi";
import { useDraggablePanel } from "../hooks/useDraggablePanel";
import { useEscape } from "../hooks/useEscape";
import { CreditCard, X } from "@phosphor-icons/react";
import { ArrowUUpLeft, ArrowsClockwise, CurrencyCircleDollar, Flask, LinkSimple, Prohibit } from "@phosphor-icons/react";


interface Props {
  botId: string;
  onClose: () => void;
  onSaved: (settings: PaymentSettings) => void;
  /** Открыть экран продаж. Заказы жили здесь же, под семнадцатью плитками
   * платёжных систем,: теперь у них свой экран, а отсюда ведёт ссылка. */
  onOpenSales?: () => void;
}

/** One line per provider, so choosing does not require having integrated one
 * before. The full `hint` only appears after the tile is clicked. */
const SHORT: Record<string, string> = {
  stars: "цифровые товары в Telegram",
  yookassa: "карты РФ · нужно ИП/ООО",
  tbank: "карты РФ и СБП · нужно ИП/ООО",
  cloudpayments: "карты РФ и Казахстана",
  prodamus: "карты РФ · для самозанятых",
  robokassa: "карты РФ · счёт в валюте магазина",
  paymaster: "карты РФ",
  lifepay: "СБП и карты РФ · онлайн-касса",
  lavatop: "карты РФ, покупатель платит из-за рубежа",
  freedompay: "Казахстан, Узбекистан, Кыргызстан",
  ioka: "Казахстан · тенге, рубли, доллары",
  processingkz: "Казахстан · через банк-эквайер",
  click: "Узбекистан · Click",
  payme: "Узбекистан · Payme",
  liqpay: "Украина · ПриватБанк",
  stripe: "зарубежные карты · нужна компания вне РФ и РК",
  cryptobot: "USDT, TON · без юрлица",
  link: "любая своя ссылка · подтверждаешь вручную",
  test: "только для проверки сценария",
};

/** Per-bot payment provider setup. The form is rendered from whatever
 * GET /payments/providers returns, so adding a provider on the backend
 * makes it appear here with no frontend change. */
export function PaymentSettingsPanel({ botId, onClose, onSaved, onOpenSales }: Props) {
  useEscape(onClose);
  const { panelRef, handleProps: dragProps } = useDraggablePanel();

  const [providers, setProviders] = useState<PaymentProviderInfo[] | null>(null);
  const [subscriptionsEnabled, setSubscriptionsEnabled] = useState(false);
  const [settings, setSettings] = useState<PaymentSettings | null>(null);
  const [slug, setSlug] = useState<string>("");
  const [isTest, setIsTest] = useState(true);
  const [values, setValues] = useState<Record<string, string>>({});
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  // Сохранили, но касса ещё неполная: зелёное «Сохранено» тут вводило бы в заблуждение.
  const [savedPartial, setSavedPartial] = useState(false);

  useEffect(() => {
    (async () => {
      try {
        const [list, current] = await Promise.all([
          builderApi.listPaymentProviders(),
          builderApi.getPaymentSettings(botId),
        ]);
        setProviders(list.providers);
        setSubscriptionsEnabled(Boolean(list.subscriptions_enabled));
        setSettings(current);
        setSlug(current.provider ?? "");
        setIsTest(current.is_test);
      } catch (err) {
        setError(err instanceof ApiError ? err.message : "Не удалось загрузить настройки оплаты");
      }
    })();
  }, [botId]);

  const active = providers?.find((p) => p.slug === slug) ?? null;

  // Кассы одним списком: «Оплата по ссылке» и «Демо», не кассы, они вынесены
  // отдельно, чтобы не путать выбор.
  const realProviders = (providers ?? []).filter((p) => p.slug !== "test" && p.slug !== "link");
  const linkProvider = (providers ?? []).find((p) => p.slug === "link") ?? null;
  const testProvider = (providers ?? []).find((p) => p.slug === "test") ?? null;
  const connected = settings?.provider ? providers?.find((p) => p.slug === settings.provider) : null;

  async function handleSave() {
    setSaving(true);
    setError(null);
    try {
      const next = await builderApi.savePaymentSettings(botId, {
        provider: slug || null,
        is_test: isTest,
        credentials: values,
      });
      setSettings(next);
      setValues({});
      setSavedPartial(Boolean(next.provider) && !next.ready);
      setSaved(true);
      onSaved(next);
      setTimeout(() => setSaved(false), 3500);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Не удалось сохранить");
    } finally {
      setSaving(false);
    }
  }

  return (
    <>
      <div className="sheet-backdrop edit-panel-backdrop" onClick={onClose} />
      <div className="edit-panel" ref={panelRef}>
        <div
          className="edit-panel__header"
          title="Потяни, чтобы переместить окно (двойной щелчок, вернуть на место)"
          {...dragProps}
        >
          <span className="edit-panel__icon block-card__icon--delivery" aria-hidden="true">
            <CreditCard size={20} aria-hidden="true" />
          </span>
          <span className="edit-panel__title">Приём оплаты</span>
          <button type="button" className="edit-panel__close" aria-label="Закрыть" onClick={onClose}>
            <X size={18} aria-hidden="true" />
          </button>
        </div>

        <div className="edit-panel__body">
          {providers === null ? (
            error ? <p className="publish-form__error">{error}</p> : <p className="app-hint">Загружаем…</p>
          ) : (
            <>
              <p className="payment-settings__lead">
                Деньги идут напрямую тебе на счёт в платёжной системе, мы только формируем ссылку на оплату и
                ждём подтверждение.
              </p>

              <div className={`payment-settings__status${connected ? " payment-settings__status--on" : ""}`}>
                {connected ? (
                  <>
                    <strong>Сейчас: {connected.title}</strong>
                    <span>
                      {connected.slug === "test"
                        ? "демо: деньги не принимаются"
                        : connected.has_test_mode
                          ? settings?.is_test
                            ? "тестовый режим: деньги не списываются"
                            : "боевой режим: настоящие деньги"
                          : "подключено"}
                    </span>
                  </>
                ) : (
                  <>
                    <strong>Сейчас: оплата не подключена</strong>
                    <span>бот ничего не продаёт, пока ты не выберешь кассу</span>
                  </>
                )}
              </div>

              <div className="buttons-editor__field">
                <h3 className="payment-settings__heading">1. Выбери, куда получать деньги</h3>
                {subscriptionsEnabled && (
                  <p className="app-hint payment-settings__recurring-legend">
                    Значок повтора: касса умеет списывать подписку сама. У остальных бот присылает новый счёт каждый период.
                  </p>
                )}
                <div className="payment-settings__providers">
                  {realProviders.map((provider) => (
                    <button
                      key={provider.slug}
                      type="button"
                      className={`payment-settings__provider ${slug === provider.slug ? "payment-settings__provider--active" : ""}`}
                      onClick={() => {
                        setSlug(provider.slug);
                        setValues({});
                      }}
                    >
                      <span className="payment-settings__provider-title">
                        {provider.title}
                        {subscriptionsEnabled && provider.recurring !== "none" && (
                          <span className="payment-settings__recurring"> <ArrowsClockwise size={13} className="inline-icon" aria-label="подписки" /></span>
                        )}
                      </span>
                      {SHORT[provider.slug] && (
                        <span className="payment-settings__provider-note">{SHORT[provider.slug]}</span>
                      )}
                    </button>
                  ))}
                </div>

                {linkProvider && (
                  <button
                    type="button"
                    className={`payment-settings__other ${slug === "link" ? "payment-settings__other--active" : ""}`}
                    onClick={() => setSlug("link")}
                  >
                    <strong><LinkSimple size={15} className="inline-icon" aria-hidden="true" /> Своя ссылка на оплату</strong>
                    <span>
                      Нет подключённой кассы? Бот пришлёт покупателю твою ссылку (например, на перевод по номеру
                      карты), а ты сам подтвердишь оплату, деньги он получит только после этого.
                    </span>
                  </button>
                )}
                <button
                  type="button"
                  className={`payment-settings__other ${slug === "" ? "payment-settings__other--active" : ""}`}
                  onClick={() => setSlug("")}
                >
                  <strong><Prohibit size={15} className="inline-icon" aria-hidden="true" /> Пока без оплаты</strong>
                  <span>Бот только общается и раздаёт бесплатное. Блок «Оплата» в сценарии не сработает.</span>
                </button>

                {testProvider && (
                  <details className="payment-settings__demo" open={slug === "test"}>
                    <summary>Хочу только посмотреть, как выглядит оплата</summary>
                    <button
                      type="button"
                      className={`payment-settings__other ${slug === "test" ? "payment-settings__other--active" : ""}`}
                      onClick={() => setSlug("test")}
                    >
                      <strong><Flask size={15} className="inline-icon" aria-hidden="true" /> Демо-оплата</strong>
                      <span>
                        Это не касса: покупатель нажимает «оплатить» и сразу получает товар, деньги никуда не идут.
                        Включай только чтобы проверить сценарий, перед запуском выбери настоящую кассу.
                      </span>
                    </button>
                  </details>
                )}
              </div>

              {active && (
                <>
                  <h3 className="payment-settings__heading">
                    {active.fields.length > 0 ? `2. Данные из кабинета ${active.title}` : "2. Как это работает"}
                  </h3>
                  {active.hint.split("\n\n").map((part) =>
                    part.startsWith("!") ? (
                      <p key={part} className="payment-settings__callout">
                        {part.slice(1)}
                      </p>
                    ) : (
                      <p key={part} className="payment-settings__hint">
                        {part}
                      </p>
                    ),
                  )}
                  <div className="payment-settings__return">
                    <span className="payment-settings__return-icon" aria-hidden="true">
                      <ArrowUUpLeft size={18} />
                    </span>
                    <div>
                      <p className="payment-settings__return-title">Куда вернётся покупатель после оплаты</p>
                      <p className="payment-settings__return-text">
                        В твоего бота, если он уже опубликован. Пока бота нет в Telegram или ты смотришь «Как в чате»,
                        покупатель увидит страницу «Готово». Так и должно быть.
                      </p>
                    </div>
                  </div>

                  {active.fields.map((field) => {
                    const filled = settings?.provider === active.slug && settings.filled_fields.includes(field.key);
                    return (
                      <label key={field.key} className="buttons-editor__field">
                        <span className="buttons-editor__field-label">
                          {field.label}
                          {field.required === false && <span className="payment-settings__filled"> · необязательно</span>}
                          {filled && <span className="payment-settings__filled"> · сохранено</span>}
                        </span>
                        <input
                          className="payment-editor__input"
                          type={field.secret ? "password" : "text"}
                          autoComplete="off"
                          placeholder={filled ? "•••••••• (не менять: пусто)" : field.hint}
                          value={values[field.key] ?? ""}
                          onChange={(e) => setValues((prev) => ({ ...prev, [field.key]: e.target.value }))}
                        />
                      </label>
                    );
                  })}

                  {active.has_test_mode && (
                    <div className="buttons-editor__field">
                      <h3 className="payment-settings__heading">3. Режим кассы</h3>
                      <div className="payment-settings__modes" role="radiogroup" aria-label="Режим кассы">
                        <button
                          type="button"
                          role="radio"
                          aria-checked={isTest}
                          className={`payment-settings__mode${isTest ? " payment-settings__mode--active" : ""}`}
                          onClick={() => setIsTest(true)}
                        >
                          <strong><Flask size={15} className="inline-icon" aria-hidden="true" /> Тестовый</strong>
                          <span>Деньги не списываются. Для проверки (нужны тестовые ключи кассы).</span>
                        </button>
                        <button
                          type="button"
                          role="radio"
                          aria-checked={!isTest}
                          className={`payment-settings__mode${!isTest ? " payment-settings__mode--active" : ""}`}
                          onClick={() => setIsTest(false)}
                        >
                          <strong><CurrencyCircleDollar size={15} className="inline-icon" aria-hidden="true" /> Боевой</strong>
                          <span>Покупатели платят по-настоящему, деньги идут тебе. Нужны боевые ключи.</span>
                        </button>
                      </div>
                    </div>
                  )}

                  {settings?.callback_base && !active.sends_own_callback_url && active.uses_callback && (
                    <div className="payment-settings__callback">
                      <span className="buttons-editor__field-label">
                        Этот адрес нужно указать в кабинете платёжной системы как уведомление об оплате
                      </span>
                      <code>{`${settings.callback_base}/${active.slug}`}</code>
                    </div>
                  )}
                </>
              )}

              {error && <p className="publish-form__error">{error}</p>}

              <button type="button" className="payment-settings__save" onClick={handleSave} disabled={saving}>
                {saving ? "Сохраняем…" : saved ? (savedPartial ? "Сохранено, но поля заполнены не все" : "Сохранено") : "Сохранить"}
              </button>

              {/* Сами продажи живут на своём экране: настройки кассы
                  трогают один раз, а заказы смотрят каждый день, и
                  проскроллить ради них семнадцать плиток было незачем. */}
              {onOpenSales && (
                <button type="button" className="payment-settings__sales-link" onClick={onOpenSales}>
                  Продажи и заказы →
                </button>
              )}
            </>
          )}
        </div>
      </div>
    </>
  );
}
