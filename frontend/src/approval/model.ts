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
 * showing a raw employee code to the user.
 *
 * The parenthesised job title is the ENGLISH title from the HR master
 * (`dbo.employee_master.position_name_en`, role part only — the trailing
 * "- Budgeting and Management Accounting" is dropped, it is redundant in a
 * budget-approval chip). Verified against the live master 2026-08-24:
 * 101032 = "Senior Associate - Budgeting and Management Accounting",
 * 100427 = "Assistant Department Head - Budgeting and Management Accounting".
 * These replace an earlier hand-written Thai gloss ("ผู้จัดการฝ่ายงบประมาณ")
 * that overstated Waraporn's grade. Titles are still hardcoded, not read from
 * the DB: `dbo.v_employee_budget_01` exposes only `job_level_name_en`, so a
 * DB-driven label would need that view widened first. */
export function approverLabel(position: 1 | 2 | 3 | null, approverEmpcode: string | null): string {
  if (position === 2 || approverEmpcode === NIPAPORN_EMPCODE) return 'นิภาพร ทองกิ่ง (Senior Associate)'
  if (position === 3 || approverEmpcode === WARAPORN_EMPCODE) return 'วราพร ติรสิทธิ์ (Assistant Department Head)'
  if (position === 1) return 'ผู้บังคับบัญชาสายตรง'
  return ''
}

/** The status chip's full label, e.g. "รออนุมัติ · ขั้น 2 (นิภาพร ทองกิ่ง (Senior Associate))". */
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

/** Submit is offered to: Fillers of the department, or the admin hat —
 * gated by `canSubmitServer`, the server's own verdict (`ApprovalStatusState
 * .can_submit`, `app.approval.evaluate_submit_eligibility`) on whether THIS
 * caller could actually submit RIGHT NOW. Client-side, this function keeps
 * exactly ONE thing: the "put on the admin hat first" gesture — a non-filler
 * admin with the hat OFF (`adminViewEnabled=false`) sees no Submit button
 * even if the server would accept it, because Admin mode is a deliberate,
 * visible act before any admin-only action is offered (never silently
 * available). Everything else — is this status submittable, is the year
 * open, is the department a filler's own, would a Template-2/orphan/
 * post-deadline door accept it — is decided ONCE, server-side, and read
 * here instead of re-derived (see `ApprovalStatusState.can_submit`'s
 * docstring in `types.ts` for the full predicate list).
 *
 * SIT defect fix #2 (2026-08-16): the earlier client-side version
 * (`isPendingLocked(status) || status === 'APPROVED' ? isPostDeadline :
 * true` for the admin hat) could not tell the 3 admin doors apart from a
 * 4th, refused shape — not a filler, department not orphan, no Template-2
 * rows, cycle still open — which always showed a Submit button on
 * DRAFT/REJECTED that then 403'd (`admin_cannot_submit_in_cycle`). This also
 * folds the FILLER branch into the same server verdict (previously its own
 * `status === 'DRAFT' || 'REJECTED'` check, genuinely duplicating what the
 * server already decides) — a bonus fix, not just for admin: a filler could
 * previously see Submit on an EMPTY department (0 budget rows) or a
 * NOT_OPEN/past-deadline fiscal year and get a doomed click too; the server
 * verdict already covers those, so there is no reason to keep two
 * definitions of "submittable" that can drift. See the 2026-08-14 sibling
 * fix (`is_post_deadline`, now superseded here) for the first half of this
 * story.
 *
 * Fail-closed typing (gate review, 2026-08-16): `canSubmitServer` is typed
 * `boolean`, but an older/partial server response reaching this through
 * `JSON.parse` has no such guarantee -- a missing/renamed field would come
 * through as `undefined`, which the TS type signature hides. The strict
 * `=== true` check below means only an EXPLICIT server `true` ever shows the
 * button; `undefined`/`null`/anything else stays hidden, matching this
 * function's already-documented fail-closed intent instead of merely
 * relying on `undefined` being falsy by accident. */
export function canSubmit(params: {
  isFillerOfDept: boolean
  adminViewEnabled: boolean
  canSubmitServer: boolean
}): boolean {
  const { isFillerOfDept, adminViewEnabled, canSubmitServer } = params
  if (!isFillerOfDept && !adminViewEnabled) return false
  return canSubmitServer === true
}

/** Short Thai explanation for why the Submit button is absent (design call,
 * 2026-08-16, extended the same day per jakkaritw: "ใส่ข้อความให้ผู้กรอกด้วย"
 * — show the same hint to a blocked FILLER, not just a blocked admin):
 * whoever is blocked sees a small hint line next to the status chip rather
 * than nothing at all — per the project philosophy ("decrease manual tasks,
 * minimize confusion"), a silently-absent button on a page the user expects
 * to be able to act on has its own confusion cost. A DISABLED button was
 * considered and rejected: it invites a click-then-fail habit exactly like
 * the bug this closes.
 *
 * `not_filler_of_department`'s copy was corrected in the same pass: the
 * original wording said "ผู้ดูแลระบบ" (admin), but
 * `evaluate_submit_eligibility` (backend/app/approval.py) only returns this
 * reason once `scope.is_admin` is confirmed FALSE — an actual admin never
 * reaches this branch, so the old text had the audience backwards. It is
 * now written for who the server actually sends it to: a viewer with See
 * scope on this department but no Fill scope on it, admin or not.
 *
 * One shared map, not split per audience: every reason here is written
 * audience-neutral except `admin_cannot_submit_in_cycle`, which genuinely
 * IS admin-only (`evaluate_submit_eligibility` only returns it after
 * confirming `scope.is_admin`) — the reason code itself already determines
 * who can receive each string, so a second per-audience copy would just be
 * duplication with nothing to disambiguate. */
const SUBMIT_BLOCKED_REASON_TH: Record<string, string> = {
  admin_cannot_submit_in_cycle:
    'ฝ่ายนี้ยังอยู่ในรอบอนุมัติปกติ ผู้ดูแลระบบส่งแทนไม่ได้ (ต้องรอเลยกำหนดส่ง หรือเป็นฝ่ายที่ไม่มีผู้กรอกอยู่จริง)',
  mid_chain_admin_overwrite: 'ฝ่ายนี้อยู่ระหว่างอนุมัติหรืออนุมัติแล้ว ส่งซ้ำไม่ได้',
  department_empty: 'ฝ่ายนี้ยังไม่มีข้อมูลงบประมาณ จึงส่งอนุมัติไม่ได้',
  not_filler_of_department: 'คุณไม่ใช่ผู้กรอกของฝ่ายนี้ จึงส่งอนุมัติแทนไม่ได้',
  year_not_open: 'ปีงบประมาณนี้ยังไม่เปิดให้ส่งอนุมัติ กรุณารอประกาศเปิดรอบ',
  past_deadline: 'เลยกำหนดส่งอนุมัติของปีงบประมาณนี้แล้ว จึงส่งอนุมัติไม่ได้',
  invalid_approval_state: 'ฝ่ายนี้อยู่ระหว่างอนุมัติหรืออนุมัติแล้ว จึงส่งซ้ำไม่ได้',
}

export function submitBlockedReasonLabel(reason: string | null): string | null {
  if (!reason) return null
  return SUBMIT_BLOCKED_REASON_TH[reason] ?? null
}

/** Thai confirm-dialog text for Submit — summarizes what is being sent so
 * the click is a deliberate act, not an accidental one. */
export function buildSubmitConfirmText(department: string, fiscalYear: number, rowCount: number, costCenterCount: number): string {
  return (
    `ยืนยันส่งอนุมัติงบประมาณฝ่าย "${department}" ปี ${fiscalYear}?\n` +
    `จำนวน ${rowCount} รายการ ใน ${costCenterCount} cost center — ส่งครั้งนี้จะส่งทั้งฝ่าย ไม่สามารถแก้ไขได้จนกว่าจะถูกตีกลับ`
  )
}

/** Thai confirm-dialog text for the admin step-override (ADR-0027). MUST
 * name the approver being skipped — this dialog is the ONLY guard against
 * an accidental override (D3 removed the stale-gate and the reason field),
 * so a generic "ยืนยันการอนุมัติ" is never acceptable here. */
export function buildOverrideConfirmText(department: string, fiscalYear: number, skippedApproverName: string): string {
  return (
    `⚠️ คุณกำลังอนุมัติแทน ${skippedApproverName} (ผู้อนุมัติขั้นที่ 1) ของฝ่าย "${department}" ปี ${fiscalYear}\n` +
    `ระบบจะบันทึกว่าคุณกดแทน และส่งอีเมลแจ้งผู้กรอกงบ พร้อมสำเนาถึง ${skippedApproverName} · ยืนยันหรือไม่?`
  )
}
