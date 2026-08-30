import { execSync } from "node:child_process";
import { mkdtempSync, readFileSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";

/**
 * Migrate and activate the example instrument (default theme) plus a copy
 * bound to the e2e fixture theme, so the runner has surveys to serve.
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
  execSync("uv run python manage.py migrate --noinput", { cwd: backend, stdio: "inherit" });
  execSync(`uv run python manage.py load_definition "${example}" "${themedPath}" --activate`, { cwd: backend, stdio: "inherit" });
}
