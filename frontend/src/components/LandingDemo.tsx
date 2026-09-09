import { useCallback, useEffect, useRef, useState } from "react";

interface DemoChoice {
  label: string;
  to: string;
}

interface DemoNode {
  text: string;
  next?: string;
  choices?: DemoChoice[];
}

/** A tiny branching script — the same shape the real editor produces
 * (a chain of messages, a buttons block that forks, branches that end). */
const SCRIPT: Record<string, DemoNode> = {
  start: { text: "Привет! Я бот кофейни «Сова» ☕", next: "ask" },
  ask: {
    text: "Что показать?",
    choices: [
      { label: "Меню и цены", to: "menu" },
      { label: "Забронировать стол", to: "book" },
    ],
  },
  menu: { text: "Латте — 890 ₸, раф — 1 200 ₸, десерты — от 1 500 ₸", next: "offer" },
  offer: {
    text: "Забронировать столик?",
    choices: [
      { label: "Да, давай", to: "book" },
      { label: "Не сейчас", to: "bye" },
    ],
  },
  book: { text: "Готово! Стол у окна ждёт ✅ Напомню за час до брони." },
  bye: { text: "Ок! Загляни, когда будет настроение 🙌" },
};

const TYPING_MS = 950;
const AUTO_PICK_MS = 3200;
const RESTART_MS = 3400;

interface DemoMessage {
  id: number;
  from: "bot" | "user";
  text: string;
}

/** The landing's "watch it play out" demo: the script above plays itself on
 * a loop, but every button is live — tap one and the demo follows *your*
 * branch instead of its own. Which is exactly the pitch of the section it
 * sits in, so it's a working demo rather than a screenshot of one.
 *
 * It only runs while scrolled into view (IntersectionObserver) — no point
 * looping timers for a section nobody is looking at. */
export function LandingDemo() {
  const [messages, setMessages] = useState<DemoMessage[]>([]);
  const [pending, setPending] = useState<string | null>("start");
  const [awaiting, setAwaiting] = useState<string | null>(null);
  const [finished, setFinished] = useState(false);
  const [typing, setTyping] = useState(false);
  const [visible, setVisible] = useState(false);

  const rootRef = useRef<HTMLDivElement | null>(null);
  const bodyRef = useRef<HTMLDivElement | null>(null);
  const seq = useRef(0);
  // Alternates which branch the demo picks for itself, so a visitor who
  // watches two loops sees two different paths instead of the same one.
  const loop = useRef(0);

  useEffect(() => {
    const el = rootRef.current;
    if (!el) return;
    const observer = new IntersectionObserver(([entry]) => setVisible(entry.isIntersecting), { threshold: 0.4 });
    observer.observe(el);
    return () => observer.disconnect();
  }, []);

  // Type out the pending node, then either fork, continue, or finish.
  useEffect(() => {
    if (!visible || !pending) return;
    const node = SCRIPT[pending];
    if (!node) return;

    setTyping(true);
    const timer = setTimeout(() => {
      setTyping(false);
      setMessages((prev) => [...prev, { id: seq.current++, from: "bot", text: node.text }]);
      if (node.choices) {
        setAwaiting(pending);
        setPending(null);
      } else if (node.next) {
        setPending(node.next);
      } else {
        setPending(null);
        setFinished(true);
      }
    }, TYPING_MS);

    return () => clearTimeout(timer);
  }, [pending, visible]);

  const pick = useCallback((choice: DemoChoice) => {
    setAwaiting(null);
    setMessages((prev) => [...prev, { id: seq.current++, from: "user", text: choice.label }]);
    setPending(choice.to);
  }, []);

  // Nobody tapped — the demo picks for itself so the loop keeps moving.
  useEffect(() => {
    if (!visible || !awaiting) return;
    const choices = SCRIPT[awaiting].choices!;
    const timer = setTimeout(() => pick(choices[loop.current % choices.length]), AUTO_PICK_MS);
    return () => clearTimeout(timer);
  }, [awaiting, visible, pick]);

  useEffect(() => {
    if (!visible || !finished) return;
    const timer = setTimeout(() => {
      loop.current += 1;
      setMessages([]);
      setFinished(false);
      setPending("start");
    }, RESTART_MS);
    return () => clearTimeout(timer);
  }, [finished, visible]);

  useEffect(() => {
    bodyRef.current?.scrollTo({ top: bodyRef.current.scrollHeight, behavior: "smooth" });
  }, [messages, typing, awaiting]);

  const choices = awaiting ? SCRIPT[awaiting].choices ?? [] : [];

  return (
    <div className="demo-chat" ref={rootRef}>
      <div className="demo-chat__bar">
        <span className="demo-chat__avatar" aria-hidden="true">
          ☕
        </span>
        <span className="demo-chat__name">
          Кофейня «Сова»
          <span className="demo-chat__tag">bot</span>
        </span>
        <span className="demo-chat__live">живое демо</span>
      </div>

      <div className="demo-chat__body" ref={bodyRef}>
        {messages.map((message) => (
          <div key={message.id} className={`demo-msg demo-msg--${message.from}`}>
            {message.text}
          </div>
        ))}

        {typing && (
          <div className="demo-msg demo-msg--bot demo-msg--typing" aria-label="печатает">
            <span />
            <span />
            <span />
          </div>
        )}

        {choices.length > 0 && (
          <div className="demo-chat__choices">
            {choices.map((choice) => (
              <button key={choice.to} type="button" className="demo-chat__choice" onClick={() => pick(choice)}>
                {choice.label}
              </button>
            ))}
          </div>
        )}
      </div>

      <p className="demo-chat__hint">
        {choices.length > 0 ? "👆 Нажми на кнопку — сценарий пойдёт по твоей ветке" : "Демо крутится само — но кнопки живые"}
      </p>
    </div>
  );
}
