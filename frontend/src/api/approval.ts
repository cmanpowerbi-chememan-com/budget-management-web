/** Typed calls to the A6/A10 approval endpoints, built on the shared
 * `apiFetch` (401/error handling centralized there). One function per
 * endpoint, no caching/state here — that lives in `ApprovalActionBar`
 * (approval status/actions) and `BudgetGrid` (the รออนุมัติ badge list). */
import { apiFetch } from './client'
import type { ApprovalStatusState, PendingForMeResponse } from './types'

/** `GET /approval/status` — current state for one (department, fiscal_year). */
export function fetchApprovalStatus(department: string, fiscalYear: number): Promise<ApprovalStatusState> {
  const params = new URLSearchParams({ department, fiscal_year: String(fiscalYear) })
  return apiFetch<ApprovalStatusState>(`/approval/status?${params.toString()}`)
}

/** `POST /approval/submit` — sends the whole department's Pending budget
 * into the approval chain (or straight to APPROVED, admin branches). */
export function submitDepartment(department: string, fiscalYear: number): Promise<ApprovalStatusState> {
  return apiFetch<ApprovalStatusState>('/approval/submit', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ department, fiscal_year: fiscalYear }),
  })
}

/** `POST /approval/approve` — only valid when the caller is the CURRENT
 * approver step (`ApprovalStatusState.can_act`); the server re-checks this
 * regardless of what the UI shows. */
export function approveDepartment(department: string, fiscalYear: number, comment?: string): Promise<ApprovalStatusState> {
  return apiFetch<ApprovalStatusState>('/approval/approve', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ department, fiscal_year: fiscalYear, comment: comment ?? null }),
  })
}

/** `POST /approval/reject` — `reason` is required (server 422s a blank one
 * via Pydantic; the UI also blocks submitting an empty reason). */
export function rejectDepartment(department: string, fiscalYear: number, reason: string): Promise<ApprovalStatusState> {
  return apiFetch<ApprovalStatusState>('/approval/reject', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ department, fiscal_year: fiscalYear, reason }),
  })
}

/** `GET /approval/pending-for-me` — departments waiting on the caller's own
 * approval step, for the รออนุมัติ ฝ่าย-picker badge. */
export function fetchPendingForMe(fiscalYear: number): Promise<PendingForMeResponse> {
  return apiFetch<PendingForMeResponse>(`/approval/pending-for-me?fiscal_year=${fiscalYear}`)
}
