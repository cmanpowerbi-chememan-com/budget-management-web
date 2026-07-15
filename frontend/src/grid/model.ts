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
}

const UNCATEGORIZED: GlMeta = { gl_group: 'Uncategorized', gl_name: null, is_special: false }

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
  return { gl_group: found.gl_group ?? 'Uncategorized', gl_name: found.gl_name, is_special: found.is_special }
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
 * never a direct main-page cell edit, even when the row is otherwise
 * editable. */
export function isEditableCell(rowEditable: boolean, isSpecialGl: boolean): boolean {
  return rowEditable && !isSpecialGl
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
