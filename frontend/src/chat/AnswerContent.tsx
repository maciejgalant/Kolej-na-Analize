import type { Evidence } from "./model";
const value = (v: number | string | null) =>
  v === null
    ? "Brak danych"
    : typeof v === "number"
      ? v.toLocaleString("pl-PL", { maximumFractionDigits: 1 })
      : v;
const statusLabel = (s: string) =>
  ({
    ok: "dane dostępne",
    modelled: "modelowane",
    unknown: "brak danych",
    planned: "rozkład pasażerski",
    measured: "pomiar",
  })[s] ?? s;
/** React escapes all text. No HTML or arbitrary actions from the model. */
export function AnswerText({ text }: { text: string }) {
  return (
    <div className="answer-text">
      {text.split(/\n\s*\n/).map((p, i) => (
        <p key={i}>
          {p
            .split(/(\*\*[^*]+\*\*)/g)
            .map((part, j) =>
              part.startsWith("**") ? (
                <strong key={j}>{part.slice(2, -2)}</strong>
              ) : (
                part
              ),
            )}
        </p>
      ))}
    </div>
  );
}
export function AnswerContent({
  evidence,
  onMap,
  onCard,
}: {
  evidence?: Evidence;
  onMap: (ids: number[]) => void;
  onCard: (id: number) => void;
}) {
  if (!evidence) return null;
  return (
    <div className="answer-results">
      {evidence.cards.length > 0 && (
        <div className="result-cards">
          {evidence.cards.map((c) => (
            <button
              className="result-card"
              key={c.crossing_id}
              onClick={() => onCard(c.crossing_id)}
            >
              <span className="eyebrow">
                PRZEJAZD · {c.district ?? "Brak dzielnicy"}
              </span>
              <strong>{c.title}</strong>
              <span>
                Kategoria {c.category ?? "nieznana"} ·{" "}
                {c.rank === null ? "Poza rankingiem" : `Pozycja ${c.rank}`}
              </span>
              <span className="card-metrics">
                <span>
                  RPS <b>{value(c.rps)}</b>
                </span>
                <span>
                  Pociągi / dzień roboczy <b>{value(c.trains)}</b>
                </span>
              </span>
              <span className="result-link">Otwórz szczegóły ↗</span>
            </button>
          ))}
        </div>
      )}
      {evidence.tables.map((t, i) => (
        <div className="result-table-wrap" key={i}>
          <table className="result-table">
            <caption>{t.title}</caption>
            <thead>
              <tr>
                {t.columns.map((c, j) => (
                  <th key={j} scope="col">
                    {c}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {t.rows.map((r, j) => (
                <tr key={j}>
                  {r.map((v, k) => (
                    <td key={k}>{value(v)}</td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ))}
      {evidence.charts.map((chart, i) => {
        const maximum =
          chart.unit === "pkt / 100"
            ? 100
            : Math.max(1, ...chart.points.map((p) => p.value ?? 0));
        return (
          <figure className="result-chart" key={i}>
            <figcaption>
              {chart.title}
              <small>{chart.unit}</small>
            </figcaption>
            <div
              className="chart-bars"
              role="img"
              aria-label={`${chart.title}. ${chart.points.map((p) => `${p.label}: ${value(p.value)} (${statusLabel(p.status)})`).join("; ")}`}
            >
              {chart.points.map((p, j) => (
                <div className="chart-row" key={j}>
                  <span className="chart-label">
                    {p.label}
                    <small>{statusLabel(p.status)}</small>
                  </span>
                  <span className="chart-track">
                    <span
                      className={
                        p.status === "modelled"
                          ? "chart-fill modelled"
                          : "chart-fill"
                      }
                      style={{
                        width: `${Math.max(0, Math.min(100, ((p.value ?? 0) / maximum) * 100))}%`,
                      }}
                    />
                  </span>
                  <b>{value(p.value)}</b>
                </div>
              ))}
            </div>
            <details>
              <summary>Wartości wykresu</summary>
              <table className="result-table">
                <thead>
                  <tr>
                    <th>Pozycja</th>
                    <th>Wartość ({chart.unit})</th>
                    <th>Status</th>
                  </tr>
                </thead>
                <tbody>
                  {chart.points.map((p, j) => (
                    <tr key={j}>
                      <td>{p.label}</td>
                      <td>{value(p.value)}</td>
                      <td>{statusLabel(p.status)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </details>
          </figure>
        );
      })}
      {evidence.map_ids.length > 0 && (
        <button
          className="map-answer-button"
          onClick={() => onMap(evidence.map_ids)}
        >
          ↗ Pokaż na mapie <span>{evidence.map_ids.length}</span>
        </button>
      )}
      {(evidence.sources.length > 0 || evidence.notes.length > 0) && (
        <details className="answer-evidence">
          <summary>Źródła danych i wyjaśnienie wyniku</summary>
          {evidence.sources.length > 0 && (
            <>
              <h4>Sprawdzone źródła</h4>
              <ul>
                {evidence.sources.map((s, i) => (
                  <li key={i}>{s}</li>
                ))}
              </ul>
            </>
          )}
          {evidence.notes.length > 0 && (
            <>
              <h4>Wyjaśnienia i ograniczenia</h4>
              <ul>
                {evidence.notes.map((s, i) => (
                  <li key={i}>{s}</li>
                ))}
              </ul>
            </>
          )}
        </details>
      )}
    </div>
  );
}
