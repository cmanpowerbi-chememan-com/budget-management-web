import { describe, expect, it } from 'vitest'
import type { BudgetRow, DepartmentRow } from '../api/types'
import { countDistinctFillGlAccounts, deriveScopeSummary } from './model'

function dept(cost_center: string, department: string | null, division: string | null): DepartmentRow {
  return { cost_center, department, division, c_level: null }
}

function row(cost_center: string, gl_account: string): BudgetRow {
  return {
    cost_center,
    gl_account,
    sap: {} as BudgetRow['sap'],
    board: {} as BudgetRow['board'],
    pending: {} as BudgetRow['pending'],
    editable: true,
  }
}

describe('deriveScopeSummary', () => {
  it('restricts to the caller Fill cost centers and returns distinct Thai-sorted สายงาน/ฝ่าย', () => {
    const departments = [
      dept('10CA013000', 'ฝ่ายบัญชี', 'สายงานการเงิน'),
      dept('10CA013001', 'ฝ่ายการเงิน', 'สายงานการเงิน'),
      dept('10MN012100', 'ฝ่ายผลิต', 'สายงานผลิต'),
    ]

    const summary = deriveScopeSummary(departments, ['10CA013000', '10CA013001'])

    expect(summary.divisions).toEqual(['สายงานการเงิน'])
    expect(summary.departments).toEqual(['ฝ่ายการเงิน', 'ฝ่ายบัญชี'])
  })

  it('excludes See-only cost centers not present in the Fill list', () => {
    const departments = [dept('10CA013000', 'ฝ่ายบัญชี', 'สายงานการเงิน'), dept('SEE-ONLY-CC', 'ฝ่ายอื่น', 'สายงานอื่น')]

    const summary = deriveScopeSummary(departments, ['10CA013000'])

    expect(summary.departments).toEqual(['ฝ่ายบัญชี'])
    expect(summary.divisions).toEqual(['สายงานการเงิน'])
  })

  it('drops blank/null division or department rows quietly instead of a placeholder chip', () => {
    const departments = [dept('10CA013000', null, null), dept('10CA013001', 'ฝ่ายบัญชี', 'สายงานการเงิน')]

    const summary = deriveScopeSummary(departments, ['10CA013000', '10CA013001'])

    expect(summary.divisions).toEqual(['สายงานการเงิน'])
    expect(summary.departments).toEqual(['ฝ่ายบัญชี'])
  })

  it('returns empty arrays when the caller has no Fill cost centers or no matching rows', () => {
    const departments = [dept('10CA013000', 'ฝ่ายบัญชี', 'สายงานการเงิน')]

    expect(deriveScopeSummary(departments, [])).toEqual({ divisions: [], departments: [] })
    expect(deriveScopeSummary([], ['10CA013000'])).toEqual({ divisions: [], departments: [] })
  })

  it('dedupes multiple cost centers under the same ฝ่าย/สายงาน', () => {
    const departments = [
      dept('CC1', 'ฝ่ายบัญชี', 'สายงานการเงิน'),
      dept('CC2', 'ฝ่ายบัญชี', 'สายงานการเงิน'),
      dept('CC3', 'ฝ่ายบัญชี', 'สายงานการเงิน'),
    ]

    const summary = deriveScopeSummary(departments, ['CC1', 'CC2', 'CC3'])

    expect(summary.departments).toEqual(['ฝ่ายบัญชี'])
    expect(summary.divisions).toEqual(['สายงานการเงิน'])
  })
})

describe('countDistinctFillGlAccounts', () => {
  it('counts distinct GL accounts across rows whose cost_center is in the Fill list', () => {
    const rows = [row('CC1', 'GL1'), row('CC1', 'GL2'), row('CC2', 'GL1'), row('CC3', 'GL9')]

    expect(countDistinctFillGlAccounts(rows, ['CC1', 'CC2'])).toBe(2)
  })

  it('ignores rows whose cost_center is See-only (not in the Fill list)', () => {
    const rows = [row('CC1', 'GL1'), row('SEE-ONLY', 'GL2')]

    expect(countDistinctFillGlAccounts(rows, ['CC1'])).toBe(1)
  })

  it('returns 0 for no rows or no Fill cost centers', () => {
    expect(countDistinctFillGlAccounts([], ['CC1'])).toBe(0)
    expect(countDistinctFillGlAccounts([row('CC1', 'GL1')], [])).toBe(0)
  })
})
