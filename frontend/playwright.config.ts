import { defineConfig, devices } from "@playwright/test";

/**
 * End-to-end tests run against a real backend (local PostgreSQL) and the Vite
 * dev server (ports 8765/5199 to stay clear of local defaults). `e2e/global-setup.ts` loads and activates the example
 * definition. Run: `npm run e2e` (needs `uv` and PostgreSQL on :5432).
 */
export default defineConfig({
  testDir: "./e2e",
  globalSetup: "./e2e/global-setup.ts",
  timeout: 30_000,
  fullyParallel: false,
  retries: process.env.CI ? 1 : 0,
  reporter: process.env.CI ? "github" : "list",
  use: { baseURL: "http://localhost:5199", trace: "retain-on-failure" },
  projects: [
    { name: "mobile", use: { ...devices["Pixel 7"] } },
    { name: "desktop", use: { ...devices["Desktop Chrome"] } },
  ],
  webServer: [
    {
      // Migrate first: /api/health/ answers 503 while migrations are pending, and
      // web servers start before globalSetup runs.
      command:
        "cd ../backend && uv run python manage.py migrate --noinput && uv run python manage.py runserver 8765 --noreload",
      url: "http://localhost:8765/api/health/",
      env: {
        DEBUG: "true", // the development key is fine for a local test backend
        PROLOG_THEME_DIRS: `${process.cwd()}/../themes:${process.cwd()}/e2e/fixtures/themes`,
        // Every e2e run shares one client key; never let the abuse throttles interfere.
        PROLOG_THROTTLE_CREATE: "100000/hour",
        PROLOG_THROTTLE_ANSWER: "100000/hour",
        PROLOG_THROTTLE_READ: "100000/hour",
      },
      reuseExistingServer: !process.env.CI,
      timeout: 60_000,
    },
    {
      command: "npm run dev -- --port 5199 --strictPort",
      url: "http://localhost:5199",
      env: { VITE_API_PROXY: "http://localhost:8765" },
      reuseExistingServer: !process.env.CI,
      timeout: 60_000,
    },
  ],
});
