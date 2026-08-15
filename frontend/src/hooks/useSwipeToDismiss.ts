import { useRef } from "react";

/** Drag the sheet's handle down to dismiss it — the gesture people expect
 * from a native bottom sheet. Wired to .sheet__handle only, which is
 * display:none on the desktop centered-modal layout, so this is
 * automatically mobile-only with no risk of fighting that layout's own
 * CSS transform for centering. Pointer events (not framer-motion) — the
 * sheet is plain CSS-animated, and mixing a second transform-driving
 * library in on top would be the same class of bug ChatBubble/dnd-kit
 * has already been bitten by once. */
export function useSwipeToDismiss(onDismiss: () => void) {
  const sheetRef = useRef<HTMLDivElement | null>(null);
  const startY = useRef(0);
  const dragging = useRef(false);

  function onPointerDown(e: React.PointerEvent<HTMLDivElement>) {
    dragging.current = true;
    startY.current = e.clientY;
    if (sheetRef.current) sheetRef.current.style.transition = "none";
    e.currentTarget.setPointerCapture(e.pointerId);
  }

  function onPointerMove(e: React.PointerEvent<HTMLDivElement>) {
    if (!dragging.current || !sheetRef.current) return;
    const delta = Math.max(0, e.clientY - startY.current);
    sheetRef.current.style.transform = `translateY(${delta}px)`;
  }

  function endDrag(e: React.PointerEvent<HTMLDivElement>) {
    if (!dragging.current || !sheetRef.current) return;
    dragging.current = false;
    const delta = e.clientY - startY.current;
    sheetRef.current.style.transition = "";
    if (delta > 90) {
      sheetRef.current.style.transform = "translateY(100%)";
      setTimeout(onDismiss, 180);
    } else {
      sheetRef.current.style.transform = "";
    }
  }

  return {
    sheetRef,
    handleProps: {
      onPointerDown,
      onPointerMove,
      onPointerUp: endDrag,
      onPointerCancel: endDrag,
    },
  };
}
