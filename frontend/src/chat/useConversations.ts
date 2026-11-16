import { useEffect, useRef, useState } from "react";
import {
  activePath,
  analysisContext,
  appendQuestion,
  decodeState,
  initialState,
  replaceMessage,
  STORAGE_KEY,
  uid,
  validReply,
} from "./model";
import type { Attachment, ChatState, Conversation, Message } from "./model";

export function useConversations() {
  const [loaded] = useState(() => {
    try {
      const raw = localStorage.getItem(STORAGE_KEY);
      const state = raw ? decodeState(raw) : initialState();
      if (localStorage.getItem("railsafe.map.palette.v2") !== "1") {
        state.conversations = state.conversations.map((c) => ({
          ...c,
          map: {
            ...c.map,
            basemap: c.map.basemap === "gray" ? "color" : c.map.basemap,
          },
        }));
      }
      return { state, error: "" };
    } catch {
      return {
        state: initialState(),
        error:
          "Nie udało się odczytać historii. Oryginalny zapis zachowano; bieżąca sesja działa bez zapisu.",
      };
    }
  });
  const [state, render] = useState<ChatState>(loaded.state);
  const [storageError, setStorageError] = useState(loaded.error);
  const current = useRef(state);
  const requests = useRef(
    new Map<string, { controller: AbortController; messageId: string }>(),
  );
  function change(fn: (s: ChatState) => ChatState) {
    const next = fn(current.current);
    current.current = next;
    render(next);
  }
  function update(id: string, fn: (c: Conversation) => Conversation) {
    change((s) => ({
      ...s,
      conversations: s.conversations.map((c) => (c.id === id ? fn(c) : c)),
    }));
  }
  useEffect(() => {
    if (loaded.error) return;
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(state));
      localStorage.setItem("railsafe.map.palette.v2", "1");
      setStorageError("");
    } catch {
      setStorageError(
        "Nie udało się zapisać historii w przeglądarce. Zmiany w tej sesji mogą zniknąć po odświeżeniu.",
      );
    }
  }, [state, loaded.error]);
  useEffect(
    () => () => {
      requests.current.forEach((r) => r.controller.abort());
    },
    [],
  );

  async function request(
    c: Conversation,
    question: Message,
    response: Message,
  ) {
    const controller = new AbortController();
    requests.current.set(c.id, { controller, messageId: response.id });
    try {
      const history = activePath(c, question.parent)
        .filter((m) => !m.status && m.content.trim())
        .slice(-8)
        .map((m) => ({
          role: m.role,
          content: (
            (m.attachment ? `[Przejazd: ${m.attachment.label}]\n` : "") +
            m.content
          ).slice(0, 2000),
        }));
      const result = await fetch("/api/v1/assistant/chat", {
        method: "POST",
        signal: controller.signal,
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          message: question.content,
          history,
          crossing_id: question.attachment?.id ?? null,
          analysis_crossing_ids: analysisContext(c, question.parent),
        }),
      });
      const body = await result.json().catch(() => null);
      if (!result.ok)
        throw Error(
          result.status === 504 || result.status === 502
            ? "Model nie zdążył odpowiedzieć. Spróbuj zadać węższe pytanie."
            : typeof body?.detail === "string"
              ? body.detail
              : "Nie udało się uzyskać odpowiedzi asystenta.",
        );
      if (!validReply(body))
        throw Error(
          "Serwer zwrócił nieprawidłową odpowiedź. Spróbuj ponownie.",
        );
      if (!controller.signal.aborted)
        change((s) =>
          replaceMessage(s, c.id, response.id, {
            content: body.answer,
            reply: body,
            status: undefined,
          }),
        );
    } catch (error) {
      if (!controller.signal.aborted)
        change((s) =>
          replaceMessage(s, c.id, response.id, {
            status: "error",
            content:
              error instanceof Error ? error.message : "Błąd połączenia.",
          }),
        );
    } finally {
      if (requests.current.get(c.id)?.messageId === response.id)
        requests.current.delete(c.id);
    }
  }
  function send(
    id: string,
    text: string,
    attachment?: Attachment,
    parent?: string | null,
  ) {
    const c = current.current.conversations.find((c) => c.id === id);
    if (!c || requests.current.has(id) || !text.trim()) return;
    const next = appendQuestion(
      c,
      text.trim(),
      attachment,
      parent === undefined ? c.leaf : parent,
    );
    update(id, () => next.conversation);
    void request(next.conversation, next.question, next.response);
  }
  function regenerate(id: string, message: Message) {
    const c = current.current.conversations.find((c) => c.id === id);
    const question = c?.messages.find(
      (m) => m.id === message.parent && m.role === "user",
    );
    if (!c || !question || requests.current.has(id)) return;
    const response: Message = {
      id: uid(),
      parent: question.id,
      role: "assistant",
      content: "",
      status: "pending",
      created: Date.now(),
    };
    const next = {
      ...c,
      leaf: response.id,
      updated: Date.now(),
      messages: [...c.messages, response],
    };
    update(id, () => next);
    void request(next, question, response);
  }
  function stop(id: string) {
    const pending = requests.current.get(id);
    if (!pending) return;
    pending.controller.abort();
    requests.current.delete(id);
    change((s) =>
      replaceMessage(s, id, pending.messageId, {
        status: "stopped",
        content:
          "Przerwano oczekiwanie na odpowiedź. Model lokalny może jeszcze kończyć pracę.",
      }),
    );
  }
  return { state, change, update, send, regenerate, stop, storageError };
}
