import { expect, test } from "@playwright/test";
import { mockApi } from "./fixtures";

test("icon actions expose visible hints with mouse and keyboard and preserve dialogs", async ({ page }) => {
  await mockApi(page);
  await page.goto("/");
  await expect(page.getByRole("button", { name: "Ruch kolejowy PKP PLK", exact: true })).toHaveCount(0);

  const info = page.getByRole("button", { name: "O danych i metodzie", exact: true });
  await expect(info.locator("svg")).toHaveCount(1);
  await info.focus();
  await expect(page.getByRole("tooltip")).toHaveText("O danych i metodzie");
  await info.press("Enter");
  const dialog = page.getByRole("dialog", { name: "O danych i metodzie", exact: true });
  await expect(dialog).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(dialog).toBeHidden();

  const pin = page.getByRole("button", { name: "Przypnij rozmowę", exact: true }).first();
  await pin.hover();
  await expect(page.getByRole("tooltip")).toHaveText("Przypnij rozmowę");
  await pin.click();
  await expect(page.getByRole("button", { name: "Odepnij rozmowę", exact: true })).toBeVisible();

  const history = page.getByRole("button", { name: "Historia w tej przeglądarce", exact: true });
  await history.focus();
  await expect(page.getByRole("tooltip")).toContainText("tylko w tej przeglądarce");
});
