/**
 * Light/dark theme for the standalone web constructor.
 *
 * The palette itself lives in index.css under `:root[data-theme="dark"]`,
 * a single block — not a `prefers-color-scheme` media query. That is
 * deliberate: the *resolved* theme is always written onto the root element
 * (by the inline script in index.html, before first paint, and by this
 * module afterwards), so the CSS never has to express the same palette
 * twice. There is no no-JS story to protect: the whole app is a React
 * bundle, so if scripts do not run there is nothing to paint anyway.
 *
 * Inside the Telegram Mini App this barely matters — Telegram injects its
 * own `--tg-theme-*` values, which win over every fallback in the palette.
 * What the resolved theme still buys us there is `color-scheme`, i.e.
 * scrollbars and form controls drawn to match, so we take Telegram's
 * `colorScheme` as the system signal when it is available.
 */

export type ThemePref = "system" | "light" | "dark";
export type Theme = "light" | "dark";

const STORAGE_KEY = "bf_theme";

/** Keep in sync with the inline bootstrap in index.html. */
function systemTheme(): Theme {
  const injected = window.Telegram?.WebApp?.colorScheme;
  if (injected === "light" || injected === "dark") return injected;
  return window.matchMedia?.("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}

export function readPref(): ThemePref {
  try {
    const stored = localStorage.getItem(STORAGE_KEY);
    if (stored === "light" || stored === "dark" || stored === "system") return stored;
  } catch {
    /* Safari in private mode throws on localStorage — fall through to system. */
  }
  return "system";
}

export function resolve(pref: ThemePref): Theme {
  return pref === "system" ? systemTheme() : pref;
}

export function apply(pref: ThemePref) {
  const theme = resolve(pref);
  document.documentElement.dataset.theme = theme;
  // The browser UI (address bar on Android, status bar on iOS) picks this up.
  const meta = document.querySelector('meta[name="theme-color"]');
  if (meta) meta.setAttribute("content", theme === "dark" ? "#0f0e16" : "#4338ca");
}

export function writePref(pref: ThemePref) {
  try {
    if (pref === "system") localStorage.removeItem(STORAGE_KEY);
    else localStorage.setItem(STORAGE_KEY, pref);
  } catch {
    /* Preference simply does not persist; the session still switches. */
  }
  apply(pref);
}

/**
 * Notify when the *system* theme changes, so a viewer on "system" follows
 * along without a reload. Returns an unsubscribe function.
 */
export function onSystemChange(cb: () => void): () => void {
  const mq = window.matchMedia?.("(prefers-color-scheme: dark)");
  mq?.addEventListener?.("change", cb);
  const webApp = window.Telegram?.WebApp;
  webApp?.onEvent?.("themeChanged", cb);
  return () => {
    mq?.removeEventListener?.("change", cb);
    webApp?.offEvent?.("themeChanged", cb);
  };
}
