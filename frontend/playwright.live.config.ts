import { defineConfig, devices } from '@playwright/test'

/** LIVE-stack E2E suite (frontend/e2e/live-*.spec.ts) — the REAL topology:
 * browser -> uvicorn (FastAPI serves API + the built `frontend/out` static
 * export, one origin, no CORS) -> live Fabric SQL DB. NOTHING is mocked:
 * `installMocks`/`page.route()` are never called in these specs.
 *
 * Safety contract (mirrors backend/tests/test_integration_live.py): every
 * write the spec drives goes to sentinel fiscal_year 2099 only, and
 * `e2e/live_db.py cleanup` wipes + verifies that year before AND after the
 * run. Email is safe by config default (`notifications_dry_run=True`).
 *
 * Run via `npm run test:e2e:live` (which rebuilds `frontend/out` first so
 * the served bundle is current). The default mocked suite
 * (playwright.config.ts) explicitly testIgnores live-*.spec.ts. */
export default defineConfig({
  testDir: './e2e',
  testMatch: 'live-*.spec.ts',
  fullyParallel: false,
  // ONE shared live database + one shared sentinel year — parallel workers
  // would race each other's writes/cleanup. Serial, always.
  workers: 1,
  // Live Fabric SQL latency (msal token + TDS to the cloud) makes even a
  // single grid load far slower than the mocked suite; plus uvicorn's
  // first-hit imports. Generous, not infinite.
  timeout: 180_000,
  forbidOnly: !!process.env.CI,
  retries: 0,
  reporter: [['list']],
  use: {
    // baseURL = the uvicorn server itself (same-origin SPA + API), NOT a
    // Next dev server — there is no CORS middleware, so the browser must be
    // same-origin with the backend.
    baseURL: 'http://127.0.0.1:8000',
    trace: 'retain-on-failure',
  },
  projects: [
    { name: 'chromium', use: { ...devices['Desktop Chrome'] } },
  ],
  webServer: {
    // Absolute venv python (has uvicorn + the backend deps); cwd=backend so
    // `app.main:app` imports and backend/.env resolves exactly as documented
    // in CLAUDE.md.
    command: 'C:/04.budget_management_web/venv/Scripts/python.exe -m uvicorn app.main:app --port 8000',
    cwd: 'C:/04.budget_management_web/backend',
    url: 'http://127.0.0.1:8000/health',
    reuseExistingServer: true,
    // First boot imports pyodbc/msal and may lazily warm the token cache.
    timeout: 120_000,
  },
})
