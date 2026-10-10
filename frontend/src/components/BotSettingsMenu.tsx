import type { ReactNode } from "react";

import { CaretRight, GearSix, Trash, X } from "@phosphor-icons/react";

import { useEscape } from "../hooks/useEscape";

export interface SettingsItem {
  key: string;
  icon: ReactNode;
  title: string;
  hint: string;
  /** ok: всё готово; warn: надо заняться; без значения: обычная строка. */
  tone?: "ok" | "warn";
  onClick: () => void;
}

interface Props {
  items: SettingsItem[];
  deleting?: boolean;
  onDelete: () => void;
  onClose: () => void;
}

/** Все настройки бота в одном месте: оплата, продажи, оформление, страница для банка и удаление.
 * В шапке остаётся одна иконка шестерёнки вместо ряда кнопок, которые не помещались на телефоне. */
export function BotSettingsMenu({ items, deleting, onDelete, onClose }: Props) {
  useEscape(onClose);

  return (
    <>
      <div className="sheet-backdrop edit-panel-backdrop" onClick={onClose} />
      <div className="edit-panel settings-menu" role="dialog" aria-label="Настройки бота">
        <div className="edit-panel__header">
          <span className="edit-panel__icon block-card__icon--delivery" aria-hidden="true">
            <GearSix size={20} />
          </span>
          <span className="edit-panel__title">Настройки бота</span>
          <button type="button" className="edit-panel__close" aria-label="Закрыть" onClick={onClose}>
            <X size={18} aria-hidden="true" />
          </button>
        </div>
        <div className="edit-panel__body">
          <ul className="settings-menu__list">
            {items.map((item) => (
              <li key={item.key}>
                <button
                  type="button"
                  className={`settings-menu__row${item.tone ? ` settings-menu__row--${item.tone}` : ""}`}
                  onClick={() => {
                    onClose();
                    item.onClick();
                  }}
                >
                  <span className="settings-menu__icon" aria-hidden="true">
                    {item.icon}
                  </span>
                  <span className="settings-menu__text">
                    <span className="settings-menu__title">{item.title}</span>
                    <span className="settings-menu__hint">{item.hint}</span>
                  </span>
                  <CaretRight size={16} className="settings-menu__chevron" aria-hidden="true" />
                </button>
              </li>
            ))}
          </ul>
          <button type="button" className="settings-menu__danger" onClick={onDelete} disabled={deleting}>
            <Trash size={18} aria-hidden="true" /> Удалить бота
          </button>
        </div>
      </div>
    </>
  );
}
