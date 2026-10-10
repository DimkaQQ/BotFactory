import { type RefObject, useEffect } from "react";

const FOCUSABLE =
  'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])';

let nextId = 0;

/** Окно как диалог для скринридера и клавиатуры: роль и подпись по заголовку, фокус внутрь при
 * открытии, Tab не уходит за окно, а при закрытии фокус возвращается туда, откуда пришли.
 * Заголовок ищется по классу `titleSelector` внутри окна. */
export function useDialogA11y(
  ref: RefObject<HTMLElement | null>,
  titleSelector = ".edit-panel__title, .sheet__title",
  active = true,
) {
  useEffect(() => {
    const el = ref.current;
    if (!active || !el) return;
    const previous = document.activeElement instanceof HTMLElement ? document.activeElement : null;

    el.setAttribute("role", "dialog");
    el.setAttribute("aria-modal", "true");
    const title = el.querySelector<HTMLElement>(titleSelector);
    if (title) {
      if (!title.id) title.id = `dialog-title-${++nextId}`;
      el.setAttribute("aria-labelledby", title.id);
    }
    if (!el.hasAttribute("tabindex")) el.setAttribute("tabindex", "-1");
    // Не отбираем фокус у поля, которое окно уже взяло само.
    if (!el.contains(document.activeElement)) el.focus({ preventScroll: true });

    function trap(event: KeyboardEvent) {
      if (event.key !== "Tab" || !el) return;
      const items = Array.from(el.querySelectorAll<HTMLElement>(FOCUSABLE)).filter((node) => node.offsetParent !== null);
      if (items.length === 0) {
        event.preventDefault();
        return;
      }
      const first = items[0];
      const last = items[items.length - 1];
      const active = document.activeElement;
      if (event.shiftKey && (active === first || active === el)) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && active === last) {
        event.preventDefault();
        first.focus();
      }
    }
    el.addEventListener("keydown", trap);
    return () => {
      el.removeEventListener("keydown", trap);
      if (previous && document.contains(previous)) previous.focus({ preventScroll: true });
    };
  }, [ref, titleSelector, active]);
}
