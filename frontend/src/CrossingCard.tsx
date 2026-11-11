import { useEffect, useState } from "react";

import { type CrossingDetail, fetchCrossingDetail } from "./api";
import {
  attributeLabel,
  CATEGORY_DESCRIPTION,
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

      <h4>Ruch i priorytet</h4>
      <p className="muted small">
        Brak danych: liczba pociągów, natężenie ruchu drogowego i wskaźnik priorytetu pojawią się
        po kolejnych zadaniach (RSA-006 – RSA-010).
      </p>

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
