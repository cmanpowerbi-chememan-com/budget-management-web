/** Typed calls to the A4/A5/A8 budget endpoints, built on the shared
 * `apiFetch` (401/error handling centralized there). Kept thin — one
 * function per endpoint, no caching/state here (that lives in the grid
 * hooks/components that call these). */
import { apiFetch } from './client'
import type { BudgetRow, DepartmentRow, GlAccount, PendingRowInput, PendingRowState } from './types'

export interface BudgetGridFilter {
  year: number
  costCenter?: string
  department?: string
  adminViewEnabled?: boolean
}

function buildQuery(params: Record<string, string | number | boolean | undefined>): string {
  const search = new URLSearchParams()
  for (const [key, value] of Object.entries(params)) {
    if (value === undefined || value === '') continue
    search.set(key, String(value))
  }
  const qs = search.toString()
  return qs ? `?${qs}` : ''
}

/** `GET /budget` — the merged 3-layer grid, RLS-filtered server-side (A4). */
export function fetchBudgetGrid(filter: BudgetGridFilter): Promise<BudgetRow[]> {
  const query = buildQuery({
    year: filter.year,
    cost_center: filter.costCenter,
    department: filter.department,
    admin_view_enabled: filter.adminViewEnabled,
  })
  return apiFetch<BudgetRow[]>(`/budget${query}`)
}

/** `GET /budget/gl-accounts` — full GL master, flagged `is_special` (A8). */
export function fetchGlAccounts(): Promise<GlAccount[]> {
  return apiFetch<GlAccount[]>('/budget/gl-accounts')
}

/** `GET /scope/departments` — caller's (cost_center, department, division,
 * c_level) rows for the ฝ่าย picker (A8, ADR-0019). */
export function fetchDepartments(adminViewEnabled = false): Promise<DepartmentRow[]> {
  const query = buildQuery({ admin_view_enabled: adminViewEnabled })
  return apiFetch<DepartmentRow[]>(`/scope/departments${query}`)
}

/** `PUT /budget/rows` — create (expected_updated_at=null) or update a
 * Pending row. Throws `ApiError` on 400/403/409/5xx — the caller decides
 * how to surface it (per-row, since the endpoint is one row per call). */
export function saveRow(payload: PendingRowInput): Promise<PendingRowState> {
  return apiFetch<PendingRowState>('/budget/rows', {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
}

/** `DELETE /budget/rows` — grid trailing "ลบ" column: remove one
 * manually-added Pending row (the server cascades any special-GL detail
 * lines it owns). Throws `ApiError` on 400/403/409/5xx — a stale
 * `expectedUpdatedAt` throws 409 and deletes nothing. */
export function deleteRow(params: {
  costCenter: string
  glAccount: string
  fiscalYear: number
  expectedUpdatedAt: string
}): Promise<{ ok: true }> {
  const query = buildQuery({
    cost_center: params.costCenter,
    gl_account: params.glAccount,
    fiscal_year: params.fiscalYear,
    expected_updated_at: params.expectedUpdatedAt,
  })
  return apiFetch<{ ok: true }>(`/budget/rows${query}`, { method: 'DELETE' })
}
