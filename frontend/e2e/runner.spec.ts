import { expect, test, type Page } from "@playwright/test";
import { expectAccessible } from "./helpers";

const SLUG = "sample-wellbeing";

async function start(page: Page) {
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.goto(`/s/${SLUG}`);
  await page.evaluate(() => localStorage.clear());
  await page.reload();
  await expectAccessible(page, "intro");
  await page.getByTestId("start").click();
  await expect(page.getByTestId("question-welcome")).toBeVisible();
  await expectAccessible(page, "info");
}

test.describe("runner core", () => {
  test("intro → simple questions → overview → resume", async ({ page }) => {
    await start(page);

    // info block → country dropdown
    await page.getByTestId("next").click();
    await expect(page.getByTestId("question-country")).toBeVisible();
    await expectAccessible(page, "dropdown");
    await page.getByTestId("combobox").fill("United King");
    await page.getByTestId("combobox-option-GB").click();
    await page.getByTestId("next").click();

    // single choice saves on selection
    await expect(page.getByTestId("question-age_band")).toBeVisible();
    await expectAccessible(page, "single");
    await page.getByTestId("option-30_49").click();
    await expect(page.getByText("Saved")).toBeVisible();
    await page.getByTestId("next").click();

    // optional number: skipping silently records a skip
    await expect(page.getByTestId("question-birth_year")).toBeVisible();
    await page.getByTestId("next").click();
    await expect(page.getByTestId("question-last_visit")).toBeVisible();
    await page.getByTestId("date-input").fill("2025-05-01");
    await page.getByTestId("next").click();

    // section interstitial then scale
    await expect(page.getByTestId("interstitial")).toBeVisible();
    await page.getByTestId("next").click();
    await expect(page.getByTestId("question-overall")).toBeVisible();
    await expectAccessible(page, "scale");
    await page.getByTestId("scale-overall-4").click();
    await expect(page.getByRole("radio", { name: "4" })).toBeChecked();
    await page.getByTestId("next").click();

    // soft-required skip prompt on an unanswered required question
    await expect(page.getByTestId("question-has_symptoms")).toBeVisible();
    await page.getByTestId("next").click();
    await expect(page.getByRole("alertdialog")).toBeVisible();
    await expectAccessible(page, "skip prompt");
    await page.getByTestId("skip-confirm").click();
    await expect(page.getByTestId("question-daily_activities")).toBeVisible();

    // overview: jump back to the skipped question and answer it, revealing a branch
    await page.getByRole("button", { name: "All questions" }).click();
    await expectAccessible(page, "overview");
    await page.getByTestId("overview-has_symptoms").click();
    await expect(page.getByTestId("question-has_symptoms")).toBeVisible();
    await page.getByTestId("option-yes").click();
    await page.getByTestId("next").click();
    await expect(page.getByTestId("question-symptoms")).toBeVisible();

    // resume after reload lands on the first open question
    await page.goto(`/s/${SLUG}`);
    await expect(page.getByTestId("resume-card")).toBeVisible();
    await page.getByTestId("resume").click();
    await expect(page.getByTestId("question-symptoms")).toBeVisible();
  });

  test("language switch keeps answers", async ({ page }) => {
    await page.goto(`/s/${SLUG}`);
    await page.evaluate(() => localStorage.clear());
    await page.reload();
    await page.getByTestId("lang-es").click();
    await expect(page.getByRole("heading", { level: 1 })).toHaveText("Chequeo de bienestar");
    await page.getByTestId("start").click();
    await page.getByTestId("next").click();
    await page.getByTestId("combobox").fill("Reino");
    await page.getByTestId("combobox-option-GB").click();
    await page.getByTestId("next").click();
    await page.locator("#language-switch").selectOption("en");
    await expect(page.getByTestId("question-age_band")).toContainText("How old are you?");
    await page.getByRole("button", { name: "All questions" }).click();
    await expect(page.getByTestId("overview-country")).toContainText("United Kingdom");
  });
});
