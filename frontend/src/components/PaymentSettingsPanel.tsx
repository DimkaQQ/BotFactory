import { useEffect, useState } from "react";

import {
  type PaymentProviderInfo,
  type PaymentRegion,
  type PaymentSettings,
  ApiError,
  builderApi,
} from "../api/builderApi";
import { useDraggablePanel } from "../hooks/useDraggablePanel";
import { useEscape } from "../hooks/useEscape";

interface Props {
  botId: string;
  onClose: () => void;
  onSaved: (settings: PaymentSettings) => void;
  /** Открыть экран продаж. Заказы жили здесь же, под семнадцатью плитками
   * платёжных систем, — теперь у них свой экран, а отсюда ведёт ссылка. */
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
  const [regions, setRegions] = useState<PaymentRegion[]>([]);
  const [subscriptionsEnabled, setSubscriptionsEnabled] = useState(false);
  const [settings, setSettings] = useState<PaymentSettings | null>(null);
  const [slug, setSlug] = useState<string>("");
  const [isTest, setIsTest] = useState(true);
  const [values, setValues] = useState<Record<string, string>>({});
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    (async () => {
      try {
        const [list, current] = await Promise.all([
          builderApi.listPaymentProviders(),
          builderApi.getPaymentSettings(botId),
        ]);
        setProviders(list.providers);
        setRegions(list.regions ?? []);
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

  // Nineteen gateways in one flat grid is a wall to scan, and the only
  // question anyone brings here is "which of these works for my country".
  // Sections come from the server (see payments/__init__.py) and are dropped
  // when empty, so this stays correct as gateways are added or moved.
  const grouped = (regions.length ? regions : [{ slug: "global", title: "" }])
    .map((region) => ({
      ...region,
      items: (providers ?? []).filter((p) => (p.region || "global") === region.slug),
    }))
    .filter((group) => group.items.length > 0);
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
      setSaved(true);
      onSaved(next);
      setTimeout(() => setSaved(false), 2500);
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
          title="Потяни, чтобы переместить окно (двойной щелчок — вернуть на место)"
          {...dragProps}
        >
          <span className="edit-panel__icon block-card__icon--delivery" aria-hidden="true">
            💳
          </span>
          <span className="edit-panel__title">Приём оплаты</span>
          <button type="button" className="edit-panel__close" aria-label="Закрыть" onClick={onClose}>
            ✕
          </button>
        </div>

        <div className="edit-panel__body">
          {providers === null ? (
            <p className="app-hint">Загружаем…</p>
          ) : (
            <>
              <p className="payment-settings__lead">
                Деньги идут напрямую тебе на счёт в платёжной системе — мы только формируем ссылку на оплату и
                ждём подтверждение.
              </p>

              <div className="buttons-editor__field">
                <h3 className="payment-settings__heading">Платёжная система</h3>
                {subscriptionsEnabled && (
                  <p className="app-hint payment-settings__recurring-legend">
                    🔁 — умеет списывать подписку сама. У остальных бот присылает новый счёт каждый период.
                  </p>
                )}
                {grouped.map((group) => (
                  <div key={group.slug} className="payment-settings__region">
                    {group.title && <p className="payment-settings__region-title">{group.title}</p>}
                    <div className="payment-settings__providers">
                      {group.items.map((provider) => (
                        <button
                          key={provider.slug}
                          type="button"
                          className={`payment-settings__provider ${slug === provider.slug ? "payment-settings__provider--active" : ""}${
                            provider.slug === "test" ? " payment-settings__provider--test" : ""
                          }`}
                          onClick={() => setSlug(provider.slug)}
                        >
                          <span className="payment-settings__provider-title">
                            {provider.title}
                            {subscriptionsEnabled && provider.recurring !== "none" && (
                              <span
                                className="payment-settings__recurring"
                                title={
                                  provider.recurring === "gateway"
                                    ? "Ведёт подписку сама: списывает следующий период без участия покупателя"
                                    : "Автосписание: первая оплата сохраняет карту, дальше бот списывает сам"
                                }
                              >
                                {" "}🔁
                              </span>
                            )}
                          </span>
                          {SHORT[provider.slug] && (
                            <span className="payment-settings__provider-note">{SHORT[provider.slug]}</span>
                          )}
                        </button>
                      ))}
                    </div>
                  </div>
                ))}
                <button
                  type="button"
                  className={`payment-settings__none ${slug === "" ? "payment-settings__none--active" : ""}`}
                  onClick={() => setSlug("")}
                >
                  Без оплаты — бот ничего не продаёт
                </button>
              </div>

              {active && (
                <>
                  <p className="payment-settings__hint">{active.hint}</p>

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
                          placeholder={filled ? "•••••••• (не менять — пусто)" : field.hint}
                          value={values[field.key] ?? ""}
                          onChange={(e) => setValues((prev) => ({ ...prev, [field.key]: e.target.value }))}
                        />
                      </label>
                    );
                  })}

                  {active.has_test_mode && (
                    <label className="payment-settings__test">
                      <input type="checkbox" checked={isTest} onChange={(e) => setIsTest(e.target.checked)} />
                      <span>
                        Тестовый режим — платежи не настоящие. Сними галочку, когда проверишь сценарий и будешь
                        готов принимать деньги.
                      </span>
                    </label>
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
                {saving ? "Сохраняем…" : saved ? "✓ Сохранено" : "Сохранить"}
              </button>

              {/* Сами продажи живут на своём экране: настройки кассы
                  трогают один раз, а заказы смотрят каждый день — и
                  проскроллить ради них семнадцать плиток было незачем. */}
              {onOpenSales && (
                <button type="button" className="payment-settings__sales-link" onClick={onOpenSales}>
                  💰 Продажи и заказы →
                </button>
              )}
            </>
          )}
        </div>
      </div>
    </>
  );
}
