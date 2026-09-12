import { useEffect, useState } from "react";

import { apply, onSystemChange, readPref, writePref, type ThemePref } from "../theme";

const ORDER: ThemePref[] = ["system", "light", "dark"];

const LABEL: Record<ThemePref, string> = {
  system: "Тема: как в системе",
  light: "Тема: светлая",
  dark: "Тема: тёмная",
};

const GLYPH: Record<ThemePref, string> = {
  system: "🌓",
  light: "☀️",
  dark: "🌙",
};

/**
 * Three-state theme control: system → light → dark → system.
 *
 * Three rather than two on purpose. A plain light/dark switch forces a
 * choice the moment it is touched and then ignores the OS forever; keeping
 * "как в системе" as a reachable state means a viewer who flips their
 * laptop to dark at sunset gets it here too, without hunting for a reset.
 */
export function ThemeToggle({ className = "" }: { className?: string }) {
  const [pref, setPref] = useState<ThemePref>(readPref);

  // Re-apply on mount so the React tree and the inline bootstrap in
  // index.html can never disagree, and follow the OS while on "system".
  useEffect(() => {
    apply(pref);
    if (pref !== "system") return;
    return onSystemChange(() => apply("system"));
  }, [pref]);

  const next = ORDER[(ORDER.indexOf(pref) + 1) % ORDER.length];

  return (
    <button
      type="button"
      className={`theme-toggle ${className}`.trim()}
      onClick={() => {
        writePref(next);
        setPref(next);
      }}
      title={`${LABEL[pref]}. Нажми, чтобы переключить.`}
      aria-label={`${LABEL[pref]}. Переключить на: ${LABEL[next].replace("Тема: ", "")}`}
    >
      <span className="theme-toggle__glyph" aria-hidden="true">
        {GLYPH[pref]}
      </span>
      {pref === "system" && (
        <span className="theme-toggle__auto" aria-hidden="true">
          авто
        </span>
      )}
    </button>
  );
}
