import type { Page } from "@playwright/test";
export const healthy = {
  status: "ok",
  version: "test",
  demo_mode: true,
  services: {
    database: {
      status: "ok",
      postgis_version: "test",
      schema_revision: "0008",
      demo_data: true,
    },
    ollama: { status: "ok", model: "test", model_available: true },
  },
};
export const crossings = [7, 9, 11].map((id, i) => ({
  type: "Feature",
  id,
  geometry: {
    type: "Point",
    coordinates: [21.01 + i * 0.02, 52.23 + i * 0.01],
  },
  properties: {
    crossing_id: id,
    official_id: `DEMO-${id}`,
    name: `DEMO-${id}`,
    street: ["Testowa", "Kolejowa", "Leśna"][i],
    category: ["B", "D", "E"][i],
    is_pedestrian: i === 2,
    verification_status: "verified",
    district_id: i === 1 ? 2 : 1,
    district_name: i === 1 ? "Demo Bemowo" : "Demo Wawer",
    manager: null,
    warnings: 0,
    trains_weekday: i === 2 ? null : 12 + i,
    rank: i === 2 ? null : i + 1,
    rps: i === 2 ? null : 50 - i * 5,
  },
}));
export const districts = [1, 2].map((id, i) => ({
  type: "Feature",
  id,
  properties: {
    district_id: id,
    name: i ? "Demo Bemowo" : "Demo Wawer",
    teryt: null,
    crossings_verified: 2,
    road_crossings: 1,
    pedestrian_crossings: 1,
  },
  geometry: {
    type: "MultiPolygon",
    coordinates: [
      [
        [
          [20.99 + i * 0.03, 52.21],
          [21.04 + i * 0.03, 52.21],
          [21.04 + i * 0.03, 52.27],
          [20.99 + i * 0.03, 52.27],
          [20.99 + i * 0.03, 52.21],
        ],
      ],
    ],
  },
}));
export const evidence = {
  cards: [
    {
      crossing_id: 7,
      title: "DEMO-7",
      district: "Demo Wawer",
      category: "B",
      rps: 50,
      rank: 1,
      trains: 12,
    },
  ],
  tables: [
    {
      title: "Ranking testowy",
      columns: ["Przejazd", "RPS"],
      rows: [["DEMO-7", 50]],
    },
  ],
  charts: [
    {
      title: "Planowy ruch pasażerski",
      unit: "pociągi / dzień",
      points: [
        { label: "Dzień roboczy", value: 12, status: "planned" },
        { label: "Sobota", value: null, status: "unknown" },
      ],
    },
  ],
  sources: ["Źródło demonstracyjne"],
  notes: ["RPS to priorytet do dalszej oceny."],
  map_ids: [7],
};
export const reply = (answer = "Wynik analizy przejazdu DEMO-7.") => ({
  answer,
  grounded: true,
  tool_calls: [
    { name: "get_crossing", arguments: { number: "DEMO-7" }, ok: true },
  ],
  disclaimer: "Wartości demonstracyjne.",
  evidence,
});
export async function mockApi(
  page: Page,
  options: { ready?: boolean; empty?: boolean } = {},
) {
  await page.route(
    /tile\.openstreetmap\.org|mapy\.geoportal\.gov\.pl/,
    (route) =>
      route.fulfill({
        contentType: "image/svg+xml",
        body: '<svg xmlns="http://www.w3.org/2000/svg" width="256" height="256"><rect width="256" height="256" fill="#eef0ed"/><path d="M0 130h256M140 0v256" stroke="white" stroke-width="10"/></svg>',
      }),
  );
  await page.route("**/api/v1/**", async (route) => {
    const url = new URL(route.request().url());
    let body: unknown;
    if (url.pathname.endsWith("/health"))
      body =
        options.ready === false
          ? {
              ...healthy,
              status: "degraded",
              services: {
                ...healthy.services,
                ollama: {
                  status: "unavailable",
                  model: "test",
                  model_available: false,
                },
              },
            }
          : healthy;
    else if (url.pathname.endsWith("/districts"))
      body = { features: options.empty ? [] : districts };
    else if (url.pathname.endsWith("/crossings"))
      body = {
        features: options.empty ? [] : crossings,
        total: options.empty ? 0 : 3,
      };
    else if (/\/crossings\/\d+$/.test(url.pathname)) {
      const id = Number(url.pathname.split("/").pop()),
        c = crossings.find((c) => c.id === id)!;
      body = {
        ...c.properties,
        lon: c.geometry.coordinates[0],
        lat: c.geometry.coordinates[1],
        verified_at: null,
        attributes: [],
        quality_flags: [],
        road_counts: [],
        roads: [],
        tracks: [],
        sources: [
          {
            name: "Źródło demonstracyjne",
            attribution: null,
            license_verified: true,
          },
        ],
        rail_flow: null,
        priority: null,
      };
    } else if (url.pathname.endsWith("/analysis/latest")) {
      await route.fulfill({ status: 404, json: { detail: "Brak analizy" } });
      return;
    } else if (url.pathname.endsWith("/assistant/chat")) body = reply();
    else {
      await route.abort();
      return;
    }
    await route.fulfill({ json: body });
  });
}
