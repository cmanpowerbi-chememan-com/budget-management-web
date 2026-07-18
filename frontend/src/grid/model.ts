/** Pure grid logic — no DOM, no fetch. Everything here is unit-testable
 * without a browser. Owns the never-cut structural rule (BUILD_PLAN A2):
 * COST (5xxx GL) and SG&A (6xxx GL) totals must never cross/combine —
 * there is deliberately no function that sums a COST section and an SGA
 * section together. */
import type { BudgetRow, GlAccount, LayerAmounts, PendingRowInput, PendingRowState } from '../api/types'

export const MONTH_KEYS = [
  'm01', 'm02', 'm03', 'm04', 'm05', 'm06', 'm07', 'm08', 'm09', 'm10', 'm11', 'm12',
] as const
export type MonthKey = (typeof MONTH_KEYS)[number]

/** Real month names for the grid header (mockup 0002.3budget-export.html
 * `MONTHS_EN`, line 1932) — the header previously rendered the raw
 * `MonthKey` ('m01'..'m12'), which is a storage key, not a label. */
export const MONTH_LABELS: Record<MonthKey, string> = {
  m01: 'Jan', m02: 'Feb', m03: 'Mar', m04: 'Apr', m05: 'May', m06: 'Jun',
  m07: 'Jul', m08: 'Aug', m09: 'Sep', m10: 'Oct', m11: 'Nov', m12: 'Dec',
}

/** Current-month key for the header/body "now" highlight (UI-parity point
 * 8a). Takes an optional `Date` so it is unit-testable without depending on
 * the real system clock; defaults to `new Date()` at call time — the
 * intended behavior in the running app. */
export function nowMonthKey(date: Date = new Date()): MonthKey {
  return MONTH_KEYS[date.getMonth()]
}

export type Side = 'COST' | 'SGA' | 'OTHER'

/** GL account prefix decides the accounting side (5=COST/ผลิต·ต้นทุน,
 * 6=SG&A/บริหาร·ขาย) — same rule the mockup and `write_model.py`'s
 * `TRAVEL_GL_BY_TYPE_SIDE` use. Anything else is bucketed as OTHER rather
 * than throwing, so one unexpected GL code never crashes the whole grid. */
export function sideOfGl(glAccount: string): Side {
  if (glAccount.startsWith('5')) return 'COST'
  if (glAccount.startsWith('6')) return 'SGA'
  return 'OTHER'
}

export interface GlMeta {
  gl_group: string
  gl_name: string | null
  is_special: boolean
  /** false = the GL is not in the GL master (`GET /budget/gl-accounts`).
   * Such rows are reference-only — not budgetable until an admin adds the
   * GL via Edit GL Group (add-later policy); the flag flips automatically
   * on the next master load, no special-casing. */
  in_master: boolean
}

const UNCATEGORIZED: GlMeta = { gl_group: 'Uncategorized', gl_name: null, is_special: false, in_master: false }

/** Group name -> color-chip class, ported verbatim from the mockup's
 * `GROUP_CHIP_CLASS` (0002.3budget-export.html lines 1437-1444). Deliberately
 * keyed by GROUP NAME, not the per-GL `is_special` flag: a fixture/live GL can
 * carry `is_special:false` while still belonging to one of the 6 special
 * groups (e.g. a Travelling Expense GL not yet flagged), which would leave
 * some rows in the same group un-chipped. Gating on the group name instead
 * guarantees every row in a chipped group renders the same color. */
const GROUP_CHIP_CLASS: Record<string, string> = {
  Entertainment: 'gl-yellow',
  'Lease & Rental': 'gl-pink',
  'Professional & Legal Fee': 'gl-purple',
  'Public Relation & Donation': 'gl-orange',
  'Training & Seminar': 'gl-blue',
  'Travelling Expense': 'gl-green',
}

/** Returns the color-chip class for a GL group name, or '' when the group
 * is not one of the 6 special groups (plain text, no chip). */
export function groupChipClass(glGroup: string): string {
  return GROUP_CHIP_CLASS[glGroup] ?? ''
}

/** Resolves a GL account's group/name/special-flag from the reference
 * list fetched from `GET /budget/gl-accounts` — the single source of
 * truth for GL metadata, used for EVERY row regardless of which layer
 * happens to be populated (a pure-SAP-led row has no gl_group of its own
 * on `read_model.py`'s BoardLayer/PendingLayer — see A8 decision log).
 * An unknown GL falls back to "Uncategorized"/non-special rather than
 * crashing the grid. */
export function glMetaFor(glAccount: string, glRef: GlAccount[]): GlMeta {
  const found = glRef.find((g) => g.gl_code === glAccount)
  if (!found) return UNCATEGORIZED
  return { gl_group: found.gl_group ?? 'Uncategorized', gl_name: found.gl_name, is_special: found.is_special, in_master: true }
}

/** Shared per-column text filters (UI-parity point 8b) — one filter string
 * per identity column, applied across BOTH side-tables (COST/SGA) so a
 * split view stays in sync rather than drifting into two independent
 * searches. */
export interface ColumnFilters {
  cc: string
  gl: string
  glGroup: string
}

export const BLANK_COLUMN_FILTERS: ColumnFilters = { cc: '', gl: '', glGroup: '' }

/** Identity-column widths (UI-parity point 8c) — replaces point 1's STATIC
 * freeze offsets (fixed `--frz1/2/3` px in CSS) with state-derived offsets,
 * so a column resize keeps the frozen band's left position correct. Only
 * the 3 identity columns are resizable — Status and the 12 month columns
 * are out of this feature's scope. */
export interface ColumnWidths {
  cc: number
  gl: number
  glGroup: number
}

export type ColumnWidthKey = keyof ColumnWidths

/** Pre-measurement placeholder only (point-1's original static offsets:
 * frz2=130, frz3=130+150=280) — used for the very first paint before the
 * fit-to-content measurement effect runs, and as `loadStoredColumnWidths`'s
 * per-key fallback when a stored value is missing/corrupted. The REAL
 * default width is fit-to-content (GridTable.tsx's measurement effect,
 * point 8d) — this constant is not "the" default column width anymore. */
export const DEFAULT_COLUMN_WIDTHS: ColumnWidths = { cc: 130, gl: 150, glGroup: 150 }

export const COLUMN_WIDTH_MIN = 60
export const COLUMN_WIDTH_MAX = 800

/** Clamp a dragged width to a sane range (mockup 0002.3budget-export.html
 * `initColumnResize`'s `Math.max(60, Math.min(800, ...))`). */
export function clampColumnWidth(width: number): number {
  return Math.min(COLUMN_WIDTH_MAX, Math.max(COLUMN_WIDTH_MIN, width))
}

/** localStorage key for persisting column widths across sessions/reloads
 * (UI-parity point 8c, matches the mockup's persistence intent). One flat
 * object for the 3 fixed keys — the mockup's per-index scheme doesn't apply
 * here since our identity-column set is fixed, not dynamic. */
export const COLUMN_WIDTHS_STORAGE_KEY = 'budgetGridColWidths'

function isFiniteNumber(value: unknown): value is number {
  return typeof value === 'number' && Number.isFinite(value)
}

/** Reads persisted column widths from localStorage. Guarded end-to-end: a
 * disabled/unavailable localStorage, corrupted JSON, or a missing/
 * non-numeric field each fall back to `DEFAULT_COLUMN_WIDTHS` (per-key, not
 * all-or-nothing) rather than throwing or producing a broken layout. Every
 * value is re-clamped in case a stale localStorage entry predates a range
 * change. */
export function loadStoredColumnWidths(): ColumnWidths {
  try {
    const raw = window.localStorage.getItem(COLUMN_WIDTHS_STORAGE_KEY)
    if (!raw) return DEFAULT_COLUMN_WIDTHS
    const parsed = JSON.parse(raw) as Partial<Record<ColumnWidthKey, unknown>>
    return {
      cc: clampColumnWidth(isFiniteNumber(parsed.cc) ? parsed.cc : DEFAULT_COLUMN_WIDTHS.cc),
      gl: clampColumnWidth(isFiniteNumber(parsed.gl) ? parsed.gl : DEFAULT_COLUMN_WIDTHS.gl),
      glGroup: clampColumnWidth(isFiniteNumber(parsed.glGroup) ? parsed.glGroup : DEFAULT_COLUMN_WIDTHS.glGroup),
    }
  } catch {
    return DEFAULT_COLUMN_WIDTHS
  }
}

/** Persists column widths — called after a drag ends or on Reset, never on
 * every intermediate drag frame (keeps writes cheap). Guarded the same way
 * as `loadStoredColumnWidths`: a quota-exceeded/disabled localStorage never
 * breaks the resize interaction itself, it just won't survive a reload. */
export function persistColumnWidths(widths: ColumnWidths): void {
  try {
    window.localStorage.setItem(COLUMN_WIDTHS_STORAGE_KEY, JSON.stringify(widths))
  } catch {
    // localStorage unavailable — resize still works for the session.
  }
}

/** True when a column-width entry already exists in localStorage — presence
 * alone (not validity of its values) marks "the user/a previous session has
 * an explicit width", which must win over the fit-to-content auto-default
 * (see `GridTable.tsx`'s measurement effect). A corrupted entry is repaired
 * per-key by `loadStoredColumnWidths`, not by pretending no override exists. */
export function hasStoredColumnWidthsOverride(): boolean {
  try {
    return window.localStorage.getItem(COLUMN_WIDTHS_STORAGE_KEY) !== null
  } catch {
    return false
  }
}

/** Removes the persisted override — called by "Reset columns" so the grid
 * goes back to fit-to-content on the NEXT data change too, not just once. */
export function clearStoredColumnWidths(): void {
  try {
    window.localStorage.removeItem(COLUMN_WIDTHS_STORAGE_KEY)
  } catch {
    // localStorage unavailable — nothing to clear, resize still works this session.
  }
}

/** Derives the 3 frozen-column left offsets from the CURRENT widths — no
 * DOM measurement (unlike the mockup's `applyFreeze()`, which reads real
 * header `getBoundingClientRect()`s). Both side-tables (COST/SGA) read the
 * SAME `colWidths` state and call this same pure function, so they stay
 * pixel-aligned by construction rather than by re-measuring two separate
 * DOM trees. */
export function freezeOffsets(widths: ColumnWidths): { frz1: number; frz2: number; frz3: number } {
  return { frz1: 0, frz2: widths.cc, frz3: widths.cc + widths.gl }
}

/** Horizontal padding allowance added to a raw measured TEXT width to
 * approximate the real cell's box size (`.data-table td`/`th` both use
 * `padding: Npx 10px`, i.e. 20px of horizontal padding, plus a buffer for
 * the resize-handle hit strip, sub-pixel rounding, and font-metric drift
 * across machines). Used by `fitColumnWidth` (GridTable.tsx's DOM
 * measurement pass feeds it raw text widths). Since the grid switched to
 * FIXED table layout this allowance is no longer a mere floor that
 * min-content sizing could backstop — it IS the rendered width, so a
 * too-tight buffer visibly ellipsizes a header label that measured within
 * a pixel of the content box ("Cost Center" measured 76px → 24px allowance
 * left 0px of slack). 32 = 20px padding + 12px slack. */
export const COLUMN_WIDTH_MEASURE_PADDING = 32

/** Converts a raw measured text/content width into a usable column width:
 * add the cell's own padding allowance, then clamp to the same 60-800 range
 * as a manual drag. A raw width of 0 (e.g. jsdom, which never lays out real
 * text) deterministically floors to `COLUMN_WIDTH_MIN` via the clamp. */
export function fitColumnWidth(rawTextWidth: number): number {
  return clampColumnWidth(Math.ceil(rawTextWidth) + COLUMN_WIDTH_MEASURE_PADDING)
}

/** Bounded set of "longest unique" candidate strings per identity column,
 * fed to the hidden DOM measurement pass (GridTable.tsx). A column's natural
 * fit width is driven by its LONGEST value, so measuring every row would be
 * wasted DOM work for no better an answer — dedup + cap keeps the pass
 * O(unique values, capped) instead of O(rows). `glGroup` cardinality is
 * small and fixed (GL master group names) so it is never capped. */
export interface ColumnMeasureCandidates {
  cc: string[]
  /** GL account codes (e.g. "6210900060"). */
  gl: string[]
  /** GL account names (e.g. "ค่าซ่อมบำรุง - ซอฟต์แวร์") — the second line of
   * the GL cell, often WIDER than the code, so the GL column's fit-to-content
   * width must be max(widest code, widest name) or the name overflows. */
  glName: string[]
  glGroup: string[]
}

export const COLUMN_MEASURE_CANDIDATE_CAP = 30

export function selectMeasureCandidates(
  rows: BudgetRow[],
  glRef: GlAccount[],
  cap: number = COLUMN_MEASURE_CANDIDATE_CAP,
): ColumnMeasureCandidates {
  const ccSet = new Set<string>()
  const glSet = new Set<string>()
  const glNameSet = new Set<string>()
  const glGroupSet = new Set<string>()
  rows.forEach((r) => {
    const meta = glMetaFor(r.gl_account, glRef)
    ccSet.add(r.cost_center)
    glSet.add(r.gl_account)
    // The GL cell stacks the code + the name; the column must fit whichever is
    // wider. Skip null names so the measurer never sizes to the literal "null".
    if (meta.gl_name) glNameSet.add(meta.gl_name)
    glGroupSet.add(meta.gl_group)
  })
  const topLongest = (values: Set<string>) => [...values].sort((a, b) => b.length - a.length).slice(0, cap)
  return {
    cc: topLongest(ccSet),
    gl: topLongest(glSet),
    glName: topLongest(glNameSet),
    glGroup: [...glGroupSet],
  }
}

function matchesFilter(value: string, filter: string): boolean {
  const trimmed = filter.trim()
  if (!trimmed) return true
  return value.toLowerCase().includes(trimmed.toLowerCase())
}

/** Filters rows BEFORE grouping (`groupAndSortBySide`) so both side-tables
 * and their subtotals only ever reflect matching rows — case-insensitive
 * substring match, empty filter = matches everything. `gl_group` is
 * resolved via `glMetaFor` (never `row.gl_group`, which doesn't exist on
 * `BudgetRow` — group membership always comes from the GL master). */
export function filterRows(rows: BudgetRow[], glRef: GlAccount[], filters: ColumnFilters): BudgetRow[] {
  if (!filters.cc.trim() && !filters.gl.trim() && !filters.glGroup.trim()) return rows
  return rows.filter((r) => {
    const meta = glMetaFor(r.gl_account, glRef)
    return (
      matchesFilter(r.cost_center, filters.cc) &&
      matchesFilter(r.gl_account, filters.gl) &&
      matchesFilter(meta.gl_group, filters.glGroup)
    )
  })
}

export interface GlGroupSection {
  glGroup: string
  rows: BudgetRow[]
  subtotal: { sap: LayerAmounts; board: LayerAmounts; pending: LayerAmounts }
}

function blankTotals(): LayerAmounts {
  const base = { total_year: 0 } as LayerAmounts
  MONTH_KEYS.forEach((m) => {
    ;(base as unknown as Record<MonthKey, number>)[m] = 0
  })
  return base
}

function addLayer(acc: LayerAmounts, layer: LayerAmounts): LayerAmounts {
  const result = { ...acc }
  MONTH_KEYS.forEach((m) => {
    ;(result as unknown as Record<MonthKey, number>)[m] += layer[m]
  })
  result.total_year += layer.total_year
  return result
}

/** Sums the 3 layers across a list of rows. Callers must only pass rows
 * from ONE side (COST or SGA) — this function does not check the side
 * itself; `groupAndSortBySide` is what guarantees the split upstream. */
export function sectionTotals(rows: BudgetRow[]): { sap: LayerAmounts; board: LayerAmounts; pending: LayerAmounts } {
  return rows.reduce(
    (acc, r) => ({
      sap: addLayer(acc.sap, r.sap),
      board: addLayer(acc.board, r.board),
      pending: addLayer(acc.pending, r.pending),
    }),
    { sap: blankTotals(), board: blankTotals(), pending: blankTotals() },
  )
}

/** Splits + groups the visible rows for the main grid: COST (5xxx) and
 * SG&A (6xxx) sections are structurally separate return values — never a
 * single combined list — then each side is grouped by gl_group (sorted
 * alphabetically, Thai-aware) with a per-group subtotal, rows sorted by
 * gl_account within a group. `OTHER`-side rows (unexpected GL prefix) are
 * dropped from both sections rather than silently miscounted into either
 * — logged by the caller if it wants visibility. */
export function groupAndSortBySide(
  rows: BudgetRow[],
  glRef: GlAccount[],
): { COST: GlGroupSection[]; SGA: GlGroupSection[] } {
  const bySide: Record<Side, BudgetRow[]> = { COST: [], SGA: [], OTHER: [] }
  rows.forEach((r) => bySide[sideOfGl(r.gl_account)].push(r))

  function buildSections(sideRows: BudgetRow[]): GlGroupSection[] {
    const byGroup = new Map<string, BudgetRow[]>()
    sideRows.forEach((r) => {
      const { gl_group } = glMetaFor(r.gl_account, glRef)
      const list = byGroup.get(gl_group) ?? []
      list.push(r)
      byGroup.set(gl_group, list)
    })
    return [...byGroup.entries()]
      .sort(([a], [b]) => a.localeCompare(b, 'th'))
      .map(([glGroup, groupRows]) => {
        const sorted = [...groupRows].sort((a, b) => a.gl_account.localeCompare(b.gl_account))
        return { glGroup, rows: sorted, subtotal: sectionTotals(sorted) }
      })
  }

  return { COST: buildSections(bySide.COST), SGA: buildSections(bySide.SGA) }
}

/** A month cell is editable only when the row itself is in the caller's
 * Fill scope (`row.editable`, from A3/A4 RLS) AND the GL is not one of
 * the 6 special groups — those always route through their subform (A9),
 * never a direct main-page cell edit — AND the GL is in the GL master
 * (`glInMaster`). A GL outside the master is deliberately not budgetable
 * (add-later policy): the server would 400 any `PUT /budget/rows` for it
 * ("not a recognised GL account"), so rendering an input would be a trap.
 * Once an admin adds the GL via Edit GL Group, the freshly-loaded master
 * makes the row editable automatically. */
export function isEditableCell(rowEditable: boolean, isSpecialGl: boolean, glInMaster: boolean): boolean {
  return rowEditable && !isSpecialGl && glInMaster
}

/** Pure: returns a NEW row with one Pending month cell updated and
 * `total_year` recomputed client-side for immediate display. The server
 * remains the authority — `mergeSavedRow` overwrites this with the real
 * persisted state once the save round-trip completes. */
export function applyMonthEdit(row: BudgetRow, month: MonthKey, value: number): BudgetRow {
  const nextPending = { ...row.pending, [month]: value }
  nextPending.total_year = MONTH_KEYS.reduce((sum, m) => sum + nextPending[m], 0)
  return { ...row, pending: nextPending }
}

/** Builds the `PUT /budget/rows` payload from a row's CURRENT pending
 * state — `expected_updated_at` is the optimistic-lock token
 * (`pending.updated_at`), `null` when no pending row exists yet (create
 * path, per `write_model.py`'s contract). */
export function buildSavePayload(row: BudgetRow, fiscalYear: number): PendingRowInput {
  const months = Object.fromEntries(MONTH_KEYS.map((m) => [m, row.pending[m]])) as Record<MonthKey, number>
  return {
    cost_center: row.cost_center,
    gl_account: row.gl_account,
    fiscal_year: fiscalYear,
    ...months,
    remark: row.pending.remark,
    expected_updated_at: row.pending.updated_at,
  }
}

/** After a successful save, replace the Pending layer with the
 * server-authoritative state (months/total_year/updated_at) — never trust
 * the locally-computed `total_year` as final. */
export function mergeSavedRow(row: BudgetRow, saved: PendingRowState): BudgetRow {
  const months = Object.fromEntries(MONTH_KEYS.map((m) => [m, saved[m]])) as Record<MonthKey, number>
  return {
    ...row,
    pending: {
      ...row.pending,
      ...months,
      total_year: saved.total_year,
      remark: saved.remark,
      template: saved.template,
      gl_name: saved.gl_name,
      gl_group: saved.gl_group,
      c_level: saved.c_level,
      division: saved.division,
      department: saved.department,
      updated_at: saved.updated_at,
    },
  }
}

/** Builds the all-zero create payload for "+ เพิ่ม transaction" — a brand
 * new (cost_center, gl_account) row, never seen before, always
 * `expected_updated_at: null` (create path). */
export function buildNewRowPayload(costCenter: string, glAccount: string, fiscalYear: number): PendingRowInput {
  const months = Object.fromEntries(MONTH_KEYS.map((m) => [m, 0])) as Record<MonthKey, number>
  return {
    cost_center: costCenter,
    gl_account: glAccount,
    fiscal_year: fiscalYear,
    ...months,
    remark: null,
    expected_updated_at: null,
  }
}

export interface NewTransactionInput {
  costCenter: string
  glAccount: string
  fillCostCenters: string[]
  glRef: GlAccount[]
  existingRows: BudgetRow[]
}

export interface ValidationResult {
  ok: boolean
  errorTh?: string
}

/** Validates "+ เพิ่ม transaction" BEFORE calling the API — the server
 * re-checks all of this anyway (Fill scope, special-GL block, PK
 * collision -> 409), but a client-side check gives an immediate,
 * friendly message instead of a round-trip for an obviously-invalid pick. */
export function validateNewTransaction(input: NewTransactionInput): ValidationResult {
  if (!input.costCenter) return { ok: false, errorTh: 'กรุณาเลือก Cost Center' }
  if (!input.glAccount) return { ok: false, errorTh: 'กรุณาเลือก GL Code' }
  if (!input.fillCostCenters.includes(input.costCenter)) {
    return { ok: false, errorTh: `${input.costCenter} ไม่อยู่ในสิทธิ์กรอกงบของคุณ` }
  }
  const meta = glMetaFor(input.glAccount, input.glRef)
  if (meta.is_special) {
    return { ok: false, errorTh: `${input.glAccount} เป็นกลุ่มพิเศษ (${meta.gl_group}) — แก้ไขผ่านฟอร์มย่อย` }
  }
  const exists = input.existingRows.some(
    (r) => r.cost_center === input.costCenter && r.gl_account === input.glAccount,
  )
  if (exists) {
    return { ok: false, errorTh: 'รายการนี้มีอยู่ในตารางแล้ว' }
  }
  return { ok: true }
}

/** THB display formatting matching the mockup's `fmt()`: thousands
 * separators, zero shown as an em-dash placeholder (never a bare "0"). */
export function formatThb(value: number): string {
  if (!value) return '—'
  return Math.round(value).toLocaleString('en-US')
}
