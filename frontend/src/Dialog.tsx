import { useEffect, useId, useRef } from "react";

interface Props {
  title: string;
  open: boolean;
  onClose: () => void;
  children: React.ReactNode;
  className?: string;
}

/** Okno modalne na natywnym <dialog>: fokus, Esc i tło obsługuje przeglądarka. */
export function Dialog({
  title,
  open,
  onClose,
  children,
  className = "",
}: Props) {
  const ref = useRef<HTMLDialogElement>(null);
  const titleId = useId();
  useEffect(() => {
    const previous = document.activeElement;
    return () => {
      queueMicrotask(() => {
        if (
          !ref.current?.isConnected &&
          previous instanceof HTMLElement &&
          previous.isConnected &&
          document.activeElement === document.body
        )
          previous.focus();
      });
    };
  }, []);

  useEffect(() => {
    const node = ref.current;
    if (!node) return;
    if (open && !node.open) node.showModal();
    if (!open && node.open) node.close();
  }, [open]);

  return (
    <dialog
      ref={ref}
      className={`dialog ${className}`}
      aria-labelledby={titleId}
      onCancel={(event) => {
        event.preventDefault();
        onClose();
      }}
      onClose={onClose}
      onClick={(event) => {
        // Kliknięcie w tło (sam element dialog, nie jego zawartość) zamyka okno.
        if (event.target === ref.current) onClose();
      }}
    >
      <div className="dialog-body">
        <header className="dialog-head">
          <h2 id={titleId}>{title}</h2>
          <button
            type="button"
            className="icon-button"
            onClick={onClose}
            aria-label="Zamknij okno"
          >
            ×
          </button>
        </header>
        {children}
      </div>
    </dialog>
  );
}
