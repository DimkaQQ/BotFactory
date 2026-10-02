import { useEffect, useState } from "react";

import { type PublicConfig, builderApi } from "../api/builderApi";

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
        </div>
      )}
      <div className="landing-footer__row landing-footer__links">
        {config.support_telegram && (
          <a href={`https://t.me/${config.support_telegram}`} target="_blank" rel="noreferrer">
            Поддержка: @{config.support_telegram}
          </a>
        )}
        {config.support_email && <a href={`mailto:${config.support_email}`}>{config.support_email}</a>}
        {/* Пока реквизиты не заполнены, документов нет — и ссылки на них не
            показываются: пустая «Оферта» хуже её отсутствия. */}
        {(config.legal_docs ?? []).map((doc) => (
          <a key={doc.path} href={doc.path} target="_blank" rel="noreferrer">
            {doc.title}
          </a>
        ))}
      </div>
      {!compact && (
        <p className="landing-footer__note">
          Деньги покупателей идут напрямую на счёт владельца бота — сервис их не принимает и не хранит.
          Bot Factory — независимый сервис и не связан с Telegram Messenger Inc.
        </p>
      )}
    </footer>
  );
}
