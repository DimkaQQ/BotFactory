import { CreditCard, FilePdf, Robot } from "@phosphor-icons/react";
import { motion, useReducedMotion } from "framer-motion";

/** Живое превью того, что видит покупатель: диалог с продажей от кнопки до выдачи.
 * Собрано из настоящей разметки чата (те же пузыри и кнопки, что в конструкторе),
 * поэтому это не картинка, а честный образец. Цифры в нём примерные. */
export function HeroMockup() {
  const reduce = useReducedMotion();
  const step = (i: number) => ({
    initial: reduce ? false : { opacity: 0, y: 14, scale: 0.98 },
    animate: { opacity: 1, y: 0, scale: 1 },
    transition: { duration: 0.5, delay: reduce ? 0 : 0.5 + i * 0.7, ease: [0.16, 1, 0.3, 1] as const },
  });

  return (
    <div className="lp-phone" role="img" aria-label="Пример диалога бота: покупатель выбирает товар, платит и получает файл">
      <div className="lp-phone__bar">
        <span className="lp-phone__avatar" aria-hidden="true">
          <Robot size={18} weight="fill" />
        </span>
        <span className="lp-phone__who">
          <strong>Ваш бот</strong>
          <small>бот</small>
        </span>
      </div>
      <div className="lp-phone__chat">
        <motion.div className="lp-msg lp-msg--bot" {...step(0)}>
          Здравствуйте! Что вас интересует?
          <span className="lp-msg__btns">
            <span className="lp-msg__btn">Купить гайд</span>
            <span className="lp-msg__btn">Записаться на консультацию</span>
          </span>
        </motion.div>
        <motion.div className="lp-msg lp-msg--user" {...step(1)}>
          Купить гайд
        </motion.div>
        <motion.div className="lp-msg lp-msg--bot" {...step(2)}>
          Гайд «Старт», 1 990 ₸. После оплаты файл придёт сюда.
          <span className="lp-msg__btns">
            <span className="lp-msg__btn lp-msg__btn--pay">
              <CreditCard size={16} aria-hidden="true" /> Оплатить
            </span>
          </span>
        </motion.div>
        <motion.div className="lp-msg lp-msg--bot" {...step(3)}>
          Оплата прошла, спасибо! Вот ваш гайд.
          <span className="lp-msg__file">
            <FilePdf size={22} weight="regular" aria-hidden="true" />
            <span>
              <strong>start-guide.pdf</strong>
              <small>2,4 МБ</small>
            </span>
          </span>
        </motion.div>
      </div>
      <p className="lp-phone__caption">Пример диалога, цифры условные</p>
    </div>
  );
}
