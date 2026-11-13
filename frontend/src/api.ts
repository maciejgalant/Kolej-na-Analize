export type ServiceState = "ok" | "unavailable";

export interface Health {
  status: "ok" | "degraded";
  version: string;
  demo_mode: boolean;
  services: {
    database: {
      status: ServiceState;
      postgis_version: string | null;
      schema_revision: string | null;
      demo_data?: boolean;
    };
    ollama: { status: ServiceState; model: string; model_available: boolean };
  };
}

export type Category = "A" | "B" | "C" | "D" | "E" | "F";
export type VerificationStatus =
  "verified" | "unverified" | "rejected_grade_separated" | "rejected_other";

export interface DistrictProperties {
  district_id: number;
  name: string;
  teryt: string | null;
  crossings_verified: number;
  road_crossings: number;
  pedestrian_crossings: number;
}

export interface DistrictFeature {
  type: "Feature";
  id: number;
  geometry: GeoJSON.MultiPolygon;
  properties: DistrictProperties;
}

export interface CrossingProperties {
  crossing_id: number;
  official_id: string | null;
  name: string | null;
  category: Category | null;
  is_pedestrian: boolean;
  verification_status: VerificationStatus;
  district_id: number;
  district_name: string;
  manager: string | null;
  warnings: number;
  /** Średnia planowa liczba pociągów pasażerskich w dzień roboczy; null = brak danych. */
  trains_weekday: number | null;
  /** Pozycja i wynik RPS z ostatniego przebiegu; null = poza rankingiem lub brak przebiegu. */
  rank: number | null;
  rps: number | null;
  /** Nazwa ulicy przejazdu z BDOT10k; null = brak nazwanej jezdni w pobliżu. */
  street: string | null;
}

export interface CrossingFeature {
  type: "Feature";
  id: number;
  geometry: GeoJSON.Point;
  properties: CrossingProperties;
}

export interface CrossingDetail {
  crossing_id: number;
  official_id: string | null;
  name: string | null;
  category: Category | null;
  is_pedestrian: boolean;
  verification_status: VerificationStatus;
  verified_at: string | null;
  district_id: number | null;
  district_name: string | null;
  lon: number;
  lat: number;
  attributes: {
    code: string;
    value: string | null;
    confidence: string;
    source: string;
  }[];
  quality_flags: { code: string; severity: string; message: string | null }[];
  roads: {
    name: string | null;
    road_class: string | null;
    management: string | null;
    distance_m: number;
  }[];
  tracks: {
    line_number: string | null;
    track_function: string | null;
    track_count: number | null;
    existence: string | null;
    distance_m: number;
  }[];
  sources: {
    name: string;
    attribution: string | null;
    license_verified: boolean;
  }[];
  priority: {
    run_id: number;
    method_version: string;
    rps: number | null;
    rank: number | null;
    rank_best: number | null;
    rank_worst: number | null;
    ranked_total: number;
    completeness_pct: number;
    quality_status: string;
    components: {
      component: "T" | "P" | "G" | "H";
      value: number | null;
      weight: number;
      status: "ok" | "modelled" | "unknown";
      detail: Record<string, unknown>;
    }[];
  } | null;
  rail_flow: {
    weekday_avg: number;
    saturday: number | null;
    sunday: number | null;
    period_start: string;
    period_end: string;
    unit: string;
    evidence_type: string;
    method_version: string;
    source: string | null;
  } | null;
}

async function getJson<T>(url: string, signal?: AbortSignal): Promise<T> {
  const response = await fetch(url, { signal });
  if (!response.ok) throw new Error(`HTTP ${response.status}`);
  return (await response.json()) as T;
}

export const fetchHealth = (signal?: AbortSignal) =>
  getJson<Health>("/api/v1/health", signal);

export const fetchDistricts = (signal?: AbortSignal) =>
  getJson<{ features: DistrictFeature[] }>("/api/v1/districts", signal).then(
    (c) => c.features,
  );

export const fetchCrossings = (signal?: AbortSignal) =>
  getJson<{ features: CrossingFeature[]; total: number }>(
    "/api/v1/crossings?verification_status=all&limit=500",
    signal,
  ).then((c) => c.features);

export const fetchCrossingDetail = (id: number, signal?: AbortSignal) =>
  getJson<CrossingDetail>(`/api/v1/crossings/${id}`, signal);

export interface AnalysisRun {
  run_id: number;
  method_version: string;
  period_start: string;
  period_end: string;
  finished_at: string;
  is_demo: boolean;
  scored: number;
  ranked: number;
  disclaimer: string;
}

/** Zwraca null, gdy nie ma jeszcze żadnego zakończonego przebiegu analizy (HTTP 404). */
export async function fetchLatestAnalysis(
  signal?: AbortSignal,
): Promise<AnalysisRun | null> {
  const response = await fetch("/api/v1/analysis/latest", { signal });
  if (response.status === 404) return null;
  if (!response.ok) throw new Error(`HTTP ${response.status}`);
  return (await response.json()) as AnalysisRun;
}
