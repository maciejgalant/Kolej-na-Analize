import { useEffect, useState } from "react";
import { fetchIncidentHistory, type IncidentHistoryData } from "./api";

export function IncidentHistory({ crossingId, compact = false }: { crossingId?: number; compact?: boolean }) {
  const [data, setData] = useState<IncidentHistoryData | null>(null);
  const [error, setError] = useState(false);
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    const controller = new AbortController();
    setData(null);
    setError(false);
    fetchIncidentHistory(crossingId, controller.signal)
      .then((result) => { if (!controller.signal.aborted) setData(result); })
      .catch(() => {
        if (!controller.signal.aborted) setError(true);
      });
    return () => controller.abort();
  }, [crossingId, attempt]);
  if (error)
    return (
      <p role="alert">
        Nie udało się wczytać historii SEWiK.{" "}
        <button onClick={() => setAttempt((n) => n + 1)}>
          Spróbuj ponownie
        </button>
      </p>
    );
  if (!data) return <p role="status">Wczytywanie wykazu SEWiK…</p>;
  const candidates = data.scope === "street_candidates";
  if (compact) return <CompactHistory data={data} />;
  return (
    <section className="incident-history" aria-label="Historia zdarzeń SEWiK">
      <p className="small">
        <strong>SEWiK · częściowy wykaz</strong>
      </p>
      {candidates && (
        <p className="small">
          Poniższe wpisy pasują nazwą ulicy. Nie potwierdzono, że dotyczą tego
          przejazdu. Nie są używane w RPS.
        </p>
      )}
      {!data.records.length ? (
        <p className="muted small">
          Nie znaleziono pasujących wpisów w tym częściowym wykazie. Nie oznacza
          to braku wypadków.
        </p>
      ) : (
        <>
          <p className="small">
            {candidates
              ? "Wpisy z pasujących ulic"
              : "Widoczne wpisy dla Warszawy"}
            : <strong>{data.records.length}</strong>
          </p>
          <ol className="incident-list">
            {data.records.map((r) => (
              <li key={r.source_object_id}>
                <strong>
                  {r.occurred_on.split("-").reverse().join(".")} ·{" "}
                  {r.local_time}
                </strong>
                <span>{r.address}</span>
                <span>
                  {r.incident_type} · {r.place}
                </span>
                <span>
                  {r.injured === null
                    ? "Ranni: brak informacji"
                    : `Ranni: ${r.injured}`}{" "}
                  · Zabici: {r.killed === null ? "brak informacji" : r.killed}
                </span>
                <small>
                  SEWiK ID {r.source_object_id} · lokalizacja do weryfikacji
                </small>
              </li>
            ))}
          </ol>
        </>
      )}
      <p className="muted small">{data.notice}</p>
      <a href={data.source_url} target="_blank" rel="noreferrer">
        Źródło: SEWiK / sewik.pl ↗
      </a>
    </section>
  );
}

function CompactHistory({ data }: { data: IncidentHistoryData }) {
  const years = [...new Set(data.records.map(r => r.occurred_on.slice(0, 4)))].sort();
  const yearly = years.map(year => ({
    year, count: data.records.filter(r => r.occurred_on.startsWith(year)).length,
  }));
  const maximum = Math.max(1, ...yearly.map(y => y.count));
  return <section className="incident-history incident-compact" aria-label="Historia zdarzeń SEWiK">
    <div className="history-total">
      <strong>{data.records.length || "—"}</strong>
      <span>{data.records.length ? "wpisy z pasujących ulic" : "brak dopasowanych wpisów"}</span>
    </div>
    <p className="muted small">Częściowy wykaz. Nie potwierdzono, że dotyczą tego przejazdu. Bez punktacji H.</p>
    {!!yearly.length && <>
      <p className="history-chart-caption">Liczba wpisów w wykazie według roku</p>
      <div className="history-year-chart" role="img"
        aria-label={`Wpisy z pasujących ulic według roku: ${yearly.map(y => `${y.year}: ${y.count}`).join("; ")}. Pominięte lata nie oznaczają zera zdarzeń.`}>
        {yearly.map(y => <div key={y.year}>
          <strong>{y.count}</strong>
          <span className="history-year-track"><i style={{ height: `${100 * y.count / maximum}%` }} /></span>
          <small>{y.year}</small>
        </div>)}
      </div>
    </>}
    <details className="supporting-data history-details">
      <summary>Dane dodatkowe · wpisy i źródło</summary>
      {!data.records.length && <p className="small">Brak wpisów w tym wykazie nie oznacza braku wypadków.</p>}
      <ol className="incident-list">{data.records.map(r => <li key={r.source_object_id}>
        <strong>{r.occurred_on.split("-").reverse().join(".")} · {r.local_time}</strong>
        <span>{r.address}</span>
        <span>{r.incident_type} · {r.place}</span>
        <span>{r.injured === null ? "Ranni: brak informacji" : `Ranni: ${r.injured}`} · Zabici: {r.killed === null ? "brak informacji" : r.killed}</span>
        <small>SEWiK ID {r.source_object_id} · lokalizacja do weryfikacji</small>
      </li>)}</ol>
      <p className="muted small">{data.notice}</p>
      <a href={data.source_url} target="_blank" rel="noreferrer">Źródło: SEWiK / sewik.pl ↗</a>
    </details>
  </section>;
}
