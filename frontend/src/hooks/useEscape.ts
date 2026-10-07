import { useEffect, useRef } from "react";

/** Открытые окна в порядке открытия: последнее — самое верхнее. */
const stack: Array<{ current: () => void }> = [];
let listening = false;

function handle(event: KeyboardEvent) {
  if (event.key !== "Escape") return;
  const top = stack[stack.length - 1];
  if (!top) return;
  // Одно нажатие закрывает одно, самое верхнее окно. Раньше каждое окно слушало клавишу само,
  // и Escape закрывал сразу все открытые одно над другим.
  event.stopPropagation();
  top.current();
}

function attach() {
  if (listening) return;
  window.addEventListener("keydown", handle, true);
  listening = true;
}

function detach() {
  if (!listening || stack.length > 0) return;
  window.removeEventListener("keydown", handle, true);
  listening = false;
}

/** Close on Escape.
 *
 * Every overlay in the app traps the key: a modal that can only be
 * dismissed by finding and hitting a small ✕ (or guessing that the backdrop
 * is clickable) reads as stuck, and Escape is the one thing everybody tries
 * first. Закрывается только самое верхнее из открытых окон.
 */
export function useEscape(onEscape: () => void, active = true): void {
  // Обработчик меняется при каждом рендере, а место в стопке — нет: иначе окно, которое
  // перерисовалось, «всплывало» бы наверх.
  const entry = useRef<{ current: () => void }>({ current: onEscape });
  entry.current.current = onEscape;

  useEffect(() => {
    if (!active) return;
    const item = entry.current;
    stack.push(item);
    attach();
    return () => {
      const index = stack.lastIndexOf(item);
      if (index !== -1) stack.splice(index, 1);
      detach();
    };
  }, [active]);
}
