import { expect, test } from "@playwright/test";
import { mockApi, reply, evidence } from "./fixtures";

test("comparison picker sends two explicit crossing numbers without inherited attachment", async ({
  page,
}) => {
  await mockApi(page);
  const requests: any[] = [];
  await page.route("**/api/v1/assistant/chat", (route) => {
    requests.push(route.request().postDataJSON());
    return route.fulfill({
      json: {
        ...reply(),
        evidence: {
          ...evidence,
          cards: [
            ...evidence.cards,
            { ...evidence.cards[0], crossing_id: 9, title: "DEMO-9" },
          ],
          map_ids: [7, 9],
          tables: [
            {
              title: "Porównanie składników: A minus B",
              columns: ["Składnik", "A", "B", "Różnica"],
              rows: [["Ekspozycja", 40, 30, 10]],
            },
          ],
        },
      },
    });
  });
  await page.goto("/");
  await page
    .getByRole("button", { name: "Porównaj przejazdy", exact: true })
    .click();
  await page.getByLabel("Przejazd A", { exact: true }).selectOption("7");
  await expect(
    page.getByLabel("Przejazd B", { exact: true }).locator('option[value="7"]'),
  ).toHaveAttribute("disabled", "");
  await expect(
    page.getByRole("button", { name: "Porównaj wybrane" }),
  ).toBeDisabled();
  expect(requests).toHaveLength(0);
  await page.getByLabel("Przejazd B", { exact: true }).selectOption("9");
  await page.screenshot({ path: "test-results/comparison-picker.png" });
  await page.getByRole("button", { name: "Porównaj wybrane" }).click();
  await expect(
    page.getByRole("table", { name: "Porównanie składników: A minus B" }),
  ).toBeVisible();
  expect(requests[0].message).toContain("DEMO-7");
  expect(requests[0].message).toContain("DEMO-9");
  expect(requests[0].crossing_id).toBeNull();
  await page.getByRole("button", { name: /Pokaż na mapie/ }).click();
  await expect(
    page
      .getByRole("dialog", { name: "Mapa przejazdów" })
      .locator(".leaflet-marker-icon"),
  ).toHaveCount(2);
});

test("quality and capabilities shortcuts work and smalltalk hides analytical trace", async ({
  page,
}) => {
  await mockApi(page);
  const requests: any[] = [];
  await page.route("**/api/v1/assistant/chat", (route) => {
    const body = route.request().postDataJSON();
    requests.push(body);
    return route.fulfill({
      json:
        body.message === "Co potrafisz?"
          ? {
              answer: "Mogę porównać przejazdy i sprawdzić jakość danych.",
              model: "test",
              grounded: false,
              tool_calls: [],
              disclaimer: "",
            }
          : {
              ...reply("Niepełne dane wymagają weryfikacji."),
              evidence: {
                ...evidence,
                tables: [
                  {
                    title: "Jakość danych — lista do weryfikacji",
                    columns: ["Przejazd", "Kompletność (%)", "Ruch"],
                    rows: [["DEMO-7", 70, "model"]],
                  },
                ],
              },
            },
    });
  });
  await page.goto("/");
  await page
    .getByRole("button", { name: "Co potrafisz?", exact: true })
    .click();
  await expect(
    page.getByText("Mogę porównać przejazdy i sprawdzić jakość danych.", {
      exact: true,
    }),
  ).toBeVisible();
  await expect(page.locator(".answer-trace")).toHaveCount(0);
  await page
    .getByRole("button", { name: "Sprawdź jakość danych", exact: true })
    .click();
  await expect(
    page.getByRole("table", { name: "Jakość danych — lista do weryfikacji" }),
  ).toBeVisible();
  expect(requests[1].message).toContain("jakość danych");
  await page
    .getByRole("button", { name: "Wyjaśnij prościej ten wynik", exact: true })
    .last()
    .click();
  await expect.poll(() => requests.length).toBe(3);
  expect(requests[2].crossing_id).toBe(7);
});
