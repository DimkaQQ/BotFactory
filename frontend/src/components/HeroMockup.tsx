/** A real, working preview — not a fake screenshot — built from the exact
 * same chat-bubble markup/CSS the constructor itself uses, so the promise
 * ("live chat preview") is demonstrated rather than just claimed. Bubbles
 * stagger in via the same --stagger/bubble-in mechanism as the real canvas.
 *
 * The chat card sells "this is what your client sees"; the small branch
 * strip underneath sells the other half of the pitch — "this is what you
 * build it with" — without pulling in React Flow just for a decoration. */
export function HeroMockup() {
  return (
    <div className="landing-mockup">
      <div className="landing-mockup__bar">
        <span className="landing-mockup__dot" />
        <span className="landing-mockup__dot" />
        <span className="landing-mockup__dot" />
        <span className="landing-mockup__title">@your_bot</span>
      </div>
      <div className="chat-canvas landing-mockup__canvas">
        <div className="chat-row" style={{ "--stagger": 0 } as React.CSSProperties}>
          <div className="chat-row__avatar" />
          <div className="chat-row__content">
            <div className="chat-bubble">
              <p className="chat-bubble__text">Привет! Рады видеть тебя здесь 👋</p>
            </div>
          </div>
        </div>
        <div className="chat-row" style={{ "--stagger": 1 } as React.CSSProperties}>
          <div className="chat-row__avatar" />
          <div className="chat-row__content">
            <div className="chat-bubble">
              <p className="chat-bubble__text">Расскажи, что внутри и кому это подойдёт.</p>
            </div>
          </div>
        </div>
        <div className="chat-row" style={{ "--stagger": 2 } as React.CSSProperties}>
          <div className="chat-row__avatar" />
          <div className="chat-row__content">
            <div className="chat-bubble">
              <div className="chat-bubble__media-thumb" aria-hidden="true">
                🖼️
              </div>
              <p className="chat-bubble__text">Как это выглядит</p>
            </div>
          </div>
        </div>
        <div className="chat-row" style={{ "--stagger": 3 } as React.CSSProperties}>
          <div className="chat-row__avatar">
            <span className="chat-avatar">🤖</span>
          </div>
          <div className="chat-row__content">
            <div className="chat-bubble">
              <p className="chat-bubble__text">Готов начать?</p>
            </div>
            <div className="chat-buttons">
              <div className="chat-buttons__preview">
                <span className="chat-buttons__pill">Да, интересно 🛒</span>
                <span className="chat-buttons__pill">Пока нет</span>
              </div>
            </div>
          </div>
        </div>
      </div>

      <div className="landing-mockup__branches" aria-hidden="true">
        <span className="landing-mockup__branch-source">🔘 Готов начать?</span>
        <span className="landing-mockup__branch">
          <span className="landing-mockup__branch-arrow">↳</span> «Да» → Оплата
        </span>
        <span className="landing-mockup__branch">
          <span className="landing-mockup__branch-arrow">↳</span> «Пока нет» → Напоминание через день
        </span>
      </div>
    </div>
  );
}
