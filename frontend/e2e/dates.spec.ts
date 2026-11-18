import { expect, test, type Page } from "@playwright/test";
import { expectAccessible } from "./helpers";

const SLUG = "sample-history";
const API = "http://localhost:8765/api/run";

async function start(page: Page) {
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.goto(`/s/${SLUG}`);
  await page.evaluate(() => localStorage.clear());
  await page.reload();
  await page.getByTestId("start").click();
  await expect(page.getByTestId("question-taking")).toBeVisible();
  return (await page.evaluate((slug) => localStorage.getItem(`prolog:response:${slug}`), SLUG))!;
}

test.describe("partial dates and any-of conditions", () => {
  test("a month-or-year date, its own 'not sure', and a question either answer opens", async ({ page, request }) => {
    const id = await start(page);
    await page.getByTestId("option-stopped").click();
    await page.getByTestId("next").click();

    // month and year as separate fields; the month may be left out
    await expect(page.getByTestId("question-started")).toBeVisible();
    await expect(page.getByTestId("date-day")).toHaveCount(0);
    await expectAccessible(page, "partial date");
    await page.getByTestId("date-year").fill("2019");
    await page.getByTestId("date-month").selectOption("06");
    await expect(page.getByText("Saved")).toBeVisible();
    await page.getByTestId("next").click();

    // "not sure" instead of a date opens the review question (an any group)
    await expect(page.getByTestId("question-ended")).toBeVisible();
    await page.getByTestId("option-not_sure").click();
    await page.getByTestId("next").click();
    await expect(page.getByTestId("question-review")).toBeVisible();
    await page.getByTestId("option-yes").click();

    // a year alone instead: neither branch holds, so the review answer goes
    await page.goto(`/s/${SLUG}/q/ended`);
    await expect(page.getByTestId("option-not_sure")).toBeChecked();
    await page.getByTestId("date-year").fill("2021");
    await expect(page.getByTestId("option-not_sure")).not.toBeChecked();
    await page.getByTestId("date-year").blur();
    await expect(page.getByText("Saved")).toBeVisible();
    await page.getByTestId("next").click();
    await expect(page.getByTestId("question-diagnosed_year")).toBeVisible();

    const r = await request.get(`${API}/responses/${id}/`);
    const body = (await r.json()) as { answers: Record<string, unknown>; visible: string[] };
    expect(body.answers.started).toEqual({ date: "2019-06" });
    expect(body.answers.ended).toEqual({ date: "2021" });
    expect(body.answers).not.toHaveProperty("review");
    expect(body.visible).not.toContain("review");
  });

  test("a year-only date asks for the year alone; a day-month-year date takes any of the three", async ({ page, request }) => {
    const id = await start(page);
    await page.getByTestId("option-never").click();
    await page.getByTestId("next").click();
    await expect(page.getByTestId("question-diagnosed_year")).toBeVisible();
    await expect(page.getByTestId("date-month")).toHaveCount(0);
    await page.getByTestId("date-year").fill("1998");
    await page.getByTestId("date-year").blur();
    await expect(page.getByText("Saved")).toBeVisible();
    await page.getByTestId("next").click();

    await expect(page.getByTestId("question-last_test")).toBeVisible();
    await expectAccessible(page, "day, month, year");
    await page.getByTestId("date-day").fill("5");
    await page.getByTestId("date-month").selectOption("03");
    await page.getByTestId("date-year").fill("2024");
    await page.getByTestId("date-year").blur();
    await expect(page.getByText("Saved")).toBeVisible();

    const r = await request.get(`${API}/responses/${id}/`);
    const body = (await r.json()) as { answers: Record<string, unknown> };
    expect(body.answers.diagnosed_year).toEqual({ date: "1998" });
    expect(body.answers.last_test).toEqual({ date: "2024-03-05" });
  });
});
