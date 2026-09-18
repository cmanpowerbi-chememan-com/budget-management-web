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

type DeptEntry = [department: string, costCenters: Set<string>]

const byThaiName = (a: [string, unknown], b: [string, unknown]) => a[0].localeCompare(b[0], 'th')

/** Splits entries into "in `pending`" (alphabetical) then "the rest"
 * (alphabetical) — the ONE partition rule behind both the division-level
 * and department-level ordering below (jakkaritw, 2026-09-18: pending
 * items surface first so an admin/approver's queue is always on top,
 * without breaking alphabetical order inside either half). */
function pendingFirst<T extends [string, unknown]>(entries: T[], isPending: (name: string) => boolean): T[] {
  const pending = entries.filter(([name]) => isPending(name)).sort(byThaiName)
  const rest = entries.filter(([name]) => !isPending(name)).sort(byThaiName)
  return [...pending, ...rest]
}

/** Groups rows into สายงาน (division) -> ฝ่าย (department) -> unique Cost
 * Centers. A row with a blank division/department is bucketed under a
 * visible placeholder rather than silently dropped or crashing.
 *
 * `pending` (jakkaritw, 2026-09-18 — admin-mode queue + approver's own
 * queue) reorders BOTH levels: departments in `pending` come first within
 * their division (alphabetical within each half), and divisions that
 * contain at least one pending department come before those that do not
 * (alphabetical within each half too). No pending set (or an empty one)
 * leaves the plain alphabetical order from before this feature. */
export function buildDeptHierarchy(rows: DepartmentRow[], pending?: ReadonlySet<string>): DivisionNode[] {
  const pendingSet = pending ?? new Set<string>()
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

  const divisionEntries = pendingFirst(
    [...byDivision.entries()],
    (division) => [...(byDivision.get(division) as Map<string, Set<string>>).keys()].some((d) => pendingSet.has(d)),
  )

  return divisionEntries.map(([division, depts]) => ({
    division,
    departments: pendingFirst<DeptEntry>([...depts.entries()], (department) => pendingSet.has(department)).map(
      ([department, ccs]) => ({ department, division, costCenters: [...ccs].sort() }),
    ),
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
 * 2. Otherwise the page must NEVER land unselected (2026-07-21 jakkaritw
 *    — supersedes the earlier ">1 ฝ่าย → null, user consciously picks"
 *    rule): default to the FIRST ฝ่าย in scope (alphabetical hierarchy
 *    order); the user can switch any time via the picker. `null` only when
 *    the scope is empty (0 ฝ่าย). */
export function resolveInitialDept(divisions: DivisionNode[], deepLinkDept: string | null): string | null {
  const all = flattenDepartments(divisions)
  if (deepLinkDept && all.some((d) => d.department === deepLinkDept)) return deepLinkDept
  return all.length > 0 ? all[0].department : null
}
