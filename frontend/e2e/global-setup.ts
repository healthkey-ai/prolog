import { execSync } from "node:child_process";
import { resolve } from "node:path";

/** Migrate and activate the example instrument so the runner has a survey to serve. */
export default function globalSetup() {
  const backend = resolve(import.meta.dirname, "..", "..", "backend");
  const example = resolve(import.meta.dirname, "..", "..", "examples", "sample-wellbeing.json");
  execSync("uv run python manage.py migrate --noinput", { cwd: backend, stdio: "inherit" });
  execSync(`uv run python manage.py load_definition "${example}" --activate`, { cwd: backend, stdio: "inherit" });
}
