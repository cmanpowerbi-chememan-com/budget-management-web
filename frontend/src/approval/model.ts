/** Pure helpers for the A10 approval UI — no DOM, no fetch. Keeps
 * `ApprovalActionBar` a thin renderer over these decisions. */
import type { ApprovalStatusState, DepartmentRow } from '../api/types'

// Reject reason cap (jakkaritw, 2026-09-17, from UAT): the box's `maxLength`
// and its counter both read this ONE constant so they can never drift. The
// server mirrors the same value as its own constant (`MAX_LEN_REJECT_REASON`,
// backend/app/routers/approval.py) -- kept as two constants, not one shared
// value, since the two sides do not share a build step.
export const REJECT_REASON_MAX_LEN = 100

// Position 2/3 are FIXED constants (ADR-0006: always Nipaporn/Waraporn) —
// safe to name here, this is public information already in
// docs/reference/approval-workflow.md, not sensitive employee data.
const NIPAPORN_EMPCODE = '101032'
const WARAPORN_EMPCODE = '100427'

// Issue #13 (2026-09-17): mirrors `app.approval.LOCKED_APPROVAL_STATUSES`
// exactly (PENDING_* + APPROVED) — was `PENDING_STATUSES` (PENDING_* only,
// used by the now-removed `isPendingLocked`), which drifted from the
// server's own definition the day ADR-0013 shipped write-side enforcement
// for APPROVED too. ONE definition here so the two can never drift again.
const LOCKED_STATUSES = new Set(['PENDING_APPROVER1', 'PENDING_APPROVER2', 'PENDING_APPROVER3', 'APPROVED'])

const BASE_STATUS_LABEL: Record<string, string> = {
  DRAFT: 'Draft — not submitted',
  APPROVED: 'Approved',
  REJECTED: 'Rejected',
}

/** Friendly name for the CURRENT approver step. Positions 2/3 always
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
  if (position === 1) return 'Direct manager'
  return ''
}

/** The status chip's full label, e.g. "Pending · Step 2 (นิภาพร ทองกิ่ง (Senior Associate))". */
export function statusChipLabel(state: Pick<ApprovalStatusState, 'status' | 'current_position' | 'current_approver_empcode'>): string {
  if (state.status in BASE_STATUS_LABEL && state.current_position === null) {
    return BASE_STATUS_LABEL[state.status]
  }
  if (state.current_position) {
    return `Pending · Step ${state.current_position} (${approverLabel(state.current_position, state.current_approver_empcode)})`
  }
  return BASE_STATUS_LABEL[state.status] ?? state.status
}

/** True while the department is locked for editing — PENDING_* (mid-chain)
 * OR APPROVED (fully signed off). Renamed from `isPendingLocked` (issue #13,
 * 2026-09-17) once APPROVED joined the set: the backend write path DOES
 * enforce this lock, for both statuses (ADR-0013, `write_model
 * ._ensure_department_not_locked`) — the note this drives is informational
 * (explains a state the server already refuses), not the enforcement
 * itself. */
export function isEditLocked(status: string): boolean {
  return LOCKED_STATUSES.has(status)
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

/** Short explanation for why the Submit button is absent (design call,
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
const SUBMIT_BLOCKED_REASON: Record<string, string> = {
  admin_cannot_submit_in_cycle:
    'This department is still inside the normal approval cycle, so an admin cannot submit for it (wait until the submission deadline has passed, or the department genuinely has no filler).',
  mid_chain_admin_overwrite: 'This department is already in approval or approved, so it cannot be submitted again.',
  department_empty: 'This department has no budget data yet, so it cannot be submitted.',
  not_filler_of_department: 'You are not a filler of this department, so you cannot submit on its behalf.',
  year_not_open: 'This fiscal year is not open for submission yet. Please wait for the round to be announced.',
  past_deadline: 'The submission deadline for this fiscal year has passed, so it can no longer be submitted.',
  invalid_approval_state: 'This department is already in approval or approved, so it cannot be submitted again.',
}

export function submitBlockedReasonLabel(reason: string | null): string | null {
  if (!reason) return null
  return SUBMIT_BLOCKED_REASON[reason] ?? null
}

/** Confirm-dialog text for Submit — a deliberate-act guard, not a data
 * summary. 2026-09-16 (jakkaritw): the row/cost-centre counts were dropped
 * from this dialog. */
export function buildSubmitConfirmText(department: string, fiscalYear: number): string {
  return (
    `Submit the budget of department "${department}" for FY ${fiscalYear}?\n` +
    `This submits the WHOLE department. You cannot edit it until it is rejected.`
  )
}

/** Confirm-dialog text for the admin step-override (ADR-0027). MUST
 * name the approver being skipped — this dialog is the ONLY guard against
 * an accidental override (D3 removed the stale-gate and the reason field),
 * so a generic "confirm approval" is never acceptable here. */
export function buildOverrideConfirmText(department: string, fiscalYear: number, skippedApproverName: string): string {
  return (
    `⚠️ You are approving on behalf of ${skippedApproverName} (approver step 1) for department "${department}", FY ${fiscalYear}\n` +
    `The system will record that you approved on their behalf and will email the budget filler, with a copy to ${skippedApproverName}. Continue?`
  )
}
