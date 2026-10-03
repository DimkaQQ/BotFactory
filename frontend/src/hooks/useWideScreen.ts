import { useEffect, useState } from "react";

/** Same breakpoint the desktop shell uses (see App.css). On a wide canvas the
 * scenario reads left to right, so arrows leave a block on its right side and
 * enter on its left; on a phone it reads top to bottom. */
const QUERY = "(min-width: 960px)";

export function useWideScreen(): boolean {
  const [wide, setWide] = useState(() => (typeof window !== "undefined" ? window.matchMedia(QUERY).matches : false));
  useEffect(() => {
    const media = window.matchMedia(QUERY);
    const onChange = () => setWide(media.matches);
    media.addEventListener("change", onChange);
    return () => media.removeEventListener("change", onChange);
  }, []);
  return wide;
}
