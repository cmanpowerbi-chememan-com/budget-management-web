/** LIVE-stack e2e — browser -> uvicorn (FastAPI, serving API + the built
 * `frontend/out` static export, one origin) -> live Fabric SQL DB. NOTHING
 * is mocked: this spec never imports `installMocks` and never calls
 * `page.route()`. Every byte on the wire is real.
 *
 * Safety contract (mirrors backend/tests/test_integration_live.py):
 * - Every write goes to sentinel fiscal_year 2099 ONLY (a year no real
 *   budget cycle can ever use). Cleanup runs before AND after (afterAll
 *   fires even on test failure), deleting every 2099 row across the 3
 *   transactional tables + approval_log/approval_status (Submit writes
 *   those) and verifying 0 remain — via `live_db.py`, shelled out to the
 *   repo venv python.
 * - Real (cost_center, filler_email, department, GL) are DISCOVERED from
 *   the live masters at runtime, never hardcoded (they change on their own
 *   SharePoint sync cadence).
 * - Email is safe: `notifications_dry_run` defaults to True in
 *   backend/app/config.py — Submit logs, never sends.
 *
 * The ONE test-environment shim (not a mock): the browser's clock is pinned
 * to 2098 via addInitScript. Why: the product deliberately rejects deep-link
 * years outside "now" ± 5 (`filters/deepLink.ts`) and the YearPicker only
 * offers labels up to the current calendar year (planning years
 * FIRST_PLANNING_YEAR..current+1) — so sentinel planning-year 2099 is
 * unreachable through the real UI unless "now" moves. With the clock at
 * 2098, `?year=2098` parses to planning year 2099 through the REAL deep-link
 * code path. All backend/DB behavior is untouched by this.
 */
import { execFileSync } from 'node:child_process'
import { test, expect, type Page } from '@playwright/test'

const VENV_PYTHON = 'C:/04.budget_management_web/venv/Scripts/python.exe'
const HELPER = 'C:/04.budget_management_web/frontend/e2e/live_db.py'

const SENTINEL_YEAR = 2099
/** The URL's `year` param is the LABEL (standing) year = planning year - 1
 * (see `filters/deepLink.ts` — `parseYear` returns labelYear + 1). */
const DEEP_LINK_LABEL_YEAR = SENTINEL_YEAR - 1 // 2098
/** Browser "now" — inside the deep-link window for label year 2098 and makes
 * 2099 a YearPicker option. Any 2098 date works. */
const FAKE_NOW_ISO = '2098-06-15T12:00:00Z'

interface Discovered {
  cost_center: string
  filler_email: string
  department: string
  gl_account: string
}

function runHelper(command: 'discover' | 'cleanup'): string {
  return execFileSync(VENV_PYTHON, [HELPER, command], {
    encoding: 'utf-8',
    timeout: 120_000, // msal token + live TDS round-trips
  }).trim()
}

// Same reasoning as e2e/fixtures.ts: Chromium logs every non-2xx fetch as a
// console.error even when the app handled it — the ONLY allowlisted noise.
// PLUS (live-stack only): `extraHTTPHeaders` sends the Easy Auth identity
// header on EVERY request, including the cross-origin Google Fonts fetches —
// fonts.gstatic.com's preflight rejects the unknown header, Chromium falls
// back to system fonts, and logs the CORS message + its paired generic
// net::ERR_FAILED. Test-environment noise only: production Easy Auth injects
// the header server-side, so real users' font loads never carry it.
const CONSOLE_ALLOWLIST: RegExp[] = [
  /^Failed to load resource: the server responded with a status of \d+/,
  /^Access to font at 'https:\/\/fonts\.gstatic\.com\/.+Request header field x-ms-client-principal-name is not allowed /,
  /^Failed to load resource: net::ERR_FAILED$/,
]

/** Attaches the console-error collector (any unexpected console.error /
 * uncaught page error fails the test). */
function watchConsole(page: Page, unexpected: string[]): void {
  page.on('console', (msg) => {
    if (msg.type() !== 'error') return
    if (CONSOLE_ALLOWLIST.some((re) => re.test(msg.text()))) return
    unexpected.push(msg.text())
  })
  page.on('pageerror', (err) => unexpected.push(`pageerror: ${err.message}`))
}

/** GET /budget for the discovered department at the sentinel planning year
 * — THE response that proves the grid talked to the real backend. */
function budgetGridResponse(page: Page, department: string) {
  return page.waitForResponse(
    (r) => {
      if (r.request().method() !== 'GET') return false
      const url = new URL(r.url())
      return (
        url.pathname === '/budget' &&
        url.searchParams.get('department') === department &&
        url.searchParams.get('year') === String(SENTINEL_YEAR)
      )
    },
    { timeout: 120_000 },
  )
}

function putRowResponse(page: Page) {
  return page.waitForResponse(
    (r) => r.request().method() === 'PUT' && new URL(r.url()).pathname === '/budget/rows',
    { timeout: 120_000 },
  )
}

/** Pins the page's Date to FAKE_NOW_ISO (see the file docstring — the only
 * way the real UI reaches sentinel year 2099). */
async function pinClock(page: Page): Promise<void> {
  await page.addInitScript((iso: string) => {
    const RealDate = window.Date
    const fixedMs = new RealDate(iso).getTime()
    class PinnedDate extends RealDate {
      constructor(...args: unknown[]) {
        if (args.length === 0) super(fixedMs)
        else super(...(args as []))
      }
      static now(): number {
        return fixedMs
      }
    }
    window.Date = PinnedDate
  }, FAKE_NOW_ISO)
}

test.describe('live stack (real backend + real Fabric SQL DB)', () => {
  let discovered: Discovered

  test.beforeAll(() => {
    // Clean FIRST: a crashed earlier run must never leave 2099 residue that
    // would department-lock or duplicate-collide this run.
    runHelper('cleanup')
    discovered = JSON.parse(runHelper('discover')) as Discovered
  })

  test.afterAll(() => {
    // Runs even when the test fails. live_db.py exits non-zero (failing the
    // run loudly) if any 2099 row survives.
    runHelper('cleanup')
  })

  test('filler adds a Pending row at sentinel year 2099, it persists in the DB, and Submit starts the real approval chain', async ({ browser }) => {
    const { cost_center: cc, filler_email: fillerEmail, department: dept, gl_account: gl } = discovered
    const unexpectedConsole: string[] = []

    const context = await browser.newContext({
      // Easy Auth's identity header, trusted as-is by backend/app/auth.py
      // (locally there is no Easy Auth in front of uvicorn).
      extraHTTPHeaders: { 'x-ms-client-principal-name': fillerEmail },
    })
    const page = await context.newPage()
    watchConsole(page, unexpectedConsole)
    await pinClock(page)

    try {
      // -- (c) deep-link load: the grid really fetched from the backend ----
      const initialGrid = budgetGridResponse(page, dept)
      await page.goto(`/?dept=${encodeURIComponent(dept)}&year=${DEEP_LINK_LABEL_YEAR}`)

      await expect(page.getByRole('button', { name: dept })).toBeVisible({ timeout: 60_000 })
      // The clock shim + real deep-link parse landed us on planning year 2099.
      await expect(page.getByRole('combobox', { name: /ปีฐาน/ })).toHaveValue(String(SENTINEL_YEAR))

      const gridResp = await initialGrid
      expect(gridResp.ok()).toBeTruthy()
      // 2099 starts empty (no SAP/board data for 2098, cleanup emptied
      // pending) — the "add a NEW GL row" path below is the real filler flow.
      expect(await gridResp.json()).toEqual([])

      // -- (d) "+ เพิ่ม Transaction": real UI add-row flow for (cc, gl) ----
      await page.getByRole('button', { name: '+ เพิ่ม Transaction' }).click()
      await page.getByLabel('Cost Center').selectOption(cc)
      const glInput = page.getByRole('textbox', { name: 'GL Code' })
      await glInput.click() // focus opens the searchable list
      await glInput.fill(gl)
      await page.getByRole('option', { name: new RegExp(`^${gl} —`) }).click()

      const createResp = putRowResponse(page)
      await page.locator('.add-txn-form').getByRole('button', { name: 'บันทึก' }).click()
      expect((await createResp).ok()).toBeTruthy()

      const m01 = page.getByTestId(`pending-input-${cc}-${gl}-m01`)
      await expect(m01).toBeVisible()
      await expect(m01).toHaveValue('0')

      // -- (d cont.) edit the real Pending cell ---------------------------
      const saveResp = putRowResponse(page)
      await m01.fill('1500')
      await m01.blur()
      expect((await saveResp).ok()).toBeTruthy()
      await expect(m01).toHaveValue('1500')

      // -- (e) reload: the value must survive — proof of the DB round-trip -
      const reloadedGrid = budgetGridResponse(page, dept)
      await page.reload()
      expect((await reloadedGrid).ok()).toBeTruthy()
      await expect(page.getByTestId(`pending-input-${cc}-${gl}-m01`)).toHaveValue('1500')

      // -- (f) Submit via the real button; the real chain starts -----------
      const chip = page.getByTestId('approval-status-chip')
      await expect(chip).toContainText('แบบร่าง') // never-submitted DRAFT
      await expect(page.getByTestId('approval-submit-btn')).toBeVisible()

      let dialogMessage = ''
      page.once('dialog', (dialog) => {
        dialogMessage = dialog.message()
        void dialog.accept()
      })
      const submitRespPromise = page.waitForResponse(
        (r) => r.request().method() === 'POST' && new URL(r.url()).pathname === '/approval/submit',
        { timeout: 120_000 },
      )
      await page.getByTestId('approval-submit-btn').click()

      const submitResp = await submitRespPromise
      expect(submitResp.ok()).toBeTruthy()
      expect(dialogMessage).toContain(dept)
      expect(dialogMessage).toContain(`ปี ${SENTINEL_YEAR}`)

      const submitBody = (await submitResp.json()) as { status: string }
      expect(submitBody.status).toBe('PENDING_APPROVER1')
      await expect(chip).toContainText('รออนุมัติ')
      await expect(chip).toContainText('ขั้น 1')

      expect(unexpectedConsole, 'no unexpected browser console errors on the live stack').toEqual([])
    } finally {
      await context.close()
    }
  })
})
