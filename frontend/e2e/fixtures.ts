/** Shared E2E fixtures for the permanent Playwright journey suite
 * (frontend/e2e/*.spec.ts). Owns two things every journey spec needs:
 *
 * 1. A console-error collector — wraps Playwright's `page` fixture so ANY
 *    `console.error`/uncaught page error fails the test, unless the message
 *    matches `CONSOLE_ALLOWLIST` (documented at the constant below).
 * 2. Per-persona network mocks — `installMocks(page, world)` intercepts
 *    every backend call this SPA makes (see `src/api/*.ts`) and serves
 *    contract-accurate JSON built from the SAME `src/api/types.ts` shapes
 *    the real components consume, so a shape drift here would show up as a
 *    real rendering failure, not a silently-passing test.
 *
 * All backend calls are intercepted — no live backend/DB is ever touched.
 */
import { test as base, type Page, type Route } from '@playwright/test'
import type {
  ApprovalStatusState,
  AttachmentInfo,
  BoardLayer,
  BudgetRow,
  DepartmentRow,
  DetailLineState,
  GlAccount,
  MeResponse,
  PendingForMeResponse,
  PendingLayer,
  PendingRowState,
  SapLayer,
  ScopeResponse,
  TripListItem,
  TripState,
} from '../src/api/types'

// ---------------------------------------------------------------------------
// Console-error collector (fails the test on any unexpected console.error /
// uncaught page error). No THIRD-PARTY noise has been observed in this app
// (no analytics/ads/fonts-over-CORS) — the one allowlisted pattern below is
// NOT third-party noise, it's Chromium's own resource-loading diagnostic:
// every `fetch()` whose response has a non-2xx status logs
// "Failed to load resource: the server responded with a status of NNN" as a
// console.error, regardless of whether the app handled the error correctly.
// Several journeys/edge-states DELIBERATELY mock 403/409/502/500 responses to
// prove the app's OWN error handling — this browser-level message is expected
// noise on those tests, not an application bug. Do not widen this beyond the
// exact message shape.
// ---------------------------------------------------------------------------
const CONSOLE_ALLOWLIST: RegExp[] = [/^Failed to load resource: the server responded with a status of \d+/]

export const test = base.extend<{ page: Page }>({
  // eslint-disable-next-line no-empty-pattern
  page: async ({ page }, use) => {
    const unexpected: string[] = []
    page.on('console', (msg) => {
      if (msg.type() !== 'error') return
      const text = msg.text()
      if (CONSOLE_ALLOWLIST.some((re) => re.test(text))) return
      unexpected.push(text)
    })
    page.on('pageerror', (err) => unexpected.push(`pageerror: ${err.message}`))

    await use(page)

    if (unexpected.length > 0) {
      throw new Error(`unexpected console error(s):\n${unexpected.join('\n')}`)
    }
  },
})

export { expect } from '@playwright/test'

// ---------------------------------------------------------------------------
// Fixture data — Thai names deliberately match the domain (CC/ฝ่าย/GL),
// mirroring the shapes already proven in src/grid/BudgetGrid.test.tsx and
// src/App.test.tsx so a shape mismatch here would be a real regression, not
// a fixture quirk.
// ---------------------------------------------------------------------------
export const PLANNING_YEAR = new Date().getFullYear() + 1

export const DIVISION = 'สายงานสนับสนุนองค์กร'
export const C_LEVEL = 'CFO'

export const DEPT = 'ฝ่ายบัญชี'
export const CC = '10CA013000'

export const DEPT2 = 'ฝ่ายจัดซื้อ'
export const CC2 = '10PU014000'

export const GL_OFFICE_COST = '5211800030'
export const GL_OFFICE_SGA = '6211800030'
export const GL_ENTERTAIN_EXT = '5211900030'
export const GL_TRAVEL_PERDIEM_COST = '5210400010'

export const GL_REF: GlAccount[] = [
  { gl_code: GL_OFFICE_COST, gl_group: 'Office Expenses', gl_name: 'ค่าใช้จ่ายสำนักงาน', is_special: false },
  { gl_code: GL_OFFICE_SGA, gl_group: 'Office Expenses', gl_name: 'ค่าใช้จ่ายสำนักงาน (บริหาร)', is_special: false },
  { gl_code: GL_ENTERTAIN_EXT, gl_group: 'Entertainment', gl_name: 'ค่าเลี้ยงรับรองภายนอก', is_special: true },
  { gl_code: GL_TRAVEL_PERDIEM_COST, gl_group: 'Travelling Expense', gl_name: 'เบี้ยเลี้ยง', is_special: true },
]

const MONTH_KEYS = ['m01', 'm02', 'm03', 'm04', 'm05', 'm06', 'm07', 'm08', 'm09', 'm10', 'm11', 'm12'] as const

export function blankLayer(overrides: Partial<Record<(typeof MONTH_KEYS)[number] | 'total_year', number>> = {}): SapLayer {
  const base = { total_year: 0 } as SapLayer
  MONTH_KEYS.forEach((m) => {
    ;(base as unknown as Record<string, number>)[m] = 0
  })
  return { ...base, ...overrides }
}

export function makeBudgetRow(input: {
  costCenter: string
  glAccount: string
  editable?: boolean
  sap?: Partial<Record<(typeof MONTH_KEYS)[number] | 'total_year', number>>
  pending?: Partial<Record<(typeof MONTH_KEYS)[number] | 'total_year', number>>
  pendingUpdatedAt?: string | null
}): BudgetRow {
  const board: BoardLayer = { ...blankLayer(), gl_name: null, gl_group: null, c_level: null, division: null, department: null }
  const pending: PendingLayer = {
    ...blankLayer(input.pending ?? {}),
    template: null,
    remark: null,
    gl_name: null,
    gl_group: null,
    c_level: null,
    division: null,
    department: null,
    updated_at: input.pendingUpdatedAt ?? null,
  }
  return {
    cost_center: input.costCenter,
    gl_account: input.glAccount,
    sap: blankLayer(input.sap ?? {}),
    board,
    pending,
    editable: input.editable ?? true,
  }
}

/** A ready-to-use `ApprovalStatusState` — every field defaults to the
 * "never submitted" DRAFT shape (per `types.ts`'s own doc comment); callers
 * override just the fields their scenario cares about. */
export function approvalState(overrides: Partial<ApprovalStatusState> = {}): ApprovalStatusState {
  return {
    department: DEPT,
    fiscal_year: PLANNING_YEAR,
    status: 'DRAFT',
    submitter_empcode: null,
    submitter_email: null,
    submitted_at: null,
    approver1_empcode: null,
    approver1_actioned_at: null,
    approver2_actioned_at: null,
    approver3_actioned_at: null,
    reject_reason: null,
    rejected_by_empcode: null,
    updated_at: null,
    current_position: null,
    current_approver_empcode: null,
    can_act: false,
    notification_warning: null,
    ...overrides,
  }
}

// ---------------------------------------------------------------------------
// World — the mutable mock backend state for one test.
//
// Endpoints triggered by an explicit user action (a button click's PUT/POST/
// DELETE) read from a QUEUE (array): the first call shifts the first entry
// off; the LAST remaining entry keeps being returned forever after (so a
// test can set up "initial response, then what a second call should
// return"). This is safe for those because a click only ever fires once.
//
// Endpoints fetched from a component's MOUNT effect (GET /budget,
// /approval/status, /attachments, /budget/detail, /budget/trip) are a
// DIFFERENT story: React StrictMode (main.tsx) double-invokes the initial
// mount's effects in dev, which would silently consume TWO queue entries
// before a test ever gets to act — turning "item[0]=initial, item[1]=after
// my action" into "item[1] shows up immediately, item[0] is never seen".
// `/budget` is guarded structurally (see its dispatch branch below); approval
// status and attachments instead use CURRENT MUTABLE STATE (a plain value,
// not a queue) that only changes when a write's `onServed` hook fires — safe
// under any number of extra mount reads because re-reading unchanged state is
// a no-op.
// ---------------------------------------------------------------------------
interface ErrorResult {
  status: 'error'
  httpStatus: number
  detail?: string
  /** Runs exactly once, when this response is actually served — the escape
   * hatch for "and THEN the mock backend's state changes", e.g. simulating
   * that a concurrent approve landed first. Never tied to queue position,
   * so it is immune to StrictMode's extra mount-triggered reads. */
  onServed?: () => void
}
function ok<T>(body: T, onServed?: () => void): { status: 'ok'; body: T; onServed?: () => void } {
  return { status: 'ok', body, onServed }
}
function err(httpStatus: number, detail?: string, onServed?: () => void): ErrorResult {
  return { status: 'error', httpStatus, detail, onServed }
}
type Result<T> = { status: 'ok'; body: T; onServed?: () => void } | ErrorResult

export interface World {
  me: MeResponse
  scope: ScopeResponse
  scopeErrorStatus: number | null
  departments: DepartmentRow[]
  departmentsErrorStatus: number | null
  glAccounts: GlAccount[]

  budgetGridQueue: BudgetRow[][]
  budgetGridErrorStatus: number | null

  saveRowQueue: Result<PendingRowState>[]
  detailLinesQueue: DetailLineState[][]
  saveDetailQueue: Result<DetailLineState>[]
  deleteDetailQueue: Result<{ ok: true }>[]
  tripsQueue: TripListItem[][]
  saveTripQueue: Result<TripState>[]
  deleteTripQueue: Result<{ ok: true }>[]

  /** Keyed by department name — the CURRENT status for that department
   * (mutable, not a queue: GET /approval/status is mount-triggered, so a
   * queue would be silently double-drained by React StrictMode's dev-only
   * double-mount before a test ever acts). To simulate "this department's
   * status changed", either mutate this map directly in the test body, or
   * attach an `onServed` hook to a submit/approve/reject queue entry. */
  approvalStatusByDept: Record<string, ApprovalStatusState>
  submitQueue: Result<ApprovalStatusState>[]
  approveQueue: Result<ApprovalStatusState>[]
  rejectQueue: Result<ApprovalStatusState>[]
  pendingForMe: PendingForMeResponse

  /** Mutable, not a queue — same StrictMode reasoning as
   * `approvalStatusByDept`. A successful upload's `onServed` hook is the
   * normal way to append the new file (mirrors a real backend). */
  attachments: AttachmentInfo[]
  uploadQueue: Result<AttachmentInfo>[]
  downloadUrl: string

  captured: {
    budgetQueries: Record<string, string>[]
    departmentsQueries: Record<string, string>[]
    saveRowBodies: unknown[]
    detailQueries: Record<string, string>[]
    detailBodies: unknown[]
    deleteDetailParams: Record<string, string>[]
    tripQueries: Record<string, string>[]
    tripBodies: unknown[]
    deleteTripParams: Record<string, string>[]
    submitBodies: unknown[]
    approveBodies: unknown[]
    rejectBodies: unknown[]
    approvalStatusQueries: Record<string, string>[]
    pendingForMeQueries: Record<string, string>[]
    attachmentsQueries: Record<string, string>[]
    uploadRaw: string[]
  }
}

function nextFromQueue<T>(queue: T[], label: string): T {
  if (queue.length === 0) throw new Error(`e2e fixtures: queue exhausted for ${label}`)
  if (queue.length > 1) return queue.shift() as T
  return queue[0]
}

export function createWorld(overrides: Partial<World> = {}): World {
  return {
    me: { email: 'somchai.f@chememan.com', app_env: 'local' },
    scope: { email: 'somchai.f@chememan.com', is_admin: false, role: 'filler', fill_cost_centers: [CC], see_cost_centers: [CC] },
    scopeErrorStatus: null,
    departments: [{ cost_center: CC, department: DEPT, division: DIVISION, c_level: C_LEVEL }],
    departmentsErrorStatus: null,
    glAccounts: GL_REF,

    budgetGridQueue: [[]],
    budgetGridErrorStatus: null,

    saveRowQueue: [],
    detailLinesQueue: [[]],
    saveDetailQueue: [],
    deleteDetailQueue: [],
    tripsQueue: [[]],
    saveTripQueue: [],
    deleteTripQueue: [],

    approvalStatusByDept: {},
    submitQueue: [],
    approveQueue: [],
    rejectQueue: [],
    pendingForMe: { departments: [] },

    attachments: [],
    uploadQueue: [],
    downloadUrl: 'https://cmandwprd.sharepoint.com/mock-download/invoice.pdf',

    captured: {
      budgetQueries: [],
      departmentsQueries: [],
      saveRowBodies: [],
      detailQueries: [],
      detailBodies: [],
      deleteDetailParams: [],
      tripQueries: [],
      tripBodies: [],
      deleteTripParams: [],
      submitBodies: [],
      approveBodies: [],
      rejectBodies: [],
      approvalStatusQueries: [],
      pendingForMeQueries: [],
      attachmentsQueries: [],
      uploadRaw: [],
    },
    ...overrides,
  }
}

// ---------------------------------------------------------------------------
// Persona builders
// ---------------------------------------------------------------------------
export function fillerWorld(overrides: Partial<World> = {}): World {
  return createWorld({
    scope: { email: 'somchai.f@chememan.com', is_admin: false, role: 'filler', fill_cost_centers: [CC], see_cost_centers: [CC] },
    ...overrides,
  })
}

/** Approver = a See-only caller (not necessarily a Filler of the department
 * they approve — project decision: `see_only` keeps the full page). Two
 * departments in scope so "buttons only on my turn" can be proven against a
 * SECOND, non-turn department. */
export function approverWorld(overrides: Partial<World> = {}): World {
  return createWorld({
    scope: { email: 'nipaporn.t@chememan.com', is_admin: false, role: 'see_only', fill_cost_centers: [], see_cost_centers: [CC, CC2] },
    departments: [
      { cost_center: CC, department: DEPT, division: DIVISION, c_level: C_LEVEL },
      { cost_center: CC2, department: DEPT2, division: DIVISION, c_level: C_LEVEL },
    ],
    ...overrides,
  })
}

export function dualRoleAdminWorld(overrides: Partial<World> = {}): World {
  return createWorld({
    scope: { email: 'admin.dual@chememan.com', is_admin: true, role: 'admin', fill_cost_centers: [CC], see_cost_centers: [CC] },
    ...overrides,
  })
}

export function pureAdminWorld(overrides: Partial<World> = {}): World {
  return createWorld({
    scope: { email: 'jakkaritw@chememan.com', is_admin: true, role: 'admin', fill_cost_centers: [], see_cost_centers: [] },
    ...overrides,
  })
}

export function noScopeWorld(overrides: Partial<World> = {}): World {
  return createWorld({
    scope: { email: 'outsider@chememan.com', is_admin: false, role: 'none', fill_cost_centers: [], see_cost_centers: [] },
    departments: [],
    ...overrides,
  })
}

// ---------------------------------------------------------------------------
// Route installation — one catch-all matcher on the known API path
// namespaces (matches vite.config.ts's dev proxy list); everything else
// (Vite's own JS/CSS/HMR) is passed through untouched via `route.continue()`.
// ---------------------------------------------------------------------------
const API_PREFIXES = ['/me', '/scope', '/budget', '/approval', '/attachments']

function isApiPath(pathname: string): boolean {
  return API_PREFIXES.some((p) => pathname === p || pathname.startsWith(`${p}/`))
}

function fulfillJson(route: Route, status: number, body: unknown) {
  return route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) })
}

function queryOf(url: URL): Record<string, string> {
  return Object.fromEntries(url.searchParams.entries())
}

export async function installMocks(page: Page, world: World): Promise<void> {
  await page.route('**/*', async (route) => {
    const request = route.request()
    const url = new URL(request.url())
    if (!isApiPath(url.pathname)) return route.continue()

    const method = request.method()
    const path = url.pathname

    if (path === '/me' && method === 'GET') {
      return fulfillJson(route, 200, world.me)
    }

    if (path === '/scope' && method === 'GET') {
      if (world.scopeErrorStatus) return fulfillJson(route, world.scopeErrorStatus, { detail: 'scope lookup failed' })
      return fulfillJson(route, 200, world.scope)
    }

    if (path === '/scope/departments' && method === 'GET') {
      world.captured.departmentsQueries.push(queryOf(url))
      if (world.departmentsErrorStatus) return fulfillJson(route, world.departmentsErrorStatus, { detail: 'departments lookup failed' })
      return fulfillJson(route, 200, world.departments)
    }

    if (path === '/budget' && method === 'GET') {
      world.captured.budgetQueries.push(queryOf(url))
      if (world.budgetGridErrorStatus) {
        return fulfillJson(route, world.budgetGridErrorStatus, { detail: 'SAP actuals unavailable, please try again later' })
      }
      // BudgetGrid's `department` state starts `null` and is only resolved
      // asynchronously (deep-link validation against the fetched hierarchy,
      // A8) — PLUS React StrictMode (main.tsx) double-invokes the initial
      // mount's effects in dev. Both mean this endpoint is legitimately
      // called 2-3 times with NO department before the "real" filtered
      // request ever fires. Serve empty data for those WITHOUT consuming a
      // test's queue, so a spec's queue ordering (item[0] = initial state,
      // item[1] = post-action state) stays deterministic regardless of how
      // many of these harmless pre-resolution calls happen first.
      if (!url.searchParams.get('department')) {
        return fulfillJson(route, 200, [])
      }
      return fulfillJson(route, 200, nextFromQueue(world.budgetGridQueue, 'GET /budget'))
    }

    if (path === '/budget/gl-accounts' && method === 'GET') {
      return fulfillJson(route, 200, world.glAccounts)
    }

    if (path === '/budget/rows' && method === 'PUT') {
      world.captured.saveRowBodies.push(request.postDataJSON())
      const next = nextFromQueue(world.saveRowQueue, 'PUT /budget/rows')
      next.onServed?.()
      if (next.status === 'error') return fulfillJson(route, next.httpStatus, { detail: next.detail })
      return fulfillJson(route, 200, next.body)
    }

    if (path === '/budget/detail' && method === 'GET') {
      world.captured.detailQueries.push(queryOf(url))
      return fulfillJson(route, 200, nextFromQueue(world.detailLinesQueue, 'GET /budget/detail'))
    }

    if (path === '/budget/detail' && method === 'PUT') {
      world.captured.detailBodies.push(request.postDataJSON())
      const next = nextFromQueue(world.saveDetailQueue, 'PUT /budget/detail')
      next.onServed?.()
      if (next.status === 'error') return fulfillJson(route, next.httpStatus, { detail: next.detail })
      return fulfillJson(route, 200, next.body)
    }

    if (path === '/budget/detail' && method === 'DELETE') {
      world.captured.deleteDetailParams.push(queryOf(url))
      const next = nextFromQueue(world.deleteDetailQueue, 'DELETE /budget/detail')
      next.onServed?.()
      if (next.status === 'error') return fulfillJson(route, next.httpStatus, { detail: next.detail })
      return fulfillJson(route, 200, next.body)
    }

    if (path === '/budget/trip' && method === 'GET') {
      world.captured.tripQueries.push(queryOf(url))
      return fulfillJson(route, 200, nextFromQueue(world.tripsQueue, 'GET /budget/trip'))
    }

    if (path === '/budget/trip' && (method === 'POST' || method === 'PUT')) {
      world.captured.tripBodies.push(request.postDataJSON())
      const next = nextFromQueue(world.saveTripQueue, 'POST|PUT /budget/trip')
      next.onServed?.()
      if (next.status === 'error') return fulfillJson(route, next.httpStatus, { detail: next.detail })
      return fulfillJson(route, 200, next.body)
    }

    if (path === '/budget/trip' && method === 'DELETE') {
      world.captured.deleteTripParams.push(queryOf(url))
      const next = nextFromQueue(world.deleteTripQueue, 'DELETE /budget/trip')
      next.onServed?.()
      if (next.status === 'error') return fulfillJson(route, next.httpStatus, { detail: next.detail })
      return fulfillJson(route, 200, next.body)
    }

    if (path === '/approval/status' && method === 'GET') {
      world.captured.approvalStatusQueries.push(queryOf(url))
      const department = url.searchParams.get('department') ?? ''
      const current = world.approvalStatusByDept[department] ?? approvalState({ department })
      return fulfillJson(route, 200, current)
    }

    if (path === '/approval/submit' && method === 'POST') {
      const body = request.postDataJSON()
      world.captured.submitBodies.push(body)
      const next = nextFromQueue(world.submitQueue, 'POST /approval/submit')
      next.onServed?.()
      if (next.status === 'error') return fulfillJson(route, next.httpStatus, { detail: next.detail })
      world.approvalStatusByDept[body.department] = next.body
      return fulfillJson(route, 200, next.body)
    }

    if (path === '/approval/approve' && method === 'POST') {
      const body = request.postDataJSON()
      world.captured.approveBodies.push(body)
      const next = nextFromQueue(world.approveQueue, 'POST /approval/approve')
      next.onServed?.()
      if (next.status === 'error') return fulfillJson(route, next.httpStatus, { detail: next.detail })
      world.approvalStatusByDept[body.department] = next.body
      return fulfillJson(route, 200, next.body)
    }

    if (path === '/approval/reject' && method === 'POST') {
      const body = request.postDataJSON()
      world.captured.rejectBodies.push(body)
      const next = nextFromQueue(world.rejectQueue, 'POST /approval/reject')
      next.onServed?.()
      if (next.status === 'error') return fulfillJson(route, next.httpStatus, { detail: next.detail })
      world.approvalStatusByDept[body.department] = next.body
      return fulfillJson(route, 200, next.body)
    }

    if (path === '/approval/pending-for-me' && method === 'GET') {
      world.captured.pendingForMeQueries.push(queryOf(url))
      return fulfillJson(route, 200, world.pendingForMe)
    }

    if (path === '/attachments' && method === 'GET') {
      world.captured.attachmentsQueries.push(queryOf(url))
      return fulfillJson(route, 200, world.attachments)
    }

    if (path === '/attachments/upload' && method === 'POST') {
      world.captured.uploadRaw.push(request.postData() ?? '')
      const next = nextFromQueue(world.uploadQueue, 'POST /attachments/upload')
      next.onServed?.()
      if (next.status === 'error') return fulfillJson(route, next.httpStatus, { detail: next.detail })
      return fulfillJson(route, 200, next.body)
    }

    if (path === '/attachments/download-url' && method === 'GET') {
      return fulfillJson(route, 200, { url: world.downloadUrl })
    }

    return fulfillJson(route, 404, { detail: `unmocked in e2e fixtures: ${method} ${path}` })
  })
}

/** Extracts `department`/`fiscal_year`/the uploaded file's `filename` from a
 * raw `multipart/form-data` request body (Playwright's `request.postData()`
 * does not parse multipart) — a small, purpose-built regex reader, not a
 * general MIME parser, since these 3 fields are all step 3.2 needs to
 * assert. */
export function parseMultipartFields(raw: string): { department?: string; fiscal_year?: string; filename?: string } {
  const department = raw.match(/name="department"\r?\n\r?\n([^\r\n]*)/)?.[1]
  const fiscal_year = raw.match(/name="fiscal_year"\r?\n\r?\n([^\r\n]*)/)?.[1]
  const filename = raw.match(/name="file";\s*filename="([^"]*)"/)?.[1]
  return { department, fiscal_year, filename }
}

export { ok, err }
