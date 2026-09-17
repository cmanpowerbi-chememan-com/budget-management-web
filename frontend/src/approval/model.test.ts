import { describe, expect, it } from 'vitest'
import type { DepartmentRow } from '../api/types'
import {
  buildOverrideConfirmText,
  buildSubmitConfirmText,
  canSubmit,
  costCentersOfDepartment,
  isEditLocked,
  isFillerOfDepartment,
  pendingApproverDisplayName,
  statusChipLabel,
  submitBlockedReasonLabel,
} from './model'

describe('pendingApproverDisplayName', () => {
  it('returns the server name while pending', () => {
    expect(
      pendingApproverDisplayName({ current_position: 2, current_approver_name: 'Nipaporn Tongking' }),
    ).toBe('Nipaporn Tongking')
  })

  it('returns null when not on a pending step, even if a name is present', () => {
    expect(pendingApproverDisplayName({ current_position: null, current_approver_name: 'Nipaporn Tongking' })).toBeNull()
  })
})

describe('statusChipLabel', () => {
  it('labels DRAFT plainly', () => {
    expect(statusChipLabel({ status: 'DRAFT', current_position: null, current_approver_name: null })).toContain('Draft')
  })

  // jakkaritw, 2026-09-17: the chip names the real person, in English, not a
  // role/typed-in title -- e.g. "Pending on Nipaporn Tongking".
  it('names the current approver in English when pending with a name', () => {
    const label = statusChipLabel({ status: 'PENDING_APPROVER2', current_position: 2, current_approver_name: 'Nipaporn Tongking' })
    expect(label).toBe('Pending on Nipaporn Tongking')
  })

  it('falls back to the step number when pending without a name', () => {
    const label = statusChipLabel({ status: 'PENDING_APPROVER1', current_position: 1, current_approver_name: null })
    expect(label).toBe('Pending · Step 1')
  })

  it('labels APPROVED plainly', () => {
    expect(statusChipLabel({ status: 'APPROVED', current_position: null, current_approver_name: null })).toContain('Approved')
  })

  it('labels REJECTED plainly', () => {
    expect(statusChipLabel({ status: 'REJECTED', current_position: null, current_approver_name: null })).toContain('Rejected')
  })
})

describe('isEditLocked', () => {
  it.each(['PENDING_APPROVER1', 'PENDING_APPROVER2', 'PENDING_APPROVER3', 'APPROVED'])('is true for %s', (status) => {
    expect(isEditLocked(status)).toBe(true)
  })

  it.each(['DRAFT', 'REJECTED'])('is false for %s', (status) => {
    expect(isEditLocked(status)).toBe(false)
  })
})

const ROWS: DepartmentRow[] = [
  { cost_center: 'CC1', department: 'Accounting', division: 'Finance', c_level: 'CFO' },
  { cost_center: 'CC2', department: 'Accounting', division: 'Finance', c_level: 'CFO' },
  { cost_center: 'CC3', department: 'IT', division: 'Digital', c_level: 'CTO' },
]

describe('costCentersOfDepartment', () => {
  it('returns the distinct cost centers of the given department', () => {
    expect(costCentersOfDepartment(ROWS, 'Accounting')).toEqual(['CC1', 'CC2'])
  })

  it('returns an empty array for an unknown department', () => {
    expect(costCentersOfDepartment(ROWS, 'Nonexistent')).toEqual([])
  })
})

describe('isFillerOfDepartment', () => {
  it('is true when any of the department CCs is in Fill scope', () => {
    expect(isFillerOfDepartment(ROWS, 'Accounting', ['CC2'])).toBe(true)
  })

  it('is false when Fill scope has none of the department CCs', () => {
    expect(isFillerOfDepartment(ROWS, 'Accounting', ['CC3'])).toBe(false)
  })
})

describe('canSubmit', () => {
  it('shows Submit for a Filler when the server allows it', () => {
    expect(canSubmit({ isFillerOfDept: true, adminViewEnabled: false, canSubmitServer: true })).toBe(true)
  })

  // Regression guard for the 2026-08-14 fix (77308d7): a filler must never
  // see Submit once the department is locked (mid-chain / APPROVED, no
  // recall -- ADR-0006). The server's own `evaluate_submit_eligibility`
  // encodes this now (`invalid_approval_state`); the client just reads it.
  it('hides Submit for a Filler when the server blocks it (mid-chain, no recall)', () => {
    expect(canSubmit({ isFillerOfDept: true, adminViewEnabled: false, canSubmitServer: false })).toBe(false)
  })

  it('hides Submit for a non-Filler, non-admin viewer regardless of the server verdict', () => {
    expect(canSubmit({ isFillerOfDept: false, adminViewEnabled: false, canSubmitServer: true })).toBe(false)
  })

  // The "put on the admin hat first" gesture stays entirely client-side: an
  // admin who has not toggled Admin mode on never sees an admin-only action,
  // even for a department the server would actually let them submit.
  it('hides Submit for an admin viewer with the hat OFF, even when the server would allow it', () => {
    expect(canSubmit({ isFillerOfDept: false, adminViewEnabled: false, canSubmitServer: true })).toBe(false)
  })

  // SIT defect fix #2 (2026-08-16): shape (a), the actual reported bug -- a
  // non-filler admin, department not orphan, no Template-2 rows, cycle
  // still open. `canSubmitServer` is now `false`
  // (`admin_cannot_submit_in_cycle`) and the button must not appear.
  it('hides Submit for admin (hat on) when the server refuses -- shape (a), the SIT defect', () => {
    expect(canSubmit({ isFillerOfDept: false, adminViewEnabled: true, canSubmitServer: false })).toBe(false)
  })

  // Shapes (b) orphan department / (c) Template-2 rows present / (d)
  // post-deadline override -- the server says true and the button shows.
  it('shows Submit for admin (hat on) when the server allows it -- shapes (b)/(c)/(d)', () => {
    expect(canSubmit({ isFillerOfDept: false, adminViewEnabled: true, canSubmitServer: true })).toBe(true)
  })

  // A caller who BOTH Fills the department AND has the admin hat on
  // (Nipaporn/Waraporn's dual role, ADR-0006) follows the FILLER branch --
  // the hat is irrelevant once isFillerOfDept is true, matching the
  // server's own branch selection (a filler ALWAYS routes through the
  // normal chain, never the admin doors, regardless of scope.is_admin).
  it('follows the server verdict for a filler-admin regardless of the hat (dual-role, ADR-0006)', () => {
    expect(canSubmit({ isFillerOfDept: true, adminViewEnabled: true, canSubmitServer: true })).toBe(true)
    expect(canSubmit({ isFillerOfDept: true, adminViewEnabled: true, canSubmitServer: false })).toBe(false)
  })

  // Fail-closed typing regression guard (gate review, 2026-08-16):
  // `canSubmitServer` is typed `boolean`, but an older/partial server
  // response is not actually guaranteed to carry it -- `undefined` must
  // still hide the button, not throw or accidentally show it. Cast through
  // `unknown` deliberately: this is testing behaviour AGAINST the type
  // system's own guarantee, which a plain missing property could not do.
  it('hides Submit when the server response is missing can_submit entirely (fail-closed, not just falsy)', () => {
    const staleServerResponse = { isFillerOfDept: true, adminViewEnabled: false } as unknown as Parameters<typeof canSubmit>[0]
    expect(canSubmit(staleServerResponse)).toBe(false)
  })
})

describe('submitBlockedReasonLabel', () => {
  it('returns null when there is no blocked reason', () => {
    expect(submitBlockedReasonLabel(null)).toBeNull()
  })

  it("explains shape (a)'s admin_cannot_submit_in_cycle reason", () => {
    expect(submitBlockedReasonLabel('admin_cannot_submit_in_cycle')).toContain('normal approval cycle')
  })

  it('explains department_empty, for a department with no budget data yet', () => {
    expect(submitBlockedReasonLabel('department_empty')).toBe('This department has no budget data yet, so it cannot be submitted.')
  })

  it('returns null for an unmapped/unknown reason code (never shows a raw machine code)', () => {
    expect(submitBlockedReasonLabel('some_future_reason')).toBeNull()
  })

  // Filler-blocked-hint fix (2026-08-16, jakkaritw: "ใส่ข้อความให้ผู้กรอกด้วย"):
  // these 3 reasons are the filler-reachable ones confirmed against
  // `evaluate_submit_eligibility` in backend/app/approval.py (department_empty
  // was already covered above, since it fires for every caller).
  it('explains year_not_open, saying the year has not opened yet', () => {
    expect(submitBlockedReasonLabel('year_not_open')).toContain('not open')
  })

  it('explains past_deadline, saying the deadline has already passed', () => {
    expect(submitBlockedReasonLabel('past_deadline')).toContain('has passed')
  })

  it('explains invalid_approval_state (already mid-chain or approved)', () => {
    expect(submitBlockedReasonLabel('invalid_approval_state')).toContain('cannot be submitted again')
  })

  it('explains not_filler_of_department without assuming the reader is an admin (evaluate_submit_eligibility only returns this reason when scope.is_admin is False -- an actual admin never sees it)', () => {
    const text = submitBlockedReasonLabel('not_filler_of_department')
    expect(text).not.toBeNull()
    expect(text).not.toContain('admin')
  })
})

describe('buildSubmitConfirmText', () => {
  // 2026-09-16 (jakkaritw): the row/cost-centre counts were dropped from
  // this dialog — assert the exact remaining string, not a substring.
  it('asks to confirm the whole-department submit, with no row/cost-center counts', () => {
    const text = buildSubmitConfirmText('Accounting', 2027)
    expect(text).toBe(
      'Submit the budget of department "Accounting" for FY 2027?\n' +
        'This submits the WHOLE department. You cannot edit it until it is rejected.',
    )
    expect(text).not.toContain('rows in')
  })
})

describe('buildOverrideConfirmText', () => {
  // 2026-09-17 (jakkaritw, UAT): trimmed from two sentences to one -- assert
  // the exact remaining string, not a substring, so the old wording cannot
  // creep back in.
  it('is one line naming who is approved on behalf of, the department and the fiscal year', () => {
    const text = buildOverrideConfirmText('Data & Analytic', 2027, 'Laddawan Kearnoi')
    expect(text).toBe('⚠️ You are approving on behalf of Laddawan Kearnoi for department "Data & Analytic", FY 2027')
    expect(text).not.toContain('(approver step 1)')
    expect(text).not.toContain('The system will record')
    expect(text).not.toContain('Continue?')
  })
})
