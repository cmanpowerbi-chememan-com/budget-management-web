/** Pure derivations for the header (`UserBar`) — สายงาน/ฝ่าย/GL summary. No
 * DOM, no fetch — built from data the hooks in this folder already fetched
 * (`useOwnDepartments`/`useFillGlCount`). */
import type { BudgetRow, DepartmentRow } from '../api/types'

export interface ScopeSummary {
  /** Distinct สายงาน across the caller's scope CCs, Thai-sorted. */
  divisions: string[]
  /** Distinct ฝ่าย across the caller's scope CCs, Thai-sorted. */
  departments: string[]
}

/** Restricts `departments` (`GET /scope/departments` rows, already
 * See-scoped server-side) to the CCs that drive the header chip, then
 * derives the distinct สายงาน/ฝ่าย.
 *
 * Which CC list drives the chip:
 * - Fill non-empty (the common Filler case) → Fill only, UNCHANGED from
 *   before this fallback existed. See is broader/viewing and deliberately
 *   excluded here so an ordinary Filler's header never grows extra chips
 *   from departments they merely manage.
 * - Fill empty, See non-empty (a manager/See-only user with real scope
 *   granted via `_MANAGER_SEE_ADD_SQL`/overlay, e.g. laddawank managing
 *   pornthipp — `laddawank-no-division-chip`) → fall back to See, so the
 *   header shows their real สายงาน/ฝ่าย instead of "ไม่ระบุสายงาน". The
 *   Cost Centers/GL Codes pills stay Fill-gated in `UserBar.tsx`, so this
 *   fallback never implies the ability to type.
 * - Both empty → empty arrays, same as today (`UserBar`'s no-scope path
 *   renders nothing here; the empty state itself lives elsewhere).
 *
 * A blank/null division or department is dropped quietly rather than shown
 * as a placeholder chip — an unmapped CC↔department row is a known
 * data-gap the admin fixes later (see project memory), not something the
 * header should surface. The Fill CC *count* itself is NOT derived here —
 * it comes straight from `scope.fillCostCenters.length`, always available
 * immediately without waiting on this fetch. */
export function deriveScopeSummary(
  departments: DepartmentRow[],
  fillCostCenters: string[],
  seeCostCenters: string[] = [],
): ScopeSummary {
  const scopeCostCenters = fillCostCenters.length > 0 ? fillCostCenters : seeCostCenters
  const scopeSet = new Set(scopeCostCenters)
  const rows = departments.filter((d) => scopeSet.has(d.cost_center))
  return {
    divisions: distinctSortedTh(rows.map((r) => r.division)),
    departments: distinctSortedTh(rows.map((r) => r.department)),
  }
}

function distinctSortedTh(values: (string | null)[]): string[] {
  const trimmed = values.map((v) => v?.trim()).filter((v): v is string => Boolean(v))
  return [...new Set(trimmed)].sort((a, b) => a.localeCompare(b, 'th'))
}

/** Chip name after truncation: the first names to show, plus an optional
 * Thai "+N <unit>" suffix for the rest. */
export interface TruncatedChip {
  shown: string[]
  suffix: string | null
}

/** Number of names a header chip shows before collapsing the rest into a
 * "+N <unit>" suffix (jakkaritw, verbatim: "โชว์ 3 ชื่อแรก แล้วต่อท้าย +6
 * สายงาน") — a senior manager's See-fallback สายงาน/ฝ่าย chip
 * (`deriveScopeSummary`) can otherwise fan out to 9 สายงาน / 45 ฝ่าย and
 * overflow the header (`bunpotk@chememan.com`, measured 174 rendered
 * chars). Below this count, both chips render exactly as before — no
 * suffix. `unit` is the Thai word for what is being counted ("สายงาน" or
 * "ฝ่าย"); Thai does not inflect for plural, so "+6 สายงาน" needs no
 * singular/plural handling. */
export function truncateChipNames(names: string[], unit: string): TruncatedChip {
  const CHIP_NAME_LIMIT = 3
  if (names.length <= CHIP_NAME_LIMIT) {
    return { shown: names, suffix: null }
  }
  const shown = names.slice(0, CHIP_NAME_LIMIT)
  const hiddenCount = names.length - CHIP_NAME_LIMIT
  return { shown, suffix: `+${hiddenCount} ${unit}` }
}

/** Distinct GL accounts across every visible row whose cost_center is in
 * the caller's Fill scope — the header's "GL Codes" pill. `rows` comes
 * from `GET /budget` (no department filter), already RLS-scoped
 * server-side to Fill ∪ See; this narrows further to Fill only, mirroring
 * the mockup's `codes.includes(t.costCenter)` rule. */
export function countDistinctFillGlAccounts(rows: BudgetRow[], fillCostCenters: string[]): number {
  const fillSet = new Set(fillCostCenters)
  const glCodes = new Set(rows.filter((r) => fillSet.has(r.cost_center)).map((r) => r.gl_account))
  return glCodes.size
}
