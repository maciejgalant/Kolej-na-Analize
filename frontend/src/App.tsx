import { MapIcon } from "./UiIcons";
import { useEffect, useState } from "react";

import {
  type AnalysisRun,
  type CrossingFeature,
  type DistrictFeature,
  fetchCrossings,
  fetchDistricts,
  fetchHealth,
  fetchLatestAnalysis,
  type Health,
} from "./api";
import { Assistant } from "./Assistant";
import { ConversationList } from "./chat/ConversationList";
import { newConversation } from "./chat/model";

import { Dialog } from "./Dialog";
import { MapExplorer } from "./MapExplorer";
import { useConversations } from "./chat/useConversations";

type HealthState =
  | { kind: "loading" }
  | { kind: "error" }
  | { kind: "ready"; health: Health };

type DataState =
  | { kind: "loading" }
  | { kind: "error" }
  | {
      kind: "ready";
      districts: DistrictFeature[];
      crossings: CrossingFeature[];
      analysis: AnalysisRun | null;
    };

function useHealth(): HealthState {
  const [state, setState] = useState<HealthState>({ kind: "loading" });

  useEffect(() => {
    const controller = new AbortController();
    const load = () =>
      fetchHealth(controller.signal)
        .then((health) => setState({ kind: "ready", health }))
        .catch(() => {
          if (!controller.signal.aborted) setState({ kind: "error" });
        });
    void load();
    const timer = window.setInterval(load, 30_000);
    return () => {
      controller.abort();
      window.clearInterval(timer);
    };
  }, []);

  return state;
}

function useInventory(): [DataState, () => void] {
  const [state, setState] = useState<DataState>({ kind: "loading" });
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    const controller = new AbortController();
    setState({ kind: "loading" });
    Promise.all([
      fetchDistricts(controller.signal),
      fetchCrossings(controller.signal),
      fetchLatestAnalysis(controller.signal),
    ])
      .then(([districts, crossings, analysis]) =>
        setState({ kind: "ready", districts, crossings, analysis }),
      )
      .catch(() => {
        if (!controller.signal.aborted) setState({ kind: "error" });
      });
    return () => controller.abort();
  }, [attempt]);

  return [state, () => setAttempt((n) => n + 1)];
}

function StatusRow({
  label,
  ok,
  detail,
}: {
  label: string;
  ok: boolean;
  detail: string;
}) {
  return (
    <li className="status-row">
      <span className={ok ? "badge badge-ok" : "badge badge-warn"}>
        {ok ? "✓ działa" : "! niedostępne"}
      </span>
      <span className="status-label">{label}</span>
      <span className="status-detail">{detail}</span>
    </li>
  );
}

function ServiceStatus({ state }: { state: HealthState }) {
  if (state.kind === "loading")
    return <p className="muted">Sprawdzanie usług…</p>;
  if (state.kind === "error")
    return (
      <p className="alert" role="alert">
        Brak połączenia z backendem. Sprawdź <code>docker compose ps</code>.
      </p>
    );
  const { database, ollama } = state.health.services;
  return (
    <ul className="status-list">
      <StatusRow label="Backend" ok detail={`wersja ${state.health.version}`} />
      <StatusRow
        label="PostGIS"
        ok={database.status === "ok"}
        detail={
          database.postgis_version
            ? `PostGIS ${database.postgis_version}, schemat ${database.schema_revision ?? "bez migracji"}`
            : "brak połączenia"
        }
      />
      <StatusRow
        label="Ollama"
        ok={ollama.status === "ok" && ollama.model_available}
        detail={
          ollama.status !== "ok"
            ? "usługa niedostępna"
            : ollama.model_available
              ? ollama.model
              : `model ${ollama.model} nie jest jeszcze pobrany`
        }
      />
    </ul>
  );
}

export function App() {
  const health = useHealth();
  const [data, reload] = useInventory();
  const chat = useConversations();
  const [sidebar, setSidebar] = useState(true);
  const [infoOpen, setInfoOpen] = useState(false),
    [statusOpen, setStatusOpen] = useState(false);
  const [mapRequest, setMapRequest] = useState<{
    ids?: number[];
    selected?: number;
  } | null>(null);
  const conversation = chat.state.conversations.find(
    (c) => c.id === chat.state.active,
  )!;
  const demo =
    health.kind === "ready" &&
    health.health.services.database.demo_data === true;
  const modelReady =
    health.kind === "ready" &&
    health.health.services.ollama.status === "ok" &&
    health.health.services.ollama.model_available;
  const servicesOk = health.kind === "ready" && health.health.status === "ok";
  function openMap(ids?: number[], selected?: number) {
    if (ids)
      chat.update(conversation.id, (c) => ({
        ...c,
        map: { ...c.map, districtId: null, category: "" },
      }));
    setMapRequest({ ids, selected });
  }
  function createConversation() {
    const c = newConversation();
    chat.change((s) => ({
      ...s,
      active: c.id,
      conversations: [...s.conversations, c],
    }));
  }
  return (
    <div className={`app chat-app ${sidebar ? "" : "sidebar-collapsed"}`}>
      {sidebar && (
        <ConversationList
          conversations={chat.state.conversations}
          active={conversation.id}
          onSelect={(id) => chat.change((s) => ({ ...s, active: id }))}
          onNew={createConversation}
          onMap={() => openMap()}
          onRename={(id, title) => chat.update(id, (c) => ({ ...c, title }))}
          onPin={(id) => chat.update(id, (c) => ({ ...c, pinned: !c.pinned }))}
          onDelete={(id) => {
            const c = chat.state.conversations.find((c) => c.id === id);
            if (
              !confirm(`Usunąć rozmowę „${c?.title}” i wszystkie jej gałęzie?`)
            )
              return;
            chat.stop(id);
            chat.change((s) => {
              const conversations = s.conversations.filter((c) => c.id !== id);
              if (!conversations.length) conversations.push(newConversation());
              return {
                ...s,
                conversations,
                active: s.active === id ? conversations[0].id : s.active,
              };
            });
          }}
        />
      )}
      <main className="chat-main">
        <header className="chat-header">
          <button
            className="sidebar-toggle"
            aria-label={sidebar ? "Zwiń listę rozmów" : "Rozwiń listę rozmów"}
            aria-expanded={sidebar}
            onClick={() => setSidebar((v) => !v)}
          >
            ☰
          </button>
          <div className="chat-heading">
            <strong>{conversation.title}</strong>
            <small>Analiza przejazdów kolejowo-drogowych · Warszawa</small>
          </div>
          {!sidebar && (
            <button className="header-map" onClick={() => openMap()}>
              <MapIcon /> Mapa
            </button>
          )}
          <button onClick={() => setInfoOpen(true)}>O danych i metodzie</button>
          <div className="status-wrap">
            <button
              className="service-pill"
              aria-expanded={statusOpen}
              onClick={() => setStatusOpen((v) => !v)}
            >
              <span className={servicesOk ? "dot dot-ok" : "dot dot-warn"} />
              {health.kind === "loading"
                ? "Łączenie…"
                : servicesOk
                  ? "Usługi działają"
                  : "Sprawdź usługi"}
            </button>
            {statusOpen && (
              <div className="popover" role="dialog" aria-label="Stan usług">
                <ServiceStatus state={health} />
              </div>
            )}
          </div>
        </header>
        {demo && (
          <div className="demo-bar demo-bar-strong" role="alert">
            <strong>DANE DEMONSTRACYJNE.</strong> Obiekty i liczby są fikcyjne.
          </div>
        )}
        {chat.storageError && (
          <div className="alert storage-alert" role="alert">
            {chat.storageError}
          </div>
        )}
        <Assistant
          key={conversation.id}
          conversation={conversation}
          modelReady={modelReady}
          onDraft={(draft) =>
            chat.update(conversation.id, (c) => ({ ...c, draft }))
          }
          onAttachment={(attachment) =>
            chat.update(conversation.id, (c) => ({ ...c, attachment }))
          }
          onSend={(text, a, parent) =>
            chat.send(conversation.id, text, a, parent)
          }
          onRegenerate={(m) => chat.regenerate(conversation.id, m)}
          onStop={() => chat.stop(conversation.id)}
          onBranch={(leaf) =>
            chat.update(conversation.id, (c) => ({ ...c, leaf }))
          }
          onMap={openMap}
        />
      </main>
      {mapRequest && (
        <MapExplorer
          key={conversation.id}
          crossings={data.kind === "ready" ? data.crossings : []}
          districts={data.kind === "ready" ? data.districts : []}
          demo={demo}
          loading={data.kind === "loading"}
          error={data.kind === "error"}
          onRetry={reload}
          saved={conversation.map}
          onSave={(patch) =>
            chat.update(conversation.id, (c) => ({
              ...c,
              map: { ...c.map, ...patch },
            }))
          }
          ids={mapRequest.ids}
          initialSelected={mapRequest.selected}
          onClose={() => setMapRequest(null)}
          onAsk={(attachment) => {
            chat.update(conversation.id, (c) => ({ ...c, attachment }));
            setMapRequest(null);
          }}
        />
      )}
      <Dialog
        title="O danych i metodzie"
        open={infoOpen}
        onClose={() => setInfoOpen(false)}
      >
        <h3>Co pokazuje ranking</h3>
        <p>
          RPS to eksperymentalny priorytet do dalszej oceny, a nie prognoza
          wypadków ani urzędowa klasyfikacja przejazdów. Łączy ekspozycję,
          poziom zabezpieczeń wynikający z kategorii i geometrię skrzyżowania.
        </p>
        <h3>Źródła i ograniczenia</h3>
        <ul>
          <li>
            Ruch drogowy pochodzi z pomiaru ZDM, gdy dostępny jest odpowiedni
            punkt. W pozostałych miejscach jest szacowany z klasy drogi.
          </li>
          <li>
            Liczba pociągów pochodzi z rozkładu pasażerskiego; ruch towarowy i
            manewrowy nie jest uwzględniony.
          </li>
          <li>
            Brak danych o historii zdarzeń. Przejazdy bez kluczowych danych nie
            otrzymują pozycji w rankingu.
          </li>
        </ul>
        {data.kind === "ready" && data.analysis && (
          <p>
            Metoda: {data.analysis.method_version}. Okres:{" "}
            {data.analysis.period_start} – {data.analysis.period_end}.
          </p>
        )}
        <h3>Rozmowy</h3>
        <p>
          Historia i gałęzie rozmów są przechowywane wyłącznie w tej
          przeglądarce. Wyczyszczenie danych witryny usuwa historię. Pytania są
          przetwarzane przez lokalny backend i model Ollama.
        </p>
        {demo && (
          <p className="warnings">
            Dane demonstracyjne: obiekty i wartości są fikcyjne.
          </p>
        )}
      </Dialog>
    </div>
  );
}
