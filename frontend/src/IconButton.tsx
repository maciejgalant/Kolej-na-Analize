import { useEffect, useId, useRef, useState, type ButtonHTMLAttributes } from "react";
import { createPortal } from "react-dom";

/** Visible hints for pointer and keyboard users, including inside modal dialogs. */
export function IconButton({
  label, hint = label, children, className = "", ...props
}: ButtonHTMLAttributes<HTMLButtonElement> & { label: string; hint?: string }) {
  const id = useId();
  const ref = useRef<HTMLButtonElement>(null);
  const [position, setPosition] = useState<{ left: number; top: number; above: boolean } | null>(null);
  function show() {
    const rect = ref.current?.getBoundingClientRect();
    if (!rect) return;
    window.dispatchEvent(new CustomEvent("kolej-tooltip", { detail: id }));
    const above = rect.bottom > window.innerHeight - 85;
    setPosition({
      left: Math.max(128, Math.min(window.innerWidth - 128, rect.left + rect.width / 2)),
      top: above ? rect.top - 9 : rect.bottom + 9, above,
    });
  }
  useEffect(() => {
    const hide = () => setPosition(null);
    const replaceHint = (event: Event) => { if ((event as CustomEvent<string>).detail !== id) hide(); };
    window.addEventListener("kolej-tooltip", replaceHint);
    window.addEventListener("scroll", hide, true);
    window.addEventListener("resize", hide);
    return () => {
      window.removeEventListener("kolej-tooltip", replaceHint);
      window.removeEventListener("scroll", hide, true);
      window.removeEventListener("resize", hide);
    };
  }, [id]);
  return <>
    <button {...props} ref={ref} type={props.type ?? "button"}
      className={`ui-icon-button ${className}`} aria-label={label}
      aria-describedby={position ? id : undefined}
      onMouseEnter={show} onMouseLeave={() => setPosition(null)}
      onFocus={show} onBlur={() => setPosition(null)}
      onKeyDown={(event) => { if (event.key === "Escape") setPosition(null); props.onKeyDown?.(event); }}>
      {children}
    </button>
    {position && createPortal(
      <span id={id} role="tooltip" className={`ui-tooltip ${position.above ? "above" : ""}`}
        style={{ left: position.left, top: position.top }}>{hint}</span>,
      ref.current?.closest("dialog") ?? document.body,
    )}
  </>;
}
