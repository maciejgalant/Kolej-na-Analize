import { useEffect, useState } from "react";

import { type CrossingDetail, fetchCrossingDetail } from "./api";
import {
  attributeLabel,
  CATEGORY_DESCRIPTION,
  COMPONENT_LABEL,
  COMPONENT_STATUS,
  crossingTitle,
  FLAG_LABEL,
  STATUS_LABEL,
} from "./labels";

type State =
  | { kind: "loading" }
  | { kind: "error" }
  | { kind: "ready"; detail: CrossingDetail };

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="kv">
      <dt>{label}</dt>
      <dd>{children}</dd>
    </div>
  );
}

function componentNote(c: NonNullable<CrossingDetail["priority"]>["components"][number]): string {
  const detail = c.detail as Record<string, string | number | null>;
  if (c.value === null) return String(detail.reason ?? "brak danych");
  if (c.component === "T")
    return `${Math.round(Number(detail.trains_per_day))} poc. × ok. ${Number(
      detail.vehicles_per_day_model,
    ).toLocaleString("pl-PL")} poj./dobę (model z klasy drogi)`;
  if (c.component === "P") return `kategoria ${detail.category}`;
  if (c.component === "G")
    return `torów: ${detail.tracks}${
      detail.angle_deg !== null && detail.angle_deg !== undefined
        ? `, kąt ${Math.round(Number(detail.angle_deg))}°`
        : ""
    }`;
  return "";
}

function PriorityBlock({ detail }: { detail: CrossingDetail }) {
  const p = detail.priority;
  if (detail.is_pedestrian)
    return (
      <p className="muted small">Przejścia dla pieszych nie są objęte rankingiem priorytetów.</p>
    );
  if (p === null)
    return (
      <p className="muted small">
        Brak wyniku priorytetu: analiza nie była jeszcze uruchomiona albo obiekt jest poza jej
        zakresem.
      </p>
    );
  return (
    <section className="priority" aria-label="Priorytet do dalszej oceny">
      <h4>Priorytet do dalszej oceny</h4>
      {p.rps === null ? (
        <p className="priority-none">
          <strong>Bez pozycji w rankingu</strong> — brakuje kluczowych danych (kompletność{" "}
          {Math.round(p.completeness_pct)}%).
        </p>
      ) : (
        <p className="priority-head">
          <span className="priority-score">{p.rps.toFixed(1)}</span>
          <span>
            <strong>
              pozycja {p.rank} z {p.ranked_total}
            </strong>
            <br />
            <span className="muted small">
              przy zmianie wag o ±20%: {p.rank_best}–{p.rank_worst} · kompletność{" "}
              {Math.round(p.completeness_pct)}%
            </span>
          </span>
        </p>
      )}
      <ul className="components">
        {p.components.map((c) => (
          <li key={c.component}>
            <div className="component-head">
              <span>
                {COMPONENT_LABEL[c.component]}{" "}
                <span className="muted">(waga {Math.round(c.weight * 100)}%)</span>
              </span>
              <span>{c.value === null ? "—" : Math.round(c.value)}</span>
            </div>
            <div
              className="bar"
              role="img"
              aria-label={
                c.value === null
                  ? `${COMPONENT_LABEL[c.component]}: brak danych`
                  : `${COMPONENT_LABEL[c.component]}: ${Math.round(c.value)} na 100`
              }
            >
              {c.value !== null && (
                <span
                  className={c.status === "modelled" ? "bar-fill bar-modelled" : "bar-fill"}
                  style={{ width: `${c.value}%` }}
                />
              )}
            </div>
            <div className="muted small">
              {COMPONENT_STATUS[c.status] ?? c.status}: {componentNote(c)}
            </div>
          </li>
        ))}
      </ul>
      <p className="muted small">
        To nie jest prognoza wypadków ani urzędowa klasyfikacja. Metoda {p.method_version}, wagi
        eksperymentalne.
      </p>
    </section>
  );
}

export function CrossingCard({ crossingId }: { crossingId: number }) {
  const [state, setState] = useState<State>({ kind: "loading" });

  useEffect(() => {
    const controller = new AbortController();
    setState({ kind: "loading" });
    fetchCrossingDetail(crossingId, controller.signal)
      .then((detail) => setState({ kind: "ready", detail }))
      .catch(() => {
        if (!controller.signal.aborted) setState({ kind: "error" });
      });
    return () => controller.abort();
  }, [crossingId]);

  if (state.kind === "loading") return <p className="muted">Wczytywanie szczegółów…</p>;
  if (state.kind === "error")
    return (
      <p className="alert" role="alert">
        Nie udało się wczytać szczegółów przejazdu.
      </p>
    );

  const d = state.detail;
  const shown = d.attributes
    .map((a) => ({ ...a, label: attributeLabel(a.code) }))
    .filter((a) => a.label !== null && a.value);
  const warnings = d.quality_flags.filter((f) => f.severity !== "info");
  const notes = d.quality_flags.filter((f) => f.severity === "info");

  return (
    <article aria-live="polite">
      <h3 className="card-title">
        {d.is_pedestrian ? "Przejście" : "Przejazd"} {crossingTitle(d)}
      </h3>
      <p className="card-sub">
        {d.category ? (
          <>
            Kategoria <strong>{d.category}</strong> — {CATEGORY_DESCRIPTION[d.category]}
          </>
        ) : (
          "Kategoria nieznana"
        )}
      </p>

      {warnings.length > 0 && (
        <ul className="warnings" aria-label="Ostrzeżenia o danych">
          {warnings.map((f) => (
            <li key={f.code}>
              <strong>! {FLAG_LABEL[f.code] ?? f.code}.</strong> {f.message}
            </li>
          ))}
        </ul>
      )}

      <PriorityBlock detail={d} />

      <dl>
        <Row label="Dzielnica">{d.district_name ?? "poza Warszawą"}</Row>
        <Row label="Status">
          {STATUS_LABEL[d.verification_status]}
          {d.verified_at ? ` (${d.verified_at.slice(0, 10)})` : ""}
        </Row>
        {shown.map((a) => (
          <Row key={`${a.code}-${a.source}`} label={a.label as string}>
            {a.value}
            {a.confidence === "probable" ? " (niepotwierdzone)" : ""}
          </Row>
        ))}
        <Row label="Współrzędne">
          {d.lat.toFixed(5)}, {d.lon.toFixed(5)}
        </Row>
      </dl>

      <h4>Droga</h4>
      {d.roads.length === 0 ? (
        <p className="muted small">
          {d.is_pedestrian ? "Nie dotyczy przejścia dla pieszych." : "Brak jezdni w danych."}
        </p>
      ) : (
        <ul className="plain">
          {d.roads.map((r, i) => (
            <li key={i}>
              {r.name ?? "droga bez nazwy"}
              <span className="muted"> — {[r.road_class, r.management].filter(Boolean).join(", ")}</span>
            </li>
          ))}
        </ul>
      )}

      <h4>Tory</h4>
      {d.tracks.length === 0 ? (
        <p className="muted small">Brak toru w danych.</p>
      ) : (
        <ul className="plain">
          {d.tracks.map((t, i) => (
            <li key={i}>
              {t.line_number ? `linia ${t.line_number}, ` : ""}
              {t.track_function ?? "tor"}
              <span className="muted">
                {" "}
                — {[t.track_count ? `torów: ${t.track_count}` : null, t.existence]
                  .filter(Boolean)
                  .join(", ")}
              </span>
            </li>
          ))}
        </ul>
      )}

      <h4>Ruch kolejowy (plan)</h4>
      {d.rail_flow === null ? (
        <p className="muted small">Brak danych rozkładowych dla tego obiektu.</p>
      ) : (
        <>
          <dl>
            <Row label="Dzień roboczy">
              <strong>{Math.round(d.rail_flow.weekday_avg)}</strong> pociągów pasażerskich na dobę
            </Row>
            <Row label="Sobota">{d.rail_flow.saturday ?? "brak danych"}</Row>
            <Row label="Niedziela">{d.rail_flow.sunday ?? "brak danych"}</Row>
          </dl>
          <p className="muted small">
            Rozkład planowy, tydzień {d.rail_flow.period_start} – {d.rail_flow.period_end}. Tylko
            pociągi pasażerskie
            {d.rail_flow.weekday_avg === 0
              ? "; zero nie oznacza braku ruchu towarowego lub manewrowego."
              : "; bez towarowych i służbowych."}
          </p>
        </>
      )}


      {notes.length > 0 && (
        <>
          <h4>Uwagi</h4>
          <ul className="plain small">
            {notes.map((f) => (
              <li key={f.code}>
                {FLAG_LABEL[f.code] ?? f.code}
                {f.message ? ` — ${f.message}` : ""}
              </li>
            ))}
          </ul>
        </>
      )}

      <h4>Źródła</h4>
      <ul className="plain small">
        {d.sources.map((s) => (
          <li key={s.name}>
            {s.name}
            {s.license_verified ? "" : " (warunki wykorzystania niepotwierdzone)"}
          </li>
        ))}
      </ul>
    </article>
  );
}
