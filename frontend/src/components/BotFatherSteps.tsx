/** How to get a bot token, in the order a person does it. Shown wherever we
 * ask for one: the paywall (before paying) and the publish form (after),
 * because somebody coming back the next day shouldn't have to remember. */
export function BotFatherSteps() {
  return (
    <details className="botfather-steps">
      <summary>Как получить токен бота: 4 шага</summary>
      <ol>
        <li>
          Открой{" "}
          <a href="https://t.me/BotFather" target="_blank" rel="noreferrer">
            @BotFather
          </a>{" "}
         : это официальный бот Telegram, и отправь ему <code>/newbot</code>.
        </li>
        <li>Придумай имя бота (любое, его увидят покупатели) и username, он должен заканчиваться на <code>bot</code>.</li>
        <li>
          BotFather пришлёт токен: строку вида <code>123456789:AAH…</code>. Скопируй её целиком и вставь сюда.
        </li>
        <li>
          Токен: это ключ от бота: никому его не показывай. Если пересоздашь токен в BotFather, старый перестанет
          работать, и бот замолчит, пока не вставишь новый.
        </li>
      </ol>
      <p className="botfather-steps__note">
        Если выбрать бота, который уже работает где-то ещё, он переедет к нам и перестанет отвечать на старом месте.
      </p>
    </details>
  );
}
