import { useState } from "react";
import type { Conversation } from "./model";
interface Props {
  conversations: Conversation[];
  active: string;
  onSelect: (id: string) => void;
  onNew: () => void;
  onRename: (id: string, title: string) => void;
  onPin: (id: string) => void;
  onDelete: (id: string) => void;
}
export function ConversationList({
  conversations,
  active,
  onSelect,
  onNew,
  onRename,
  onPin,
  onDelete,
}: Props) {
  const [query, setQuery] = useState("");
  const [renaming, setRenaming] = useState<string | null>(null);
  const [title, setTitle] = useState("");
  const visible = conversations
    .filter((c) =>
      (c.title + " " + c.messages.map((m) => m.content).join(" "))
        .toLocaleLowerCase("pl")
        .includes(query.toLocaleLowerCase("pl")),
    )
    .sort(
      (a, b) => Number(b.pinned) - Number(a.pinned) || b.updated - a.updated,
    );
  return (
    <aside className="conversation-sidebar" aria-label="Rozmowy">
      <div className="sidebar-brand">
        <span className="rail-mark" aria-hidden="true">
          R
        </span>
        <div>
          <strong>RailSafe AI</strong>
          <small>Asystent analizy przejazdów</small>
        </div>
      </div>
      <button className="primary new-conversation" onClick={onNew}>
        ＋ Nowa rozmowa
      </button>
      <label className="sr-only" htmlFor="conversation-search">
        Szukaj w rozmowach
      </label>
      <input
        id="conversation-search"
        className="conversation-search"
        placeholder="Szukaj w rozmowach…"
        value={query}
        onChange={(e) => setQuery(e.target.value)}
      />
      <div className="sidebar-section-label">
        Twoje rozmowy <span>{conversations.length}</span>
      </div>
      <ul className="conversation-items">
        {visible.map((c) => (
          <li
            key={c.id}
            className={`conversation-row ${c.id === active ? "selected" : ""}`}
          >
            {renaming === c.id ? (
              <form
                className="rename-form"
                onSubmit={(e) => {
                  e.preventDefault();
                  if (title.trim()) {
                    onRename(c.id, title.trim());
                    setRenaming(null);
                  }
                }}
              >
                <input
                  aria-label="Tytuł rozmowy"
                  autoFocus
                  value={title}
                  maxLength={100}
                  onChange={(e) => setTitle(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === "Escape") setRenaming(null);
                  }}
                />
                <button type="submit">Zapisz</button>
                <button type="button" onClick={() => setRenaming(null)}>
                  Anuluj
                </button>
              </form>
            ) : (
              <>
                <button
                  className="conversation-select"
                  aria-current={c.id === active ? "page" : undefined}
                  onClick={() => onSelect(c.id)}
                >
                  <span>
                    {c.pinned ? "◆ " : ""}
                    {c.title}
                  </span>
                  <small>
                    {new Date(c.updated).toLocaleDateString("pl-PL", {
                      day: "numeric",
                      month: "short",
                    })}
                    {c.messages.some((m) => m.status === "pending")
                      ? " · Odpowiadam…"
                      : ""}
                  </small>
                </button>
                <div className="conversation-actions">
                  <button
                    aria-label={
                      c.pinned ? "Odepnij rozmowę" : "Przypnij rozmowę"
                    }
                    title={c.pinned ? "Odepnij" : "Przypnij"}
                    aria-pressed={c.pinned}
                    onClick={() => onPin(c.id)}
                  >
                    ◆
                  </button>
                  <button
                    title="Zmień tytuł"
                    aria-label="Zmień tytuł"
                    onClick={() => {
                      setTitle(c.title);
                      setRenaming(c.id);
                    }}
                  >
                    ✎
                  </button>
                  <button
                    title="Usuń rozmowę"
                    aria-label="Usuń rozmowę"
                    onClick={() => onDelete(c.id)}
                  >
                    ×
                  </button>
                </div>
              </>
            )}
          </li>
        ))}
      </ul>
      {!visible.length && (
        <p className="sidebar-empty">Brak pasujących rozmów.</p>
      )}
      <footer className="sidebar-footer">
        <span className="dot dot-ok" /> Historia w tej przeglądarce
        <small>Projekt edukacyjny, niezależny</small>
      </footer>
    </aside>
  );
}
