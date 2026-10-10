import { useEffect, useState } from "react";

import { apply, readPref, writePref, type ThemePref } from "../theme";
import { Moon, Sun } from "@phosphor-icons/react";


const LABEL: Record<ThemePref, string> = {
  light: "светлая",
  dark: "тёмная",
};

/** Винительный падеж для «включить …». */
const TURN_ON: Record<ThemePref, string> = {
  light: "светлую",
  dark: "тёмную",
};

/**
 * Переключатель темы из двух состояний: тёмная (по умолчанию) ↔ светлая.
 * Режима «как в системе» нет: он не срабатывал надёжно.
 */
export function ThemeToggle({ className = "" }: { className?: string }) {
  const [pref, setPref] = useState<ThemePref>(readPref);

  // Применяем при монтировании, чтобы React и скрипт в index.html не расходились.
  useEffect(() => {
    apply(pref);
  }, [pref]);

  const next: ThemePref = pref === "dark" ? "light" : "dark";

  return (
    <button
      type="button"
      className={`theme-toggle ${className}`.trim()}
      onClick={() => {
        writePref(next);
        setPref(next);
      }}
      title={`Тема: ${LABEL[pref]}. Нажми, чтобы включить ${TURN_ON[next]}.`}
      aria-label={`Тема: ${LABEL[pref]}. Включить ${TURN_ON[next]}`}
    >
      <span className="theme-toggle__glyph" aria-hidden="true">
        {pref === "dark" ? <Moon size={18} weight="regular" /> : <Sun size={18} weight="regular" />}
      </span>
    </button>
  );
}
