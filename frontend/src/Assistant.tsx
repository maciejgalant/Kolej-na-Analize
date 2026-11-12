import { useEffect, useRef, useState } from "react";

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

const SUGGESTIONS = [
  "Które przejazdy mają najwyższy priorytet?",
  "Pokaż ranking dla Targówka.",
  "Co oznacza wskaźnik RPS?",
];

function describe(call: ToolCall): string {
  const args = Object.values(call.arguments).filter((v) => v !== null && v !== "");
  const label = TOOL_LABEL[call.name] ?? call.name;
  return args.length > 0 ? `${label}: ${args.join(", ")}` : label;
}

export function Assistant({ modelReady }: { modelReady: boolean }) {
  const [turns, setTurns] = useState<Turn[]>([]);
  const [draft, setDraft] = useState("");
  const [busy, setBusy] = useState(false);
  const [open, setOpen] = useState(false);
  const log = useRef<HTMLDivElement>(null);

  useEffect(() => {
    log.current?.scrollTo({ top: log.current.scrollHeight });
  }, [turns, busy]);

  async function send(question: string) {
    const message = question.trim();
    if (!message || busy) return;
    const history = turns
      .filter((t) => !t.error)
      .slice(-6)
      .map((t) => ({ role: t.role, content: t.content.slice(0, 2000) }));
    setTurns((current) => [...current, { role: "user", content: message }]);
    setDraft("");
    setOpen(true);
    setBusy(true);
    try {
      const response = await fetch("/api/v1/assistant/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message, history }),
      });
      const body = await response.json();
      if (!response.ok) throw new Error(typeof body.detail === "string" ? body.detail : "");
      setTurns((current) => [
        ...current,
        {
          role: "assistant",
          content: body.answer,
          toolCalls: body.tool_calls,
          grounded: body.grounded,
        },
      ]);
    } catch (error) {
      const detail = error instanceof Error && error.message ? error.message : "";
      setTurns((current) => [
        ...current,
        {
          role: "assistant",
          error: true,
          content: detail || "Nie udało się uzyskać odpowiedzi asystenta. Spróbuj ponownie.",
        },
      ]);
    } finally {
      setBusy(false);
    }
  }

  return (
    <footer className="assistant-dock">
      {open && (
        <section className="assistant-panel" aria-label="Rozmowa z asystentem AI">
          <div className="assistant-head">
            <strong>Asystent AI</strong>
            <span className="muted small">
              lokalny model; odpowiada na podstawie danych aplikacji, może się mylić
            </span>
            <button type="button" className="link" onClick={() => setOpen(false)}>
              Zwiń
            </button>
          </div>
          <div className="assistant-log" ref={log} aria-live="polite">
            {turns.map((turn, index) => (
              <div
                key={index}
                className={
                  "bubble " +
                  (turn.role === "user" ? "bubble-user" : "bubble-ai") +
                  (turn.error ? " bubble-error" : "")
                }
              >
                <span className="bubble-who">{turn.role === "user" ? "Ty" : "Asystent"}</span>
                <p>{turn.content}</p>
                {turn.role === "assistant" && !turn.error && (
                  <p className="muted small">
                    {turn.grounded
                      ? `Sprawdzone dane: ${(turn.toolCalls ?? [])
                          .filter((c) => c.ok)
                          .map(describe)
                          .join("; ")}`
                      : "! Odpowiedź bez odczytu danych z aplikacji — traktuj ją ostrożnie."}
                  </p>
                )}
              </div>
            ))}
            {busy && (
              <p className="muted small" role="status">
                Asystent analizuje dane… Na komputerze bez karty graficznej może to potrwać
                minutę lub dłużej.
              </p>
            )}
          </div>
        </section>
      )}
      <form
        className="assistant"
        onSubmit={(event) => {
          event.preventDefault();
          void send(draft);
        }}
      >
        <label htmlFor="assistant-input">Asystent AI</label>
        <input
          id="assistant-input"
          type="text"
          value={draft}
          maxLength={500}
          onChange={(event) => setDraft(event.target.value)}
          onFocus={() => turns.length > 0 && setOpen(true)}
          placeholder={
            modelReady
              ? "Zapytaj o ranking, przejazd lub metodę…"
              : "Model nie jest jeszcze gotowy — sprawdź „Stan usług”"
          }
          disabled={busy}
        />
        <button type="submit" disabled={busy || draft.trim() === ""} aria-label="Wyślij pytanie">
          →
        </button>
      </form>
      {turns.length === 0 && (
        <div className="suggestions">
          {SUGGESTIONS.map((text) => (
            <button key={text} type="button" className="chip" onClick={() => void send(text)}>
              {text}
            </button>
          ))}
        </div>
      )}
    </footer>
  );
}
