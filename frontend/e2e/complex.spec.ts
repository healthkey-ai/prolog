import { expect, test, type APIRequestContext, type Page } from "@playwright/test";
import { expectAccessible } from "./helpers";

const SLUG = "sample-wellbeing";
const API = "http://localhost:8765/api/run";

async function startAndPrefill(page: Page, request: APIRequestContext, answers: Record<string, unknown>) {
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.goto(`/s/${SLUG}`);
  await page.evaluate(() => localStorage.clear());
  await page.reload();
  await page.getByTestId("start").click();
  await expect(page.getByTestId("question-welcome")).toBeVisible();
  const id = await page.evaluate((slug) => localStorage.getItem(`prolog:response:${slug}`), SLUG);
  for (const [key, value] of Object.entries(answers)) {
    const r = await request.put(`${API}/responses/${id}/answers/${key}/`, { data: { value } });
    expect(r.ok(), `${key}: ${await r.text()}`).toBeTruthy();
  }
  return id!;
}

async function serverAnswers(request: APIRequestContext, id: string) {
  const r = await request.get(`${API}/responses/${id}/`);
  return (await r.json()) as { answers: Record<string, unknown>; visible: string[] };
}

const BASE = {
  country: { option: "GB" },
  age_band: { option: "30_49" },
  birth_year: { skipped: true },
  last_visit: { skipped: true },
  overall: { value: 3 },
};

test.describe("complex question types", () => {
  test("multi: limit, exclusive, other text; matrix rows follow the selection", async ({ page, request }) => {
    const id = await startAndPrefill(page, request, { ...BASE, has_symptoms: { option: "yes" } });
    await page.goto(`/s/${SLUG}/q/symptoms`);
    await expect(page.getByTestId("question-symptoms")).toBeVisible();
    await expectAccessible(page, "multi");

    await page.getByTestId("option-fatigue").click();
    await page.getByTestId("option-pain").click();
    await page.getByTestId("option-sleep").click();
    await expect(page.getByTestId("multi-counter")).toContainText("3 of 3 selected");
    await expect(page.getByTestId("option-worry")).toBeDisabled();

    // exclusive clears the others; picking another clears the exclusive
    await page.getByTestId("option-none").click();
    await expect(page.getByTestId("option-fatigue")).not.toBeChecked();
    await page.getByTestId("option-fatigue").click();
    await expect(page.getByTestId("option-none")).not.toBeChecked();

    // other with free text
    await page.getByTestId("option-other").click();
    await page.getByTestId("other-text").fill("Dizziness");
    await page.getByTestId("other-text").blur();
    await expect(page.getByText("Saved")).toBeVisible();
    await page.getByTestId("next").click();

    // matrix rows = selection, with the participant's own "other" text
    await expect(page.getByTestId("question-symptom_impact")).toBeVisible();
    await expectAccessible(page, "matrix");
    await expect(page.getByTestId("matrix-row-fatigue")).toBeVisible();
    await expect(page.getByTestId("matrix-row-other")).toContainText("Dizziness");
    await expect(page.getByTestId("matrix-row-pain")).toHaveCount(0);
    await page.getByTestId("scale-symptom_impact-fatigue-2").click();
    await page.getByTestId("scale-symptom_impact-other-4").click();
    await expect(page.getByText("Saved")).toBeVisible();

    // go back and drop "other": the matrix keeps only the surviving row
    await page.getByTestId("next").click(); // to daily_activities
    await page.getByRole("button", { name: "All questions" }).click();
    await page.getByTestId("overview-symptoms").click();
    await page.getByTestId("option-other").click();
    await expect(page.getByText("Saved")).toBeVisible();
    const after = await serverAnswers(request, id);
    expect(after.answers.symptom_impact).toEqual({ ratings: { fatigue: 2 } });
    expect(after.answers.symptoms).toEqual({ options: ["fatigue"] });
  });

  test("ranking by keyboard/buttons with an optional item", async ({ page, request }) => {
    const id = await startAndPrefill(page, request, { ...BASE, has_symptoms: { option: "no" }, daily_activities: { ratings: { walking: 1, housework: 2, socialising: 3 } } });
    await page.goto(`/s/${SLUG}/q/outcome_ranking`);
    await expect(page.getByTestId("question-outcome_ranking")).toBeVisible();
    await expectAccessible(page, "ranking");

    await page.getByTestId("ranking-up-independence").click();
    await page.getByTestId("ranking-up-independence").click();
    await expect(page.getByTestId("ranking-announce")).toContainText("Staying independent is now at position 2 of 4");
    await page.getByTestId("ranking-include-other").click();
    await page.getByTestId("other-text").fill("Sleeping well");
    await page.getByTestId("other-text").blur();
    await expect(page.getByText("Saved")).toBeVisible();

    const { answers } = await serverAnswers(request, id);
    expect(answers.outcome_ranking).toEqual({ order: ["energy", "independence", "fewer_visits", "side_effects", "other"], other_text: "Sleeping well" });

    await page.getByTestId("ranking-remove-other").click();
    await expect(page.getByText("Saved")).toBeVisible();
    expect((await serverAnswers(request, id)).answers.outcome_ranking).toEqual({ order: ["energy", "independence", "fewer_visits", "side_effects"] });
  });

  test("an untouched ranking is accepted as-is on Next", async ({ page, request }) => {
    const id = await startAndPrefill(page, request, { ...BASE, has_symptoms: { option: "no" }, daily_activities: { ratings: { walking: 1, housework: 2, socialising: 3 } } });
    await page.goto(`/s/${SLUG}/q/outcome_ranking`);
    await expect(page.getByTestId("ranking-list")).toBeVisible(); // lazily loaded renderer
    await page.getByTestId("next").click();
    await expect(page.getByTestId("question-support_wanted")).toBeVisible();
    expect((await serverAnswers(request, id)).answers.outcome_ranking).toEqual({ order: ["energy", "fewer_visits", "side_effects", "independence"] });
  });

  test("gate closes and reopens: downstream answers invalidated, overview updates", async ({ page, request }) => {
    const id = await startAndPrefill(page, request, {
      ...BASE,
      has_symptoms: { option: "yes" },
      symptoms: { options: ["fatigue", "worry"] },
      symptom_impact: { ratings: { fatigue: 1, worry: 5 } },
    });
    await page.goto(`/s/${SLUG}/q/has_symptoms`);
    await page.getByTestId("option-no").click();
    await expect(page.getByText("Saved")).toBeVisible();
    await page.getByRole("button", { name: "All questions" }).click();
    await expect(page.getByTestId("overview-symptoms")).toHaveCount(0);
    await expect(page.getByTestId("overview-told_clinician")).toHaveCount(0);
    await page.getByRole("button", { name: "Close" }).click();

    const closed = await serverAnswers(request, id);
    expect(closed.answers.symptoms).toBeUndefined();
    expect(closed.answers.symptom_impact).toBeUndefined();
    expect(closed.visible).not.toContain("symptoms");

    await page.getByTestId("option-yes").click();
    await expect(page.getByText("Saved")).toBeVisible();
    await page.getByTestId("next").click();
    await expect(page.getByTestId("question-symptoms")).toBeVisible();
    await expect(page.getByTestId("option-fatigue")).not.toBeChecked();
  });

  test("full completion including the contact step", async ({ page, request }) => {
    await startAndPrefill(page, request, {
      ...BASE,
      has_symptoms: { option: "not_sure" },
      daily_activities: { ratings: { walking: 1, housework: 2, socialising: 3 } },
      outcome_ranking: { order: ["energy", "independence", "fewer_visits", "side_effects"] },
      support_wanted: { options: ["peer"] },
      told_clinician: { option: "yes" },
      anything_else: { skipped: true },
    });
    await page.goto(`/s/${SLUG}/q/contact_email`);
    await expect(page.getByTestId("question-contact_email")).toBeVisible();
    await expectAccessible(page, "email");
    await page.getByTestId("email-input").fill("not-an-email");
    await page.getByTestId("email-save").click();
    await expect(page.getByRole("alert")).toContainText("valid email");
    await page.getByTestId("email-input").fill("someone@example.org");
    await page.getByTestId("email-save").click();
    await expect(page.getByText("your email has been saved")).toBeVisible();
    await page.getByTestId("next").click(); // Finish
    await expect(page.getByTestId("complete")).toBeVisible();
    await expectAccessible(page, "complete");

    // read-only afterwards: intro offers no "start again", wizard redirects
    await page.goto(`/s/${SLUG}`);
    await expect(page.getByTestId("start-again")).toHaveCount(0);
    await page.goto(`/s/${SLUG}/q/overall`);
    await expect(page.getByTestId("complete")).toBeVisible();
  });
});
