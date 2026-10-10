import { useState } from "react";

import type { BotBlock, PaymentProviderInfo } from "../../api/builderApi";
import { BLOCK_TYPE_BY_ID } from "../../blockTypes";
import { useDraggablePanel } from "../../hooks/useDraggablePanel";
import { useEscape } from "../../hooks/useEscape";
import { BroadcastButton } from "../BroadcastButton";
import { ButtonsEditor } from "../ButtonsEditor";
import { MediaEditor } from "../MediaEditor";
import { PaymentEditor } from "../PaymentEditor";
import { BookingEditor, ContactEditor } from "../BookingEditor";
import { DelayEditor } from "../DelayEditor";
import { PollEditor } from "../PollEditor";
import { BlockIcon } from "../../icons";
import { Trash, X } from "@phosphor-icons/react";

const PLACEHOLDER: Record<BotBlock["block_type"], string> = {
  welcome: "Привет! Рады видеть тебя здесь 👋",
  description: "Расскажи, чем занимается твой бизнес…",
  image: "Добавь ссылку на изображение и подпись",
  video: "Добавь ссылку на видео и подпись",
  buttons: "Текст перед кнопками (необязательно)",
  poll: "О чём спросим?",
  delivery: "Вот твой файл / ссылка / инструкция",
  payment: "",
  booking: "",
  contact: "",
  delay: "",
};

interface Props {
  block: BotBlock;
  botId: string;
  /** The bot's other blocks, ButtonsEditor names the block each button
   * leads to, instead of leaving "куда ведёт" an unanswered question. */
  blocks: BotBlock[];
  onChange: (content: BotBlock["content"]) => void;
  onDelete: () => void;
  onClose: () => void;
  /** Payment blocks need to know whether the bot can actually take money. */
  paymentProvider: string | null;
  paymentCurrencies: string[];
  /** The chosen provider's catalogue entry, drives the per-product fields
   * the payment block asks for. */
  paymentProviderInfo?: PaymentProviderInfo | null;
  paymentMissingFields?: string[];
  onOpenPaymentSettings: () => void;
  /** Broadcasting needs a token, which only a published bot has. */
  botPublished?: boolean;
  subscriptionsEnabled?: boolean;
}

/** The block's full editor, opened on the side (desktop) / as a bottom sheet
 * (mobile) when its node is clicked on the flow canvas, this is where
 * MediaEditor/PollEditor/ButtonsEditor now live, having moved out of the old
 * inline chat-bubble editor they were built for. */
export function BlockEditPanel({
  block,
  botId,
  blocks,
  onChange,
  onDelete,
  onClose: closeNow,
  paymentProvider,
  paymentCurrencies,
  paymentProviderInfo,
  paymentMissingFields,
  onOpenPaymentSettings,
  botPublished,
  subscriptionsEnabled,
}: Props) {
  // Закрытие с плавным уходом: окно не исчезает рывком.
  const [closing, setClosing] = useState(false);
  const onClose = () => {
    if (closing) return;
    setClosing(true);
    window.setTimeout(closeNow, 180);
  };
  useEscape(onClose);
  const { panelRef, handleProps: dragProps } = useDraggablePanel();
  const def = BLOCK_TYPE_BY_ID[block.block_type];
  const isMediaBlock = block.block_type === "image" || block.block_type === "video";
  const isPollBlock = block.block_type === "poll";
  const isDeliveryBlock = block.block_type === "delivery";
  // Not payment (an invoice has to belong to a conversation) and not
  // delay (it says nothing on its own).
  const canBroadcast = !["payment", "delay", "booking", "contact"].includes(block.block_type);
  const isButtonsBlock = block.block_type === "buttons";
  const isDelayBlock = block.block_type === "delay";
  const isPaymentBlock = block.block_type === "payment";

  return (
    <>
      <div className="sheet-backdrop edit-panel-backdrop" onClick={onClose} />
      <div className={`edit-panel${closing ? " edit-panel--closing" : ""}`} ref={panelRef}>
        <div
          className="edit-panel__header"
          title="Потяни, чтобы переместить окно (двойной щелчок, вернуть на место)"
          {...dragProps}
        >
          <span className={`edit-panel__icon block-card__icon--${def.accent}`} aria-hidden="true">
            <BlockIcon type={def.type} size={20} />
          </span>
          <span className="edit-panel__title">{def.label}</span>
          <button type="button" className="edit-panel__delete" aria-label="Удалить блок" onClick={onDelete}>
            <Trash size={18} aria-hidden="true" />
          </button>
          <button type="button" className="edit-panel__close" aria-label="Закрыть" onClick={onClose}>
            <X size={18} aria-hidden="true" />
          </button>
        </div>

        <div className="edit-panel__body">
          {isDelayBlock ? (
            <DelayEditor content={block.content} onChange={onChange} />
          ) : isPaymentBlock ? (
            <PaymentEditor
              blockId={block.id}
              content={block.content}
              provider={paymentProvider}
              currencies={paymentCurrencies}
              providerInfo={paymentProviderInfo}
              missingFields={paymentMissingFields}
              subscriptionsEnabled={subscriptionsEnabled}
              onChange={onChange}
              onOpenSettings={onOpenPaymentSettings}
            />
          ) : block.block_type === "booking" ? (
            <BookingEditor content={block.content} onChange={onChange} />
          ) : block.block_type === "contact" ? (
            <ContactEditor content={block.content} onChange={onChange} />
          ) : isMediaBlock ? (
            <MediaEditor kind={block.block_type as "image" | "video"} botId={botId} content={block.content} onChange={onChange} />
          ) : isDeliveryBlock ? (
            /* Выдача: это и есть товар: методичка, архив, запись. Текст плюс
               файл, а не текст вместо файла. */
            <>
              <p className="edit-panel__section-label">Сообщение покупателю</p>
              <textarea
                className="chat-bubble__textarea edit-panel__textarea"
                autoFocus
                value={block.content.text ?? ""}
                placeholder={PLACEHOLDER[block.block_type]}
                onChange={(e) => onChange({ ...block.content, text: e.target.value })}
                rows={4}
              />
              <p className="edit-panel__section-label">Файл (придёт вместе с сообщением)</p>
              <MediaEditor kind="file" botId={botId} content={block.content} onChange={onChange} />
            </>
          ) : isPollBlock ? (
            <PollEditor content={block.content} onChange={onChange} botId={botId} blockId={block.id} />
          ) : (
            <textarea
              className="chat-bubble__textarea edit-panel__textarea"
              autoFocus
              value={block.content.text ?? ""}
              placeholder={PLACEHOLDER[block.block_type]}
              onChange={(e) => onChange({ ...block.content, text: e.target.value })}
              rows={4}
            />
          )}

          {isButtonsBlock && (
            <div className="edit-panel__buttons">
              <p className="edit-panel__section-label">Кнопки</p>
              <ButtonsEditor content={block.content} onChange={onChange} blocks={blocks} />
            </div>
          )}

          {/* Any block that is just a message can also be sent to everyone —
              which is what «рассылка» on the landing page has always meant,
              and what the constructor had no way to do. */}
          {canBroadcast && botPublished && (
            <div className="edit-panel__buttons">
              <p className="edit-panel__section-label">Разослать этот блок</p>
              <BroadcastButton botId={botId} blockId={block.id} published={Boolean(botPublished)} />
            </div>
          )}

          {isDeliveryBlock && (
            <div className="edit-panel__buttons">
              {/* «Или» было неправдой: файл и доступ в чат в одном блоке
                  поддерживаются намеренно, и уходит и то и другое. Текст
                  говорил «или», код делал «и». */}
              <p className="edit-panel__section-label">И / или пусти в закрытую группу</p>
              <label className="buttons-editor__field">
                <span className="buttons-editor__field-label">ID группы или канала</span>
                <input
                  className="payment-editor__input"
                  placeholder="-1001234567890 или @mychannel"
                  value={block.content.group_chat_id ?? ""}
                  onChange={(e) => onChange({ ...block.content, group_chat_id: e.target.value.trim() })}
                />
              </label>
              <p className="app-hint">
                {block.content.group_chat_id ? (
                  <>
                    Бот выдаст каждому покупателю <b>свою одноразовую ссылку</b>: переслать её другу не выйдет.
                    Когда подписка закончится, бот уберёт человека из группы. Для этого добавь бота в группу
                    администратором с правами «Приглашать пользователей» и «Блокировать пользователей».
                  </>
                ) : (
                  <>
                    Оставь пустым, если выдаёшь файл или ссылку. Узнать ID: перешли любое сообщение из группы
                    боту @userinfobot.
                  </>
                )}
              </p>
            </div>
          )}
        </div>
      </div>
    </>
  );
}
