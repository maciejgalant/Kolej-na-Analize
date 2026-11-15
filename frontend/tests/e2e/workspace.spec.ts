import { expect, test } from "@playwright/test";
import { mockApi, reply } from "./fixtures";
const input = (page) =>
  page.getByRole("textbox", { name: "Pytanie do Kolej na Analizę" });
async function send(page, text = "Pokaż ranking") {
  await input(page).fill(text);
  await page
    .getByRole("button", { name: "Wyślij pytanie", exact: true })
    .click();
}
const saved = (page) =>
  page.evaluate(() => JSON.parse(localStorage.getItem("railsafe.chat.v1")!));

test("welcome, full-width answers, evidence and map scoped to an answer", async ({
  page,
}) => {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await mockApi(page);
  await page.goto("/");
  await expect(page).toHaveTitle(/Kolej na Analizę/);
  const brand = page.locator(".brand-logo");
  await expect(brand).toHaveAttribute("alt", "Kolej na Analizę");
  await expect
    .poll(async () =>
      brand.evaluate(
        (img: HTMLImageElement) => img.complete && img.naturalWidth > 0,
      ),
    )
    .toBeTruthy();

  await expect(
    page.getByRole("heading", { name: "Przyjrzyjmy się przejazdom." }),
  ).toBeVisible();
  await expect(
    page.getByRole("complementary", { name: "Rozmowy" }),
  ).toBeVisible();
  await expect(
    page.getByText("DANE DEMONSTRACYJNE.", { exact: true }),
  ).toBeVisible();
  await page.screenshot({ path: "test-results/welcome.png" });
  await page.getByRole("button", { name: "↗ Mapa", exact: true }).click();
  const map = page.getByRole("dialog", { name: "Mapa przejazdów" });
  await expect(map).toBeVisible();
  await expect(map.locator(".leaflet-marker-icon")).toHaveCount(3);
  await map.getByLabel("Dzielnica", { exact: true }).selectOption("2");
  await map.getByLabel("Kategoria przejazdu").selectOption("D");
  await expect(map.locator(".leaflet-marker-icon")).toHaveCount(1);
  await page.keyboard.press("Escape");
  await expect(map).not.toBeVisible();
  await send(page);
  await expect(
    page.getByText("Wynik analizy przejazdu DEMO-7.", { exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("table", { name: "Ranking testowy" }),
  ).toBeVisible();
  await expect(
    page.getByRole("img", { name: /Planowy ruch pasażerski/ }),
  ).toBeVisible();
  await page
    .getByText("Źródła danych i wyjaśnienie wyniku", { exact: true })
    .click();
  await expect(
    page.getByText("Źródło demonstracyjne", { exact: true }),
  ).toBeVisible();
  await page.screenshot({ path: "test-results/answer.png" });
  await page.getByRole("button", { name: /Pokaż na mapie/ }).click();
  await expect(map).toBeVisible();
  await expect(map.locator(".leaflet-marker-icon")).toHaveCount(1);
  await expect(map.getByLabel("Dzielnica", { exact: true })).toHaveValue("");
  await expect(map.getByLabel("Kategoria przejazdu")).toHaveValue("");
  await expect(
    map.getByRole("button", { name: /Testowa, DEMO-7/ }),
  ).toBeVisible();
  await page.keyboard.press("Escape");
  await page.reload();
  await expect(
    page.getByRole("button", { name: /Pokaż na mapie/ }),
  ).toBeVisible();
  expect(errors).toEqual([]);
});

test("manual map attaches crossing, preserves state per conversation and sends only on demand", async ({
  page,
}) => {
  const requests: unknown[] = [];
  await mockApi(page);
  page.on("request", (r) => {
    if (r.url().endsWith("/assistant/chat")) requests.push(r.postDataJSON());
  });
  await page.goto("/");
  await page.getByRole("button", { name: "↗ Mapa", exact: true }).click();
  const map = page.getByRole("dialog", { name: "Mapa przejazdów" });
  await map.getByLabel("Dzielnica", { exact: true }).selectOption("1");
  await map.getByLabel("Kategoria przejazdu").selectOption("B");
  await map.locator('[title="Podkład: ortofoto"]').click();
  await map.getByRole("button", { name: /Testowa, DEMO-7/ }).click();
  await expect(
    map.getByRole("complementary", { name: "Szczegóły przejazdu" }),
  ).toBeVisible();
  await map.getByRole("button", { name: "Zapytaj o ten przejazd" }).click();
  await expect(map).not.toBeVisible();
  await expect(input(page)).toBeFocused();
  await expect(page.locator(".composer-attachment")).toContainText("Testowa");
  expect(requests).toHaveLength(0);
  await input(page).fill("Dlaczego taki priorytet?");
  await send(page, "Dlaczego taki priorytet?");
  await expect(
    page.getByText("Wynik analizy przejazdu DEMO-7.", { exact: true }),
  ).toBeVisible();
  expect(requests[0]).toMatchObject({ crossing_id: 7 });
  await page.getByRole("button", { name: "↗ Mapa", exact: true }).click();
  await expect(map.getByLabel("Dzielnica", { exact: true })).toHaveValue("1");
  await expect(map.getByLabel("Kategoria przejazdu")).toHaveValue("B");
  await expect(map.locator('[title="Podkład: ortofoto"]')).toHaveAttribute(
    "aria-pressed",
    "true",
  );
  await page.keyboard.press("Escape");
  const old = await saved(page);
  const oldId = old.active;
  const oldMap = old.conversations[0].map;
  expect(oldMap.zoom).toBeGreaterThan(11);
  await page
    .getByRole("button", { name: "＋ Nowa rozmowa", exact: true })
    .click();
  await page.getByRole("button", { name: "↗ Mapa", exact: true }).click();
  await expect(map.getByLabel("Dzielnica", { exact: true })).toHaveValue("");
  await expect(map.getByLabel("Kategoria przejazdu")).toHaveValue("");
  await page.keyboard.press("Escape");
  expect(
    (await saved(page)).conversations.find((c) => c.id === oldId).map,
  ).toEqual(oldMap);
});

test("edit and regenerate retain branches after reload; titles, pinning, search and delete work", async ({
  page,
}) => {
  await mockApi(page);
  await page.goto("/");
  await send(page, "Pierwsze pytanie");
  await expect(
    page.getByText("Wynik analizy przejazdu DEMO-7.", { exact: true }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Edytuj", exact: true }).click();
  await page
    .getByRole("textbox", { name: "Edytuj pytanie" })
    .fill("Zmienione pytanie");
  await page.getByRole("button", { name: "Wyślij jako nową gałąź" }).click();
  await expect(
    page.getByText("Zmienione pytanie", { exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Ponów odpowiedź" }),
  ).toBeEnabled();
  await page.getByRole("button", { name: "Ponów odpowiedź" }).click();
  await expect(page.locator(".assistant-message .branch-switch")).toContainText(
    "2 / 2",
  );
  await page.getByRole("button", { name: "Poprzednia wersja" }).first().click();
  await expect(
    page.getByText("Pierwsze pytanie", { exact: true }).first(),
  ).toBeVisible();
  expect((await saved(page)).conversations[0].messages).toHaveLength(5);
  await page.reload();
  await expect(page.locator(".user-message")).toContainText("Pierwsze pytanie");
  await page.getByRole("button", { name: "Zmień tytuł" }).click();
  await page
    .getByRole("textbox", { name: "Tytuł rozmowy" })
    .fill("Moja analiza");
  await page.getByRole("button", { name: "Zapisz", exact: true }).click();
  await page.getByRole("button", { name: "Przypnij rozmowę" }).click();
  await page
    .getByRole("textbox", { name: "Szukaj w rozmowach" })
    .fill("Moja analiza");
  await expect(
    page.getByRole("button", { name: "Odepnij rozmowę" }),
  ).toBeVisible();
  page.once("dialog", (d) => d.accept());
  await page.getByRole("button", { name: "Usuń rozmowę" }).click();
  await expect(
    page.getByRole("heading", { name: "Przyjrzyjmy się przejazdom." }),
  ).toBeVisible();
  expect((await saved(page)).conversations).toHaveLength(1);
});

test("late answers stay in the originating conversation; stop discards late completion", async ({
  page,
}) => {
  await mockApi(page);
  let release: () => void;
  let arrived: () => void;
  const pending = new Promise<void>((r) => {
    release = r;
  });
  const received = new Promise<void>((r) => {
    arrived = r;
  });
  await page.route("**/api/v1/assistant/chat", async (route) => {
    arrived();
    await pending;
    await route
      .fulfill({ json: reply("Odpowiedź w pierwszej rozmowie.") })
      .catch(() => {});
  });
  await page.goto("/");
  await send(page, "Długie pytanie");
  await received;
  await page
    .getByRole("button", { name: "＋ Nowa rozmowa", exact: true })
    .click();
  release!();
  await expect
    .poll(
      async () =>
        (await saved(page)).conversations.find(
          (c) => c.title === "Długie pytanie",
        ).messages[1].content,
    )
    .toBe("Odpowiedź w pierwszej rozmowie.");
  await expect(
    page.getByText("Odpowiedź w pierwszej rozmowie.", { exact: true }),
  ).not.toBeVisible();
  await page.getByRole("button", { name: /Długie pytanie/ }).click();
  await expect(
    page.getByText("Odpowiedź w pierwszej rozmowie.", { exact: true }),
  ).toBeVisible();
  let releaseStopped: () => void;
  const stopped = new Promise<void>((r) => {
    releaseStopped = r;
  });
  await page.route("**/api/v1/assistant/chat", async (route) => {
    await stopped;
    await route
      .fulfill({ json: reply("Ta odpowiedź nie powinna się pojawić.") })
      .catch(() => {});
  });
  await send(page, "Kolejne pytanie");
  await page.getByRole("button", { name: "■ Zatrzymaj" }).click();
  releaseStopped!();
  await expect(
    page.getByText(/Przerwano oczekiwanie na odpowiedź/),
  ).toBeVisible();
  await expect(
    page.getByText("Ta odpowiedź nie powinna się pojawić.", { exact: true }),
  ).not.toBeVisible();
});

test("unavailable model still permits map use; empty inventory is explained", async ({
  page,
}) => {
  await mockApi(page, { ready: false, empty: true });
  await page.goto("/");
  await expect(page.getByText(/Asystent jest niedostępny/)).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Wyślij pytanie", exact: true }),
  ).toBeDisabled();
  await page.getByRole("button", { name: "↗ Mapa", exact: true }).click();
  await expect(page.getByText(/Brak przejazdów w tym zakresie/)).toBeVisible();
});

test("corrupt saved history is retained; API errors can be retried", async ({
  page,
}) => {
  await mockApi(page);
  await page.goto("/");
  await page.evaluate(() =>
    localStorage.setItem("railsafe.chat.v1", "{broken"),
  );
  await page.reload();
  await expect(page.getByText(/Nie udało się odczytać historii/)).toBeVisible();
  await input(page).fill("Pytanie");
  expect(
    await page.evaluate(() => localStorage.getItem("railsafe.chat.v1")),
  ).toBe("{broken");
  await page.route("**/api/v1/assistant/chat", (route) =>
    route.fulfill({ status: 503, json: { detail: "Model nie odpowiada." } }),
  );
  await send(page);
  await expect(
    page.getByText("Model nie odpowiada.", { exact: true }),
  ).toBeVisible();
  await page.route("**/api/v1/assistant/chat", (route) =>
    route.fulfill({ json: reply() }),
  );
  await page.getByRole("button", { name: "Ponów odpowiedź" }).click();
  await expect(
    page.getByText("Wynik analizy przejazdu DEMO-7.", { exact: true }),
  ).toBeVisible();
});

test("multiple answer objects fit the visible modal at desktop widths", async ({
  page,
}) => {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await mockApi(page);
  await page.route("**/api/v1/assistant/chat", (route) => {
    const body = reply();
    body.evidence.map_ids = [7, 9];
    return route.fulfill({ json: body });
  });
  await page.goto("/");
  await send(page);
  await page.getByRole("button", { name: /Pokaż na mapie/ }).click();
  const map = page.getByRole("dialog", { name: "Mapa przejazdów" });
  await expect(map.locator(".leaflet-marker-icon")).toHaveCount(2);
  await expect
    .poll(async () => (await saved(page)).conversations[0].map.zoom)
    .toBeGreaterThan(11);
  for (const width of [1024, 1280, 1920]) {
    await page.setViewportSize({ width, height: 1000 });
    await expect(map).toBeVisible();
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth,
      ),
    ).toBeTruthy();
  }
  await page.screenshot({ path: "test-results/map.png" });
  await page.keyboard.press("Escape");
  await expect(map).not.toBeVisible();
  expect(errors).toEqual([]);
});
