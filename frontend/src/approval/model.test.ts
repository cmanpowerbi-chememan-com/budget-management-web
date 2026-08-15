import { describe, expect, it } from 'vitest'
import type { DepartmentRow } from '../api/types'
import {
  approverLabel,
  buildSubmitConfirmText,
  canSubmit,
  costCentersOfDepartment,
  isFillerOfDepartment,
  isPendingLocked,
  statusChipLabel,
  submitBlockedReasonLabel,
} from './model'

describe('approverLabel', () => {
  it('names Nipaporn at position 2', () => {
    expect(approverLabel(2, '101032')).toContain('นิภาพร')
  })

  it('names Waraporn at position 3', () => {
    expect(approverLabel(3, '100427')).toContain('วราพร')
  })

  it('falls back to a generic role label at position 1 (no name available)', () => {
    const label = approverLabel(1, '200')
    expect(label).not.toContain('200')
    expect(label).toContain('ผู้บังคับบัญชา')
  })

  it('names Nipaporn even at position 1 when approver1 collapsed onto her empcode (invalid-approver1 fallback)', () => {
    expect(approverLabel(1, '101032')).toContain('นิภาพร')
  })
})

describe('statusChipLabel', () => {
  it('labels DRAFT plainly', () => {
    expect(statusChipLabel({ status: 'DRAFT', current_position: null, current_approver_empcode: null })).toContain('แบบร่าง')
  })

  it('labels a PENDING step with the position number and approver name', () => {
    const label = statusChipLabel({ status: 'PENDING_APPROVER2', current_position: 2, current_approver_empcode: '101032' })
    expect(label).toContain('ขั้น 2')
    expect(label).toContain('นิภาพร')
  })

  it('labels APPROVED plainly', () => {
    expect(statusChipLabel({ status: 'APPROVED', current_position: null, current_approver_empcode: null })).toContain('อนุมัติแล้ว')
  })

  it('labels REJECTED plainly', () => {
    expect(statusChipLabel({ status: 'REJECTED', current_position: null, current_approver_empcode: null })).toContain('ตีกลับ')
  })
})

describe('isPendingLocked', () => {
  it.each(['PENDING_APPROVER1', 'PENDING_APPROVER2', 'PENDING_APPROVER3'])('is true for %s', (status) => {
    expect(isPendingLocked(status)).toBe(true)
  })

  it.each(['DRAFT', 'APPROVED', 'REJECTED'])('is false for %s', (status) => {
    expect(isPendingLocked(status)).toBe(false)
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

  it("explains shape (a)'s admin_cannot_submit_in_cycle reason in Thai", () => {
    expect(submitBlockedReasonLabel('admin_cannot_submit_in_cycle')).toContain('รอบอนุมัติปกติ')
  })

  it("explains department_empty in Thai, matching the server's own DepartmentEmptyError text", () => {
    expect(submitBlockedReasonLabel('department_empty')).toBe('ฝ่ายนี้ยังไม่มีข้อมูลงบประมาณ จึงส่งอนุมัติไม่ได้')
  })

  it('returns null for an unmapped/unknown reason code (never shows a raw machine code)', () => {
    expect(submitBlockedReasonLabel('some_future_reason')).toBeNull()
  })

  // Filler-blocked-hint fix (2026-08-16, jakkaritw: "ใส่ข้อความให้ผู้กรอกด้วย"):
  // these 3 reasons are the filler-reachable ones confirmed against
  // `evaluate_submit_eligibility` in backend/app/approval.py (department_empty
  // was already covered above, since it fires for every caller).
  it('explains year_not_open in Thai, saying the year has not opened yet', () => {
    expect(submitBlockedReasonLabel('year_not_open')).toContain('ยังไม่เปิด')
  })

  it('explains past_deadline in Thai, saying the deadline has already passed', () => {
    expect(submitBlockedReasonLabel('past_deadline')).toContain('เลยกำหนด')
  })

  it('explains invalid_approval_state in Thai (already mid-chain or approved)', () => {
    expect(submitBlockedReasonLabel('invalid_approval_state')).toContain('ส่งซ้ำไม่ได้')
  })

  it('explains not_filler_of_department without assuming the reader is an admin (evaluate_submit_eligibility only returns this reason when scope.is_admin is False -- an actual admin never sees it)', () => {
    const text = submitBlockedReasonLabel('not_filler_of_department')
    expect(text).not.toBeNull()
    expect(text).not.toContain('ผู้ดูแลระบบ')
  })
})

describe('buildSubmitConfirmText', () => {
  it('mentions the department, year, row count, and cost center count', () => {
    const text = buildSubmitConfirmText('Accounting', 2027, 12, 3)
    expect(text).toContain('Accounting')
    expect(text).toContain('2027')
    expect(text).toContain('12')
    expect(text).toContain('3')
  })
})
