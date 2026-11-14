import { useEffect, useRef, useState } from "react";

import { FloatingWindow } from "./FloatingWindow";

interface ToolCall {
  name: string;
  arguments: Record<string, unknown>;
  ok: boolean;
}

interface Turn {
  role: "user" | "assistant";
  content: string;
  toolCalls?: ToolCall[];
  grounded?: boolean;
  error?: boolean;
}

const TOOL_LABEL: Record<string, string> = {
  get_ranking: "ranking",
  get_crossing: "karta przejazdu",
  compare_crossings: "porównanie przejazdów",
  list_districts: "lista dzielnic",
  get_method: "opis metody",
};

function describe(call: ToolCall): string {
  const args = Object.values(call.arguments).filter(
    (v) => v !== null && v !== "",
  );
  const label = TOOL_LABEL[call.name] ?? call.name;
  return args.length > 0 ? `${label}: ${args.join(", ")}` : label;
}

function ChatIcon() {
  return (
    <svg viewBox="0 0 24 24" width="26" height="26" aria-hidden="true">
      <path
        d="M4 5.5A2.5 2.5 0 0 1 6.5 3h11A2.5 2.5 0 0 1 20 5.5v8a2.5 2.5 0 0 1-2.5 2.5H11l-4.6 3.7A.6.6 0 0 1 5.4 19.2V16A2.5 2.5 0 0 1 4 13.5z"
        fill="currentColor"
      />
    </svg>
  );
}

interface Props {
  modelReady: boolean;
  /** Dzielnica do przykładowego pytania; pochodzi z wczytanych danych, nie z kodu. */
  exampleDistrict: string | null;
}

export function Assistant({ modelReady, exampleDistrict }: Props) {
  const [turns, setTurns] = useState<Turn[]>([]);
  const [draft, setDraft] = useState("");
  const [busy, setBusy] = useState(false);
  const [waited, setWaited] = useState(0);
  const [open, setOpen] = useState(false);
  const [unread, setUnread] = useState(false);
  const log = useRef<HTMLDivElement>(null);
  const input = useRef<HTMLInputElement>(null);
  const openRef = useRef(open);
  openRef.current = open;

  const suggestions = [
    "Które przejazdy mają najwyższy priorytet?",
    ...(exampleDistrict
      ? [`Pokaż ranking dla dzielnicy ${exampleDistrict}.`]
      : []),
    "Co oznacza wskaźnik RPS?",
  ];

  useEffect(() => {
    log.current?.scrollTo({
      top: log.current.scrollHeight,
      behavior: "smooth",
    });
  }, [turns, busy, open]);

  useEffect(() => {
    if (!open) return;
    setUnread(false);
    input.current?.focus();
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") setOpen(false);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open]);

  // Licznik sekund pokazuje, że lokalny model pracuje, a nie się zawiesił.
  useEffect(() => {
    if (!busy) return;
    setWaited(0);
    const timer = window.setInterval(() => setWaited((s) => s + 1), 1000);
    return () => window.clearInterval(timer);
  }, [busy]);

  async function send(question: string) {
    const message = question.trim();
    if (!message || busy) return;
    const history = turns
      .filter((t) => !t.error)
      .slice(-6)
      .map((t) => ({ role: t.role, content: t.content.slice(0, 2000) }));
    setTurns((current) => [...current, { role: "user", content: message }]);
    setDraft("");
    setBusy(true);
    let reply: Turn;
    try {
      const response = await fetch("/api/v1/assistant/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message, history }),
      });
      // Przy przekroczeniu czasu serwer pośredniczący zwraca stronę HTML, nie JSON.
      const body = await response.json().catch(() => null);
      if (response.status === 504 || response.status === 502) {
        throw new Error(
          "Lokalny model nie zdążył odpowiedzieć w wyznaczonym czasie. Spróbuj ponownie " +
            "albo zadaj węższe pytanie, np. o jedną dzielnicę.",
        );
      }
      if (!response.ok || !body) {
        throw new Error(
          body && typeof body.detail === "string" ? body.detail : "",
        );
      }
      reply = {
        role: "assistant",
        content: body.answer,
        toolCalls: body.tool_calls,
        grounded: body.grounded,
      };
    } catch (error) {
      const detail =
        error instanceof Error && error.message ? error.message : "";
      reply = {
        role: "assistant",
        error: true,
        content:
          detail ||
          "Nie udało się uzyskać odpowiedzi asystenta. Spróbuj ponownie.",
      };
    }
    setTurns((current) => [...current, reply]);
    setBusy(false);
    if (!openRef.current) setUnread(true);
  }

  return (
    <div className="chat">
      {open && (
        <FloatingWindow
          id="assistant"
          floating
          fixed
          className="chat-window"
          ariaLabel="Rozmowa z asystentem AI"
          title={
            <span className="chat-title">
              <span className="chat-avatar" aria-hidden="true">
                <ChatIcon />
              </span>
              <span>
                <strong>Asystent RailSafe</strong>
                <span className="chat-state">
                  <span
                    className={modelReady ? "dot dot-ok" : "dot dot-warn"}
                    aria-hidden="true"
                  />
                  {modelReady ? "lokalny model gotowy" : "model niedostępny"}
                </span>
              </span>
            </span>
          }
          onClose={() => setOpen(false)}
          closeLabel="Zamknij okno asystenta"
          defaultRect={(w, h) => {
            const width = Math.min(400, w - 32);
            const height = Math.min(560, h - 140);
            return { x: w - width - 16, y: h - height - 96, w: width, h: height };
          }}
          minWidth={300}
          minHeight={280}
        >
          <div className="chat-log" ref={log} aria-live="polite">
            {turns.length === 0 && (
              <div className="chat-empty">
                <p>
                  Zapytaj o ranking, wybrany przejazd albo metodę. Odpowiadam
                  wyłącznie na podstawie danych tej aplikacji.
                </p>
                <div className="suggestions">
                  {suggestions.map((text) => (
                    <button
                      key={text}
                      type="button"
                      className="chip"
                      disabled={!modelReady}
                      onClick={() => void send(text)}
                    >
                      {text}
                    </button>
                  ))}
                </div>
              </div>
            )}
            {turns.map((turn, index) => (
              <div
                key={index}
                className={
                  "bubble " +
                  (turn.role === "user" ? "bubble-user" : "bubble-ai") +
                  (turn.error ? " bubble-error" : "")
                }
              >
                <p>{turn.content}</p>
                {turn.role === "assistant" && !turn.error && (
                  <details className="bubble-meta">
                    <summary>
                      {turn.grounded
                        ? "✓ na podstawie danych"
                        : "! bez odczytu danych"}
                    </summary>
                    <p>
                      {turn.grounded
                        ? `Sprawdzone dane: ${(turn.toolCalls ?? [])
                            .filter((c) => c.ok)
                            .map(describe)
                            .join("; ")}.`
                        : "Model nie odczytał danych z aplikacji — traktuj tę odpowiedź ostrożnie."}
                    </p>
                  </details>
                )}
              </div>
            ))}
            {busy && (
              <div className="bubble bubble-ai typing" role="status">
                <span className="typing-dots" aria-hidden="true">
                  <i />
                  <i />
                  <i />
                </span>
                <span className="muted small">
                  Analizuję dane… {waited} s
                  {waited >= 20 ? " (lokalny model potrzebuje chwili)" : ""}
                </span>
              </div>
            )}
          </div>

          <form
            className="chat-form"
            onSubmit={(event) => {
              event.preventDefault();
              void send(draft);
            }}
          >
            <label htmlFor="assistant-input" className="sr-only">
              Pytanie do asystenta
            </label>
            <input
              id="assistant-input"
              ref={input}
              type="text"
              value={draft}
              maxLength={500}
              onChange={(event) => setDraft(event.target.value)}
              placeholder={
                modelReady ? "Napisz pytanie…" : "Model nie jest jeszcze gotowy"
              }
              disabled={busy}
            />
            <button
              type="submit"
              disabled={busy || draft.trim() === ""}
              aria-label="Wyślij pytanie"
            >
              ➤
            </button>
          </form>
          <p className="chat-foot">
            Model lokalny, może się mylić. Dane nie opuszczają komputera.
          </p>
        </FloatingWindow>
      )}

      <button
        type="button"
        className={"chat-fab" + (busy ? " chat-fab-busy" : "")}
        onClick={() => setOpen((value) => !value)}
        aria-expanded={open}
        aria-label={open ? "Zamknij asystenta AI" : "Otwórz asystenta AI"}
      >
        {open ? <span className="chat-fab-close">×</span> : <ChatIcon />}
        {unread && !open && (
          <span className="chat-unread" aria-label="Nowa odpowiedź" />
        )}
      </button>
    </div>
  );
}
