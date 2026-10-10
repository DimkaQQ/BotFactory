import { ArrowBendDownRight, Bell, CreditCard, FilePdf, TelegramLogo } from "@phosphor-icons/react";

/** Маленькие рабочие образцы для витрины возможностей. Это те же элементы, что видит
 * покупатель (кнопки под сообщением, окошки времени), а не рисунок интерфейса. */

export function PayMini() {
  return (
    <div className="lp-mini lp-mini--pay" aria-hidden="true">
      <div className="lp-msg lp-msg--bot">
        Гайд «Старт», 1 990 ₸
        <span className="lp-msg__btns">
          <span className="lp-msg__btn lp-msg__btn--pay">
            <CreditCard size={16} /> Оплатить
          </span>
        </span>
      </div>
      <div className="lp-msg lp-msg--bot">
        Оплата подтверждена. Вот файл.
        <span className="lp-msg__file">
          <FilePdf size={22} />
          <span>
            <strong>start-guide.pdf</strong>
          </span>
        </span>
      </div>
    </div>
  );
}

const DAYS = [
  { d: "Пн", n: "12" },
  { d: "Вт", n: "13" },
  { d: "Ср", n: "14" },
  { d: "Чт", n: "15" },
];
const SLOTS = ["10:00", "11:30", "13:00", "15:30"];

export function SlotsMini() {
  return (
    <div className="lp-mini lp-mini--slots" aria-hidden="true">
      <div className="lp-slots__days">
        {DAYS.map((day, i) => (
          <span key={day.n} className={`lp-slots__day${i === 2 ? " is-on" : ""}`}>
            <small>{day.d}</small>
            {day.n}
          </span>
        ))}
      </div>
      <div className="lp-slots__times">
        {SLOTS.map((time, i) => (
          <span key={time} className={`lp-slots__time${i === 1 ? " is-on" : ""}${i === 3 ? " is-taken" : ""}`}>
            {time}
          </span>
        ))}
      </div>
    </div>
  );
}

export function ContactsMini() {
  return (
    <div className="lp-mini lp-mini--contacts" aria-hidden="true">
      <span className="lp-chip">
        <TelegramLogo size={15} weight="fill" /> Telegram
      </span>
      <span className="lp-chip">Телефон</span>
      <span className="lp-chip">История заказов</span>
      <span className="lp-chip">Записи</span>
    </div>
  );
}

export function BranchMini() {
  return (
    <div className="lp-mini lp-mini--branch" aria-hidden="true">
      <div className="lp-branch__src">Готовы начать?</div>
      <div className="lp-branch__row">
        <span className="lp-msg__btn">Да</span>
        <ArrowBendDownRight size={16} />
        <span className="lp-branch__to">Оплата</span>
      </div>
      <div className="lp-branch__row">
        <span className="lp-msg__btn">Позже</span>
        <ArrowBendDownRight size={16} />
        <span className="lp-branch__to">Напоминание</span>
      </div>
    </div>
  );
}

export function RemindMini() {
  return (
    <div className="lp-mini lp-mini--remind" aria-hidden="true">
      <span className="lp-chip lp-chip--accent">
        <Bell size={15} weight="fill" /> за сутки
      </span>
      <span className="lp-chip lp-chip--accent">
        <Bell size={15} weight="fill" /> за 2 часа
      </span>
      <span className="lp-chip">пауза между репликами</span>
      <span className="lp-chip">рассылка</span>
    </div>
  );
}
