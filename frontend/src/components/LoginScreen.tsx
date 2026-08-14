import { useEffect, useRef, useState } from "react";

import { type TelegramLoginPayload, ApiError, builderApi, configureSessionAuth } from "../api/builderApi";

interface Props {
  onLoggedIn: () => void;
}

declare global {
  interface Window {
    onTelegramAuth?: (user: TelegramLoginPayload) => void;
  }
}

/** Standalone web entry point (outside the Telegram Mini App) — logs in via
 * the Telegram Login Widget, which hands us a signed payload we exchange
 * for a session token (see app/routers/auth.py). */
export function LoginScreen({ onLoggedIn }: Props) {
  const widgetRef = useRef<HTMLDivElement | null>(null);
  const [botUsername, setBotUsername] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    builderApi
      .getPublicConfig()
      .then((cfg) => setBotUsername(cfg.meta_bot_username || null))
      .catch(() => setError("Не удалось связаться с сервером"));
  }, []);

  useEffect(() => {
    if (!botUsername || !widgetRef.current) return;

    window.onTelegramAuth = async (user) => {
      setLoading(true);
      setError(null);
      try {
        const { token } = await builderApi.loginWithTelegram(user);
        configureSessionAuth(token);
        onLoggedIn();
      } catch (err) {
        setError(err instanceof ApiError ? err.message : "Не удалось войти");
        setLoading(false);
      }
    };

    const script = document.createElement("script");
    script.src = "https://telegram.org/js/telegram-widget.js?22";
    script.async = true;
    script.setAttribute("data-telegram-login", botUsername);
    script.setAttribute("data-size", "large");
    script.setAttribute("data-radius", "12");
    script.setAttribute("data-onauth", "onTelegramAuth(user)");
    script.setAttribute("data-request-access", "write");
    widgetRef.current.innerHTML = "";
    widgetRef.current.appendChild(script);

    return () => {
      delete window.onTelegramAuth;
    };
  }, [botUsername, onLoggedIn]);

  return (
    <div className="screen screen--login">
      <div className="login-hero">
        <div className="login-hero__pitch">
          <div className="state-icon">🏭</div>
          <h1 className="login-title">Bot Factory</h1>
          <p className="login-hero__lead">Собирай Telegram-ботов визуально — без кода. Пиши сообщения прямо в
            превью чата, перетаскивай порядок, публикуй за пару минут.</p>
          <ul className="login-hero__features">
            <li>👋 Готовые шаблоны — товар, подписка, запись, рассылка</li>
            <li>💬 Редактор выглядит как настоящая переписка</li>
            <li>🤖 Управляй несколькими ботами из одного аккаунта</li>
          </ul>
        </div>

        <div className="login-card">
          <p className="login-card__title">Войти через Telegram</p>
          {loading ? (
            <p className="app-hint">Входим…</p>
          ) : botUsername ? (
            <div ref={widgetRef} className="login-widget" />
          ) : !error ? (
            <p className="app-hint">Загрузка…</p>
          ) : null}
          {error && <p className="publish-form__error">{error}</p>}
        </div>
      </div>
    </div>
  );
}
