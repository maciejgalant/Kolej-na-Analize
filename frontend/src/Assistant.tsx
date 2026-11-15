import { useEffect, useRef, useState } from "react";
import { AnswerContent, AnswerText } from "./chat/AnswerContent";
import { activePath, branchLeaf } from "./chat/model";
import type { Attachment, Conversation, Message } from "./chat/model";
interface Props {
  conversation: Conversation;
  modelReady: boolean;
  onDraft: (draft: string) => void;
  onAttachment: (a?: Attachment) => void;
  onSend: (
    text: string,
    attachment?: Attachment,
    parent?: string | null,
  ) => void;
  onRegenerate: (m: Message) => void;
  onStop: () => void;
  onBranch: (leaf: string) => void;
  onMap: (ids?: number[], selected?: number) => void;
}
export function Assistant({
  conversation,
  modelReady,
  onDraft,
  onAttachment,
  onSend,
  onRegenerate,
  onStop,
  onBranch,
  onMap,
}: Props) {
  const [editing, setEditing] = useState<Message | null>(null),
    [editText, setEditText] = useState("");
  const [notice, setNotice] = useState(""),
    [now, setNow] = useState(Date.now());
  const input = useRef<HTMLTextAreaElement>(null),
    log = useRef<HTMLDivElement>(null);
  const { draft, attachment } = conversation;
  const path = activePath(conversation);
  const pending = conversation.messages.find((m) => m.status === "pending");
  const busy = !!pending;
  const last = path[path.length - 1];
  const suggestions = [
    "Które przejazdy mają najwyższy priorytet?",
    "Co oznacza wskaźnik RPS?",
    "W których dzielnicach są przejazdy?",
  ];
  useEffect(() => {
    if (!busy) return;
    const t = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(t);
  }, [busy]);
  useEffect(() => {
    log.current?.scrollTo({
      top: log.current.scrollHeight,
      behavior: matchMedia("(prefers-reduced-motion: reduce)").matches
        ? "instant"
        : "smooth",
    });
  }, [conversation.leaf, last?.content, last?.status]);
  useEffect(() => {
    if (attachment) input.current?.focus();
  }, [attachment]);
  async function copy(message: Message) {
    try {
      await navigator.clipboard.writeText(message.content);
      setNotice("Skopiowano odpowiedź.");
    } catch {
      setNotice(
        "Nie udało się skopiować. Zaznacz tekst odpowiedzi i skopiuj ręcznie.",
      );
    }
  }
  function submit(text = draft) {
    if (!text.trim() || busy || !modelReady) return;
    onSend(text, attachment);
    input.current?.focus();
  }
  return (
    <section className="chat-workspace" aria-label="Aktywna rozmowa">
      <div className="message-scroll" ref={log}>
        <div className="message-column">
          {!path.length && (
            <div className="chat-welcome">
              <span className="welcome-symbol" aria-hidden="true">
                R
              </span>
              <p className="eyebrow">RAILSAFE AI · WARSZAWA</p>
              <h1>Przyjrzyjmy się przejazdom.</h1>
              <p>
                Zapytaj o ruch, porównaj przejazdy i poznaj podstawy ich
                priorytetu do dalszej oceny.
              </p>
              <div className="welcome-suggestions">
                {suggestions.map((s) => (
                  <button
                    key={s}
                    disabled={!modelReady}
                    onClick={() => submit(s)}
                  >
                    {s}
                    <span aria-hidden="true">↗</span>
                  </button>
                ))}
              </div>
              <button className="map-answer-button" onClick={() => onMap()}>
                ↗ Otwórz mapę
              </button>
            </div>
          )}
          {path.map((message) => {
            const siblings = conversation.messages.filter(
              (m) => m.parent === message.parent && m.role === message.role,
            );
            const index = siblings.findIndex((m) => m.id === message.id);
            return (
              <article
                key={message.id}
                className={`chat-message ${message.role === "user" ? "user-message" : "assistant-message"}`}
                aria-label={
                  message.role === "user"
                    ? "Pytanie użytkownika"
                    : "Odpowiedź RailSafe AI"
                }
              >
                {message.role === "assistant" && (
                  <div className="assistant-label">
                    <span aria-hidden="true">R</span> RailSafe AI
                  </div>
                )}
                {message.attachment && (
                  <div className="message-attachment">
                    Przejazd: {message.attachment.label}
                  </div>
                )}
                {editing?.id === message.id ? (
                  <form
                    className="edit-message"
                    onSubmit={(e) => {
                      e.preventDefault();
                      if (editText.trim()) {
                        onSend(editText, message.attachment, message.parent);
                        setEditing(null);
                      }
                    }}
                  >
                    <textarea
                      aria-label="Edytuj pytanie"
                      autoFocus
                      value={editText}
                      maxLength={500}
                      onChange={(e) => setEditText(e.target.value)}
                    />
                    <div>
                      <button type="button" onClick={() => setEditing(null)}>
                        Anuluj
                      </button>
                      <button
                        className="primary"
                        disabled={busy || !modelReady || !editText.trim()}
                      >
                        Wyślij jako nową gałąź
                      </button>
                    </div>
                  </form>
                ) : message.status === "pending" ? (
                  <div className="answer-pending" role="status">
                    <span className="spinner" /> Analizuję dane…{" "}
                    <span>
                      {Math.max(0, Math.floor((now - message.created) / 1000))}{" "}
                      s
                    </span>
                  </div>
                ) : (
                  <>
                    <div className={message.status ? "message-status" : ""}>
                      <AnswerText text={message.content} />
                    </div>
                    {message.role === "assistant" && !message.status && (
                      <>
                        <AnswerContent
                          evidence={message.reply?.evidence}
                          onMap={(ids) => onMap(ids)}
                          onCard={(id) => onMap([id], id)}
                        />
                        {message.reply && (
                          <details className="answer-trace">
                            <summary>
                              {message.reply.grounded
                                ? "✓ Odpowiedź na podstawie danych"
                                : "! Odpowiedź bez odczytu danych"}
                            </summary>
                            <ul>
                              {message.reply.tool_calls.map((call, i) => (
                                <li key={i}>
                                  {call.name}:{" "}
                                  {call.ok
                                    ? "odczyt zakończony"
                                    : "błąd odczytu"}
                                </li>
                              ))}
                            </ul>
                            {message.reply.disclaimer && (
                              <p>{message.reply.disclaimer}</p>
                            )}
                          </details>
                        )}
                      </>
                    )}
                  </>
                )}
                <div className="message-actions">
                  {message.status !== "pending" &&
                    (message.role === "user" ? (
                      <button
                        disabled={busy}
                        onClick={() => {
                          setEditing(message);
                          setEditText(message.content);
                        }}
                      >
                        Edytuj
                      </button>
                    ) : (
                      <>
                        <button onClick={() => void copy(message)}>
                          Kopiuj
                        </button>
                        <button
                          disabled={busy || !modelReady}
                          onClick={() => onRegenerate(message)}
                        >
                          Ponów odpowiedź
                        </button>
                      </>
                    ))}
                  {siblings.length > 1 && (
                    <div
                      className="branch-switch"
                      aria-label="Wersje wiadomości"
                    >
                      <button
                        aria-label="Poprzednia wersja"
                        disabled={index === 0}
                        onClick={() => {
                          setEditing(null);
                          onBranch(
                            branchLeaf(conversation, siblings[index - 1].id),
                          );
                        }}
                      >
                        ‹
                      </button>
                      <span>
                        {index + 1} / {siblings.length}
                      </span>
                      <button
                        aria-label="Następna wersja"
                        disabled={index === siblings.length - 1}
                        onClick={() => {
                          setEditing(null);
                          onBranch(
                            branchLeaf(conversation, siblings[index + 1].id),
                          );
                        }}
                      >
                        ›
                      </button>
                    </div>
                  )}
                </div>
              </article>
            );
          })}
          {busy && !path.some((m) => m.status === "pending") && (
            <p className="message-status" role="status">
              Odpowiedź powstaje w innej gałęzi tej rozmowy.
            </p>
          )}
        </div>
      </div>
      <div className="composer-area">
        <div className="composer-inner">
          {!modelReady && (
            <p className="model-unavailable" role="status">
              Asystent jest niedostępny. Nadal możesz otworzyć mapę i sprawdzić
              przejazdy.
            </p>
          )}
          <p className="copy-notice" role="status">
            {notice}
          </p>
          <form
            className="message-composer"
            onSubmit={(e) => {
              e.preventDefault();
              submit();
            }}
          >
            {attachment && (
              <div className="composer-attachment">
                Przejazd: {attachment.label}
                <button
                  type="button"
                  aria-label="Usuń przejazd z pytania"
                  onClick={() => onAttachment(undefined)}
                >
                  ×
                </button>
              </div>
            )}
            <label className="sr-only" htmlFor="chat-question">
              Pytanie do RailSafe AI
            </label>
            <textarea
              id="chat-question"
              ref={input}
              placeholder="Zapytaj o przejazdy, ruch lub wynik analizy…"
              value={draft}
              maxLength={500}
              rows={2}
              onChange={(e) => onDraft(e.target.value)}
              onKeyDown={(e) => {
                if (
                  e.key === "Enter" &&
                  !e.shiftKey &&
                  !e.nativeEvent.isComposing
                ) {
                  e.preventDefault();
                  submit();
                }
              }}
            />
            <div className="composer-tools">
              <button type="button" onClick={() => onMap()}>
                ↗ Otwórz mapę
              </button>
              <span>{draft.length}/500</span>
              {busy ? (
                <button className="stop-button" type="button" onClick={onStop}>
                  ■ Zatrzymaj
                </button>
              ) : (
                <button
                  className="send-button"
                  type="submit"
                  disabled={!modelReady || !draft.trim()}
                  aria-label="Wyślij pytanie"
                >
                  ↑
                </button>
              )}
            </div>
          </form>
          <p className="composer-footnote">
            Lokalny model może się mylić. RPS oznacza priorytet do dalszej
            oceny, a nie prawdopodobieństwo wypadku.
          </p>
        </div>
      </div>
    </section>
  );
}
