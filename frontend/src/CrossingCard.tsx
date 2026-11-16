import { useEffect, useState } from "react";

import { type CrossingDetail, fetchCrossingDetail, type RoadCount } from "./api";
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

function Row({
  label,
  children,
}: {
  label: string;
  children: React.ReactNode;
}) {
  return (
    <div className="kv">
      <dt>{label}</dt>
      <dd>{children}</dd>
    </div>
  );
}

function Section({
  title,
  summary,
  open = false,
  children,
}: {
  title: string;
  summary?: string;
  open?: boolean;
  children: React.ReactNode;
}) {
  return (
    <details className="section" open={open}>
      <summary>
        <span className="section-title">{title}</span>
        {summary && <span className="section-summary">{summary}</span>}
      </summary>
      <div className="section-body">{children}</div>
    </details>
  );
}

export function CardSkeleton() {
  return (
    <div
      className="skeleton-card"
      role="status"
      aria-label="Wczytywanie szczegółów"
    >
      <span className="skeleton skeleton-title" />
      <span className="skeleton skeleton-line" />
      <span className="skeleton skeleton-block" />
      <span className="skeleton skeleton-line" />
      <span className="skeleton skeleton-line skeleton-short" />
    </div>
  );
}

function componentNote(
  c: NonNullable<CrossingDetail["priority"]>["components"][number],
): string {
  const detail = c.detail as Record<string, string | number | null>;
  if (c.value === null) return String(detail.reason ?? "brak danych");
  if (c.component === "T") {
    const trains = `${Math.round(Number(detail.trains_per_day))} poc.`;
    if (detail.vehicles_source === "measured") {
      const m = (c.detail as { measurement?: Record<string, string | number> })
        .measurement;
      const where = m
        ? `, ul. ${m.street}, punkt ${Math.round(Number(m.distance_m))} m od przejazdu, ${m.period_start} – ${m.period_end}`
        : "";
      const label =
        m?.source === "zdm_apr" ? "pomiar ZDM" : "pomiar fikcyjny (demo)";
      return `${trains} × ${Number(detail.vehicles_per_day_measured).toLocaleString(
        "pl-PL",
      )} poj./dobę (${label}${where}; model z klasy drogi: ${Number(
        detail.vehicles_per_day_model,
      ).toLocaleString("pl-PL")})`;
    }
    return `${trains} × ok. ${Number(detail.vehicles_per_day_model).toLocaleString(
      "pl-PL",
    )} poj./dobę (model z klasy drogi)`;
  }
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
      <p className="muted small">
        Przejścia dla pieszych nie są objęte rankingiem priorytetów.
      </p>
    );
  if (p === null)
    return (
      <p className="muted small">
        Brak wyniku priorytetu: analiza nie była jeszcze uruchomiona albo obiekt
        jest poza jej zakresem.
      </p>
    );
  return (
    <>
      <section className="priority" aria-label="Priorytet do dalszej oceny">
        {p.rps === null ? (
          <p className="priority-none">
            <strong>Bez pozycji w rankingu</strong>
            <br />
            <span className="muted small">
              brakuje kluczowych danych (kompletność{" "}
              {Math.round(p.completeness_pct)}%)
            </span>
          </p>
        ) : (
          <p className="priority-head">
            <span className="priority-score">{p.rps.toFixed(1)}</span>
            <span>
              <span className="priority-label">
                Priorytet do dalszej oceny (RPS)
              </span>
              <strong>
                pozycja {p.rank} z {p.ranked_total}
              </strong>
            </span>
          </p>
        )}
      </section>
      <Section title="Skąd ten wynik" summary="składniki priorytetu" open>
        <ul className="components">
          {p.components.map((c) => (
            <li key={c.component}>
              <div className="component-head">
                <span>
                  {COMPONENT_LABEL[c.component]}{" "}
                  <span className="muted">
                    (waga {Math.round(c.weight * 100)}%)
                  </span>
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
                    className={
                      c.status === "modelled"
                        ? "bar-fill bar-modelled"
                        : "bar-fill"
                    }
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
          {p.rps !== null &&
            (p.rank_best === p.rank_worst
              ? "Przy zmianie wag o ±20% pozycja się nie zmienia. "
              : `Przy zmianie wag o ±20% pozycja mieści się w zakresie ${p.rank_best}–${p.rank_worst}. `)}
          Kompletność danych {Math.round(p.completeness_pct)}%. To nie jest
          prognoza wypadków ani urzędowa klasyfikacja; metoda {p.method_version}
          , wagi eksperymentalne.
        </p>
      </Section>
    </>
  );
}

const pl = (value: number) => value.toLocaleString("pl-PL");
const fmt1 = (value: number | null) =>
  value === null ? "—" : value.toLocaleString("pl-PL", { maximumFractionDigits: 1 });

/** Pociągi w każdej godzinie dnia roboczego; tło = szczyt drogowy, linia = ruch drogowy. */
function DayProfile({
  trains,
  peaks,
  road,
}: {
  trains: number[];
  peaks: number[];
  road: number[] | null;
}) {
  const W = 288;
  const H = 96;
  const pad = { l: 22, b: 16, t: 6 };
  const plotH = H - pad.b - pad.t;
  const bar = (W - pad.l) / 24;
  const max = Math.max(1, ...trains);
  const roadMax = road ? Math.max(1, ...road) : 1;
  const y = (v: number) => pad.t + plotH - (v / max) * plotH;
  const roadPath = road
    ?.map(
      (v, h) =>
        `${h === 0 ? "M" : "L"}${(pad.l + bar * (h + 0.5)).toFixed(1)},${(
          pad.t + plotH - (v / roadMax) * plotH
        ).toFixed(1)}`,
    )
    .join(" ");
  const label = trains
    .map((v, h) => (v > 0 ? `${h}:00 ${fmt1(v)}` : null))
    .filter(Boolean)
    .join(", ");
  return (
    <figure className="day-profile">
      <svg
        viewBox={`0 0 ${W} ${H}`}
        role="img"
        aria-label={`Pociągi w kolejnych godzinach dnia roboczego: ${label}`}
      >
        {peaks.map((h) => (
          <rect
            key={`p${h}`}
            x={pad.l + bar * h}
            y={pad.t}
            width={bar}
            height={plotH}
            className="day-profile-peak"
          />
        ))}
        {[0, max].map((v) => (
          <text key={v} x={pad.l - 4} y={y(v) + 3} className="day-profile-axis" textAnchor="end">
            {fmt1(v)}
          </text>
        ))}
        {trains.map((v, h) => (
          <rect
            key={h}
            x={pad.l + bar * h + 1}
            y={y(v)}
            width={bar - 2}
            height={Math.max(0, pad.t + plotH - y(v))}
            rx={1.5}
            className="day-profile-bar"
          >
            <title>{`${h}:00–${h + 1}:00: ${fmt1(v)} poc.`}</title>
          </rect>
        ))}
        {roadPath && <path d={roadPath} className="day-profile-road" />}
        {[0, 6, 12, 18, 23].map((h) => (
          <text
            key={`x${h}`}
            x={pad.l + bar * (h + 0.5)}
            y={H - 4}
            className="day-profile-axis"
            textAnchor="middle"
          >
            {h}
          </text>
        ))}
      </svg>
      <figcaption className="day-profile-legend">
        <span>
          <i className="swatch swatch-bar" /> pociągi/h (dzień roboczy)
        </span>
        <span>
          <i className="swatch swatch-peak" /> szczyt drogowy
        </span>
        {road && (
          <span>
            <i className="swatch swatch-road" /> ruch drogowy (licznik ZDM, skala względna)
          </span>
        )}
      </figcaption>
    </figure>
  );
}

function RoadCountItem({ count: r }: { count: RoadCount }) {
  const who = r.is_demo ? "Pomiar fikcyjny (demo)" : "ZDM";
  if (r.kind === "intersection")
    return (
      <li>
        <strong>Skrzyżowanie {r.name}</strong>
        <span className="muted"> — {Math.round(r.distance_m)} m od przejazdu</span>
        <br />
        {r.peak_vehicles !== null && (
          <>
            w szczycie {pl(r.peak_vehicles)} poj./h ({r.peak_hour}, całe skrzyżowanie)
          </>
        )}
        {r.heavy_share !== null && (
          <>, ciężarowe i autobusy {Math.round(r.heavy_share * 100)}%</>
        )}
        {r.pedestrians_max !== null && <>, piesi do {pl(r.pedestrians_max)}/h</>}
        {r.cyclists_max !== null && <>, rowerzyści do {pl(r.cyclists_max)}/h</>}
        <span className="muted small">
          {" "}
          · {who}, pomiar {r.measured_on} ({r.hours} godz.); nie zmienia rankingu
        </span>
      </li>
    );
  return (
    <li>
      <strong>Licznik {r.name}</strong>
      <span className="muted"> — {Math.round(r.distance_m)} m od przejazdu</span>
      <br />
      {r.vehicles_per_day !== null
        ? `${pl(r.vehicles_per_day)} poj./dobę (oba kierunki${r.day_type ? `, dni: ${r.day_type}` : ""})`
        : "brak pomiaru w okresie"}
      <span className="muted small">
        {" "}
        · {who}, {r.period_start} – {r.period_end};{" "}
        {r.match_type === "direct" ? "użyty w rankingu" : "tylko do porównania"}
      </span>
    </li>
  );
}

export function CrossingCard({
  crossingId,
  street = null,
  onClose,
}: {
  crossingId: number;
  street?: string | null;
  /** Bez tej funkcji karta nie ma własnego przycisku zamknięcia (zamyka okno). */
  onClose?: () => void;
}) {
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

  const close = onClose && (
    <button
      type="button"
      className="icon-button"
      onClick={onClose}
      aria-label="Zamknij szczegóły"
    >
      ×
    </button>
  );

  if (state.kind === "loading")
    return (
      <article>
        <header className="card-head">
          <span className="muted">Wczytywanie…</span>
          {close}
        </header>
        <CardSkeleton />
      </article>
    );
  if (state.kind === "error")
    return (
      <article>
        <header className="card-head">
          <span />
          {close}
        </header>
        <p className="alert" role="alert">
          Nie udało się wczytać szczegółów przejazdu.
        </p>
      </article>
    );

  const d = state.detail;
  const shown = d.attributes
    .map((a) => ({ ...a, label: attributeLabel(a.code) }))
    .filter((a) => a.label !== null && a.value);
  const warnings = d.quality_flags.filter((f) => f.severity !== "info");
  const notes = d.quality_flags.filter((f) => f.severity === "info");
  const unverifiedSources = d.sources.filter((s) => !s.license_verified).length;

  return (
    <article aria-live="polite" className="card-enter" key={d.crossing_id}>
      <header className="card-head">
        <div>
          <h3 className="card-title">
            {street ?? `${d.is_pedestrian ? "Przejście" : "Przejazd"} ${crossingTitle(d)}`}
          </h3>
          {street && (
            <p className="card-number">
              {d.is_pedestrian ? "przejście" : "przejazd"} nr {crossingTitle(d)}
            </p>
          )}
          <p className="card-sub">
            <span className="tag">kat. {d.category ?? "?"}</span>
            {d.category
              ? CATEGORY_DESCRIPTION[d.category]
              : "kategoria nieznana"}
          </p>
        </div>
        {close}
      </header>

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

      <Section
        title="Ruch kolejowy"
        summary={
          d.rail_flow === null
            ? "brak danych"
            : `${Math.round(d.rail_flow.weekday_avg)} poc./dobę (plan)`
        }
      >
        {d.rail_flow === null ? (
          <p className="muted small">
            Brak danych rozkładowych dla tego obiektu.
          </p>
        ) : (
          <>
            <dl>
              <Row label="Dzień roboczy">
                <strong>{Math.round(d.rail_flow.weekday_avg)}</strong> pociągów
                pasażerskich na dobę
              </Row>
              <Row label="Sobota">{d.rail_flow.saturday ?? "brak danych"}</Row>
              <Row label="Niedziela">{d.rail_flow.sunday ?? "brak danych"}</Row>
            </dl>
            {d.rail_flow.hourly_weekday && (
              <DayProfile
                trains={d.rail_flow.hourly_weekday}
                peaks={d.rail_flow.road_peak_hours ?? []}
                road={
                  d.road_counts.find((r) => r.match_type === "direct")
                    ?.hourly_profile ?? null
                }
              />
            )}
            {d.rail_flow.hourly_weekday && d.rail_flow.max_hour !== null && (
              <p className="small">
                Najwięcej pociągów: <strong>{fmt1(d.rail_flow.max_per_hour)}</strong>{" "}
                w godzinie {d.rail_flow.max_hour}:00–{d.rail_flow.max_hour + 1}:00. W
                godzinach szczytu drogowego (
                {d.rail_flow.road_peak_source === "zdm"
                  ? "według licznika ZDM"
                  : "przyjęte 7–9 i 15–18"}
                ): <strong>{fmt1(d.rail_flow.in_road_peaks)}</strong> z{" "}
                {Math.round(d.rail_flow.weekday_avg)} (
                {d.rail_flow.weekday_avg > 0
                  ? Math.round(
                      (100 * (d.rail_flow.in_road_peaks ?? 0)) /
                        d.rail_flow.weekday_avg,
                    )
                  : 0}
                %). Nocą (22–6): {fmt1(d.rail_flow.at_night)}.
              </p>
            )}
            <p className="muted small">
              Rozkład planowy, tydzień {d.rail_flow.period_start} –{" "}
              {d.rail_flow.period_end}. Tylko pociągi pasażerskie
              {d.rail_flow.weekday_avg === 0
                ? "; zero nie oznacza braku ruchu towarowego lub manewrowego."
                : "; bez towarowych i służbowych."}
            </p>
          </>
        )}
      </Section>

      <Section
        title="Droga i tory"
        summary={[
          d.roads[0]?.name ?? (d.roads.length ? "droga bez nazwy" : null),
          d.tracks.length ? `odcinków toru: ${d.tracks.length}` : null,
          d.road_counts.length ? "pomiary ruchu" : null,
        ]
          .filter(Boolean)
          .join(" · ")}
      >
        <h4>Droga</h4>
        {d.roads.length === 0 ? (
          <p className="muted small">
            {d.is_pedestrian
              ? "Nie dotyczy przejścia dla pieszych."
              : "Brak jezdni w danych."}
          </p>
        ) : (
          <ul className="plain">
            {d.roads.map((r, i) => (
              <li key={i}>
                {r.name ?? "droga bez nazwy"}
                <span className="muted">
                  {" "}
                  — {[r.road_class, r.management].filter(Boolean).join(", ")}
                </span>
              </li>
            ))}
          </ul>
        )}
        {d.road_counts.length > 0 && (
          <>
            <h4>Pomiary ruchu drogowego</h4>
            <ul className="plain road-counts">
              {d.road_counts.map((r) => (
                <RoadCountItem key={`${r.source}-${r.station_id}`} count={r} />
              ))}
            </ul>
          </>
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
                  —{" "}
                  {[
                    t.track_count ? `torów: ${t.track_count}` : null,
                    t.existence,
                  ]
                    .filter(Boolean)
                    .join(", ")}
                </span>
              </li>
            ))}
          </ul>
        )}
      </Section>

      <Section
        title="Dane ewidencyjne"
        summary={d.district_name ?? "poza Warszawą"}
      >
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
      </Section>

      <Section
        title="Źródła i uwagi"
        summary={
          unverifiedSources > 0
            ? `${d.sources.length} źródeł, ${unverifiedSources} bez potwierdzonych warunków`
            : `${d.sources.length} źródeł`
        }
      >
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
              {s.license_verified
                ? ""
                : " (warunki wykorzystania niepotwierdzone)"}
            </li>
          ))}
        </ul>
      </Section>
    </article>
  );
}
