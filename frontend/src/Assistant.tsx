import {
  AssistantAvatar,
  CopyIcon,
  CrossingSignal,
  EditIcon,
  RestartIcon,
} from "./UiIcons";
import { APP_NAME, BRAND_LOGO } from "./brand";
import { useEffect, useRef, useState } from "react";
import { AnswerContent, AnswerText } from "./chat/AnswerContent";
import { AnalysisShortcuts } from "./chat/AnalysisShortcuts";
import type { CrossingFeature } from "./api";
import { activePath, branchLeaf } from "./chat/model";
import type { Attachment, Conversation, Message } from "./chat/model";
interface Props {
  conversation: Conversation;
  modelReady: boolean;
  crossings: CrossingFeature[];
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
  crossings,
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
  const [copiedId, setCopiedId] = useState<string | null>(null);
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
  useEffect(() => {
    if (!copiedId) return;
    const timer = window.setTimeout(() => {
      setCopiedId(null);
      setNotice("");
    }, 2400);
    return () => window.clearTimeout(timer);
  }, [copiedId]);
  async function copy(message: Message) {
    try {
      await navigator.clipboard.writeText(message.content);
      setCopiedId(message.id);
      setNotice("Skopiowano wiadomość.");
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
              <img
                className="welcome-logo"
                src={BRAND_LOGO}
                alt={APP_NAME}
                width="2172"
                height="724"
              />
              <p className="eyebrow">ASYSTENT ANALIZY PRZEJAZDÓW · WARSZAWA</p>
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
            const onlyCard =
              message.reply?.evidence?.cards.length === 1
                ? message.reply.evidence.cards[0]
                : undefined;
            const contextAttachment =
              message.attachment ??
              [...path].reverse().find((m) => m.role === "user")?.attachment ??
              (onlyCard
                ? { id: onlyCard.crossing_id, label: onlyCard.title }
                : undefined);
            return (
              <article
                key={message.id}
                className={`chat-message ${message.role === "user" ? "user-message" : "assistant-message"}`}
                aria-label={
                  message.role === "user"
                    ? "Pytanie użytkownika"
                    : `Odpowiedź ${APP_NAME}`
                }
              >
                {message.role === "assistant" && (
                  <div className="assistant-label">
                    <AssistantAvatar />{" "}
                    <span className="assistant-name">Asystent AI</span>
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
                    <CrossingSignal />
                    <div className="pending-description">
                      <strong>Analizuję dane</strong>
                      <small>Sprawdzam informacje o przejazdach…</small>
                    </div>
                    <span className="pending-elapsed">
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
                        {message.reply &&
                          (message.reply.tool_calls.length > 0 ||
                            message.reply.disclaimer) && (
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
                {message.role === "assistant" &&
                  !message.status &&
                  message.id === last?.id && (
                    <div
                      className="followup-questions"
                      aria-label="Propozycje dalszych pytań"
                    >
                      {[
                        "Wyjaśnij prościej ten wynik",
                        contextAttachment
                          ? "Sprawdź jakość danych tego przejazdu"
                          : "Które przejazdy mają niepełne dane?",
                      ].map((question) => (
                        <button
                          key={question}
                          disabled={busy || !modelReady}
                          onClick={() => onSend(question, contextAttachment)}
                        >
                          {question} <span aria-hidden="true">↗</span>
                        </button>
                      ))}
                    </div>
                  )}
                <div className="message-actions">
                  {message.status !== "pending" && (
                    <button
                      className={`copy-message-button ${copiedId === message.id ? "is-copied" : ""}`}
                      aria-label="Kopiuj wiadomość"
                      title={
                        copiedId === message.id
                          ? "Skopiowano"
                          : "Kopiuj wiadomość"
                      }
                      onClick={() => void copy(message)}
                    >
                      <CopyIcon done={copiedId === message.id} />
                      {copiedId === message.id && <span>Skopiowano</span>}
                    </button>
                  )}
                  {message.status !== "pending" &&
                    (message.role === "user" ? (
                      <button
                        disabled={busy}
                        aria-label="Edytuj pytanie"
                        title="Edytuj pytanie"
                        className="icon-action"
                        onClick={() => {
                          setEditing(message);
                          setEditText(message.content);
                        }}
                      >
                        <EditIcon />
                      </button>
                    ) : (
                      <>
                        <button
                          disabled={busy || !modelReady}
                          className="icon-action"
                          aria-label="Ponów odpowiedź"
                          title="Ponów odpowiedź"
                          onClick={() => onRegenerate(message)}
                        >
                          <RestartIcon />
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
          <AnalysisShortcuts
            crossings={crossings}
            disabled={busy || !modelReady}
            onSend={(text) => onSend(text)}
          />
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
              Pytanie do {APP_NAME}
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
              <span className="composer-key-hint">
                Enter — wyślij · Shift+Enter — nowy wiersz
              </span>
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
