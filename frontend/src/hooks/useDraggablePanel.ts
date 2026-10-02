import { useCallback, useEffect, useRef } from "react";

const STORAGE_KEY = "bf_panel_offset";
const DESKTOP = "(min-width: 960px)";
/** Сколько пикселей панели всегда остаётся на экране, чтобы её можно было
 * достать обратно, даже если утащить почти за край. */
const KEEP_VISIBLE = 48;
const EDGE = 8;

type Offset = { x: number; y: number };

function loadOffset(): Offset {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (raw) {
      const parsed = JSON.parse(raw);
      if (Number.isFinite(parsed?.x) && Number.isFinite(parsed?.y)) return { x: parsed.x, y: parsed.y };
    }
  } catch {
    /* приватный режим Safari бросает на localStorage — тогда без памяти */
  }
  return { x: 0, y: 0 };
}

function saveOffset(offset: Offset) {
  try {
    if (offset.x === 0 && offset.y === 0) localStorage.removeItem(STORAGE_KEY);
    else localStorage.setItem(STORAGE_KEY, JSON.stringify(offset));
  } catch {
    /* см. выше */
  }
}

/** Окно редактирования блока можно взять за заголовок и унести в другое
 * место. Работает только на десктопе: на телефоне панель — нижняя шторка, и
 * её жест — смахнуть вниз, а не таскать.
 *
 * Сдвиг ставится свойством `translate`, а не `transform`: у панели есть
 * анимация появления на `transform`, и вторая запись в то же свойство
 * дралась бы с ней. Положение запоминается между открытиями (общее для всех
 * панелей), двойной щелчок по заголовку возвращает на место. */
export function useDraggablePanel() {
  const panelRef = useRef<HTMLDivElement | null>(null);
  const offset = useRef<Offset>({ x: 0, y: 0 });
  const drag = useRef<{ px: number; py: number; ox: number; oy: number } | null>(null);

  const isDesktop = () => window.matchMedia(DESKTOP).matches;

  /** Держит панель в окне: ни целиком за край, ни заголовком под шапку. */
  const clamp = useCallback((want: Offset): Offset => {
    const el = panelRef.current;
    if (!el) return want;
    // offset*, а не getBoundingClientRect: это раскладка без transform и
    // translate, поэтому анимация появления и сам сдвиг не искажают границы.
    const baseLeft = el.offsetLeft;
    const baseTop = el.offsetTop;
    const minX = EDGE - baseLeft;
    const maxX = window.innerWidth - EDGE - el.offsetWidth - baseLeft;
    const minY = EDGE - baseTop;
    const maxY = window.innerHeight - KEEP_VISIBLE - baseTop;
    return {
      x: Math.min(Math.max(want.x, Math.min(minX, maxX)), Math.max(minX, maxX)),
      y: Math.min(Math.max(want.y, minY), Math.max(minY, maxY)),
    };
  }, []);

  const apply = useCallback((next: Offset) => {
    offset.current = next;
    const el = panelRef.current;
    if (el) el.style.translate = next.x || next.y ? `${next.x}px ${next.y}px` : "";
  }, []);

  useEffect(() => {
    function place() {
      if (!isDesktop()) {
        apply({ x: 0, y: 0 });
        return;
      }
      apply(clamp(offset.current));
    }
    offset.current = loadOffset();
    place();
    window.addEventListener("resize", place);
    return () => window.removeEventListener("resize", place);
  }, [apply, clamp]);

  const handleProps = {
    onPointerDown(e: React.PointerEvent<HTMLElement>) {
      if (!isDesktop() || e.button !== 0) return;
      // Кнопки в заголовке (удалить, закрыть) нажимаются, а не тащатся.
      if ((e.target as HTMLElement).closest("button, a, input, textarea, select")) return;
      drag.current = { px: e.clientX, py: e.clientY, ox: offset.current.x, oy: offset.current.y };
      e.currentTarget.setPointerCapture(e.pointerId);
      panelRef.current?.classList.add("edit-panel--dragging");
    },
    onPointerMove(e: React.PointerEvent<HTMLElement>) {
      const d = drag.current;
      if (!d) return;
      apply(clamp({ x: d.ox + e.clientX - d.px, y: d.oy + e.clientY - d.py }));
    },
    onPointerUp() {
      if (!drag.current) return;
      drag.current = null;
      panelRef.current?.classList.remove("edit-panel--dragging");
      saveOffset(offset.current);
    },
    onPointerCancel() {
      if (!drag.current) return;
      drag.current = null;
      panelRef.current?.classList.remove("edit-panel--dragging");
      saveOffset(offset.current);
    },
    onDoubleClick(e: React.MouseEvent<HTMLElement>) {
      if ((e.target as HTMLElement).closest("button, a, input, textarea, select")) return;
      apply({ x: 0, y: 0 });
      saveOffset({ x: 0, y: 0 });
    },
  };

  return { panelRef, handleProps };
}
