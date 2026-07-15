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
    expect(canSubmit({ isFillerOfDept: true, adminViewEnabled: false, status: 'DRAFT' })).toBe(true)
  })

  it('shows Submit for a Filler when status is REJECTED', () => {
    expect(canSubmit({ isFillerOfDept: true, adminViewEnabled: false, status: 'REJECTED' })).toBe(true)
  })

  it('hides Submit for a Filler once PENDING (locked, no recall)', () => {
    expect(canSubmit({ isFillerOfDept: true, adminViewEnabled: false, status: 'PENDING_APPROVER1' })).toBe(false)
  })

  it('hides Submit for a non-Filler, non-admin viewer', () => {
    expect(canSubmit({ isFillerOfDept: false, adminViewEnabled: false, status: 'DRAFT' })).toBe(false)
  })

  it('always shows Submit in admin mode regardless of status (server decides the branch)', () => {
    expect(canSubmit({ isFillerOfDept: false, adminViewEnabled: true, status: 'APPROVED' })).toBe(true)
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
