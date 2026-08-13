import { useEffect, useMemo, useState } from "react";

export interface TelegramUser {
  id: number;
  first_name: string;
  last_name?: string;
  username?: string;
}

/**
 * Thin wrapper around `window.Telegram.WebApp`. Exposes the raw `initData`
 * string (sent to the backend for signature validation on every request)
 * and the unsafe, client-side-only `initDataUnsafe.user` (fine to use for
 * display purposes like a greeting, never for authorization).
 */
export function useTelegramWebApp() {
  const webApp = useMemo(() => window.Telegram?.WebApp, []);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    if (!webApp) {
      setReady(true); // allow running outside Telegram (e.g. plain browser) for dev
      return;
    }
    webApp.ready();
    webApp.expand();
    setReady(true);
  }, [webApp]);

  const initData = webApp?.initData ?? "";
  const user = (webApp?.initDataUnsafe?.user as TelegramUser | undefined) ?? undefined;

  return { webApp, ready, initData, user };
}

declare global {
  interface Window {
    Telegram?: {
      WebApp: {
        initData: string;
        initDataUnsafe: {
          user?: TelegramUser;
        };
        ready: () => void;
        expand: () => void;
        close: () => void;
        MainButton: {
          text: string;
          show: () => void;
          hide: () => void;
          onClick: (cb: () => void) => void;
          offClick: (cb: () => void) => void;
        };
        showAlert?: (message: string) => void;
      };
    };
  }
}
