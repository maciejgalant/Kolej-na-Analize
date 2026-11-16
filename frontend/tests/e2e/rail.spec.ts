import { expect, test } from "@playwright/test";
import { mockApi } from "./fixtures";

test("PLK panel preserves missing delays and shows station context", async ({ page }) => {
  await mockApi(page);
  await page.route("**/api/v1/rail/**", (route) => {
    const url = new URL(route.request().url());
    if (url.pathname.endsWith("/status")) return route.fulfill({ json: { configured: true } });
    const metadata = { fetched_at: "2026-11-16T12:00:00Z", source: "PKP PLK", cached: true };
    if (url.pathname.endsWith("/stations")) return route.fulfill({ json: {
      ...metadata, data: { stations: [{ id: 123, name: "Warszawa Testowa" }] },
    } });
    if (url.pathname.endsWith("/operations")) return route.fulfill({ json: {
      ...metadata, data: { pagination: { totalPages: 2 }, trains: [{
        scheduleId: 2026, orderId: 456, operatingDate: "2026-11-16", trainStatus: "P",
        stations: [{ stationId: 123, plannedDeparture: "2026-11-16T13:00:00",
          actualDeparture: null, departureDelayMinutes: null, isConfirmed: false }],
      }] },
    } });
    return route.fulfill({ json: { ...metadata, data: { disruptions: [
      { disruptionId: 1, message: "Testowe utrudnienie" },
    ] } } });
  });
  await page.goto("/");
  await page.getByRole("button", { name: "Ruch kolejowy PKP PLK", exact: true }).click();
  const panel = page.getByRole("dialog", { name: "Ruch kolejowy PKP PLK", exact: true });
  await panel.getByRole("button", { name: "Szukaj stacji" }).click();
  await panel.getByLabel("Wybierz stację").selectOption("123");
  await panel.getByRole("button", { name: "Pobierz realizację kursów" }).click();
  await expect(panel.getByText("bez potwierdzenia na stacji", { exact: false })).toBeVisible();
  await expect(panel.getByText("2026-11-16 13:00")).toBeVisible();
  await expect(panel.getByRole("button", { name: "Następna strona" })).toBeEnabled();
  await panel.getByRole("button", { name: "Pobierz utrudnienia" }).click();
  await expect(panel.getByText("Testowe utrudnienie")).toBeVisible();
});

test("missing key provides configuration instructions without upstream calls", async ({ page }) => {
  await mockApi(page);
  await page.route("**/api/v1/rail/status", (route) => route.fulfill({ json: { configured: false } }));
  await page.goto("/");
  await page.getByRole("button", { name: "Ruch kolejowy PKP PLK", exact: true }).click();
  await expect(page.getByText(/Integracja jest wyłączona/)).toBeVisible();
  await expect(page.getByRole("button", { name: "Szukaj stacji" })).toHaveCount(0);
});
