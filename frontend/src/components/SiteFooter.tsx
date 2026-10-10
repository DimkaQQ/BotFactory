import { useEffect, useState } from "react";

import { type PublicConfig, builderApi } from "../api/builderApi";
import { ChatCircleDots } from "@phosphor-icons/react";

interface Props {
  /** Уже загруженный конфиг — у лендинга он есть, лишний запрос ни к чему. */
  config?: PublicConfig | null;
  /** Короткий вариант: одна строка со ссылками, без обещаний про деньги. */
  compact?: boolean;
}

/** Кто мы, куда писать и по каким правилам.
 *
 * До этого ни одного из трёх ответов в продукте не было — ни на странице,
 * где просят денег, ни внутри кабинета. Человек, у которого бот перестал
 * продавать в субботу, не мог написать никому.
 */
export function SiteFooter({ config: given, compact = false }: Props) {
  const [config, setConfig] = useState<PublicConfig | null>(given ?? null);

  useEffect(() => {
    if (given) {
      setConfig(given);
      return;
    }
    // Не показать подвал — не повод ронять экран: тихо остаёмся ни с чем.
    builderApi.getPublicConfig().then(setConfig).catch(() => undefined);
  }, [given]);

  if (!config) return null;

  return (
    <footer className={`landing-footer${compact ? " landing-footer--compact" : ""}`}>
      {!compact && (
        <div className="landing-footer__row">
          <span className="landing-footer__brand">Bot Factory</span>
          {config.legal_name && <span className="landing-footer__legal">{config.legal_name}</span>}
          {config.payment_agent && (
            <span className="landing-footer__legal">Оплату принимает платёжный агент {config.payment_agent}</span>
          )}
        </div>
      )}
      {/* Поддержка — единственное, что здесь должно бросаться в глаза: когда
          у человека что-то не работает, он ищет именно её. Документы нужны (их
          требуют платёжные системы и закон), но читают их единицы — поэтому они
          ниже, мелко и приглушённо, а не в одном ряду с кнопкой. */}
      {(config.support_telegram || config.support_email) && (
        <div className="support-cta">
          {config.support_telegram && (
            <a
              className="support-button"
              href={`https://t.me/${config.support_telegram}`}
              target="_blank"
              rel="noreferrer"
            >
              <span className="support-button__icon" aria-hidden="true">
                <ChatCircleDots size={20} aria-hidden="true" />
              </span>
              <span className="support-button__text">
                <span className="support-button__title">Поддержка</span>
                <span className="support-button__sub">Ответим в Telegram</span>
              </span>
              <span className="support-button__arrow" aria-hidden="true">
                →
              </span>
            </a>
          )}
          {config.support_email && (
            <a className="support-email" href={`mailto:${config.support_email}`}>
              {config.support_email}
            </a>
          )}
        </div>
      )}
      {/* Пока реквизиты не заполнены, документов нет — и ссылок на них не
          показываются: пустая «Оферта» хуже её отсутствия. */}
      {(config.legal_docs ?? []).length > 0 && (
        <nav className="landing-footer__docs" aria-label="Юридические документы">
          {(config.legal_docs ?? []).map((doc) => (
            <a key={doc.path} href={doc.path} target="_blank" rel="noreferrer">
              {doc.title}
            </a>
          ))}
          <a href="/legal/?lang=en" target="_blank" rel="noreferrer">
            English
          </a>
        </nav>
      )}
      {/* Жалоба на бота не зависит от реквизитов: подать её можно всегда. */}
      <nav className="landing-footer__docs" aria-label="Жалобы">
        <a href="/report" target="_blank" rel="noreferrer">
          Пожаловаться на бота
        </a>
      </nav>
      {!compact && (
        <p className="landing-footer__note">
          Деньги покупателей идут напрямую на счёт владельца бота. Сервис их не принимает и не хранит.
          Bot Factory независимый сервис и не связан с Telegram Messenger Inc.
        </p>
      )}
    </footer>
  );
}
