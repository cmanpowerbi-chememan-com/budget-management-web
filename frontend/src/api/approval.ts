/** Typed calls to the A6/A10 approval endpoints, built on the shared
 * `apiFetch` (401/error handling centralized there). One function per
 * endpoint, no caching/state here — that lives in `ApprovalActionBar`
 * (approval status/actions) and `BudgetGrid` (the รออนุมัติ badge list). */
import { apiFetch } from './client'
import type { ApprovalStatusState, LockedDepartmentsResponse, PendingForMeResponse } from './types'

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

/** `POST /approval/override-step` — admin-only (ADR-0027): advances a stuck
 * POSITION-1 step by exactly one step (never APPROVED, never positions 2/3).
 * The admin reuses the normal อนุมัติ button in the UI — the approve/override
 * split is server-side only (two endpoints, two log actions), so this is a
 * separate client function but NOT a separate button. A 409 here carries the
 * server's Thai `StepNotOverridableError` detail, shown as-is. */
export function overrideStep(department: string, fiscalYear: number): Promise<ApprovalStatusState> {
  return apiFetch<ApprovalStatusState>('/approval/override-step', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ department, fiscal_year: fiscalYear }),
  })
}

/** `GET /approval/pending-for-me` — departments waiting on the caller's own
 * approval step, for the รออนุมัติ ฝ่าย-picker badge. */
export function fetchPendingForMe(fiscalYear: number): Promise<PendingForMeResponse> {
  return apiFetch<PendingForMeResponse>(`/approval/pending-for-me?fiscal_year=${fiscalYear}`)
}

/** `GET /approval/locked-departments` — "+ เพิ่ม Transaction" lock-awareness
 * (2026-08-08 bug fix): every one of the caller's OWN Fill-scope departments
 * that is currently mid-approval or APPROVED for `fiscalYear`. */
export function fetchLockedDepartments(fiscalYear: number): Promise<LockedDepartmentsResponse> {
  return apiFetch<LockedDepartmentsResponse>(`/approval/locked-departments?fiscal_year=${fiscalYear}`)
}
