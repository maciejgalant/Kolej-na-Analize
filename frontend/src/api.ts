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
    };
    ollama: { status: ServiceState; model: string; model_available: boolean };
  };
}

export async function fetchHealth(signal?: AbortSignal): Promise<Health> {
  const response = await fetch("/api/v1/health", { signal });
  if (!response.ok) throw new Error(`HTTP ${response.status}`);
  return (await response.json()) as Health;
}
