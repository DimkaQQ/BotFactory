import { useEffect, useState } from "react";

/**
 * Акция первых клиентов. Таймер считает до одного и того же момента для всех
 * (его задаёт сервер), а не «семь дней с момента твоего захода»: перезагрузка
 * страницы его не сбрасывает. Когда срок прошёл, плашка пропадает сама.
 */
export function LaunchOffer({ endsAt, regularPrice }: { endsAt: string; regularPrice: string }) {
  const end = Date.parse(endsAt);
  const [now, setNow] = useState(() => Date.now());

  useEffect(() => {
    const timer = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, []);

  if (!Number.isFinite(end) || end <= now) return null;

  const left = Math.floor((end - now) / 1000);
  const days = Math.floor(left / 86400);
  const hours = Math.floor((left % 86400) / 3600);
  const minutes = Math.floor((left % 3600) / 60);
  const seconds = left % 60;
  const pad = (n: number) => String(n).padStart(2, "0");

  return (
    <div className="landing-offer">
      <p className="landing-offer__title">Специальная цена для первых клиентов</p>
      <p className="landing-offer__text">
        Цена запуска действует до {new Date(end).toLocaleDateString("ru-RU", { day: "numeric", month: "long", year: "numeric" })}. После этого запуск
        будет стоить {regularPrice}.
      </p>
      <p className="landing-offer__timer" aria-label="Время до конца акции">
        <span>{days} дн</span> <span>{pad(hours)} ч</span> <span>{pad(minutes)} мин</span> <span>{pad(seconds)} с</span>
      </p>
    </div>
  );
}
