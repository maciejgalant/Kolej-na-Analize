import { useEffect, useMemo, useState } from "react";

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
import { FloatingWindow, resetWindowLayout, useFloatingLayout } from "./FloatingWindow";
import { CategoryPin } from "./CategoryPin";
import { CrossingCard } from "./CrossingCard";
import { Dialog } from "./Dialog";
import { crossingTitle, objectsLabel } from "./labels";
import { MapView } from "./MapView";
import { CATEGORY_SHORT } from "./pictograms";

type HealthState =
  { kind: "loading" } | { kind: "error" } | { kind: "ready"; health: Health };

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

function CrossingItem({
  crossing,
  active,
  onSelect,
}: {
  crossing: CrossingFeature;
  active: boolean;
  onSelect: () => void;
}) {
  const p = crossing.properties;
  const ranked = p.rank !== null && p.rps !== null;
  return (
    <li>
      <button
        type="button"
        className={active ? "item item-active" : "item"}
        aria-pressed={active}
        onClick={onSelect}
      >
        <CategoryPin
          category={p.category}
          verified={p.verification_status === "verified"}
          warning={p.warnings > 0}
          size={34}
        />
        <span className="item-text">
          <span className="item-name">{p.street ?? crossingTitle(p)}</span>
          <span className="item-sub">
            {p.street ? `nr ${crossingTitle(p)} · ` : ""}
            {p.district_name}
          </span>
          <span className="item-meta">
            <span className="chip">
              {p.category ? CATEGORY_SHORT[p.category] : "kategoria nieznana"}
            </span>
            {p.trains_weekday !== null && (
              <span className="chip">
                {p.trains_weekday} poc./dzień roboczy
              </span>
            )}
            {p.verification_status !== "verified" && (
              <span className="chip chip-muted">niezweryfikowany</span>
            )}
            {p.warnings > 0 && (
              <span className="chip chip-warn">! uwagi do danych</span>
            )}
          </span>
        </span>
        {ranked && (
          <span
            className="item-score"
            title={`Priorytet do dalszej oceny: ${p.rps!.toFixed(0)} na 100, pozycja ${p.rank}`}
          >
            <span className="item-rank">{p.rank}.</span>
            <span className="score-bar" aria-hidden="true">
              <span style={{ width: `${Math.max(4, p.rps!)}%` }} />
            </span>
            <span className="item-rps">RPS {p.rps!.toFixed(0)}</span>
          </span>
        )}
      </button>
    </li>
  );
}

function CrossingGroups({
  crossings,
  grouped,
  selectedId,
  onSelect,
}: {
  crossings: CrossingFeature[];
  grouped: boolean;
  selectedId: number | null;
  onSelect: (id: number) => void;
}) {
  const render = (items: CrossingFeature[]) =>
    items.map((c) => (
      <CrossingItem
        key={c.id}
        crossing={c}
        active={c.id === selectedId}
        onSelect={() => onSelect(c.id)}
      />
    ));
  if (!grouped) return <ul className="crossing-list">{render(crossings)}</ul>;
  const groups: { title: string; note?: string; items: CrossingFeature[] }[] = [
    {
      title: "W rankingu",
      note: "1. = najwyższy priorytet do dalszej oceny",
      items: crossings.filter((c) => c.properties.rank !== null),
    },
    {
      title: "Bez pozycji",
      note: "brak kluczowych danych, np. kursów pasażerskich",
      items: crossings.filter(
        (c) => c.properties.rank === null && !c.properties.is_pedestrian,
      ),
    },
    {
      title: "Przejścia dla pieszych",
      note: "poza rankingiem",
      items: crossings.filter(
        (c) => c.properties.rank === null && c.properties.is_pedestrian,
      ),
    },
  ];
  return (
    <div className="crossing-list">
      {groups
        .filter((g) => g.items.length > 0)
        .map((g) => (
          <section key={g.title} className="list-group" aria-label={g.title}>
            <h3 className="list-group-title">
              {g.title} <span className="list-group-count">{g.items.length}</span>
              {g.note && <span className="list-group-note">{g.note}</span>}
            </h3>
            <ul>{render(g.items)}</ul>
          </section>
        ))}
    </div>
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
  const [sortBy, setSortBy] = useState<"priority" | "name" | "trains">(
    "priority",
  );
  const [infoOpen, setInfoOpen] = useState(false);
  const [statusOpen, setStatusOpen] = useState(false);
  const floating = useFloatingLayout();

  const districts = data.kind === "ready" ? data.districts : [];
  const analysis = data.kind === "ready" ? data.analysis : null;
  const selectedStreet =
    data.kind === "ready"
      ? (data.crossings.find((c) => c.id === selectedId)?.properties.street ?? null)
      : null;
  const visible = useMemo(() => {
    if (data.kind !== "ready") return [];
    const filtered = data.crossings.filter((c) => {
      const p = c.properties;
      if (districtId !== null && p.district_id !== districtId) return false;
      if (p.is_pedestrian ? !showPedestrian : !showRoad) return false;
      if (p.verification_status.startsWith("rejected")) return false;
      return showUnverified || p.verification_status === "verified";
    });
    if (sortBy === "priority") {
      // Najpierw obiekty z pozycją, potem pozostałe w kolejności z API.
      return [...filtered].sort(
        (a, b) =>
          (a.properties.rank ?? Infinity) - (b.properties.rank ?? Infinity),
      );
    }
    if (sortBy === "trains") {
      // Obiekty bez danych rozkładowych trafiają na koniec, nie są traktowane jak zero.
      return [...filtered].sort(
        (a, b) =>
          (b.properties.trains_weekday ?? -1) -
          (a.properties.trains_weekday ?? -1),
      );
    }
    return filtered;
  }, [data, districtId, showRoad, showPedestrian, showUnverified, sortBy]);
  const hasTrainData =
    data.kind === "ready" &&
    data.crossings.some((c) => c.properties.trains_weekday !== null);

  // Wybrany przejazd znika z karty, gdy filtr go ukryje.
  useEffect(() => {
    if (selectedId !== null && !visible.some((c) => c.id === selectedId))
      setSelectedId(null);
  }, [visible, selectedId]);

  const demoMode = health.kind === "ready" && health.health.demo_mode;
  const demoData =
    health.kind === "ready" &&
    health.health.services.database.demo_data === true;
  const servicesOk = health.kind === "ready" && health.health.status === "ok";
  const hiddenUnverified =
    data.kind === "ready"
      ? data.crossings.filter(
          (c) =>
            c.properties.verification_status === "unverified" &&
            (districtId === null || c.properties.district_id === districtId),
        ).length
      : 0;

  const activeFilters = [!showRoad, !showPedestrian, showUnverified].filter(
    Boolean,
  ).length;
  const sortLabel = {
    priority: "priorytet",
    name: "dzielnica i numer",
    trains: "liczba pociągów",
  }[sortBy];
  // Przykład dla asystenta: dzielnica z największą liczbą przejazdów w bieżących danych.
  const exampleDistrict =
    [...districts].sort(
      (a, b) =>
        b.properties.crossings_verified - a.properties.crossings_verified,
    )[0]?.properties.name ?? null;
  const healthLabel =
    health.kind === "ready"
      ? servicesOk
        ? "Usługi działają"
        : "Usługi częściowo niedostępne"
      : health.kind === "loading"
        ? "Sprawdzanie…"
        : "Brak backendu";

  return (
    <div className="app">
      <header className="topbar">
        <div className="brand">
          <strong>RailSafe AI</strong>
          <span className="brand-sub">projekt edukacyjny, niezależny</span>
        </div>
        <span className="topbar-title">
          Przejazdy kolejowo-drogowe w Warszawie
        </span>
        {floating && (
          <button
            type="button"
            className="topbar-button"
            onClick={resetWindowLayout}
            title="Przywraca domyślne położenie i rozmiar okien"
          >
            Układ okien
          </button>
        )}
        <button
          type="button"
          className="topbar-button"
          onClick={() => setInfoOpen(true)}
        >
          O danych i metodzie
        </button>
        <div className="status-wrap">
          <button
            type="button"
            className="topbar-button topbar-status"
            aria-expanded={statusOpen}
            onClick={() => setStatusOpen((value) => !value)}
          >
            <span
              className={
                health.kind === "loading"
                  ? "dot dot-pulse"
                  : servicesOk
                    ? "dot dot-ok"
                    : "dot dot-warn"
              }
              aria-hidden="true"
            />
            <span aria-live="polite">{healthLabel}</span>
          </button>
          {statusOpen && (
            <div className="popover" role="dialog" aria-label="Stan usług">
              <ServiceStatus state={health} />
            </div>
          )}
        </div>
      </header>

      {demoData && (
        <div className="demo-bar demo-bar-strong" role="alert">
          <strong>DANE DEMONSTRACYJNE.</strong> Wszystkie obiekty i liczby są
          fikcyjne i nie opisują rzeczywistej sieci kolejowej.{" "}
          <button
            type="button"
            className="link link-light"
            onClick={() => setInfoOpen(true)}
          >
            Więcej
          </button>
        </div>
      )}

      <main className={floating ? "workspace" : "workspace workspace-docked"}>
        <section className="map-wrap" aria-label="Mapa">
          <MapView
            districts={districts}
            crossings={visible}
            selectedDistrictId={districtId}
            selectedCrossingId={selectedId}
            onSelectCrossing={setSelectedId}
            loading={data.kind === "loading"}
            demo={demoData}
            layoutKey={floating ? "floating" : "docked"}
            fitPadding={floating ? { left: 400, right: selectedId === null ? 40 : 420 } : null}
          />
          {selectedId === null &&
            data.kind === "ready" &&
            visible.length > 0 && (
              <p className="map-hint">
                Kliknij punkt na mapie albo pozycję na liście, aby zobaczyć
                szczegóły.
              </p>
            )}
        </section>

        <FloatingWindow
          id="list"
          floating={floating}
          ariaLabel="Przejazdy"
          className="panel"
          title={<h2 id="list-title">Przejazdy</h2>}
          titleExtra={
            data.kind === "ready" &&
            data.crossings.length > 0 && (
              <span className="pill" aria-live="polite">
                {visible.length} {objectsLabel(visible.length)}
              </span>
            )
          }
          defaultRect={(_w, h) => ({ x: 16, y: 16, w: 360, h: h - 32 })}
          minWidth={280}
        >

          <label className="sr-only" htmlFor="district">
            Dzielnica
          </label>
          <select
            id="district"
            value={districtId ?? ""}
            onChange={(e) =>
              setDistrictId(
                e.target.value === "" ? null : Number(e.target.value),
              )
            }
            disabled={data.kind !== "ready"}
          >
            <option value="">
              {demoData ? "Wszystkie dzielnice" : "Cała Warszawa"}
            </option>
            {districts.map((d) => (
              <option key={d.id} value={d.id}>
                {d.properties.name} ({d.properties.crossings_verified})
              </option>
            ))}
          </select>

          <details className="filters">
            <summary>
              <span>Filtry i kolejność</span>
              <span className="section-summary">
                {sortLabel}
                {activeFilters > 0 ? ` · zmienione: ${activeFilters}` : ""}
              </span>
            </summary>
            <fieldset>
              <legend>Rodzaj obiektu</legend>
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
              onChange={(e) =>
                setSortBy(e.target.value as "priority" | "name" | "trains")
              }
              disabled={data.kind !== "ready"}
            >
              <option value="priority" disabled={analysis === null}>
                według priorytetu (RPS)
              </option>
              <option value="name">według dzielnicy i numeru</option>
              <option value="trains" disabled={!hasTrainData}>
                według liczby pociągów (plan)
              </option>
            </select>
          </details>

          {data.kind === "loading" && (
            <ul
              className="crossing-list"
              role="status"
              aria-label="Wczytywanie ewidencji"
            >
              {Array.from({ length: 8 }, (_, i) => (
                <li key={i} className="skeleton-item">
                  <span className="skeleton skeleton-dot" />
                  <span className="skeleton-lines">
                    <span className="skeleton skeleton-line" />
                    <span className="skeleton skeleton-line skeleton-short" />
                  </span>
                </li>
              ))}
            </ul>
          )}
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
              Baza nie zawiera jeszcze przejazdów. Uruchom zadania{" "}
              <code>import-crossings</code> i <code>import-topology</code> (opis
              w README).
            </p>
          )}
          {data.kind === "ready" && data.crossings.length > 0 && (
            <>
              {analysis === null && (
                <p className="count">
                  Ranking pojawi się po uruchomieniu analizy (
                  <code>run-analysis</code>).
                </p>
              )}
              {visible.length === 0 ? (
                <p className="muted">
                  Żaden obiekt nie spełnia wybranych filtrów.
                </p>
              ) : (
                <CrossingGroups
                  crossings={visible}
                  grouped={sortBy === "priority" && analysis !== null}
                  selectedId={selectedId}
                  onSelect={setSelectedId}
                />
              )}
            </>
          )}
        </FloatingWindow>

        {selectedId !== null && (
          <FloatingWindow
            id="detail"
            floating={floating}
            ariaLabel="Szczegóły przejazdu"
            className="panel panel-detail"
            title="Szczegóły"
            onClose={() => setSelectedId(null)}
            closeLabel="Zamknij szczegóły"
            defaultRect={(w, h) => ({ x: w - 396, y: 16, w: 380, h: h - 32 })}
            minWidth={300}
          >
            <CrossingCard
              crossingId={selectedId}
              street={selectedStreet}
              onClose={floating ? undefined : () => setSelectedId(null)}
            />
          </FloatingWindow>
        )}
      </main>

      <Dialog
        title="O danych i metodzie"
        open={infoOpen}
        onClose={() => setInfoOpen(false)}
      >
        {demoData && (
          <p className="warnings">
            <strong>Dane demonstracyjne.</strong> Przejazdy „DEMO-…”, dzielnice
            „Demo-…”, tory, drogi i liczby pociągów są fikcyjne. Zestaw służy
            wyłącznie do pokazania działania aplikacji.
          </p>
        )}
        <h3>Co pokazuje ranking</h3>
        <p>
          RPS to eksperymentalny <strong>priorytet do dalszej oceny</strong>, a
          nie prognoza wypadków ani urzędowa klasyfikacja przejazdów. Łączy
          ekspozycję (pociągi × pojazdy), poziom zabezpieczeń wynikający z
          kategorii i geometrię skrzyżowania.
        </p>
        {analysis !== null && (
          <p>
            Bieżący przebieg: metoda <code>{analysis.method_version}</code>,
            pozycję ma {analysis.ranked} z {analysis.scored} przejazdów
            drogowych, dane o ruchu z tygodnia {analysis.period_start} –{" "}
            {analysis.period_end}.
          </p>
        )}
        <h3>Ograniczenia</h3>
        <ul>
          <li>
            Natężenie ruchu drogowego pochodzi z pomiaru ZDM tylko tam, gdzie
            punkt pomiarowy leży na ulicy przejazdu; w pozostałych miejscach
            jest szacowane z klasy drogi.
          </li>
          <li>
            Liczba pociągów pochodzi z rozkładu pasażerskiego; ruch towarowy i
            manewrowy nie jest uwzględniony.
          </li>
          <li>
            Brak danych o zdarzeniach: składnik historii jest pusty dla
            wszystkich obiektów.
          </li>
          <li>
            Przejazd bez kluczowych danych nie dostaje pozycji, zamiast
            zgadywanej wartości.
          </li>
        </ul>
        {demoMode && (
          <p className="muted small">
            Aplikacja działa bez zewnętrznych, płatnych API. Źródła i warunki
            ich wykorzystania są wymienione w karcie każdego przejazdu.
          </p>
        )}
      </Dialog>

      <Assistant
        modelReady={
          health.kind === "ready" &&
          health.health.services.ollama.status === "ok" &&
          health.health.services.ollama.model_available
        }
        exampleDistrict={exampleDistrict}
      />
    </div>
  );
}
