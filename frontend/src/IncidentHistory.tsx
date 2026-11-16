import { useEffect, useState } from "react";
import { fetchIncidentHistory, type IncidentHistoryData } from "./api";

export function IncidentHistory({ crossingId }: { crossingId?: number }) {
  const [data, setData] = useState<IncidentHistoryData | null>(null);
  const [error, setError] = useState(false);
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    const controller = new AbortController();
    setData(null);
    setError(false);
    fetchIncidentHistory(crossingId, controller.signal)
      .then(setData)
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
