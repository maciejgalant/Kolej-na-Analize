import { useEffect, useState } from "react";

import { fetchHealth, type Health } from "./api";
import { MapView } from "./MapView";

type HealthState =
  | { kind: "loading" }
  | { kind: "error" }
  | { kind: "ready"; health: Health };

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

function StatusRow({ label, ok, detail }: { label: string; ok: boolean; detail: string }) {
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
  if (state.kind === "loading") return <p className="muted">Sprawdzanie usług…</p>;
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
        detail={database.postgis_version ? `PostGIS ${database.postgis_version}` : "brak połączenia"}
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
  const state = useHealth();
  const demoMode = state.kind === "ready" && state.health.demo_mode;
  const headerDot =
    state.kind === "ready" && state.health.status === "ok" ? "dot dot-ok" : "dot dot-warn";

  return (
    <div className="app">
      <header className="topbar">
        <div className="brand">
          <strong>RailSafe AI</strong>
          <span className="brand-sub">projekt edukacyjny, niezależny</span>
        </div>
        <nav aria-label="Główna nawigacja">
          <span className="nav-item nav-active" aria-current="page">
            Analiza przejazdów
          </span>
          <span className="nav-item nav-disabled">Porównania</span>
          <span className="nav-item nav-disabled">O projekcie</span>
        </nav>
        <div className="data-state" aria-live="polite">
          <span className={headerDot} aria-hidden="true" />
          {state.kind === "ready"
            ? state.health.status === "ok"
              ? "Usługi działają"
              : "Usługi częściowo niedostępne"
            : state.kind === "loading"
              ? "Sprawdzanie…"
              : "Brak backendu"}
        </div>
      </header>

      {demoMode && (
        <div className="demo-bar" role="status">
          Dane demonstracyjne — tryb bez zewnętrznych API. Nie są to dane rzeczywiste.
        </div>
      )}

      <main className="layout">
        <section className="panel" aria-labelledby="ranking-title">
          <h2 id="ranking-title">Filtry i ranking</h2>
          <p className="muted">
            Brak danych. Ewidencja przejazdów i ranking pojawią się po zadaniach RSA-004 – RSA-011.
          </p>
        </section>

        <section className="map-wrap" aria-label="Mapa">
          <MapView />
        </section>

        <section className="panel" aria-labelledby="status-title">
          <h2 id="status-title">Stan usług</h2>
          <ServiceStatus state={state} />
          <p className="muted small">
            Wyniki aplikacji będą oznaczać priorytet do dalszej oceny, a nie prognozę wypadków ani
            urzędową klasyfikację przejazdów.
          </p>
        </section>
      </main>

      <footer className="assistant">
        <label htmlFor="assistant-input">Asystent AI</label>
        <input
          id="assistant-input"
          type="text"
          placeholder="Asystent będzie dostępny po zadaniu RSA-013"
          disabled
        />
        <button type="button" disabled aria-label="Wyślij pytanie">
          →
        </button>
      </footer>
    </div>
  );
}
