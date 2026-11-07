import { defineConfig, devices } from "@playwright/test";

/**
 * Browser-level tests live in `e2e/` and are separate from the jsdom suite that
 * `npm test` runs. They drive the Vite dev server, which also serves the
 * harness page at `/e2e/harness/index.html`; nothing is added to `vite build`.
 *
 * The default dev port is whatever `WEB_PORT` says (5183), so the suite uses
 * 5199 and a strict port to avoid fighting a running `npm run dev`.
 */
const PORT = 5199;
const BASE_URL = `http://127.0.0.1:${PORT}`;

export default defineConfig({
  testDir: "./e2e",
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  reporter: [["list"]],
  use: {
    baseURL: BASE_URL,
    trace: "retain-on-failure",
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
  webServer: {
    command: `npm run dev -- --port ${PORT} --strictPort --host 127.0.0.1`,
    url: `${BASE_URL}/e2e/harness/index.html`,
    reuseExistingServer: !process.env.CI,
    timeout: 60_000,
  },
});
