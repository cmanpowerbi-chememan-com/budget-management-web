/** Pure derivations for the header (`UserBar`) — สายงาน/ฝ่าย/GL summary,
 * restricted to the caller's FILL scope only (See is broader/viewing,
 * deliberately excluded from the header per the V3 design, ADR-0019). No
 * DOM, no fetch — built from data the hooks in this folder already fetched
 * (`useOwnDepartments`/`useFillGlCount`). */
import type { BudgetRow, DepartmentRow } from '../api/types'

export interface ScopeSummary {
  /** Distinct สายงาน across the caller's Fill CCs, Thai-sorted. */
  divisions: string[]
  /** Distinct ฝ่าย across the caller's Fill CCs, Thai-sorted. */
  departments: string[]
}

/** Restricts `departments` (`GET /scope/departments` rows) to the ones the
 * caller can actually FILL, then derives the distinct สายงาน/ฝ่าย for the
 * header. A blank/null division or department is dropped quietly rather
 * than shown as a placeholder chip — an unmapped CC↔department row is a
 * known data-gap the admin fixes later (see project memory), not something
 * the header should surface. The Fill CC *count* itself is NOT derived
 * here — it comes straight from `scope.fillCostCenters.length`, always
 * available immediately without waiting on this fetch. */
export function deriveScopeSummary(departments: DepartmentRow[], fillCostCenters: string[]): ScopeSummary {
  const fillSet = new Set(fillCostCenters)
  const rows = departments.filter((d) => fillSet.has(d.cost_center))
  return {
    divisions: distinctSortedTh(rows.map((r) => r.division)),
    departments: distinctSortedTh(rows.map((r) => r.department)),
  }
}

function distinctSortedTh(values: (string | null)[]): string[] {
  const trimmed = values.map((v) => v?.trim()).filter((v): v is string => Boolean(v))
  return [...new Set(trimmed)].sort((a, b) => a.localeCompare(b, 'th'))
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
