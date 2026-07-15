/** Pure helpers for the A10 approval UI — no DOM, no fetch. Keeps
 * `ApprovalActionBar` a thin renderer over these decisions. */
import type { ApprovalStatusState, DepartmentRow } from '../api/types'

// Position 2/3 are FIXED constants (ADR-0006: always Nipaporn/Waraporn) —
// safe to name here, this is public information already in
// docs/reference/approval-workflow.md, not sensitive employee data.
const NIPAPORN_EMPCODE = '101032'
const WARAPORN_EMPCODE = '100427'

const PENDING_STATUSES = new Set(['PENDING_APPROVER1', 'PENDING_APPROVER2', 'PENDING_APPROVER3'])

const BASE_STATUS_LABEL_TH: Record<string, string> = {
  DRAFT: 'แบบร่าง (ยังไม่ส่งอนุมัติ)',
  APPROVED: 'อนุมัติแล้ว',
  REJECTED: 'ถูกตีกลับ',
}

/** Friendly Thai name for the CURRENT approver step. Positions 2/3 always
 * resolve to the two fixed budget-dept approvers (their empcode never
 * varies); position 1 varies per submission and the state only ever
 * carries an empcode for it, so it falls back to a role label rather than
 * showing a raw employee code to the user. */
export function approverLabel(position: 1 | 2 | 3 | null, approverEmpcode: string | null): string {
  if (position === 2 || approverEmpcode === NIPAPORN_EMPCODE) return 'นิภาพร ทองกิ่ง (ฝ่ายงบประมาณ)'
  if (position === 3 || approverEmpcode === WARAPORN_EMPCODE) return 'วราพร ติรสิทธิ์ (ผู้จัดการฝ่ายงบประมาณ)'
  if (position === 1) return 'ผู้บังคับบัญชาสายตรง'
  return ''
}

/** The status chip's full label, e.g. "รออนุมัติ · ขั้น 2 (นิภาพร ทองกิ่ง...)". */
export function statusChipLabel(state: Pick<ApprovalStatusState, 'status' | 'current_position' | 'current_approver_empcode'>): string {
  if (state.status in BASE_STATUS_LABEL_TH && state.current_position === null) {
    return BASE_STATUS_LABEL_TH[state.status]
  }
  if (state.current_position) {
    return `รออนุมัติ · ขั้น ${state.current_position} (${approverLabel(state.current_position, state.current_approver_empcode)})`
  }
  return BASE_STATUS_LABEL_TH[state.status] ?? state.status
}

/** True while the department is locked to a PENDING_* step — informational
 * only (the note text), the backend write path does NOT yet enforce this
 * lock (flagged as a known gap, see the A10 final report). */
export function isPendingLocked(status: string): boolean {
  return PENDING_STATUSES.has(status)
}

/** Every distinct Cost Center of `department`, from the caller's own
 * `GET /scope/departments` rows (already RLS-scoped server-side). */
export function costCentersOfDepartment(rows: DepartmentRow[], department: string): string[] {
  return [...new Set(rows.filter((r) => r.department === department).map((r) => r.cost_center))]
}

export function isFillerOfDepartment(rows: DepartmentRow[], department: string, fillCostCenters: string[]): boolean {
  const fillSet = new Set(fillCostCenters)
  return costCentersOfDepartment(rows, department).some((cc) => fillSet.has(cc))
}

/** Submit is offered to: Fillers of the department while it is still
 * editable (never-submitted / DRAFT / REJECTED), or the admin hat (any
 * status — the server decides the exact admin branch: orphan / Template-2 /
 * post-deadline / 403 mid-cycle). Step-gating detail is the server's job
 * (never-cut); this only decides whether to SHOW the button. */
export function canSubmit(params: { isFillerOfDept: boolean; adminViewEnabled: boolean; status: string }): boolean {
  const { isFillerOfDept, adminViewEnabled, status } = params
  if (adminViewEnabled) return true
  return isFillerOfDept && (status === 'DRAFT' || status === 'REJECTED')
}

/** Thai confirm-dialog text for Submit — summarizes what is being sent so
 * the click is a deliberate act, not an accidental one. */
export function buildSubmitConfirmText(department: string, fiscalYear: number, rowCount: number, costCenterCount: number): string {
  return (
    `ยืนยันส่งอนุมัติงบประมาณฝ่าย "${department}" ปี ${fiscalYear}?\n` +
    `จำนวน ${rowCount} รายการ ใน ${costCenterCount} cost center — ส่งครั้งนี้จะส่งทั้งฝ่าย ไม่สามารถแก้ไขได้จนกว่าจะถูกตีกลับ`
  )
}
