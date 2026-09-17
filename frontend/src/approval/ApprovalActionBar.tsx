import { useEffect, useRef, useState } from 'react'
import { approveDepartment, fetchApprovalStatus, overrideStep, rejectDepartment, submitDepartment } from '../api/approval'
import { ApiError } from '../api/client'
import type { ApprovalStatusState } from '../api/types'
import { confirmDialog } from '../platform/confirm'
import {
  buildOverrideConfirmText,
  buildSubmitConfirmText,
  canSubmit,
  isEditLocked,
  REJECT_REASON_MAX_LEN,
  statusChipLabel,
  submitBlockedReasonLabel,
} from './model'

export interface ApprovalActionBarProps {
  department: string | null
  fiscalYear: number
  /** Bumped by the parent after any successful budget write that could
   * change what the server would allow for THIS (department, fiscalYear) --
   * e.g. a department's first saved row flips the `can_submit`/
   * `department_empty` verdict (bug fixed 2026-09-16: Submit stayed hidden
   * until a manual reload because saving a row never changed `department`/
   * `fiscalYear`, the only deps the status fetch used to key on). Refetches
   * the status IN PLACE -- unlike a department/fiscalYear change, it must
   * NOT reset actionMessage/rejecting/reason (see the effect below). */
  dataVersion: number
  isFillerOfDept: boolean
  adminViewEnabled: boolean
  /** Raw `scope.isAdmin` (NOT the admin-view toggle) — gates the ADR-0027
   * step-override visibility: an admin sees the Approve button on
   * PENDING_APPROVER1 even when they are not the frozen approver. */
  isAdmin: boolean
  /** Called after ANY successful submit/approve/reject — the parent
   * refetches the รออนุมัติ badge list (A10 §4) since this action may have
   * changed which departments are waiting on someone. */
  onChanged: () => void
}

function statusToneClass(status: string): string {
  if (status === 'APPROVED') return 'approved'
  if (status === 'REJECTED') return 'rejected'
  if (status === 'DRAFT') return 'draft'
  return 'pending'
}

/** Status chip + inline Submit/Approve/Reject (ADR-0016 — approval happens
 * on the main page, no separate inbox). One instance per selected
 * (department, fiscal_year); renders nothing when no department is
 * selected. Step-gating (`can_act`) and every business rule are decided by
 * the server — this component only shows/hides controls and surfaces the
 * server's own error messages. */
export function ApprovalActionBar({
  department, fiscalYear, dataVersion, isFillerOfDept, adminViewEnabled, isAdmin, onChanged,
}: ApprovalActionBarProps) {
  const [status, setStatus] = useState<ApprovalStatusState | null>(null)
  const [loading, setLoading] = useState(false)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [actionBusy, setActionBusy] = useState(false)
  const [actionMessage, setActionMessage] = useState<string | null>(null)
  const [rejecting, setRejecting] = useState(false)
  const [reason, setReason] = useState('')

  async function load(options: { keepStatusOnError?: boolean } = {}) {
    if (!department) return
    setLoading(true)
    if (!options.keepStatusOnError) setLoadError(null)
    try {
      const state = await fetchApprovalStatus(department, fiscalYear)
      setStatus(state)
    } catch (err) {
      // R2 (gate finding, 2026-09-16): a dataVersion-triggered refetch is a
      // background "did anything change" check, not a user-initiated load --
      // a transient failure (502, offline) must leave the currently-shown
      // status/loadError exactly as they are, so an in-progress action
      // message or reject panel is not blown away by an unrelated network
      // blip. Only the department/fiscalYear effect's plain load() (no
      // options) still surfaces the full load-error panel on failure.
      if (options.keepStatusOnError) {
        console.error('approval status refetch failed, keeping the previous status on screen', err)
      } else {
        setLoadError(err instanceof ApiError ? err.message : 'Could not load the approval status')
      }
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    setStatus(null)
    setActionMessage(null)
    setRejecting(false)
    setReason('')
    load()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [department, fiscalYear])

  // A successful budget write elsewhere on the page (month cell, remark, or
  // a special-GL detail/trip line -- BudgetGrid bumps dataVersion after any
  // of those) can flip THIS department's can_submit/department_empty
  // verdict -- refetch in place. Unlike the department/fiscalYear effect
  // above, this must NOT reset actionMessage/rejecting/reason: those belong
  // to an action the user is still reading or mid-typing, not to "switched
  // to a different department". Skips its own first (mount) run -- the
  // effect above already loads once on mount and on every remount (this
  // component unmounts/remounts whenever BudgetGrid's admin-hat toggle
  // clears `department`), so without the guard every one of those would
  // fire a second, redundant GET /approval/status back-to-back.
  const skippedFirstDataVersionRun = useRef(true)
  useEffect(() => {
    if (skippedFirstDataVersionRun.current) {
      skippedFirstDataVersionRun.current = false
      return
    }
    // R1 (gate finding, 2026-09-16): a plain row save can only ever flip
    // can_submit false->true -- the server's department_empty predicate is
    // monotonic within a session (saving never removes the department's
    // rows), so once Submit is already showing, re-asking cannot change the
    // answer. Skipping here matters: measured at ~a dozen DB round-trips per
    // GET /approval/status server-side, so 20 rows x 12 months of edits was
    // costing 240 wasted calls. Deleting the department's LAST row could
    // flip can_submit back to false, but that gap is accepted as
    // out-of-scope (documented) -- the server still refuses a stale Submit
    // with a clean 400, it just would not auto-hide the button on its own.
    if (status?.can_submit === true) return
    if (department) load({ keepStatusOnError: true })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [dataVersion])

  function describeApiError(err: unknown, fallback: string): string {
    if (err instanceof ApiError) {
      if (err.status === 409) return 'Someone else changed this status. Reload the page and try again.'
      return `${err.message}${err.detail ? ` (${err.detail})` : ''}`
    }
    return fallback
  }

  /** Override errors (ADR-0027): a 409 carries the server's own Thai
   * `StepNotOverridableError` detail — show it AS-IS (it explains WHY the
   * step cannot be overridden), never the generic concurrent-change text. */
  function describeOverrideError(err: unknown, fallback: string): string {
    if (err instanceof ApiError) {
      if (err.status === 409) return err.detail ?? err.message
      return `${err.message}${err.detail ? ` (${err.detail})` : ''}`
    }
    return fallback
  }

  async function runAction(
    action: () => Promise<ApprovalStatusState>,
    fallbackError: string,
    describeError: (err: unknown, fallback: string) => string = describeApiError,
  ) {
    setActionBusy(true)
    setActionMessage(null)
    try {
      const result = await action()
      setStatus(result)
      if (result.notification_warning) setActionMessage(result.notification_warning)
      onChanged()
    } catch (err) {
      setActionMessage(describeError(err, fallbackError))
      if (err instanceof ApiError && err.status === 409) await load()
    } finally {
      setActionBusy(false)
    }
  }

  async function handleSubmit() {
    if (!department) return
    const confirmed = await confirmDialog(buildSubmitConfirmText(department, fiscalYear))
    if (!confirmed) return
    runAction(() => submitDepartment(department, fiscalYear), 'Submit failed')
  }

  async function handleApprove() {
    if (!department || !status) return
    if (status.can_act) {
      // Normal approve — the caller IS the frozen current approver.
      if (!(await confirmDialog(`Approve the whole department "${department}" for FY ${fiscalYear}?`))) return
      runAction(() => approveDepartment(department, fiscalYear), 'Approve failed')
      return
    }
    // Admin step-override (ADR-0027): SAME Approve button, but the confirm
    // dialog must NAME the approver being skipped — it is the only guard
    // against an accidental override (no stale-gate, no reason field).
    // Falls back to a step-number wording (jakkaritw, 2026-09-17 — was a
    // typed-in name/title) when the server could not resolve a name.
    const skippedName = status.current_approver_name ?? `Step ${status.current_position} approver`
    if (!(await confirmDialog(buildOverrideConfirmText(department, fiscalYear, skippedName)))) return
    runAction(() => overrideStep(department, fiscalYear), 'Override approve failed', describeOverrideError)
  }

  async function handleConfirmReject() {
    if (!department || !reason.trim()) return
    await runAction(() => rejectDepartment(department, fiscalYear, reason.trim()), 'Reject failed')
    setRejecting(false)
    setReason('')
  }

  if (!department) return null

  if (loading && !status) {
    return (
      <div className="approval-bar" data-testid="approval-bar">
        <span className="act-status">Loading approval status…</span>
      </div>
    )
  }

  if (loadError) {
    return (
      <div className="approval-bar" data-testid="approval-bar">
        <span className="act-status act-status-error" role="alert">{loadError}</span>
        <button type="button" className="btn" onClick={() => load()}>
          Retry
        </button>
      </div>
    )
  }

  if (!status) return null

  const showSubmit = canSubmit({
    isFillerOfDept, adminViewEnabled, canSubmitServer: status.can_submit,
  })
  const showApproveReject = status.can_act && !adminViewEnabled
  // ADR-0027: ONE Approve button — visible to the frozen approver (normal
  // approve) OR to an admin while the department sits on PENDING_APPROVER1
  // (step-override; positions 2/3 stay unapproachable here, the server 409s
  // them anyway). Reject stays approver-only — an override never rejects.
  const showApprove =
    showApproveReject || (isAdmin && status.status === 'PENDING_APPROVER1' && !status.can_act)
  const locked = isEditLocked(status.status) && isFillerOfDept && !adminViewEnabled
  // Filler-blocked-hint fix (2026-08-16, same day as SIT defect fix #2,
  // jakkaritw: "ใส่ข้อความให้ผู้กรอกด้วย"): the hint used to be gated to
  // admins only (`adminViewEnabled && !isFillerOfDept`), so a Filler who
  // lost the Submit button silently (empty department / year not open /
  // past deadline / already submitted) got no explanation at all — exactly
  // the asymmetry this closes. Now shows for WHOEVER is actually blocked.
  // `!locked` avoids a duplicate line with the locked-note just below: both
  // would otherwise fire together for a Filler on a PENDING_*/APPROVED
  // department (`locked` says "Submitted/Approved..."; the server's
  // `invalid_approval_state` reason says almost the same thing) — `locked`
  // is the more specific of the two, so it wins and the generic hint stays
  // silent there. Issue #13 (2026-09-17): `isEditLocked` now covers APPROVED
  // too (was `isPendingLocked`, PENDING_* only) — the old "does NOT cover
  // APPROVED" gap this comment used to document is closed; see the
  // `locked` note below for the APPROVED-specific wording.
  const submitBlockedHint = !showSubmit && !locked ? submitBlockedReasonLabel(status.submit_blocked_reason) : null

  return (
    <div className="approval-bar" data-testid="approval-bar">
      {/* Status line sits ABOVE the action buttons (both right-aligned) —
       * chip + hints first, then Reject / Approve / Submit below. */}
      <div className="approval-bar-status">
        <span className={`status-chip status-chip-${statusToneClass(status.status)}`} data-testid="approval-status-chip">
          {statusChipLabel(status)}
        </span>
        {/* Issue #13 (2026-09-17): APPROVED gets its own wording — "submitted"
         * would misdescribe a department that already finished the whole
         * chain, and the longest-lived locked state deserves the clearest
         * explanation (user story 12). */}
        {locked && (
          <span className="act-status">
            {status.status === 'APPROVED'
              ? 'Approved — locked for editing until it is rejected'
              : 'Submitted — locked for editing until it is rejected'}
          </span>
        )}
        {submitBlockedHint && (
          <span className="act-status" data-testid="approval-submit-blocked-hint">
            {submitBlockedHint}
          </span>
        )}
        {/* No role="alert" here (unlike loadError/actionMessage below) — this
         * is a persisted field of an already-REJECTED department, not a
         * transient result of the CALLER's own action; announcing it as an
         * "alert" every time the page loads an already-rejected department
         * would be noisy for screen-reader users, not helpful. Still gets
         * the same visual .act-status-error treatment (GATE finding 1). */}
        {status.status === 'REJECTED' && status.reject_reason && (
          <span className="act-status act-status-error" data-testid="approval-reject-reason">
            Reject reason: {status.reject_reason}
          </span>
        )}
        {actionMessage && (
          <span className="act-status act-status-error" role="alert" data-testid="approval-action-message">
            {actionMessage}
          </span>
        )}
      </div>

      {showApproveReject && !rejecting && (
        <button
          type="button"
          className="btn-reject"
          data-testid="approval-reject-btn"
          disabled={actionBusy}
          onClick={() => setRejecting(true)}
        >
          Reject
        </button>
      )}
      {showApprove && (
        <button
          type="button"
          className="btn-approve"
          data-testid="approval-approve-btn"
          disabled={actionBusy}
          onClick={handleApprove}
        >
          Approve
        </button>
      )}
      {showSubmit && (
        <button
          type="button"
          className="btn-submit"
          data-testid="approval-submit-btn"
          disabled={actionBusy}
          onClick={handleSubmit}
        >
          {/* Paper-plane, mockup #submitBtn */}
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
            <path d="M22 2L11 13" />
            <path d="M22 2L15 22l-4-9-9-4 20-7z" />
          </svg>
          <span>Submit</span>
        </button>
      )}

      {rejecting && (
        <div className="reject-panel" data-testid="approval-reject-panel">
          <label htmlFor="reject-reason-input">Reject reason (required)</label>
          <textarea
            id="reject-reason-input"
            data-testid="approval-reject-reason-input"
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            rows={2}
            maxLength={REJECT_REASON_MAX_LEN}
          />
          {/* Live counter, not a colour/warning state (jakkaritw, 2026-09-17):
           * the maxLength hard stop IS the limit signal; this just tells the
           * approver how much room is left while they type. */}
          <span className="reject-panel-counter" data-testid="approval-reject-reason-counter" aria-live="polite">
            {reason.length}/{REJECT_REASON_MAX_LEN}
          </span>
          <div className="reject-panel-actions">
            <button type="button" className="btn" onClick={() => { setRejecting(false); setReason('') }}>
              Cancel
            </button>
            <button
              type="button"
              className="btn-reject"
              data-testid="approval-reject-confirm-btn"
              disabled={actionBusy || !reason.trim()}
              onClick={handleConfirmReject}
            >
              Confirm Reject
            </button>
          </div>
        </div>
      )}
    </div>
  )
}
