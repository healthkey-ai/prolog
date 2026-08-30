import { execSync } from "node:child_process";
import { mkdtempSync, readFileSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";

/**
 * Load and activate the example instrument (default theme) plus a copy bound
 * to the e2e fixture theme, so the runner has surveys to serve. Migrations run
 * in the backend webServer command (playwright.config.ts) before this.
 */
export default function globalSetup() {
  const backend = resolve(import.meta.dirname, "..", "..", "backend");
  const example = resolve(import.meta.dirname, "..", "..", "examples", "sample-wellbeing.json");
  const themed = JSON.parse(readFileSync(example, "utf-8"));
  themed.slug = "sample-themed";
  themed.theme = "e2e-test";
  delete themed.$schema;
  const dir = mkdtempSync(join(tmpdir(), "prolog-e2e-"));
  const themedPath = join(dir, "sample-themed.json");
  writeFileSync(themedPath, JSON.stringify(themed));
  // Idempotent on a reused local database: an active version refuses a changed
  // source, so the two sample surveys (and their test responses) are recreated
  // from source on every run. Nothing else in the database is touched.
  const slugs = "['sample-wellbeing', 'sample-themed']";
  const reset = [
    "from prolog_surveys import models as m",
    `m.SurveyResponse.objects.filter(survey_version__survey__slug__in=${slugs}).delete()`,
    `m.SurveyContact.objects.filter(survey_version__survey__slug__in=${slugs}).delete()`,
    `m.SurveyAdministration.objects.filter(invitation__survey__slug__in=${slugs}).delete()`,
    `m.SurveyInvitation.objects.filter(survey__slug__in=${slugs}).delete()`,
    `m.SurveyQuestion.objects.filter(survey_version__survey__slug__in=${slugs}).delete()`,
    `m.SurveyVersion.objects.filter(survey__slug__in=${slugs}).delete()`,
    `m.Survey.objects.filter(slug__in=${slugs}).delete()`,
  ].join("; ");
  execSync(`uv run python manage.py shell -c "${reset}"`, { cwd: backend, stdio: "inherit" });
  execSync(`uv run python manage.py load_definition "${example}" "${themedPath}" --activate`, { cwd: backend, stdio: "inherit" });
}
