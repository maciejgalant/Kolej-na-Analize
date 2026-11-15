/** Small native SVGs stay crisp at UI sizes and inherit the application's palette. */
function ActionIcon({ children }: { children: React.ReactNode }) {
  return (
    <svg
      viewBox="0 0 24 24"
      width="17"
      height="17"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.7"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      {children}
    </svg>
  );
}
export function EditIcon() {
  return (
    <ActionIcon>
      <path d="m15 4 5 5M4 20l5-1L20 8a2.1 2.1 0 0 0-5-5L4 14v6Z" />
    </ActionIcon>
  );
}
export function RestartIcon() {
  return (
    <ActionIcon>
      <path d="M20 10a8 8 0 1 0-2 8M20 4v6h-6" />
    </ActionIcon>
  );
}
export function PinIcon() {
  return (
    <ActionIcon>
      <path d="m9 3 6 0-1 6 4 4v2H6v-2l4-4-1-6ZM12 15v6" />
    </ActionIcon>
  );
}
export function TrashIcon() {
  return (
    <ActionIcon>
      <path d="M4 6h16M9 6V3h6v3M6 6l1 15h10l1-15M10 10v7m4-7v7" />
    </ActionIcon>
  );
}

export function MapIcon() {
  return (
    <svg
      viewBox="0 0 24 24"
      width="19"
      height="19"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.65"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <path d="m3 6 6-3 6 3 6-3v15l-6 3-6-3-6 3V6Z" />
      <path d="M9 3v15m6-12v15" />
    </svg>
  );
}

export function CopyIcon({ done = false }: { done?: boolean }) {
  return (
    <svg
      viewBox="0 0 24 24"
      width="17"
      height="17"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.7"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      {done ? (
        <path d="m5 12 4 4L19 6" />
      ) : (
        <>
          <rect x="8" y="8" width="12" height="12" rx="3" />
          <path d="M15 8V6a2 2 0 0 0-2-2H6a2 2 0 0 0-2 2v7a2 2 0 0 0 2 2h2" />
        </>
      )}
    </svg>
  );
}

export function AssistantAvatar() {
  return (
    <span className="assistant-avatar" aria-hidden="true">
      <svg viewBox="0 0 40 40" width="36" height="36" fill="none">
        <path
          d="M8 35c.7-7 5.1-10 12-10s11.3 3 12 10"
          fill="#cbdceb"
          stroke="#174a7e"
          strokeWidth="1.6"
          strokeLinecap="round"
        />
        <circle
          cx="20"
          cy="15.5"
          r="9.5"
          fill="#fff"
          stroke="#174a7e"
          strokeWidth="1.6"
        />
        <circle cx="16.6" cy="14.6" r="1.1" fill="#102b4e" />
        <circle cx="23.4" cy="14.6" r="1.1" fill="#102b4e" />
        <path
          d="M16.5 18.5c1.9 2.6 5.1 2.6 7 0"
          stroke="#d9570b"
          strokeWidth="1.7"
          strokeLinecap="round"
        />
        <path
          d="M10.5 12.5v7m19-7v7"
          stroke="#174a7e"
          strokeWidth="3"
          strokeLinecap="round"
        />
        <path
          d="M29.5 20c0 3-2 4-5.5 4"
          stroke="#174a7e"
          strokeWidth="1.5"
          strokeLinecap="round"
        />
        <circle cx="23" cy="24" r="1.7" fill="#d9570b" />
      </svg>
    </span>
  );
}

export function CrossingSignal() {
  return (
    <svg
      className="crossing-signal"
      data-testid="crossing-signal"
      viewBox="0 0 88 58"
      width="88"
      height="58"
      aria-hidden="true"
    >
      <path
        d="M32 28v24m-12 1h25"
        stroke="#8194a8"
        strokeWidth="4"
        strokeLinecap="round"
      />
      <rect x="8" y="5" width="48" height="25" rx="8" fill="#102b4e" />
      <circle cx="22" cy="17.5" r="8" fill="#273e57" />
      <circle cx="42" cy="17.5" r="8" fill="#273e57" />
      <circle
        className="crossing-light crossing-light-left"
        cx="22"
        cy="17.5"
        r="5.4"
        fill="#ff634e"
      />
      <circle
        className="crossing-light crossing-light-right"
        cx="42"
        cy="17.5"
        r="5.4"
        fill="#ff634e"
      />
      <path
        d="m35 42 43-18"
        stroke="#102b4e"
        strokeWidth="10"
        strokeLinecap="round"
      />
      <path
        d="m35 42 43-18"
        stroke="#d9570b"
        strokeWidth="6"
        strokeLinecap="round"
      />
      <path d="m46 34 2 6m10-11 2 6m10-11 2 6" stroke="#fff" strokeWidth="4" />
      <circle
        cx="35"
        cy="42"
        r="5"
        fill="#fff"
        stroke="#102b4e"
        strokeWidth="2"
      />
    </svg>
  );
}
