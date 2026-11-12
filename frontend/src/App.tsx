import { useEffect, useMemo, useState } from "react";

import {
  type CrossingFeature,
  type DistrictFeature,
  fetchCrossings,
  fetchDistricts,
  fetchHealth,
  type Health,
} from "./api";
import { CrossingCard } from "./CrossingCard";
import { crossingTitle, objectsLabel } from "./labels";
import { MapView } from "./MapView";

type HealthState =
  | { kind: "loading" }
  | { kind: "error" }
  | { kind: "ready"; health: Health };

type DataState =
  | { kind: "loading" }
  | { kind: "error" }
  | { kind: "ready"; districts: DistrictFeature[]; crossings: CrossingFeature[] };

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
    Promise.all([fetchDistricts(controller.signal), fetchCrossings(controller.signal)])
      .then(([districts, crossings]) => setState({ kind: "ready", districts, crossings }))
      .catch(() => {
        if (!controller.signal.aborted) setState({ kind: "error" });
      });
    return () => controller.abort();
  }, [attempt]);

  return [state, () => setAttempt((n) => n + 1)];
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
  const [districtId, setDistrictId] = useState<number | null>(null);
  const [showRoad, setShowRoad] = useState(true);
  const [showPedestrian, setShowPedestrian] = useState(true);
  const [showUnverified, setShowUnverified] = useState(false);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [sortBy, setSortBy] = useState<"name" | "trains">("name");

  const districts = data.kind === "ready" ? data.districts : [];
  const visible = useMemo(() => {
    if (data.kind !== "ready") return [];
    const filtered = data.crossings.filter((c) => {
      const p = c.properties;
      if (districtId !== null && p.district_id !== districtId) return false;
      if (p.is_pedestrian ? !showPedestrian : !showRoad) return false;
      if (p.verification_status.startsWith("rejected")) return false;
      return showUnverified || p.verification_status === "verified";
    });
    if (sortBy === "trains") {
      // Obiekty bez danych rozkładowych trafiają na koniec, nie są traktowane jak zero.
      return [...filtered].sort(
        (a, b) => (b.properties.trains_weekday ?? -1) - (a.properties.trains_weekday ?? -1),
      );
    }
    return filtered;
  }, [data, districtId, showRoad, showPedestrian, showUnverified, sortBy]);
  const hasTrainData =
    data.kind === "ready" && data.crossings.some((c) => c.properties.trains_weekday !== null);

  // Wybrany przejazd znika z karty, gdy filtr go ukryje.
  useEffect(() => {
    if (selectedId !== null && !visible.some((c) => c.id === selectedId)) setSelectedId(null);
  }, [visible, selectedId]);

  const demoMode = health.kind === "ready" && health.health.demo_mode;
  const servicesOk = health.kind === "ready" && health.health.status === "ok";
  const hiddenUnverified =
    data.kind === "ready"
      ? data.crossings.filter(
          (c) =>
            c.properties.verification_status === "unverified" &&
            (districtId === null || c.properties.district_id === districtId),
        ).length
      : 0;

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
          <span className={servicesOk ? "dot dot-ok" : "dot dot-warn"} aria-hidden="true" />
          {health.kind === "ready"
            ? servicesOk
              ? "Usługi działają"
              : "Usługi częściowo niedostępne"
            : health.kind === "loading"
              ? "Sprawdzanie…"
              : "Brak backendu"}
        </div>
      </header>

      {demoMode && (
        <div className="demo-bar" role="status">
          Tryb bez zewnętrznych API. Ewidencja przejazdów pochodzi z danych urzędowych; dane o
          ruchu drogowym i ranking nie są jeszcze dostępne.
        </div>
      )}

      <main className="layout">
        <section className="panel" aria-labelledby="list-title">
          <h2 id="list-title">Ewidencja przejazdów</h2>

          <label className="field" htmlFor="district">
            Dzielnica
          </label>
          <select
            id="district"
            value={districtId ?? ""}
            onChange={(e) => setDistrictId(e.target.value === "" ? null : Number(e.target.value))}
            disabled={data.kind !== "ready"}
          >
            <option value="">Cała Warszawa</option>
            {districts.map((d) => (
              <option key={d.id} value={d.id}>
                {d.properties.name} ({d.properties.crossings_verified})
              </option>
            ))}
          </select>

          <fieldset>
            <legend>Rodzaj</legend>
            <label>
              <input
                type="checkbox"
                checked={showRoad}
                onChange={(e) => setShowRoad(e.target.checked)}
              />{" "}
              przejazdy drogowe (A–D, F)
            </label>
            <label>
              <input
                type="checkbox"
                checked={showPedestrian}
                onChange={(e) => setShowPedestrian(e.target.checked)}
              />{" "}
              przejścia dla pieszych (E)
            </label>
            <label>
              <input
                type="checkbox"
                checked={showUnverified}
                onChange={(e) => setShowUnverified(e.target.checked)}
              />{" "}
              pokaż niezweryfikowane ({hiddenUnverified})
            </label>
          </fieldset>

          <label className="field" htmlFor="sort">
            Kolejność
          </label>
          <select
            id="sort"
            value={sortBy}
            onChange={(e) => setSortBy(e.target.value as "name" | "trains")}
            disabled={!hasTrainData}
          >
            <option value="name">według dzielnicy i numeru</option>
            <option value="trains">według liczby pociągów (plan)</option>
          </select>

          {data.kind === "loading" && <p className="muted">Wczytywanie ewidencji…</p>}
          {data.kind === "error" && (
            <div className="alert" role="alert">
              Nie udało się wczytać ewidencji przejazdów.{" "}
              <button type="button" className="link" onClick={reload}>
                Spróbuj ponownie
              </button>
            </div>
          )}
          {data.kind === "ready" && data.crossings.length === 0 && (
            <p className="muted">
              Baza nie zawiera jeszcze przejazdów. Uruchom zadania <code>import-crossings</code> i{" "}
              <code>import-topology</code> (opis w README).
            </p>
          )}
          {data.kind === "ready" && data.crossings.length > 0 && (
            <>
              <p className="count" aria-live="polite">
                Pokazano <strong>{visible.length}</strong> {objectsLabel(visible.length)}. To nie jest
                ranking priorytetów — ten pojawi się po zadaniu RSA-010.
              </p>
              {visible.length === 0 ? (
                <p className="muted">Żaden obiekt nie spełnia wybranych filtrów.</p>
              ) : (
                <ul className="crossing-list">
                  {visible.map((c) => (
                    <li key={c.id}>
                      <button
                        type="button"
                        className={c.id === selectedId ? "item item-active" : "item"}
                        aria-pressed={c.id === selectedId}
                        onClick={() => setSelectedId(c.id)}
                      >
                        <span
                          className={
                            "marker " +
                            (c.properties.is_pedestrian ? "marker-ped" : "marker-road") +
                            (c.properties.verification_status === "verified"
                              ? ""
                              : " marker-unverified")
                          }
                          aria-hidden="true"
                        >
                          {c.properties.category ?? "?"}
                        </span>
                        <span className="item-text">
                          <span className="item-name">{crossingTitle(c.properties)}</span>
                          <span className="item-sub">
                            kat. {c.properties.category ?? "nieznana"} ·{" "}
                            {c.properties.district_name}
                            {c.properties.trains_weekday !== null
                              ? ` · ${c.properties.trains_weekday} poc./dobę`
                              : ""}
                            {c.properties.warnings > 0 ? " · ! ostrzeżenie" : ""}
                          </span>
                        </span>
                      </button>
                    </li>
                  ))}
                </ul>
              )}
            </>
          )}
        </section>

        <section className="map-wrap" aria-label="Mapa">
          <MapView
            districts={districts}
            crossings={visible}
            selectedDistrictId={districtId}
            selectedCrossingId={selectedId}
            onSelectCrossing={setSelectedId}
          />
        </section>

        <section className="panel" aria-labelledby="detail-title">
          <h2 id="detail-title">Szczegóły</h2>
          {selectedId === null ? (
            <p className="muted">Wybierz przejazd z listy albo kliknij punkt na mapie.</p>
          ) : (
            <CrossingCard crossingId={selectedId} />
          )}
          <details className="services">
            <summary>Stan usług</summary>
            <ServiceStatus state={health} />
          </details>
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
