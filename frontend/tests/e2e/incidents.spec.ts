import { expect, test } from "@playwright/test";
import { crossings, mockApi } from "./fixtures";

test("SEWiK is shown under H as partial street evidence, with unknown casualties", async ({
  page,
}) => {
  await mockApi(page);
  await page.route("**/api/v1/crossings/7", (route) =>
    route.fulfill({
      json: {
        ...crossings[0].properties,
        lon: 21.01,
        lat: 52.23,
        verified_at: null,
        attributes: [],
        quality_flags: [],
        roads: [],
        tracks: [],
        road_counts: [],
        sources: [],
        rail_flow: null,
        priority: {
          run_id: 1,
          method_version: "test",
          rps: 50,
          rank: 1,
          ranked_total: 3,
          rank_best: 1,
          rank_worst: 1,
          completeness_pct: 90,
          quality_status: "partial",
          components: [
            {
              component: "H",
              value: null,
              weight: 0.1,
              status: "unknown",
              detail: {},
            },
          ],
        },
      },
    }),
  );
  await page.route("**/api/v1/incidents*", (route) =>
    route.fulfill({
      json: {
        source: "SEWiK",
        source_url: "https://sewik.pl/",
        coverage: "partial",
        scope: route.request().url().includes("crossing_id")
          ? "street_candidates"
          : "warsaw",
        notice: "Częściowy wykaz. Nie jest pełną statystyką Warszawy.",
        records: [
          {
            source_object_id: "109899553",
            occurred_on: "2021-02-17",
            local_time: "15:23",
            address: "WARSZAWA JUTRZENKI",
            incident_type: "Zderzenie pojazdów boczne",
            place: "Przejazd kolejowy niestrzeżony",
            injured: 3,
            killed: null,
          },
        ],
      },
    }),
  );
  await page.goto("/");
  await page
    .getByRole("button", { name: "Mapa przejazdów", exact: true })
    .click();
  const map = page.getByRole("dialog", {
    name: "Mapa przejazdów",
    exact: true,
  });
  await map.getByRole("button", { name: /Testowa, DEMO-7/ }).click();
  await map.getByText("Jak obliczono RPS", { exact: true }).click();
  const history = map.getByRole("region", { name: "Historia zdarzeń SEWiK" });
  await expect(history).toContainText(
    "Nie potwierdzono, że dotyczą tego przejazdu",
  );
  await expect(history).toContainText("Ranni: 3");
  await expect(history).toContainText("Zabici: brak informacji");
  await expect(history).toContainText("109899553");
  await map
    .getByRole("button", { name: "Historia zdarzeń · SEWiK", exact: true })
    .click();
  const city = page.getByRole("dialog", {
    name: "Historia zdarzeń w Warszawie · SEWiK",
    exact: true,
  });
  await expect(city).toContainText("Widoczne wpisy dla Warszawy: 1");
  await page.keyboard.press("Escape");
  await expect(city).toHaveCount(0);
  await expect(map).toBeVisible();
});
