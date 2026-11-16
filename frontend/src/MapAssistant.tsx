import { useEffect, useRef, useState } from "react";
import type { Attachment, Reply } from "./chat/model";
import { validReply } from "./chat/model";
import { AnswerText } from "./chat/AnswerContent";
import { AssistantAvatar, CrossingSignal } from "./UiIcons";

interface Turn {
  role: "user" | "assistant";
  content: string;
  reply?: Reply;
}

/** In-memory only. The parent remounts this chat when the selected crossing changes. */
export function MapAssistant({
  crossing,
  modelReady,
}: {
  crossing?: Attachment;
  modelReady: boolean;
}) {
  const [open, setOpen] = useState(false);
  const [turns, setTurns] = useState<Turn[]>([]);
  const [draft, setDraft] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const request = useRef<AbortController | null>(null);
  const log = useRef<HTMLDivElement>(null);
  useEffect(() => () => request.current?.abort(), []);
  useEffect(() => {
    if (log.current) log.current.scrollTop = log.current.scrollHeight;
  }, [turns, busy, error, open]);
  async function send(text = draft) {
    if (!text.trim() || busy || !modelReady) return;
    const controller = new AbortController();
    request.current = controller;
    const question: Turn = { role: "user", content: text.trim() };
    const history = turns
      .slice(-8)
      .map(({ role, content }) => ({ role, content: content.slice(0, 2000) }));
    setTurns((prev) => [...prev, question]);
    setDraft("");
    setBusy(true);
    setError("");
    try {
      const response = await fetch("/api/v1/assistant/chat", {
        method: "POST",
        signal: controller.signal,
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          message: question.content,
          history,
          crossing_id: crossing?.id ?? null,
          analysis_crossing_ids:
            [...turns].reverse().find((t) => t.reply?.evidence?.map_ids.length)
              ?.reply?.evidence?.map_ids ?? [],
        }),
      });
      const body = await response.json().catch(() => null);
      if (!response.ok || !validReply(body))
        throw new Error("Nie udało się uzyskać odpowiedzi. Spróbuj ponownie.");
      if (!controller.signal.aborted)
        setTurns((prev) => [
          ...prev,
          { role: "assistant", content: body.answer, reply: body },
        ]);
    } catch (e) {
      if (!controller.signal.aborted)
        setError(e instanceof Error ? e.message : "Błąd połączenia.");
    } finally {
      if (request.current === controller) {
        request.current = null;
        setBusy(false);
      }
    }
  }
  function stop() {
    request.current?.abort();
    request.current = null;
    setBusy(false);
    setError("Zatrzymano odpowiedź. Możesz zadać kolejne pytanie.");
  }
  return (
    <div className="map-assistant">
      {open ? (
        <section
          className="map-chat-panel"
          aria-label="Tymczasowy czat na mapie"
        >
          <header>
            <AssistantAvatar />
            <div>
              <strong>Asystent AI</strong>
              <small>Czat tymczasowy</small>
            </div>
            <button
              type="button"
              className="icon-action"
              aria-label="Zwiń czat na mapie"
              title="Zwiń czat"
              onClick={() => setOpen(false)}
            >
              ×
            </button>
          </header>
          <p className="map-chat-context">
            {crossing
              ? `Przejazd: ${crossing.label}`
              : "Pytania o mapę i przejazdy w Warszawie"}
          </p>
          <div
            className="map-chat-log"
            ref={log}
            role="log"
            aria-label="Wiadomości czatu na mapie"
          >
            <p className="map-chat-greeting">
              {crossing
                ? "Czy mogę pomóc? Chętnie wyjaśnię wynik lub dostępne dane tego przejazdu."
                : "Dzień dobry! W czym mogę pomóc przy przeglądaniu mapy?"}
            </p>
            {!turns.length && (
              <div className="map-chat-suggestions">
                {[
                  "Wyjaśnij wynik RPS",
                  crossing
                    ? "Jakie dane są dostępne dla tego przejazdu?"
                    : "Jak korzystać z mapy?",
                  ...(crossing
                    ? [
                        "Jakie działania warto rozważyć, aby poprawić bezpieczeństwo?",
                      ]
                    : []),
                ].map((s) => (
                  <button
                    key={s}
                    disabled={!modelReady}
                    onClick={() => void send(s)}
                  >
                    {s}
                  </button>
                ))}
              </div>
            )}
            {turns.map((t, i) => (
              <div key={i} className={`map-chat-turn ${t.role}`}>
                <AnswerText text={t.content} />
                {t.reply && (
                  <details>
                    <summary>Podstawa odpowiedzi</summary>
                    <p>
                      {t.reply.grounded
                        ? "Odpowiedź na podstawie danych."
                        : "Odpowiedź bez odczytu danych."}
                    </p>
                    {t.reply.evidence?.sources.map((s, j) => (
                      <p key={j}>{s}</p>
                    ))}
                    {t.reply.disclaimer && <p>{t.reply.disclaimer}</p>}
                  </details>
                )}
              </div>
            ))}
            {busy && (
              <div className="map-chat-pending" role="status">
                <CrossingSignal /> Analizuję dane…
              </div>
            )}
            {error && (
              <p role="status" className="map-chat-error">
                {error}
              </p>
            )}
          </div>
          {!modelReady && (
            <p className="map-chat-error" role="status">
              Asystent jest chwilowo niedostępny.
            </p>
          )}
          <form
            onSubmit={(e) => {
              e.preventDefault();
              void send();
            }}
          >
            <input
              aria-label="Krótkie pytanie na mapie"
              placeholder="Zapytaj o ten przejazd…"
              value={draft}
              maxLength={500}
              onChange={(e) => setDraft(e.target.value)}
            />
            {busy ? (
              <button
                type="button"
                aria-label="Zatrzymaj odpowiedź na mapie"
                onClick={stop}
              >
                ■
              </button>
            ) : (
              <button
                type="submit"
                aria-label="Wyślij pytanie na mapie"
                disabled={!modelReady || !draft.trim()}
              >
                ↑
              </button>
            )}
          </form>
          <small className="map-chat-footnote">
            Historia znika po zamknięciu mapy lub zmianie przejazdu. AI może się
            mylić.
          </small>
        </section>
      ) : (
        <button
          className="map-chat-launcher"
          aria-label="Otwórz tymczasowy czat na mapie"
          onClick={() => setOpen(true)}
        >
          <AssistantAvatar />
          <span>
            <strong>Asystent AI</strong>
            <small>
              {crossing
                ? "Czy mogę pomóc przy tym przejeździe?"
                : "Masz krótkie pytanie?"}
            </small>
          </span>
        </button>
      )}
    </div>
  );
}
