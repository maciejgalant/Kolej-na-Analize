import { useEffect, useRef, useState } from "react";

type Station = { id: number; name: string | null };
type Stop = {
  stationId: number;
  plannedArrival?: string | null;
  plannedDeparture?: string | null;
  actualArrival?: string | null;
  actualDeparture?: string | null;
  arrivalDelayMinutes?: number | null;
  departureDelayMinutes?: number | null;
  isConfirmed?: boolean;
  isCancelled?: boolean;
};
type Train = {
  scheduleId: number;
  orderId: number;
  operatingDate: string;
  trainStatus?: string | null;
  stations?: Stop[] | null;
};
type Envelope<T> = { source: string; fetched_at: string; cached: boolean; data: T };
type Operations = Envelope<{
  generatedAt?: string;
  trains: Train[] | null;
  pagination?: { totalPages?: number };
}>;
type Disruptions = Envelope<{
  generatedAt?: string;
  disruptions: { disruptionId: number; message?: string | null }[] | null;
}>;

async function get<T>(path: string, signal: AbortSignal): Promise<T> {
  const response = await fetch(`/api/v1/rail/${path}`, { signal });
  if (!response.ok) {
    const body = await response.json().catch(() => null);
    throw new Error(body?.detail?.message ?? "Nie udało się pobrać danych kolejowych.");
  }
  return response.json();
}

// Keep station wall time intact; do not reinterpret it in the browser's timezone.
function stationTime(value?: string | null) {
  return value ? value.replace("T", " ").slice(0, 16) : "brak danych";
}
const STATUS: Record<string, string> = {
  S: "nierozpoczęty", P: "w trasie", C: "zakończony",
  X: "odwołany", Q: "częściowo odwołany",
};

export function RailPanel() {
  const [configured, setConfigured] = useState<boolean | null>(null);
  const [search, setSearch] = useState("Warszawa");
  const [stations, setStations] = useState<Station[]>([]);
  const [station, setStation] = useState("");
  const [operations, setOperations] = useState<Operations | null>(null);
  const [disruptions, setDisruptions] = useState<Disruptions | null>(null);
  const [page, setPage] = useState(1);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const request = useRef<AbortController | null>(null);
  useEffect(() => {
    const controller = new AbortController();
    get<{ configured: boolean }>("status", controller.signal)
      .then((data) => setConfigured(data.configured))
      .catch(() => { if (!controller.signal.aborted) setError("Nie można sprawdzić połączenia PKP PLK."); });
    return () => { controller.abort(); request.current?.abort(); };
  }, []);

  async function load(kind: "stations" | "operations" | "disruptions", nextPage = 1) {
    request.current?.abort();
    const controller = new AbortController();
    request.current = controller;
    setBusy(true); setError("");
    try {
      if (kind === "stations") {
        setOperations(null); setDisruptions(null); setStations([]); setStation("");
        const result = await get<Envelope<{ stations: Station[] | null }>>(
          `stations?search=${encodeURIComponent(search.trim())}`, controller.signal);
        setStations(result.data.stations ?? []);
        if (!result.data.stations?.length) setError("Nie znaleziono stacji.");
      } else if (kind === "operations") {
        setOperations(null);
        const result = await get<Operations>(
          `operations?station_id=${station}&page=${nextPage}`, controller.signal);
        setOperations(result); setPage(nextPage);
      } else {
        setDisruptions(null);
        setDisruptions(await get<Disruptions>(`disruptions?station_id=${station}`, controller.signal));
      }
    } catch (e) {
      if (!controller.signal.aborted) setError(e instanceof Error ? e.message : "Błąd połączenia.");
    } finally {
      if (!controller.signal.aborted) setBusy(false);
    }
  }

  return <div className="rail-panel">
    <p>Aktualna realizacja pociągów pasażerskich i utrudnienia. Źródło: PKP Polskie Linie Kolejowe S.A.</p>
    <p className="muted">Dane dotyczą stacji. Nie potwierdzają przejazdu przez konkretny przejazd kolejowo-drogowy i nie zmieniają RPS. Są rzeczywiste również przy otwartym zestawie demonstracyjnym.</p>
    {configured === null && !error && <p role="status">Sprawdzanie konfiguracji…</p>}
    {configured === false && <p role="status">Integracja jest wyłączona. Ustaw PLK_API_KEY w lokalnym pliku .env i odtwórz kontener backendu.</p>}
    {configured && <>
      <form onSubmit={(e) => { e.preventDefault(); void load("stations"); }}>
        <label>Stacja — początek nazwy <input value={search} minLength={2} maxLength={80} onChange={(e) => setSearch(e.target.value)} /></label>{" "}
        <button disabled={busy || search.trim().length < 2}>Szukaj stacji</button>
      </form>
      {stations.length > 0 && <p><label>Wybierz stację <select value={station} disabled={busy} onChange={(e) => {
        setStation(e.target.value); setOperations(null); setDisruptions(null); setPage(1); setError("");
      }}><option value="">Wybierz…</option>{stations.map((s) => <option key={s.id} value={s.id}>{s.name ?? s.id}</option>)}</select></label></p>}
      {station && <p className="rail-actions">
        <button disabled={busy} onClick={() => void load("operations")}>Pobierz realizację kursów</button>{" "}
        <button disabled={busy} onClick={() => void load("disruptions")}>Pobierz utrudnienia</button>
      </p>}
    </>}
    {busy && <p role="status">Pobieranie danych PKP PLK…</p>}
    {error && <p className="alert" role="alert">{error}</p>}
    {operations && <section>
      <h3>Realizacja kursów — strona {page}</h3>
      <p className="muted">Wygenerowano: {operations.data.generatedAt ?? "brak daty źródłowej"}. Pobrano: {operations.fetched_at}. {operations.cached ? "Kopia z pamięci serwera (do 5 minut)." : "Pobrano z API."} Czasy stacji w Polsce: Europe/Warsaw.</p>
      <div className="rail-table"><table><thead><tr><th>Kurs / data</th><th>Status</th><th>Plan przyjazdu / odjazdu</th><th>Wykonanie przyjazdu / odjazdu</th><th>Opóźnienie przyjazdu / odjazdu</th></tr></thead>
        <tbody>{(operations.data.trains ?? []).flatMap((train) => (train.stations ?? [])
          .filter((s) => s.stationId === Number(station))
          .map((s, index) => <tr key={`${train.scheduleId}-${train.orderId}-${train.operatingDate}-${index}`}>
            <td>{train.orderId}<br />{train.operatingDate}<small> ID kursu</small></td>
            <td>{s.isCancelled ? "odwołany na stacji" : STATUS[train.trainStatus ?? ""] ?? "nieznany"}<br />{s.isConfirmed ? "potwierdzony na stacji" : "bez potwierdzenia na stacji"}</td>
            <td>{stationTime(s.plannedArrival)}<br />{stationTime(s.plannedDeparture)}</td>
            <td>{stationTime(s.actualArrival)}<br />{stationTime(s.actualDeparture)}</td>
            <td>{s.arrivalDelayMinutes == null ? "brak danych" : `${s.arrivalDelayMinutes} min`}<br />{s.departureDelayMinutes == null ? "brak danych" : `${s.departureDelayMinutes} min`}</td>
          </tr>))}</tbody></table></div>
      {!operations.data.trains?.length && <p>Brak kursów w odpowiedzi API dla tej strony. Nie oznacza to braku ruchu na linii.</p>}
      <p><button disabled={busy || page <= 1} onClick={() => void load("operations", page - 1)}>Poprzednia strona</button>{" "}
        <button disabled={busy || page >= (operations.data.pagination?.totalPages ?? page)} onClick={() => void load("operations", page + 1)}>Następna strona</button></p>
    </section>}
    {disruptions && <section><h3>Utrudnienia</h3>
      <p className="muted">Wygenerowano: {disruptions.data.generatedAt ?? "brak daty źródłowej"}. Pobrano: {disruptions.fetched_at}. {disruptions.cached ? "Kopia z pamięci serwera (do 5 minut)." : "Pobrano z API."}</p>
      {disruptions.data.disruptions?.length ? <ul>{disruptions.data.disruptions.map((d) => <li key={d.disruptionId}>{d.message ?? "Brak opisu utrudnienia."}</li>)}</ul> : <p>Brak zgłoszonych utrudnień w odpowiedzi API.</p>}
    </section>}
  </div>;
}
