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
  it('shows Submit for a Filler when status is DRAFT', () => {
    expect(canSubmit({ isFillerOfDept: true, adminViewEnabled: false, status: 'DRAFT', isPostDeadline: false })).toBe(true)
  })

  it('shows Submit for a Filler when status is REJECTED', () => {
    expect(canSubmit({ isFillerOfDept: true, adminViewEnabled: false, status: 'REJECTED', isPostDeadline: false })).toBe(true)
  })

  it('hides Submit for a Filler once PENDING (locked, no recall)', () => {
    expect(
      canSubmit({ isFillerOfDept: true, adminViewEnabled: false, status: 'PENDING_APPROVER1', isPostDeadline: false }),
    ).toBe(false)
  })

  it('hides Submit for a non-Filler, non-admin viewer', () => {
    expect(canSubmit({ isFillerOfDept: false, adminViewEnabled: false, status: 'DRAFT', isPostDeadline: false })).toBe(false)
  })

  // Guards branch order: the post-deadline override is the admin hat's alone.
  // If the `adminViewEnabled` branch is ever reordered/merged with the plain
  // filler check, a non-admin filler would start seeing Submit on a locked
  // department once the deadline passes -- a real authorization-shaped regression.
  it.each(['PENDING_APPROVER1', 'PENDING_APPROVER2', 'PENDING_APPROVER3', 'APPROVED'])(
    'still hides Submit for a non-admin Filler on locked status %s even past the deadline (override never leaks to non-admins)',
    (status) => {
      expect(canSubmit({ isFillerOfDept: true, adminViewEnabled: false, status, isPostDeadline: true })).toBe(false)
    },
  )

  // SIT defect fix (2026-08-14): admin used to always see Submit regardless
  // of status, so the button was shown mid-cycle and 403'd every time (the
  // server's normal-chain/Template-2/orphan doors all refuse a locked
  // record). The one admin door that DOES accept a locked status is the
  // post-deadline override (ADR-0012) -- gated here by `isPostDeadline`.
  it.each(['PENDING_APPROVER1', 'PENDING_APPROVER2', 'PENDING_APPROVER3', 'APPROVED'])(
    'hides Submit for admin on locked status %s while the cycle is still open',
    (status) => {
      expect(canSubmit({ isFillerOfDept: false, adminViewEnabled: true, status, isPostDeadline: false })).toBe(false)
    },
  )

  it.each(['PENDING_APPROVER1', 'PENDING_APPROVER2', 'PENDING_APPROVER3', 'APPROVED'])(
    'shows Submit for admin on locked status %s once the deadline has passed (post-deadline override door survives)',
    (status) => {
      expect(canSubmit({ isFillerOfDept: false, adminViewEnabled: true, status, isPostDeadline: true })).toBe(true)
    },
  )

  it('shows Submit for admin on DRAFT regardless of deadline (never-submitted admin door unaffected)', () => {
    expect(canSubmit({ isFillerOfDept: false, adminViewEnabled: true, status: 'DRAFT', isPostDeadline: false })).toBe(true)
  })

  it('shows Submit for admin on REJECTED regardless of deadline (Template-2/orphan doors unaffected)', () => {
    expect(canSubmit({ isFillerOfDept: false, adminViewEnabled: true, status: 'REJECTED', isPostDeadline: false })).toBe(
      true,
    )
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
