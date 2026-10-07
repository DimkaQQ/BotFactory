/** Поведение прокрутки с учётом «уменьшить движение»: CSS-правило на `behavior: "smooth"` из JS не влияет. */
export function scrollBehavior(): ScrollBehavior {
  return typeof window !== "undefined" && window.matchMedia?.("(prefers-reduced-motion: reduce)").matches
    ? "auto"
    : "smooth";
}
