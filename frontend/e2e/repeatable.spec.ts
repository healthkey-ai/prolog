import { expect, test } from "@playwright/test";

const SLUG = "sample-followup"; // participation.repeatable: answered again and again
const API = "http://localhost:8765/api/run";

test("a repeatable instrument starts afresh after a finished response, saying when it was last done", async ({ page, request }) => {
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.goto(`/s/${SLUG}`);
  await page.evaluate(() => localStorage.clear());
  await page.reload();
  await page.getByTestId("start").click();
  await expect(page.getByTestId("question-treatments")).toBeVisible();
  const first = await page.evaluate((slug) => localStorage.getItem(`prolog:response:${slug}`), SLUG);

  // Finish it (the answers do not matter here).
  for (const [key, value] of [["treatments", { options: ["not_started"] }], ["symptoms_had", { options: ["none"] }]] as const) {
    expect((await request.put(`${API}/responses/${first}/answers/${key}/`, { data: { value } })).ok()).toBeTruthy();
  }
  expect((await request.post(`${API}/responses/${first}/submit/`)).ok()).toBeTruthy();

  // The next visit is the next response: no "already completed", no resume card.
  await page.goto(`/s/${SLUG}`);
  await expect(page.getByTestId("last-completed")).toContainText("You last completed this on");
  await expect(page.getByTestId("resume-card")).toHaveCount(0);
  await page.getByTestId("start").click();
  await expect(page.getByTestId("question-treatments")).toBeVisible();
  const second = await page.evaluate((slug) => localStorage.getItem(`prolog:response:${slug}`), SLUG);
  expect(second).not.toBe(first);
});

test("an instrument that is not repeatable still shows a finished response as completed", async ({ page, request }) => {
  await page.goto("/s/sample-history");
  await page.evaluate(() => localStorage.clear());
  await page.reload();
  await page.getByTestId("start").click();
  await expect(page.getByTestId("question-taking")).toBeVisible();
  const id = await page.evaluate(() => localStorage.getItem("prolog:response:sample-history"));
  for (const [key, value] of [["taking", { option: "never" }], ["diagnosed_year", { date: "1998" }], ["last_test", { skipped: true }]] as const) {
    expect((await request.put(`${API}/responses/${id}/answers/${key}/`, { data: { value } })).ok()).toBeTruthy();
  }
  expect((await request.post(`${API}/responses/${id}/submit/`)).ok()).toBeTruthy();

  await page.goto("/s/sample-history");
  await expect(page.getByTestId("resume-card")).toContainText("already completed");
  await expect(page.getByTestId("last-completed")).toHaveCount(0);
});
