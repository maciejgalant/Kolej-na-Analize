import { expect, test } from "@playwright/test";
import { mockApi, reply } from "./fixtures";

test("temporary map chat uses selected crossing and never writes chat history", async ({
  page,
}) => {
  await mockApi(page);
  const requests: any[] = [];
  await page.route("**/api/v1/assistant/chat", (route) => {
    requests.push(route.request().postDataJSON());
    return route.fulfill({ json: reply("Krótka odpowiedź o przejeździe.") });
  });
  await page.goto("/");
  const persisted = () =>
    page.evaluate(
      () =>
        JSON.parse(localStorage.getItem("railsafe.chat.v1")!).conversations[0]
          .messages,
    );
  await page
    .getByRole("button", { name: "Mapa przejazdów", exact: true })
    .click();
  const map = page.getByRole("dialog", { name: "Mapa przejazdów" });
  await map.getByRole("button", { name: /Testowa, DEMO-7/ }).click();
  const launcher = map.getByRole("button", {
    name: "Otwórz tymczasowy czat na mapie",
  });
  await expect(launcher).toContainText("Czy mogę pomóc");
  expect(requests).toHaveLength(0);
  await launcher.click();
  const chat = map.getByRole("region", { name: "Tymczasowy czat na mapie" });
  await expect(chat).toContainText("Testowa");
  await chat
    .getByRole("textbox", { name: "Krótkie pytanie na mapie" })
    .fill("Dlaczego taki wynik?");
  await chat.getByRole("button", { name: "Wyślij pytanie na mapie" }).click();
  await expect(
    chat.getByText("Krótka odpowiedź o przejeździe.", { exact: true }),
  ).toBeVisible();
  expect(requests[0]).toMatchObject({
    crossing_id: 7,
    message: "Dlaczego taki wynik?",
    history: [],
  });
  await chat.getByRole("textbox").fill("A źródła?");
  await chat.getByRole("button", { name: "Wyślij pytanie na mapie" }).click();
  await expect.poll(() => requests.length).toBe(2);
  expect(requests[1].history).toHaveLength(2);
  expect(await persisted()).toEqual([]);
  await page.screenshot({ path: "test-results/map-assistant.png" });
  await page.keyboard.press("Escape");
  await page
    .getByRole("button", { name: "Mapa przejazdów", exact: true })
    .click();
  await map
    .getByRole("button", { name: "Otwórz tymczasowy czat na mapie" })
    .click();
  await expect(map.getByText("Krótka odpowiedź o przejeździe.")).toHaveCount(0);
  expect(await persisted()).toEqual([]);
});

test("map chat cancellation discards late replies and selection resets context", async ({
  page,
}) => {
  await mockApi(page);
  let finish!: () => void;
  const pending = new Promise<void>((resolve) => {
    finish = resolve;
  });
  await page.route("**/api/v1/assistant/chat", async (route) => {
    await pending;
    await route.fulfill({ json: reply("Spóźniona odpowiedź") }).catch(() => {});
  });
  await page.goto("/");
  await page
    .getByRole("button", { name: "Mapa przejazdów", exact: true })
    .click();
  const map = page.getByRole("dialog", { name: "Mapa przejazdów" });
  await map.getByRole("button", { name: /Testowa, DEMO-7/ }).click();
  await map
    .getByRole("button", { name: "Otwórz tymczasowy czat na mapie" })
    .click();
  await map
    .getByRole("button", { name: "Wyjaśnij wynik RPS", exact: true })
    .click();
  await expect(map.locator(".map-chat-pending")).toBeVisible();
  await map
    .getByRole("button", { name: "Zatrzymaj odpowiedź na mapie" })
    .click();
  finish();
  await expect(map.getByText(/Zatrzymano odpowiedź/)).toBeVisible();
  await map.getByRole("button", { name: /Wróć do mapy/ }).click();
  await map.getByRole("button", { name: /Kolejowa, DEMO-9/ }).click();
  await map
    .getByRole("button", { name: "Otwórz tymczasowy czat na mapie" })
    .click();
  await expect(map.locator(".map-chat-context")).toContainText("Kolejowa");
  await expect(
    map.getByText("Spóźniona odpowiedź", { exact: true }),
  ).toHaveCount(0);
  await expect(map.locator(".map-chat-turn")).toHaveCount(0);
});
