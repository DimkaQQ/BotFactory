import { useEffect, useState } from "react";

import { type BotSiteSettings, ApiError, builderApi } from "../api/builderApi";
import { useDraggablePanel } from "../hooks/useDraggablePanel";
import { useEscape } from "../hooks/useEscape";
import { Globe, X } from "@phosphor-icons/react";

type Draft = Omit<BotSiteSettings, "saved" | "url" | "can_publish">;

const TEXT_FIELDS: { key: keyof Draft; label: string; hint?: string; long?: boolean }[] = [
  { key: "title", label: "Название на странице", hint: "Например: Школа йоги Анны" },
  { key: "about", label: "Чем вы занимаетесь", hint: "Коротко: что продаёте и для кого", long: true },
  { key: "seller_name", label: "Название продавца", hint: "ИП, ТОО или ваше имя как самозанятого" },
  { key: "seller_id", label: "ИИН / БИН / ИНН", hint: "Банк проверяет реквизиты продавца" },
  { key: "seller_address", label: "Адрес (необязательно)" },
  { key: "email", label: "Почта для связи" },
  { key: "phone", label: "Телефон (необязательно)" },
  { key: "refund_text", label: "Условия возврата (необязательно)", hint: "Если пусто: подставится типовой текст", long: true },
];

/** Страница-витрина бота на нашем домене: нужна банкам Казахстана: с неё ссылка в бота. */
export function SitePanel({ botId, onClose }: { botId: string; onClose: () => void }) {
  useEscape(onClose);
  const { panelRef, handleProps: dragProps } = useDraggablePanel();
  const [site, setSite] = useState<BotSiteSettings | null>(null);
  const [draft, setDraft] = useState<Draft | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [note, setNote] = useState<string | null>(null);

  function load(s: BotSiteSettings) {
    setSite(s);
    const { saved: _s, url: _u, can_publish: _c, ...rest } = s;
    setDraft(rest);
  }

  useEffect(() => {
    builderApi.getSite(botId).then(load).catch((e) => setError(e instanceof ApiError ? e.message : "Не удалось загрузить"));
  }, [botId]);

  async function save(enabled?: boolean) {
    if (!draft) return;
    setBusy(true);
    setError(null);
    setNote(null);
    try {
      const next = await builderApi.saveSite(botId, enabled === undefined ? draft : { ...draft, enabled });
      load(next);
      setNote(enabled === true ? "Страница включена" : enabled === false ? "Страница выключена" : "Сохранено");
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Не получилось сохранить. Попробуйте ещё раз.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <div className="sheet-backdrop edit-panel-backdrop" onClick={onClose} />
      <div className="edit-panel overview-panel" ref={panelRef}>
        <div className="edit-panel__header" title="Потяни, чтобы переместить окно" {...dragProps}>
          <span className="edit-panel__icon block-card__icon--success" aria-hidden="true">
            <Globe size={20} aria-hidden="true" />
          </span>
          <span className="edit-panel__title">Страница для банка</span>
          <button type="button" className="edit-panel__close" aria-label="Закрыть" onClick={onClose}>
            <X size={18} aria-hidden="true" />
          </button>
        </div>
        <div className="edit-panel__body">
          <p className="feedback-panel__hint">
            В Казахстане банки не принимают оплату «внутри Telegram»: нужна страница с описанием, ценами, реквизитами и
            документами, а с неё: кнопка в бота. Заполните данные: страница откроется по ссылке ниже. Цены берутся из
            блоков оплаты. Документы: типовой шаблон, покажите его юристу.
          </p>
          {!draft && !error && <p className="feedback-panel__hint">Загрузка…</p>}
          {draft && site && (
            <>
              <label className="overview-panel__filter">
                <span className="buttons-editor__field-label">Адрес страницы</span>
                <input
                  className="payment-editor__input"
                  value={draft.slug}
                  maxLength={40}
                  onChange={(e) => setDraft({ ...draft, slug: e.target.value.toLowerCase() })}
                />
              </label>
              {TEXT_FIELDS.map((f) => (
                <label key={f.key} className="overview-panel__filter" style={{ marginTop: 12 }}>
                  <span className="buttons-editor__field-label">{f.label}</span>
                  {f.long ? (
                    <textarea
                      className="payment-editor__input feedback-panel__text"
                      rows={3}
                      value={String(draft[f.key] ?? "")}
                      onChange={(e) => setDraft({ ...draft, [f.key]: e.target.value })}
                    />
                  ) : (
                    <input
                      className="payment-editor__input"
                      value={String(draft[f.key] ?? "")}
                      onChange={(e) => setDraft({ ...draft, [f.key]: e.target.value })}
                    />
                  )}
                  {f.hint && <small className="feedback-panel__hint">{f.hint}</small>}
                </label>
              ))}
              {error && <p className="feedback-panel__error" role="alert">{error}</p>}
              {note && <p className="feedback-panel__ok">{note}</p>}
              <button type="button" className="payment-settings__save" disabled={busy} onClick={() => save()}>
                {busy ? "Сохраняем…" : "Сохранить"}
              </button>
              {site.saved && (
                <button
                  type="button"
                  className="payment-settings__save"
                  style={{ marginTop: 8 }}
                  disabled={busy || (!site.enabled && !site.can_publish)}
                  onClick={() => save(!site.enabled)}
                >
                  {site.enabled ? "Выключить страницу" : "Включить страницу"}
                </button>
              )}
              {!site.can_publish && <p className="feedback-panel__hint">Включить можно после публикации бота.</p>}
              {site.enabled && site.url && (
                <p className="feedback-panel__ok">
                  Страница открыта: <a href={site.url} target="_blank" rel="noreferrer">{site.url}</a>
                  <br />
                  Эту ссылку укажите банку как сайт.
                </p>
              )}
            </>
          )}
          {!draft && error && <p className="feedback-panel__error">{error}</p>}
        </div>
      </div>
    </>
  );
}
