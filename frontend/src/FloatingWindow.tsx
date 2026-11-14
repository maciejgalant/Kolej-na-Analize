import {
  type KeyboardEvent as ReactKeyboardEvent,
  type PointerEvent as ReactPointerEvent,
  type ReactNode,
  useCallback,
  useEffect,
  useLayoutEffect,
  useRef,
  useState,
} from "react";

/**
 * Okno nad mapą: przesuwanie za nagłówek, zmiana szerokości i wysokości za krawędzie
 * i narożniki, minimalizowanie do paska tytułu. Układ każdego okna jest zapamiętywany
 * w przeglądarce. Z klawiatury: fokus na nagłówku, strzałki przesuwają okno
 * (Shift — szybciej), Alt + strzałki zmieniają rozmiar.
 *
 * Na wąskim ekranie (`floating = false`) okno jest zwykłym panelem w kolumnie:
 * bez przesuwania, ale z minimalizowaniem.
 */

export interface Rect {
  x: number;
  y: number;
  w: number;
  h: number;
}

interface Stored extends Rect {
  minimized: boolean;
}

type Edge = "n" | "s" | "e" | "w" | "ne" | "nw" | "se" | "sw";

const STORAGE_PREFIX = "railsafe.window.";
export const RESET_EVENT = "railsafe:reset-windows";
const EDGES: Edge[] = ["n", "s", "e", "w", "ne", "nw", "se", "sw"];

let topZ = 10;

function load(id: string): Stored | null {
  try {
    const raw = window.localStorage.getItem(STORAGE_PREFIX + id);
    if (!raw) return null;
    const value = JSON.parse(raw) as Stored;
    return [value.x, value.y, value.w, value.h].every(Number.isFinite) ? value : null;
  } catch {
    return null;
  }
}

function save(id: string, value: Stored): void {
  try {
    window.localStorage.setItem(STORAGE_PREFIX + id, JSON.stringify(value));
  } catch {
    /* pamięć przeglądarki niedostępna: układ tylko do odświeżenia strony */
  }
}

export function resetWindowLayout(): void {
  try {
    Object.keys(window.localStorage)
      .filter((key) => key.startsWith(STORAGE_PREFIX))
      .forEach((key) => window.localStorage.removeItem(key));
  } catch {
    /* nic do usunięcia */
  }
  window.dispatchEvent(new Event(RESET_EVENT));
}

function clamp(rect: Rect, bounds: DOMRect, minW: number, minH: number): Rect {
  const limit = (value: number, low: number, high: number) =>
    Math.min(Math.max(value, low), Math.max(low, high));
  // Okno nie wychodzi poza obszar: dociśnięte do krawędzi zmniejsza się, aż do minimum.
  const x = limit(rect.x, 0, bounds.width - minW);
  const y = limit(rect.y, 0, bounds.height - minH);
  const w = limit(rect.w, minW, bounds.width - x);
  const h = limit(rect.h, minH, bounds.height - y);
  return { x, y, w, h };
}

export function FloatingWindow({
  id,
  title,
  titleExtra,
  defaultRect,
  floating,
  minWidth = 260,
  minHeight = 160,
  onClose,
  closeLabel = "Zamknij",
  fixed = false,
  className = "",
  ariaLabel,
  children,
}: {
  id: string;
  title: ReactNode;
  titleExtra?: ReactNode;
  /** Domyślne położenie względem obszaru okien (szerokość i wysokość obszaru). */
  defaultRect: (width: number, height: number) => Rect;
  floating: boolean;
  minWidth?: number;
  minHeight?: number;
  onClose?: () => void;
  closeLabel?: string;
  /** Pozycja względem okna przeglądarki zamiast obszaru mapy (np. asystent). */
  fixed?: boolean;
  className?: string;
  ariaLabel?: string;
  children: ReactNode;
}) {
  const node = useRef<HTMLElement>(null);
  const [rect, setRect] = useState<Rect | null>(null);
  const [minimized, setMinimized] = useState(() => load(id)?.minimized ?? false);
  const [z, setZ] = useState(() => ++topZ);
  const drag = useRef<{
    edge: Edge | "move";
    startX: number;
    startY: number;
    start: Rect;
  } | null>(null);

  const bounds = useCallback((): DOMRect | null => {
    if (fixed) return new DOMRect(0, 0, window.innerWidth, window.innerHeight);
    const parent = node.current?.offsetParent as HTMLElement | null;
    return parent ? parent.getBoundingClientRect() : null;
  }, [fixed]);

  const initial = useCallback(
    (ignoreStored = false): Rect | null => {
      const area = bounds();
      if (!area) return null;
      const stored = ignoreStored ? null : load(id);
      return clamp(stored ?? defaultRect(area.width, area.height), area, minWidth, minHeight);
    },
    [bounds, defaultRect, id, minHeight, minWidth],
  );

  useLayoutEffect(() => {
    if (floating) setRect(initial());
    // tylko przy przejściu w tryb okien
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [floating]);

  // przy zmianie rozmiaru przeglądarki okno nie może uciec poza obszar
  useEffect(() => {
    if (!floating) return;
    const onResize = () =>
      setRect((current) => {
        const area = bounds();
        return current && area ? clamp(current, area, minWidth, minHeight) : current;
      });
    const onReset = () => {
      setMinimized(false);
      setRect(initial(true));
    };
    window.addEventListener("resize", onResize);
    window.addEventListener(RESET_EVENT, onReset);
    return () => {
      window.removeEventListener("resize", onResize);
      window.removeEventListener(RESET_EVENT, onReset);
    };
  }, [bounds, floating, initial, minHeight, minWidth]);

  useEffect(() => {
    if (floating && rect) save(id, { ...rect, minimized });
  }, [floating, id, minimized, rect]);

  const front = () => setZ(++topZ);

  const startDrag = (edge: Edge | "move") => (event: ReactPointerEvent) => {
    if (!floating || !rect || event.button !== 0) return;
    if (edge === "move" && (event.target as HTMLElement).closest("button")) return;
    event.preventDefault();
    (event.currentTarget as HTMLElement).setPointerCapture(event.pointerId);
    drag.current = { edge, startX: event.clientX, startY: event.clientY, start: rect };
    front();
    document.body.classList.add(edge === "move" ? "is-dragging" : "is-resizing");
  };

  const onPointerMove = (event: ReactPointerEvent) => {
    const state = drag.current;
    const area = bounds();
    if (!state || !area) return;
    const dx = event.clientX - state.startX;
    const dy = event.clientY - state.startY;
    const s = state.start;
    const next = { ...s };
    if (state.edge === "move") {
      next.x = s.x + dx;
      next.y = s.y + dy;
    } else {
      if (state.edge.includes("e")) next.w = s.w + dx;
      if (state.edge.includes("s")) next.h = s.h + dy;
      if (state.edge.includes("w")) {
        next.w = Math.max(minWidth, s.w - dx);
        next.x = s.x + (s.w - next.w);
      }
      if (state.edge.includes("n")) {
        next.h = Math.max(minHeight, s.h - dy);
        next.y = s.y + (s.h - next.h);
      }
    }
    setRect(clamp(next, area, minWidth, minHeight));
  };

  const endDrag = (event: ReactPointerEvent) => {
    if (!drag.current) return;
    drag.current = null;
    (event.currentTarget as HTMLElement).releasePointerCapture?.(event.pointerId);
    document.body.classList.remove("is-dragging", "is-resizing");
  };

  const onHeaderKey = (event: ReactKeyboardEvent) => {
    if (!floating || !rect) return;
    const step = event.shiftKey ? 64 : 16;
    const moves: Record<string, [number, number]> = {
      ArrowLeft: [-step, 0],
      ArrowRight: [step, 0],
      ArrowUp: [0, -step],
      ArrowDown: [0, step],
    };
    const move = moves[event.key];
    const area = bounds();
    if (!move || !area) return;
    event.preventDefault();
    const [dx, dy] = move;
    const next = event.altKey
      ? { ...rect, w: rect.w + dx, h: rect.h + dy }
      : { ...rect, x: rect.x + dx, y: rect.y + dy };
    setRect(clamp(next, area, minWidth, minHeight));
  };

  const style =
    floating && rect
      ? {
          position: fixed ? ("fixed" as const) : ("absolute" as const),
          left: rect.x,
          top: rect.y,
          width: rect.w,
          height: minimized ? undefined : rect.h,
          zIndex: z,
        }
      : undefined;

  const classes = [
    "window",
    floating ? "window-floating" : "window-docked",
    minimized ? "window-minimized" : "",
    className,
  ]
    .filter(Boolean)
    .join(" ");

  return (
    <section
      ref={node}
      className={classes}
      style={style}
      aria-label={ariaLabel}
      onPointerDownCapture={floating ? front : undefined}
    >
      <header
        className="window-head"
        onPointerDown={startDrag("move")}
        onPointerMove={onPointerMove}
        onPointerUp={endDrag}
        onPointerCancel={endDrag}
        onDoubleClick={(e) => {
          if (!(e.target as HTMLElement).closest("button")) setMinimized((v) => !v);
        }}
        tabIndex={floating ? 0 : -1}
        onKeyDown={onHeaderKey}
        aria-roledescription={floating ? "przesuwane okno" : undefined}
        title={
          floating
            ? "Przeciągnij, aby przesunąć. Dwuklik zwija okno. Klawiatura: strzałki przesuwają, Alt + strzałki zmieniają rozmiar."
            : undefined
        }
      >
        {floating && (
          <span className="window-grip" aria-hidden="true">
            ⋮⋮
          </span>
        )}
        <span className="window-title">{title}</span>
        {titleExtra}
        <span className="window-actions">
          <button
            type="button"
            className="window-button"
            aria-expanded={!minimized}
            aria-label={minimized ? "Rozwiń okno" : "Zwiń okno"}
            title={minimized ? "Rozwiń" : "Zwiń"}
            onClick={() => setMinimized((v) => !v)}
          >
            <svg viewBox="0 0 16 16" width="14" height="14" aria-hidden="true">
              {minimized ? (
                <rect x="3" y="3" width="10" height="10" rx="1.5" fill="none" stroke="currentColor" strokeWidth="1.8" />
              ) : (
                <path d="M3 12h10" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
              )}
            </svg>
          </button>
          {onClose && (
            <button
              type="button"
              className="window-button"
              aria-label={closeLabel}
              title={closeLabel}
              onClick={onClose}
            >
              <svg viewBox="0 0 16 16" width="14" height="14" aria-hidden="true">
                <path d="M4 4l8 8M12 4l-8 8" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
              </svg>
            </button>
          )}
        </span>
      </header>
      <div className="window-body" hidden={minimized}>
        {children}
      </div>
      {floating &&
        !minimized &&
        EDGES.map((edge) => (
          <span
            key={edge}
            className={`window-resize window-resize-${edge}`}
            aria-hidden="true"
            onPointerDown={startDrag(edge)}
            onPointerMove={onPointerMove}
            onPointerUp={endDrag}
            onPointerCancel={endDrag}
          />
        ))}
    </section>
  );
}

/** Tryb okien tylko na szerokim ekranie; na wąskim panele układają się w kolumnie. */
export function useFloatingLayout(minWidth = 1100): boolean {
  const query = `(min-width: ${minWidth}px)`;
  const [matches, setMatches] = useState(() => window.matchMedia(query).matches);
  useEffect(() => {
    const media = window.matchMedia(query);
    const onChange = () => setMatches(media.matches);
    media.addEventListener("change", onChange);
    return () => media.removeEventListener("change", onChange);
  }, [query]);
  return matches;
}
