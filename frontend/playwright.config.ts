import { defineConfig, devices } from '@playwright/test'

/** Permanent E2E journey suite (frontend/e2e) — headless Chromium only.
 * The dev server is started automatically (`npm run dev`, Vite) and reused
 * if one is already running locally. All backend calls are intercepted via
 * `page.route()` in `e2e/fixtures.ts` — no live backend/DB is ever touched. */
export default defineConfig({
  testDir: './e2e',
  fullyParallel: true,
  // Capped low deliberately: every test hits the SAME single Vite dev
  // server instance (webServer below). A high worker count throws many
  // browser contexts at it simultaneously on first navigation (Vite's cold
  // dependency pre-bundling) and reliably produced "setting up page"/
  // navigation timeouts in practice — 3 workers is smooth and still parallel.
  workers: 3,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  reporter: [['list']],
  use: {
    baseURL: 'http://localhost:5173',
    trace: 'on-first-retry',
  },
  projects: [
    { name: 'chromium', use: { ...devices['Desktop Chrome'] } },
  ],
  webServer: {
    command: 'npm run dev',
    url: 'http://localhost:5173',
    reuseExistingServer: !process.env.CI,
    timeout: 30_000,
  },
})
