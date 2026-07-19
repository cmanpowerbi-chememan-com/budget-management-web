/** Pure hierarchy-building logic for the ฝ่าย picker (สายงาน›ฝ่าย›Cost
 * Center, counts inline — login-bar V3 design, ADR-0019 scope). No DOM,
 * no fetch — built from `GET /scope/departments` rows, already RLS-scoped
 * server-side. */
import type { DepartmentRow } from '../api/types'

const UNKNOWN_DIVISION = 'ไม่ระบุสายงาน'
const UNKNOWN_DEPARTMENT = 'ไม่ระบุฝ่าย'

export interface DepartmentNode {
  department: string
  division: string
  costCenters: string[]
}

export interface DivisionNode {
  division: string
  departments: DepartmentNode[]
}

/** Groups rows into สายงาน (division) -> ฝ่าย (department) -> unique Cost
 * Centers, sorted alphabetically (Thai-aware) at every level. A row with a
 * blank division/department is bucketed under a visible placeholder
 * rather than silently dropped or crashing. */
export function buildDeptHierarchy(rows: DepartmentRow[]): DivisionNode[] {
  const byDivision = new Map<string, Map<string, Set<string>>>()

  rows.forEach((r) => {
    const division = r.division?.trim() || UNKNOWN_DIVISION
    const department = r.department?.trim() || UNKNOWN_DEPARTMENT
    const depts = byDivision.get(division) ?? new Map<string, Set<string>>()
    const ccs = depts.get(department) ?? new Set<string>()
    ccs.add(r.cost_center)
    depts.set(department, ccs)
    byDivision.set(division, depts)
  })

  return [...byDivision.entries()]
    .sort(([a], [b]) => a.localeCompare(b, 'th'))
    .map(([division, depts]) => ({
      division,
      departments: [...depts.entries()]
        .sort(([a], [b]) => a.localeCompare(b, 'th'))
        .map(([department, ccs]) => ({
          department,
          division,
          costCenters: [...ccs].sort(),
        })),
    }))
}

/** Flat list of every department across all divisions, for a simple
 * search-filtered picker list (division shown as a group header). */
export function flattenDepartments(divisions: DivisionNode[]): DepartmentNode[] {
  return divisions.flatMap((d) => d.departments)
}

/** Case-insensitive substring match against department or division name —
 * used by the picker's search box. Empty query matches everything. */
export function matchesQuery(node: DepartmentNode, query: string): boolean {
  const q = query.trim().toLowerCase()
  if (!q) return true
  return node.department.toLowerCase().includes(q) || node.division.toLowerCase().includes(q)
}

/** Picks the ฝ่าย (department) the picker should start on.
 *
 * 1. A deep-link-provided department wins if it exists in the caller's
 *    scope (ADR-0016: the deep-link is convenience-only, never a bearer
 *    of access — validated against the built hierarchy, not taken on
 *    faith).
 * 2. Otherwise, with no (valid) deep-link: auto-select only when the
 *    caller has EXACTLY ONE ฝ่าย in scope — there is nothing to choose
 *    between. With 0 or >1 ฝ่าย, return `null` ("— เลือกฝ่าย —") so the
 *    user consciously picks rather than landing on an arbitrary default. */
export function resolveInitialDept(divisions: DivisionNode[], deepLinkDept: string | null): string | null {
  const all = flattenDepartments(divisions)
  if (deepLinkDept && all.some((d) => d.department === deepLinkDept)) return deepLinkDept
  return all.length === 1 ? all[0].department : null
}
