import { describe, expect, it } from 'vitest'
import type { BudgetRow, DepartmentRow } from '../api/types'
import { countDistinctFillGlAccounts, deriveScopeSummary, truncateChipNames } from './model'

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

  // laddawank-no-division-chip: a manager with NO Fill scope (not a Filler
  // anywhere) but a real See scope (granted via _MANAGER_SEE_ADD_SQL because
  // she manages a Filler) must still see her real สายงาน/ฝ่าย, not the
  // "unknown division" fallback — see/departments already returns her
  // See-scoped rows (routers/reference.py passes scope.see_cost_centers),
  // this was purely the frontend discarding them.
  it('falls back to the See cost centers when Fill is empty (manager with no Fill scope)', () => {
    const departments = [dept('10IT011300', 'Data & Analytic', 'Digital Technology')]

    const summary = deriveScopeSummary(departments, [], ['10IT011300'])

    expect(summary.divisions).toEqual(['Digital Technology'])
    expect(summary.departments).toEqual(['Data & Analytic'])
  })

  it('ignores See entirely when Fill is non-empty — the common Filler case must not change', () => {
    const departments = [
      dept('CC1', 'ฝ่ายบัญชี', 'สายงานการเงิน'),
      dept('CC2', 'ฝ่ายอื่น', 'สายงานอื่น'), // See-only via manager/overlay add, not Fill
    ]

    const summary = deriveScopeSummary(departments, ['CC1'], ['CC1', 'CC2'])

    expect(summary.divisions).toEqual(['สายงานการเงิน'])
    expect(summary.departments).toEqual(['ฝ่ายบัญชี'])
  })

  it('does not duplicate a division/department that appears in both Fill and See (Fill ⊆ See by construction)', () => {
    const departments = [dept('CC1', 'ฝ่ายบัญชี', 'สายงานการเงิน'), dept('CC2', 'ฝ่ายบัญชี', 'สายงานการเงิน')]

    const summary = deriveScopeSummary(departments, ['CC1'], ['CC1', 'CC2'])

    expect(summary.divisions).toEqual(['สายงานการเงิน'])
    expect(summary.departments).toEqual(['ฝ่ายบัญชี'])
  })

  it('returns empty arrays when both Fill and See are empty', () => {
    const departments = [dept('10CA013000', 'ฝ่ายบัญชี', 'สายงานการเงิน')]

    expect(deriveScopeSummary(departments, [], [])).toEqual({ divisions: [], departments: [] })
  })
})

describe('truncateChipNames', () => {
  // jakkaritw, verbatim: "โชว์ 3 ชื่อแรก แล้วต่อท้าย +6 สายงาน" — measured
  // against live data, bunpotk@chememan.com (9 สายงาน / 45 ฝ่าย, a see-only
  // manager whose Fill scope is empty) rendered a 174-char chip before this.
  it('9 สายงาน → keeps the first 3 and appends "+6 สายงาน"', () => {
    const names = ['D1', 'D2', 'D3', 'D4', 'D5', 'D6', 'D7', 'D8', 'D9']

    expect(truncateChipNames(names, 'สายงาน')).toEqual({
      shown: ['D1', 'D2', 'D3'],
      suffix: '+6 สายงาน',
    })
  })

  it('7 ฝ่าย → keeps the first 3 and appends "+4 ฝ่าย"', () => {
    const names = ['A1', 'A2', 'A3', 'A4', 'A5', 'A6', 'A7']

    expect(truncateChipNames(names, 'ฝ่าย')).toEqual({
      shown: ['A1', 'A2', 'A3'],
      suffix: '+4 ฝ่าย',
    })
  })

  it('boundary: exactly 3 names → no suffix, unchanged', () => {
    const names = ['A1', 'A2', 'A3']

    expect(truncateChipNames(names, 'ฝ่าย')).toEqual({ shown: ['A1', 'A2', 'A3'], suffix: null })
  })

  it('boundary: exactly 4 names → first 3 + "+1 สายงาน"', () => {
    const names = ['A1', 'A2', 'A3', 'A4']

    expect(truncateChipNames(names, 'สายงาน')).toEqual({ shown: ['A1', 'A2', 'A3'], suffix: '+1 สายงาน' })
  })

  it('1 name → unchanged, no suffix', () => {
    expect(truncateChipNames(['A1'], 'ฝ่าย')).toEqual({ shown: ['A1'], suffix: null })
  })

  it('0 names → unchanged empty, no suffix', () => {
    expect(truncateChipNames([], 'ฝ่าย')).toEqual({ shown: [], suffix: null })
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
