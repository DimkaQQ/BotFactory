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

/** Native-feeling confirm dialog — Telegram's own popup when available, browser confirm() as a fallback for dev outside Telegram. */
export function confirmDialog(message: string): Promise<boolean> {
  const webApp = window.Telegram?.WebApp;
  if (webApp?.showConfirm) {
    return new Promise((resolve) => webApp.showConfirm!(message, resolve));
  }
  return Promise.resolve(window.confirm(message));
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
        showConfirm?: (message: string, callback: (confirmed: boolean) => void) => void;
        BackButton: {
          isVisible: boolean;
          show: () => void;
          hide: () => void;
          onClick: (cb: () => void) => void;
          offClick: (cb: () => void) => void;
        };
        HapticFeedback?: {
          impactOccurred: (style: "light" | "medium" | "heavy" | "rigid" | "soft") => void;
          notificationOccurred: (type: "error" | "success" | "warning") => void;
        };
      };
    };
  }
}
