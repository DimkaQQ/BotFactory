import { useEffect, useState } from "react";

import { type PaymentProviderInfo, type PaymentSettings, ApiError, builderApi } from "../api/builderApi";

interface Props {
  botId: string;
  onClose: () => void;
  onSaved: (settings: PaymentSettings) => void;
}

/** Per-bot payment provider setup. The form is rendered from whatever
 * GET /payments/providers returns, so adding a provider on the backend
 * makes it appear here with no frontend change. */
export function PaymentSettingsPanel({ botId, onClose, onSaved }: Props) {
  const [providers, setProviders] = useState<PaymentProviderInfo[] | null>(null);
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
        setSettings(current);
        setSlug(current.provider ?? "");
        setIsTest(current.is_test);
      } catch (err) {
        setError(err instanceof ApiError ? err.message : "Не удалось загрузить настройки оплаты");
      }
    })();
  }, [botId]);

  const active = providers?.find((p) => p.slug === slug) ?? null;

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
      <div className="edit-panel">
        <div className="edit-panel__header">
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
                <span className="buttons-editor__field-label">Платёжная система</span>
                <div className="payment-settings__providers">
                  {providers.map((provider) => (
                    <button
                      key={provider.slug}
                      type="button"
                      className={`payment-settings__provider ${slug === provider.slug ? "payment-settings__provider--active" : ""}`}
                      onClick={() => setSlug(provider.slug)}
                    >
                      {provider.title}
                    </button>
                  ))}
                  <button
                    type="button"
                    className={`payment-settings__provider ${slug === "" ? "payment-settings__provider--active" : ""}`}
                    onClick={() => setSlug("")}
                  >
                    Без оплаты
                  </button>
                </div>
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
                          {filled && <span className="payment-settings__filled"> · сохранено</span>}
                        </span>
                        <input
                          className="payment-editor__input"
                          type={field.secret ? "password" : "text"}
                          autoComplete="off"
                          placeholder={filled ? "•••••••• (оставь пустым, чтобы не менять)" : field.hint}
                          value={values[field.key] ?? ""}
                          onChange={(e) => setValues((prev) => ({ ...prev, [field.key]: e.target.value }))}
                        />
                      </label>
                    );
                  })}

                  <label className="payment-settings__test">
                    <input type="checkbox" checked={isTest} onChange={(e) => setIsTest(e.target.checked)} />
                    <span>
                      Тестовый режим — платежи не настоящие. Сними галочку, когда проверишь сценарий и будешь
                      готов принимать деньги.
                    </span>
                  </label>

                  {settings?.callback_url && settings.provider === active.slug && active.slug !== "test" && (
                    <div className="payment-settings__callback">
                      <span className="buttons-editor__field-label">
                        Этот адрес нужно указать в кабинете платёжной системы как уведомление об оплате
                      </span>
                      <code>{settings.callback_url}</code>
                    </div>
                  )}
                </>
              )}

              {error && <p className="publish-form__error">{error}</p>}

              <button type="button" className="payment-settings__save" onClick={handleSave} disabled={saving}>
                {saving ? "Сохраняем…" : saved ? "✓ Сохранено" : "Сохранить"}
              </button>
            </>
          )}
        </div>
      </div>
    </>
  );
}
