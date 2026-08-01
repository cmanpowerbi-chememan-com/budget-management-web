import { useEffect, useState } from 'react'
import { approveDepartment, fetchApprovalStatus, overrideStep, rejectDepartment, submitDepartment } from '../api/approval'
import { ApiError } from '../api/client'
import type { ApprovalStatusState } from '../api/types'
import { approverLabel, buildOverrideConfirmText, buildSubmitConfirmText, canSubmit, isPendingLocked, statusChipLabel } from './model'

export interface ApprovalActionBarProps {
  department: string | null
  fiscalYear: number
  isFillerOfDept: boolean
  adminViewEnabled: boolean
  /** Raw `scope.isAdmin` (NOT the admin-view toggle) — gates the ADR-0027
   * step-override visibility: an admin sees the อนุมัติ button on
   * PENDING_APPROVER1 even when they are not the frozen approver. */
  isAdmin: boolean
  rowCount: number
  costCenterCount: number
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
  department, fiscalYear, isFillerOfDept, adminViewEnabled, isAdmin, rowCount, costCenterCount, onChanged,
}: ApprovalActionBarProps) {
  const [status, setStatus] = useState<ApprovalStatusState | null>(null)
  const [loading, setLoading] = useState(false)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [actionBusy, setActionBusy] = useState(false)
  const [actionMessage, setActionMessage] = useState<string | null>(null)
  const [rejecting, setRejecting] = useState(false)
  const [reason, setReason] = useState('')

  async function load() {
    if (!department) return
    setLoading(true)
    setLoadError(null)
    try {
      const state = await fetchApprovalStatus(department, fiscalYear)
      setStatus(state)
    } catch (err) {
      setLoadError(err instanceof ApiError ? err.message : 'โหลดสถานะอนุมัติไม่สำเร็จ')
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

  function describeApiError(err: unknown, fallback: string): string {
    if (err instanceof ApiError) {
      if (err.status === 409) return 'มีการเปลี่ยนแปลงสถานะโดยผู้อื่นระหว่างนี้ กรุณาโหลดข้อมูลใหม่แล้วลองอีกครั้ง'
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

  function handleSubmit() {
    if (!department) return
    const confirmed = window.confirm(buildSubmitConfirmText(department, fiscalYear, rowCount, costCenterCount))
    if (!confirmed) return
    runAction(() => submitDepartment(department, fiscalYear), 'ส่งอนุมัติไม่สำเร็จ')
  }

  function handleApprove() {
    if (!department || !status) return
    if (status.can_act) {
      // Normal approve — the caller IS the frozen current approver.
      if (!window.confirm(`ยืนยันอนุมัติทั้งฝ่าย "${department}" ปี ${fiscalYear}?`)) return
      runAction(() => approveDepartment(department, fiscalYear), 'อนุมัติไม่สำเร็จ')
      return
    }
    // Admin step-override (ADR-0027): SAME อนุมัติ button, but the confirm
    // dialog must NAME the approver being skipped — it is the only guard
    // against an accidental override (no stale-gate, no reason field).
    const skippedName =
      status.current_approver_name ?? approverLabel(status.current_position, status.current_approver_empcode)
    if (!window.confirm(buildOverrideConfirmText(department, fiscalYear, skippedName))) return
    runAction(() => overrideStep(department, fiscalYear), 'อนุมัติแทนไม่สำเร็จ', describeOverrideError)
  }

  async function handleConfirmReject() {
    if (!department || !reason.trim()) return
    await runAction(() => rejectDepartment(department, fiscalYear, reason.trim()), 'ตีกลับไม่สำเร็จ')
    setRejecting(false)
    setReason('')
  }

  if (!department) return null

  if (loading && !status) {
    return (
      <div className="approval-bar" data-testid="approval-bar">
        <span className="act-status">กำลังโหลดสถานะอนุมัติ…</span>
      </div>
    )
  }

  if (loadError) {
    return (
      <div className="approval-bar" data-testid="approval-bar">
        <span className="act-status act-status-error">{loadError}</span>
        <button type="button" className="btn" onClick={load}>
          ลองใหม่
        </button>
      </div>
    )
  }

  if (!status) return null

  const showSubmit = canSubmit({ isFillerOfDept, adminViewEnabled, status: status.status })
  const showApproveReject = status.can_act && !adminViewEnabled
  // ADR-0027: ONE อนุมัติ button — visible to the frozen approver (normal
  // approve) OR to an admin while the department sits on PENDING_APPROVER1
  // (step-override; positions 2/3 stay unapproachable here, the server 409s
  // them anyway). Reject stays approver-only — an override never rejects.
  const showApprove =
    showApproveReject || (isAdmin && status.status === 'PENDING_APPROVER1' && !status.can_act)
  const locked = isPendingLocked(status.status) && isFillerOfDept && !adminViewEnabled

  return (
    <div className="approval-bar" data-testid="approval-bar">
      {/* Status line sits ABOVE the action buttons (both right-aligned) —
       * chip + hints first, then Reject / Approve / Submit below. */}
      <div className="approval-bar-status">
        <span className={`status-chip status-chip-${statusToneClass(status.status)}`} data-testid="approval-status-chip">
          {statusChipLabel(status)}
        </span>
        {locked && <span className="act-status">ส่งแล้ว — แก้ไขไม่ได้จนกว่าจะถูกตีกลับ</span>}
        {status.status === 'REJECTED' && status.reject_reason && (
          <span className="act-status act-status-error" data-testid="approval-reject-reason">
            เหตุผลที่ตีกลับ: {status.reject_reason}
          </span>
        )}
        {actionMessage && (
          <span className="act-status act-status-error" data-testid="approval-action-message">
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
          ตีกลับทั้งฝ่าย
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
          อนุมัติทั้งฝ่าย
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
          <span>ส่งอนุมัติ</span>
        </button>
      )}

      {rejecting && (
        <div className="reject-panel" data-testid="approval-reject-panel">
          <label htmlFor="reject-reason-input">เหตุผลที่ตีกลับ (จำเป็น)</label>
          <textarea
            id="reject-reason-input"
            data-testid="approval-reject-reason-input"
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            rows={2}
          />
          <div className="reject-panel-actions">
            <button type="button" className="btn" onClick={() => { setRejecting(false); setReason('') }}>
              ยกเลิก
            </button>
            <button
              type="button"
              className="btn-reject"
              data-testid="approval-reject-confirm-btn"
              disabled={actionBusy || !reason.trim()}
              onClick={handleConfirmReject}
            >
              ยืนยันตีกลับ
            </button>
          </div>
        </div>
      )}
    </div>
  )
}
