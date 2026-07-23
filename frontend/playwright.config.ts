import { defineConfig, devices } from '@playwright/test'

/** Permanent E2E journey suite (frontend/e2e) — headless Chromium only.
 * The dev server is started automatically (`npm run dev`, Next) and reused
 * if one is already running locally. All backend calls are intercepted via
 * `page.route()` in `e2e/fixtures.ts` — no live backend/DB is ever touched. */
export default defineConfig({
  testDir: './e2e',
  fullyParallel: true,
  // Capped low deliberately: every test hits the SAME single Next dev
  // server instance (webServer below) — 3 workers keeps it parallel without
  // overloading one process.
  workers: 3,
  // Next's Turbopack dev server compiles the client bundle lazily, on the
  // FIRST real browser navigation (not at webServer-readiness time, since
  // `output: 'export'` + the ssr:false shell means almost nothing is
  // server-rendered — see gotcha G1). That one-time compile+hydrate has been
  // measured taking ~27s on a loaded machine, uncomfortably close to
  // Playwright's 30s default. Once warm, tests run in single-digit seconds
  // (verified: 26.6s -> 9.1s -> 19.6s across the first 3 specs). Default
  // raised so the first spec has headroom without masking a genuine hang.
  timeout: 60_000,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  reporter: [['list']],
  use: {
    baseURL: 'http://127.0.0.1:3000',
    trace: 'on-first-retry',
  },
  projects: [
    { name: 'chromium', use: { ...devices['Desktop Chrome'] } },
  ],
  webServer: {
    command: 'npm run dev',
    url: 'http://127.0.0.1:3000',
    reuseExistingServer: !process.env.CI,
    // Raised 30s -> 60s: Next cold-compiles the route on first hit.
    timeout: 60_000,
  },
})
