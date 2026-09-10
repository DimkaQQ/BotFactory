import { useEffect } from "react";

/** Close on Escape.
 *
 * Every overlay in the app trapped the key: a modal that can only be
 * dismissed by finding and hitting a small ✕ (or guessing that the backdrop
 * is clickable) reads as stuck, and Escape is the one thing everybody tries
 * first.
 */
export function useEscape(onEscape: () => void, active = true): void {
  useEffect(() => {
    if (!active) return;
    function handle(event: KeyboardEvent) {
      if (event.key === "Escape") {
        event.stopPropagation();
        onEscape();
      }
    }
    // Capture, so the innermost open overlay wins when two are stacked.
    window.addEventListener("keydown", handle, true);
    return () => window.removeEventListener("keydown", handle, true);
  }, [onEscape, active]);
}
