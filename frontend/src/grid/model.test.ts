import { afterEach, describe, expect, it, vi } from 'vitest'
import type { DepartmentRow, GlAccount, PendingRowState } from '../api/types'
import {
  applyMonthEdit,
  BLANK_COLUMN_FILTERS,
  buildNewRowPayload,
  buildSavePayload,
  clampColumnWidth,
  clearStoredColumnWidths,
  COLUMN_WIDTH_MIN,
  COLUMN_WIDTHS_STORAGE_KEY,
  DEFAULT_COLUMN_WIDTHS,
  filterRows,
  fitColumnWidth,
  formatSapMonth,
  formatThaiShortDate,
  formatThb,
  freezeOffsets,
  HIDDEN_SAP_MONTH_MARK,
  fullRowColSpan,
  glMetaFor,
  groupAndSortBySide,
  groupChipClass,
  hasStoredColumnWidthsOverride,
  identityColSpan,
  isCostCenterLocked,
  isDeletableRow,
  isEditableCell,
  loadStoredColumnWidths,
  lockedCostCenterDepartments,
  mergeSavedRow,
  MONTH_LABELS,
  nowMonthKey,
  persistColumnWidths,
  sanitizeMonthInput,
  sapCoverageLabel,
  sapFreshnessLine,
  sectionTotals,
  selectMeasureCandidates,
  sideOfGl,
  subtotalLabelColSpan,
  validateNewTransaction,
  visibleSapMonths,
  YEAR_NOT_OPEN_ADD_REASON_TH,
} from './model'
import { blankLayer, makeRow as row, sapLayer } from './testUtils'

const GL_REF: GlAccount[] = [
  { gl_code: '5211900030', gl_group: 'Entertainment', gl_name: 'Ent COST', is_special: true },
  { gl_code: '6211900030', gl_group: 'Entertainment', gl_name: 'Ent SGA', is_special: true },
  { gl_code: '5211800030', gl_group: 'Office expenses', gl_name: 'Office COST', is_special: false },
  { gl_code: '6211800030', gl_group: 'Office expenses', gl_name: 'Office SGA', is_special: false },
  { gl_code: '5210400010', gl_group: 'Travelling Expense', gl_name: 'Per diem', is_special: false },
]

describe('sideOfGl', () => {
  it('classifies a 5xxx GL as COST', () => {
    expect(sideOfGl('5211900030')).toBe('COST')
  })
  it('classifies a 6xxx GL as SGA', () => {
    expect(sideOfGl('6211900030')).toBe('SGA')
  })
  it('classifies anything else as OTHER (never crashes)', () => {
    expect(sideOfGl('9999999999')).toBe('OTHER')
  })
})

describe('glMetaFor', () => {
  it('resolves gl_group/gl_name/is_special from the reference list, flagged in_master', () => {
    const meta = glMetaFor('5211900030', GL_REF)
    expect(meta).toEqual({ gl_group: 'Entertainment', gl_name: 'Ent COST', is_special: true, in_master: true })
  })

  it('falls back to an Uncategorized/non-special/not-in-master meta for an unknown GL (never crashes)', () => {
    const meta = glMetaFor('0000000000', GL_REF)
    expect(meta.gl_group).toBe('Uncategorized')
    expect(meta.is_special).toBe(false)
    expect(meta.in_master).toBe(false)
  })
})

describe('groupAndSortBySide — NEVER-CUT: COST 5xxx and SG&A 6xxx never cross', () => {
  it('splits rows into COST and SGA sections', () => {
    const rows = [
      row({ cost_center: 'CC1', gl_account: '5211800030' }),
      row({ cost_center: 'CC1', gl_account: '6211800030' }),
    ]
    const sections = groupAndSortBySide(rows, GL_REF)
    expect(sections.COST.flatMap((g) => g.rows).map((r) => r.gl_account)).toEqual(['5211800030'])
    expect(sections.SGA.flatMap((g) => g.rows).map((r) => r.gl_account)).toEqual(['6211800030'])
  })

  it('groups rows by gl_group within a side, sorted alphabetically', () => {
    const rows = [
      row({ cost_center: 'CC1', gl_account: '5211900030' }), // Entertainment
      row({ cost_center: 'CC1', gl_account: '5211800030' }), // Office expenses
    ]
    const sections = groupAndSortBySide(rows, GL_REF)
    expect(sections.COST.map((g) => g.glGroup)).toEqual(['Entertainment', 'Office expenses'])
  })

  it('a COST-side subtotal never includes an SGA row\'s amounts', () => {
    const rows = [
      row({ cost_center: 'CC1', gl_account: '5211800030', pending: { ...row({ cost_center: 'x', gl_account: 'x' }).pending, m01: 100, total_year: 100 } }),
      row({ cost_center: 'CC1', gl_account: '6211800030', pending: { ...row({ cost_center: 'x', gl_account: 'x' }).pending, m01: 9999, total_year: 9999 } }),
    ]
    const sections = groupAndSortBySide(rows, GL_REF)
    const costGroupTotal = sections.COST[0].subtotal.pending.m01
    expect(costGroupTotal).toBe(100)
  })
})

describe('sectionTotals — NEVER-CUT: COST and SGA totals never combined', () => {
  it('computes independent totals per side, never summed together', () => {
    const costRows = [row({ cost_center: 'CC1', gl_account: '5211800030', pending: { ...row({ cost_center: 'x', gl_account: 'x' }).pending, total_year: 100 } })]
    const sgaRows = [row({ cost_center: 'CC1', gl_account: '6211800030', pending: { ...row({ cost_center: 'x', gl_account: 'x' }).pending, total_year: 250 } })]

    const costTotal = sectionTotals(costRows)
    const sgaTotal = sectionTotals(sgaRows)

    expect(costTotal.pending.total_year).toBe(100)
    expect(sgaTotal.pending.total_year).toBe(250)
    // there is no function that adds these two together — structurally enforced
  })
})

describe('isEditableCell', () => {
  it('is editable when row.editable is true, the GL is not special, and the GL is in the master', () => {
    expect(isEditableCell(true, false, true)).toBe(true)
  })
  it('is NEVER editable for a special-GL row even when row.editable is true', () => {
    expect(isEditableCell(true, true, true)).toBe(false)
  })
  it('is not editable when row.editable is false', () => {
    expect(isEditableCell(false, false, true)).toBe(false)
  })
  it('is NOT editable when the GL is not in the GL master (add-later policy), even when row.editable is true', () => {
    expect(isEditableCell(true, false, false)).toBe(false)
  })
})

describe('isDeletableRow — grid trailing "ลบ" column eligibility (jakkaritw-approved, 2 policy decisions)', () => {
  const officeMeta = glMetaFor('5211800030', GL_REF) // Office expenses — non-special, non-travel
  const travelMeta = glMetaFor('5210400010', GL_REF) // Travelling Expense

  it('is deletable when editable, no SAP value in any month, no Approved value in any month, and not Travelling Expense', () => {
    const base = row({ cost_center: 'CC1', gl_account: '5211800030', editable: true })
    const r = { ...base, pending: { ...base.pending, updated_at: '2026-01-01T00:00:00Z' } }
    expect(isDeletableRow(r, officeMeta)).toBe(true)
  })

  it('is NOT deletable when no pending_budget row exists (updated_at null) — the click would 422 on a blank lock token', () => {
    const r = row({ cost_center: 'CC1', gl_account: '5211800030', editable: true }) // testUtils default: pending.updated_at = null
    expect(isDeletableRow(r, officeMeta)).toBe(false)
  })

  it('is NOT deletable when row.editable is false (See-only / out-of-scope)', () => {
    const r = row({ cost_center: 'CC1', gl_account: '5211800030', editable: false })
    expect(isDeletableRow(r, officeMeta)).toBe(false)
  })

  it('is NOT deletable when ANY month has a SAP value (not a web-added row)', () => {
    const base = row({ cost_center: 'CC1', gl_account: '5211800030', editable: true })
    const r = { ...base, sap: { ...base.sap, m03: 100 } }
    expect(isDeletableRow(r, officeMeta)).toBe(false)
  })

  it('is NOT deletable when ANY month has an Approved (board) value', () => {
    const base = row({ cost_center: 'CC1', gl_account: '5211800030', editable: true })
    const r = { ...base, board: { ...base.board, m07: 50 } }
    expect(isDeletableRow(r, officeMeta)).toBe(false)
  })

  it('is NOT deletable for Travelling Expense, even when editable with no SAP/Approved (Trip Manager owns delete there)', () => {
    const r = row({ cost_center: 'CC1', gl_account: '5210400010', editable: true })
    expect(isDeletableRow(r, travelMeta)).toBe(false)
  })
})

// Promoted from MonthCell.tsx (was module-private) so DetailSubform's and
// TripManager's month inputs can reuse the EXACT same rule instead of each
// re-implementing their own (broken) `Number(raw.replace(/[^0-9]/g,''))`
// version — see subform/MonthAmountInput.tsx.
describe('sanitizeMonthInput', () => {
  it('keeps digits and a single decimal point', () => {
    expect(sanitizeMonthInput('51000.50')).toBe('51000.50')
  })

  it('caps to at most 2 decimal places', () => {
    expect(sanitizeMonthInput('100.567')).toBe('100.56')
  })

  it('keeps only the first decimal point when multiple dots are typed', () => {
    expect(sanitizeMonthInput('1.2.3')).toBe('1.23')
  })

  it('strips letters', () => {
    expect(sanitizeMonthInput('1a2b3')).toBe('123')
  })

  it('strips a leading minus sign — negatives are not allowed', () => {
    expect(sanitizeMonthInput('-50')).toBe('50')
  })

  it('does not destroy a partially-typed decimal ("51000.") mid-typing', () => {
    expect(sanitizeMonthInput('51000.')).toBe('51000.')
  })

  it('passes a lone "." through unchanged (caller resolves it to 0 at commit time)', () => {
    expect(sanitizeMonthInput('.')).toBe('.')
  })
})

describe('applyMonthEdit', () => {
  it('updates one month and recomputes total_year for display (server recomputes authoritatively)', () => {
    const r = row({ cost_center: 'CC1', gl_account: 'GL1' })
    const updated = applyMonthEdit(r, 'm03', 500)
    expect(updated.pending.m03).toBe(500)
    expect(updated.pending.total_year).toBe(500)
    // original untouched (pure function)
    expect(r.pending.m03).toBe(0)
  })

  it('sums all 12 months into total_year, not just the edited one', () => {
    const base = row({ cost_center: 'CC1', gl_account: 'GL1' })
    const withM01 = applyMonthEdit(base, 'm01', 100)
    const withM02 = applyMonthEdit(withM01, 'm02', 50)
    expect(withM02.pending.total_year).toBe(150)
  })
})

describe('buildSavePayload', () => {
  it('builds a PendingRowInput from the row\'s current pending months + the lock token', () => {
    const r = row({
      cost_center: 'CC1',
      gl_account: 'GL1',
      pending: { ...row({ cost_center: 'x', gl_account: 'x' }).pending, m01: 500, total_year: 500, remark: 'note', updated_at: '2026-01-01T00:00:00Z' },
    })
    const payload = buildSavePayload(r, 2027)
    expect(payload).toMatchObject({
      cost_center: 'CC1',
      gl_account: 'GL1',
      fiscal_year: 2027,
      m01: 500,
      remark: 'note',
      expected_updated_at: '2026-01-01T00:00:00Z',
    })
  })

  it('sends expected_updated_at=null when no pending row exists yet (create path)', () => {
    const r = row({ cost_center: 'CC1', gl_account: 'GL1' })
    const payload = buildSavePayload(r, 2027)
    expect(payload.expected_updated_at).toBeNull()
  })
})

describe('mergeSavedRow', () => {
  it('replaces the pending layer with the authoritative server state after a successful save', () => {
    const r = row({ cost_center: 'CC1', gl_account: 'GL1' })
    const saved: PendingRowState = {
      cost_center: 'CC1', gl_account: 'GL1', fiscal_year: 2027,
      m01: 500, m02: 0, m03: 0, m04: 0, m05: 0, m06: 0, m07: 0, m08: 0, m09: 0, m10: 0, m11: 0, m12: 0,
      total_year: 500, remark: 'note', template: 'USER',
      gl_name: 'x', gl_group: 'y', c_level: null, division: null, department: null,
      updated_at: '2026-02-02T00:00:00Z',
    }
    const merged = mergeSavedRow(r, saved)
    expect(merged.pending.m01).toBe(500)
    expect(merged.pending.updated_at).toBe('2026-02-02T00:00:00Z')
  })
})

describe('validateNewTransaction', () => {
  const existing = [row({ cost_center: 'CC1', gl_account: '5211800030' })]

  it('rejects a CC outside the caller\'s Fill scope', () => {
    const result = validateNewTransaction({
      costCenter: 'CC9', glAccount: '5210400010', fillCostCenters: ['CC1'], glRef: GL_REF, existingRows: existing,
    })
    expect(result.ok).toBe(false)
  })

  it('accepts a special-GL account — it routes into its own subform on save, same as any special-GL row (Spec B path ข, jakkaritw 2026-08-05)', () => {
    const result = validateNewTransaction({
      costCenter: 'CC1', glAccount: '5211900030', fillCostCenters: ['CC1'], glRef: GL_REF, existingRows: existing,
    })
    expect(result.ok).toBe(true)
  })

  it('rejects a (CC, GL) pair that already has a visible row', () => {
    const result = validateNewTransaction({
      costCenter: 'CC1', glAccount: '5211800030', fillCostCenters: ['CC1'], glRef: GL_REF, existingRows: existing,
    })
    expect(result.ok).toBe(false)
  })

  it('accepts a valid new (CC, GL) combination', () => {
    const result = validateNewTransaction({
      costCenter: 'CC1', glAccount: '5210400010', fillCostCenters: ['CC1'], glRef: GL_REF, existingRows: existing,
    })
    expect(result.ok).toBe(true)
  })

  // "+ เพิ่ม Transaction" lock-awareness (2026-08-08 bug fix, ADR-0013 UI
  // parity): a Cost Center whose department is mid-approval/APPROVED must
  // be rejected here, BEFORE ever calling the API — same pattern as the
  // existing duplicate-row check above.
  it('rejects a Cost Center whose department is locked, naming the department in the Thai reason', () => {
    const result = validateNewTransaction({
      costCenter: 'CC1', glAccount: '5210400010', fillCostCenters: ['CC1'], glRef: GL_REF, existingRows: existing,
      lockedCostCenters: { CC1: 'Accounting' },
    })
    expect(result.ok).toBe(false)
    expect(result.errorTh).toContain('Accounting')
  })

  it('accepts a Cost Center that is NOT in the locked map, even when lockedCostCenters has other entries', () => {
    const result = validateNewTransaction({
      costCenter: 'CC1', glAccount: '5210400010', fillCostCenters: ['CC1'], glRef: GL_REF, existingRows: existing,
      lockedCostCenters: { CC9: 'Warehouse' },
    })
    expect(result.ok).toBe(true)
  })

  it('lockedCostCenters is optional — omitting it entirely behaves like "nothing is locked"', () => {
    const result = validateNewTransaction({
      costCenter: 'CC1', glAccount: '5210400010', fillCostCenters: ['CC1'], glRef: GL_REF, existingRows: existing,
    })
    expect(result.ok).toBe(true)
  })

  // 2026-08-08 3-state extension: a YEAR-wide lock, checked FIRST — ahead of
  // the Cost Center/GL picks, since nothing about the pick matters once the
  // whole fiscal_year is closed.
  it('rejects everything with the year-not-open reason when yearNotOpen is true, even a valid pick', () => {
    const result = validateNewTransaction({
      costCenter: 'CC1', glAccount: '5210400010', fillCostCenters: ['CC1'], glRef: GL_REF, existingRows: existing,
      yearNotOpen: true,
    })
    expect(result.ok).toBe(false)
    expect(result.errorTh).toBe(YEAR_NOT_OPEN_ADD_REASON_TH)
  })

  it('yearNotOpen is optional — omitting it entirely behaves like "the year is open"', () => {
    const result = validateNewTransaction({
      costCenter: 'CC1', glAccount: '5210400010', fillCostCenters: ['CC1'], glRef: GL_REF, existingRows: existing,
    })
    expect(result.ok).toBe(true)
  })
})

describe('isCostCenterLocked', () => {
  it('true when the cost center is a key in the locked map', () => {
    expect(isCostCenterLocked('CC1', { CC1: 'Accounting' })).toBe(true)
  })

  it('false when the cost center is absent from the locked map', () => {
    expect(isCostCenterLocked('CC1', { CC9: 'Warehouse' })).toBe(false)
    expect(isCostCenterLocked('CC1', {})).toBe(false)
  })
})

describe('lockedCostCenterDepartments', () => {
  const departmentRows: DepartmentRow[] = [
    { cost_center: 'CC1', department: 'Accounting', division: null, c_level: null },
    { cost_center: 'CC2', department: 'Warehouse', division: null, c_level: null },
  ]

  it('maps only the cost centers whose department is in the locked set', () => {
    const result = lockedCostCenterDepartments(['CC1', 'CC2'], departmentRows, new Set(['Accounting']))
    expect(result).toEqual({ CC1: 'Accounting' })
  })

  it('a cost center missing from departmentRows is treated as NOT locked (fail-open, mirrors the server\'s own unresolvable-department policy)', () => {
    const result = lockedCostCenterDepartments(['CC9'], departmentRows, new Set(['Accounting', 'Warehouse']))
    expect(result).toEqual({})
  })

  it('returns an empty object when nothing is locked', () => {
    const result = lockedCostCenterDepartments(['CC1', 'CC2'], departmentRows, new Set())
    expect(result).toEqual({})
  })
})

describe('buildNewRowPayload', () => {
  it('builds an all-zero create payload for a brand-new (CC, GL) row', () => {
    const payload = buildNewRowPayload('CC1', '5210400010', 2027)
    expect(payload.expected_updated_at).toBeNull()
    expect(payload.m01).toBe(0)
    expect(payload.cost_center).toBe('CC1')
    expect(payload.gl_account).toBe('5210400010')
    expect(payload.fiscal_year).toBe(2027)
  })
})

describe('groupChipClass', () => {
  it('maps each of the 6 special groups to its mockup color class', () => {
    expect(groupChipClass('Entertainment')).toBe('gl-yellow')
    expect(groupChipClass('Lease & Rental')).toBe('gl-pink')
    expect(groupChipClass('Professional & Legal Fee')).toBe('gl-purple')
    expect(groupChipClass('Public Relation & Donation')).toBe('gl-orange')
    expect(groupChipClass('Training & Seminar')).toBe('gl-blue')
    expect(groupChipClass('Travelling Expense')).toBe('gl-green')
  })

  it('returns an empty string for a non-special group (plain text, no chip)', () => {
    expect(groupChipClass('Office expenses')).toBe('')
    expect(groupChipClass('Uncategorized')).toBe('')
  })
})

describe('MONTH_LABELS', () => {
  it('maps every MonthKey to its real English month name (mockup MONTHS_EN)', () => {
    expect(MONTH_LABELS.m01).toBe('Jan')
    expect(MONTH_LABELS.m06).toBe('Jun')
    expect(MONTH_LABELS.m12).toBe('Dec')
  })
})

describe('nowMonthKey', () => {
  it('resolves the MonthKey for a given Date, 0-indexed (Jan -> m01, Dec -> m12)', () => {
    expect(nowMonthKey(new Date(2026, 0, 15))).toBe('m01')
    expect(nowMonthKey(new Date(2026, 11, 1))).toBe('m12')
  })

  it('defaults to the real system clock when no Date is passed', () => {
    const expected = `m${String(new Date().getMonth() + 1).padStart(2, '0')}`
    expect(nowMonthKey()).toBe(expected)
  })
})

describe('filterRows', () => {
  const rows = [
    row({ cost_center: 'CC1-North', gl_account: '5211800030' }),
    row({ cost_center: 'CC2-South', gl_account: '5211900030' }),
    row({ cost_center: 'CC1-North', gl_account: '6211800030' }),
  ]

  it('returns all rows unchanged when every filter is blank', () => {
    expect(filterRows(rows, GL_REF, BLANK_COLUMN_FILTERS)).toEqual(rows)
  })

  it('matches cost_center case-insensitively by substring', () => {
    const result = filterRows(rows, GL_REF, { ...BLANK_COLUMN_FILTERS, cc: 'north' })
    expect(result).toHaveLength(2)
    expect(result.every((r) => r.cost_center === 'CC1-North')).toBe(true)
  })

  it('matches gl_account by substring', () => {
    const result = filterRows(rows, GL_REF, { ...BLANK_COLUMN_FILTERS, gl: '5211900030' })
    expect(result).toEqual([rows[1]])
  })

  it('matches the resolved gl_group (from glMetaFor, not a field on BudgetRow)', () => {
    const result = filterRows(rows, GL_REF, { ...BLANK_COLUMN_FILTERS, glGroup: 'entertainment' })
    expect(result).toEqual([rows[1]])
  })

  it('combines multiple column filters with AND', () => {
    // Both rows[0] and rows[2] are CC1-North + "Office expenses" — only the
    // gl_account filter narrows it down to the single COST-side row.
    const result = filterRows(rows, GL_REF, { ...BLANK_COLUMN_FILTERS, cc: 'CC1', gl: '5211', glGroup: 'office' })
    expect(result).toEqual([rows[0]])
  })

  it('returns an empty array when nothing matches', () => {
    expect(filterRows(rows, GL_REF, { ...BLANK_COLUMN_FILTERS, cc: 'no-such-cc' })).toEqual([])
  })

  it('matches the pending-layer remark case-insensitively by substring; a null remark never matches a non-blank filter', () => {
    const remarked = [
      row({
        cost_center: 'CC1', gl_account: '5211800030',
        pending: { ...row({ cost_center: 'x', gl_account: 'x' }).pending, remark: 'อุปกรณ์สำนักงาน IT' },
      }),
      row({
        cost_center: 'CC2', gl_account: '6211800030',
        pending: { ...row({ cost_center: 'x', gl_account: 'x' }).pending, remark: 'Notebook lease' },
      }),
      row({ cost_center: 'CC3', gl_account: '6211900030' }), // remark: null
    ]
    expect(filterRows(remarked, GL_REF, { ...BLANK_COLUMN_FILTERS, remark: 'notebook' })).toEqual([remarked[1]])
    expect(filterRows(remarked, GL_REF, { ...BLANK_COLUMN_FILTERS, remark: 'สำนักงาน' })).toEqual([remarked[0]])
    expect(filterRows(remarked, GL_REF, { ...BLANK_COLUMN_FILTERS, remark: 'x' })).toEqual([])
  })

  describe('status filter — keeps rows whose MATCHED layer has any non-zero month', () => {
    const blank = row({ cost_center: 'x', gl_account: 'x' })
    const sapOnly = { ...blank, cost_center: 'CC-SAP', sap: { ...blank.sap, m01: 100 } }
    const approvedOnly = { ...blank, cost_center: 'CC-APP', board: { ...blank.board, m02: 50 } }
    const pendingOnly = {
      ...blank,
      cost_center: 'CC-PEN',
      pending: { ...blank.pending, m03: 25 },
    }
    const mixed = [sapOnly, approvedOnly, pendingOnly]

    it('"sap" keeps only rows with an actual value in the SAP layer', () => {
      expect(filterRows(mixed, GL_REF, { ...BLANK_COLUMN_FILTERS, status: 'sap' })).toEqual([sapOnly])
    })

    it('"งบ" matches the Approved layer label and keeps only rows with an approved value', () => {
      expect(filterRows(mixed, GL_REF, { ...BLANK_COLUMN_FILTERS, status: 'งบ' })).toEqual([approvedOnly])
    })

    it('"pending" keeps only rows with a pending value', () => {
      expect(filterRows(mixed, GL_REF, { ...BLANK_COLUMN_FILTERS, status: 'pending' })).toEqual([pendingOnly])
    })

    it('a query matching no layer label hides everything', () => {
      expect(filterRows(mixed, GL_REF, { ...BLANK_COLUMN_FILTERS, status: 'zzz' })).toEqual([])
    })

    it('blank status filter is a no-op', () => {
      expect(filterRows(mixed, GL_REF, BLANK_COLUMN_FILTERS)).toEqual(mixed)
    })
  })
})

describe('identityColSpan / fullRowColSpan / subtotalLabelColSpan (compact-mode "ซ่อนคอลัมน์" toggle)', () => {
  it('identityColSpan: 4 expanded (CC/GL/GL Group/Remark), 2 collapsed (CC/GL only)', () => {
    expect(identityColSpan(false)).toBe(4)
    expect(identityColSpan(true)).toBe(2)
  })

  it('fullRowColSpan: 19 expanded (4 identity + status + year-total + 12 months + action), 16 collapsed (2 identity + year-total + 12 months + action)', () => {
    expect(fullRowColSpan(false)).toBe(19)
    expect(fullRowColSpan(true)).toBe(16)
  })

  it('subtotalLabelColSpan: identityColSpan + 1 for the Status band expanded, no +1 collapsed', () => {
    expect(subtotalLabelColSpan(false)).toBe(5)
    expect(subtotalLabelColSpan(true)).toBe(2)
  })
})

describe('formatThb', () => {
  it('formats a number with thousands separators', () => {
    expect(formatThb(1234567)).toBe('1,234,567.00')
  })
  it('formats zero as a dash placeholder', () => {
    expect(formatThb(0)).toBe('—')
  })
  it('shows 2 decimal places on a whole number too (jakkaritw 2026-08-10)', () => {
    // Was '450,000'. The three layers of one row have to read the same way:
    // SAP 1,209,793.46 next to a typed Pending 9 was unreadable as a pair.
    expect(formatThb(450000)).toBe('450,000.00')
  })
  it('shows 2 decimal places when there is a fraction', () => {
    expect(formatThb(416.66)).toBe('416.66')
  })
  it('shows 2 decimal places with thousands separators when there is a fraction', () => {
    expect(formatThb(539118.41)).toBe('539,118.41')
  })
  it('pads a single-decimal fraction to 2 places', () => {
    expect(formatThb(100.5)).toBe('100.50')
  })
  it('pads a sub-1 fraction to 2 places', () => {
    expect(formatThb(0.4)).toBe('0.40')
  })
  it('rounds float noise away instead of showing it', () => {
    expect(formatThb(100.000001)).toBe('100.00')
  })
  it('formats a small typed amount the same way as a large SAP amount', () => {
    // The exact pair from jakkaritw's screenshot.
    expect(formatThb(9)).toBe('9.00')
    expect(formatThb(1209793.46)).toBe('1,209,793.46')
  })
})

describe('clampColumnWidth (UI-parity point 8c)', () => {
  it('passes a value already inside the range through unchanged', () => {
    expect(clampColumnWidth(200)).toBe(200)
  })
  it('floors a too-small width to the minimum (60)', () => {
    expect(clampColumnWidth(10)).toBe(60)
    expect(clampColumnWidth(-500)).toBe(60)
  })
  it('caps a too-large width to the maximum (800)', () => {
    expect(clampColumnWidth(5000)).toBe(800)
  })
})

describe('freezeOffsets (UI-parity point 8c)', () => {
  it('derives frz1..frz5 from the current widths with no DOM measurement', () => {
    expect(freezeOffsets({ cc: 130, gl: 150, glGroup: 150, remark: 170 })).toEqual({ frz1: 0, frz2: 130, frz3: 280, frz4: 430, frz5: 600 })
  })
  it('reflects a resized cc column in frz2, frz3, frz4 and frz5', () => {
    expect(freezeOffsets({ cc: 200, gl: 150, glGroup: 150, remark: 170 })).toEqual({ frz1: 0, frz2: 200, frz3: 350, frz4: 500, frz5: 670 })
  })
})

describe('loadStoredColumnWidths / persistColumnWidths (UI-parity point 8c)', () => {
  afterEach(() => {
    window.localStorage.clear()
  })

  it('returns the defaults when nothing is stored', () => {
    expect(loadStoredColumnWidths()).toEqual(DEFAULT_COLUMN_WIDTHS)
  })

  it('round-trips a persisted value', () => {
    persistColumnWidths({ cc: 200, gl: 175, glGroup: 160, remark: 210 })
    expect(loadStoredColumnWidths()).toEqual({ cc: 200, gl: 175, glGroup: 160, remark: 210 })
  })

  it('falls back to defaults for a corrupted stored value (never crashes)', () => {
    window.localStorage.setItem(COLUMN_WIDTHS_STORAGE_KEY, 'not json')
    expect(loadStoredColumnWidths()).toEqual(DEFAULT_COLUMN_WIDTHS)
  })

  it('clamps a stored value that is out of range', () => {
    window.localStorage.setItem(COLUMN_WIDTHS_STORAGE_KEY, JSON.stringify({ cc: 5000, gl: 10, glGroup: 150, remark: 9999 }))
    expect(loadStoredColumnWidths()).toEqual({ cc: 800, gl: 60, glGroup: 150, remark: 800 })
  })

  it('ignores a missing/non-numeric field and falls back to its default (incl. pre-Remark stored entries)', () => {
    window.localStorage.setItem(COLUMN_WIDTHS_STORAGE_KEY, JSON.stringify({ cc: 200 }))
    expect(loadStoredColumnWidths()).toEqual({
      cc: 200,
      gl: DEFAULT_COLUMN_WIDTHS.gl,
      glGroup: DEFAULT_COLUMN_WIDTHS.glGroup,
      remark: DEFAULT_COLUMN_WIDTHS.remark,
    })
  })

  it('does not throw when localStorage.setItem fails (guarded)', () => {
    const spy = vi.spyOn(window.localStorage.__proto__, 'setItem').mockImplementation(() => {
      throw new Error('quota exceeded')
    })
    expect(() => persistColumnWidths(DEFAULT_COLUMN_WIDTHS)).not.toThrow()
    spy.mockRestore()
  })
})

describe('hasStoredColumnWidthsOverride / clearStoredColumnWidths (UI-parity point 8d)', () => {
  afterEach(() => {
    window.localStorage.clear()
  })

  it('is false when nothing is stored', () => {
    expect(hasStoredColumnWidthsOverride()).toBe(false)
  })

  it('is true once ANY value (even a corrupted one) is stored — presence, not validity, marks an override', () => {
    window.localStorage.setItem(COLUMN_WIDTHS_STORAGE_KEY, 'not json')
    expect(hasStoredColumnWidthsOverride()).toBe(true)
  })

  it('becomes false again after clearStoredColumnWidths removes the entry', () => {
    persistColumnWidths({ cc: 200, gl: 175, glGroup: 160, remark: 210 })
    expect(hasStoredColumnWidthsOverride()).toBe(true)
    clearStoredColumnWidths()
    expect(hasStoredColumnWidthsOverride()).toBe(false)
  })

  it('does not throw when localStorage is unavailable (guarded)', () => {
    const getSpy = vi.spyOn(window.localStorage.__proto__, 'getItem').mockImplementation(() => {
      throw new Error('disabled')
    })
    expect(hasStoredColumnWidthsOverride()).toBe(false)
    getSpy.mockRestore()

    const removeSpy = vi.spyOn(window.localStorage.__proto__, 'removeItem').mockImplementation(() => {
      throw new Error('disabled')
    })
    expect(() => clearStoredColumnWidths()).not.toThrow()
    removeSpy.mockRestore()
  })
})

describe('fitColumnWidth (UI-parity point 8d — fit-to-content default)', () => {
  it('adds the padding allowance then clamps to the 60-800 range', () => {
    expect(fitColumnWidth(50)).toBe(82) // 50 + 32px padding, already inside 60-800
  })

  it('floors a tiny/zero raw width (e.g. jsdom, which never lays out real text) to COLUMN_WIDTH_MIN', () => {
    expect(fitColumnWidth(0)).toBe(COLUMN_WIDTH_MIN)
  })

  it('caps a huge raw width to the 800 maximum', () => {
    expect(fitColumnWidth(5000)).toBe(800)
  })

  it('rounds up a fractional raw width before adding padding', () => {
    expect(fitColumnWidth(100.2)).toBe(101 + 32)
  })
})

describe('selectMeasureCandidates (UI-parity point 8d)', () => {
  const glRef = [
    { gl_code: '5211900030', gl_group: 'Entertainment', gl_name: 'Ent COST', is_special: true },
    { gl_code: '5211800030', gl_group: 'Office expenses', gl_name: 'Office COST', is_special: false },
  ]

  it('dedups repeated cost_center/gl_account values across rows', () => {
    const rows = [
      row({ cost_center: 'CC1', gl_account: '5211800030' }),
      row({ cost_center: 'CC1', gl_account: '5211800030' }),
      row({ cost_center: 'CC2', gl_account: '5211900030' }),
    ]
    const candidates = selectMeasureCandidates(rows, glRef)
    expect(candidates.cc.sort()).toEqual(['CC1', 'CC2'])
    expect(candidates.gl.sort()).toEqual(['5211800030', '5211900030'])
  })

  it('resolves glGroup via glMetaFor (never a raw field on BudgetRow) and dedups group names', () => {
    const rows = [
      row({ cost_center: 'CC1', gl_account: '5211800030' }),
      row({ cost_center: 'CC2', gl_account: '5211900030' }),
    ]
    const candidates = selectMeasureCandidates(rows, glRef)
    expect(candidates.glGroup.sort()).toEqual(['Entertainment', 'Office expenses'])
  })

  it('caps cc/gl candidates to the given limit, keeping the LONGEST values (those drive the max width)', () => {
    const rows = [
      row({ cost_center: 'SHORT', gl_account: '5211800030' }),
      row({ cost_center: 'A-VERY-LONG-COST-CENTER-CODE', gl_account: '5211900030' }),
    ]
    const candidates = selectMeasureCandidates(rows, glRef, 1)
    expect(candidates.cc).toEqual(['A-VERY-LONG-COST-CENTER-CODE'])
  })

  it('returns empty candidate lists for an empty row set', () => {
    expect(selectMeasureCandidates([], glRef)).toEqual({ cc: [], gl: [], glName: [], glGroup: [], remark: [] })
  })

  it('collects pending remarks (skipping null) so the Remark column fits its longest text', () => {
    const rows = [
      row({
        cost_center: 'CC1', gl_account: '5211800030',
        pending: { ...row({ cost_center: 'x', gl_account: 'x' }).pending, remark: 'อุปกรณ์สำนักงาน IT' },
      }),
      row({
        cost_center: 'CC2', gl_account: '5211800030',
        pending: { ...row({ cost_center: 'x', gl_account: 'x' }).pending, remark: 'อุปกรณ์สำนักงาน IT' }, // dup — deduped
      }),
      row({ cost_center: 'CC3', gl_account: '5211900030' }), // remark: null — skipped
    ]
    expect(selectMeasureCandidates(rows, glRef).remark).toEqual(['อุปกรณ์สำนักงาน IT'])
  })

  it('collects GL names (the second line of the cell) so the column fits the wider of code or name', () => {
    const rows = [
      row({ cost_center: 'CC1', gl_account: '5211800030' }),
      row({ cost_center: 'CC2', gl_account: '5211900030' }),
    ]
    const candidates = selectMeasureCandidates(rows, glRef)
    // gl_name values come from glMetaFor, not a raw BudgetRow field.
    const names = candidates.glName.sort()
    expect(names.length).toBe(2)
    names.forEach((n) => expect(typeof n).toBe('string'))
    // never the literal "null" — rows whose GL has no name are skipped
    expect(candidates.glName).not.toContain('null')
    expect(candidates.glName).not.toContain(null)
  })
})

// ---------------------------------------------------------------------------
// ADR-0026 — incomplete SAP months (hidden = null from the server)
// ---------------------------------------------------------------------------

describe('ADR-0026 hidden SAP months', () => {
  const JAN_TO_MAR_ROW = row({
    cost_center: 'CC1',
    gl_account: '5211800030',
    sap: sapLayer({ m01: 100, m02: 50, m03: 25, m04: null, m05: null, m06: null, m07: null, m08: null, m09: null, m10: null, m11: null, m12: null }),
  })

  it('formats a hidden month as a muted en-dash, never as a zero', () => {
    expect(formatSapMonth(null)).toBe(HIDDEN_SAP_MONTH_MARK)
    expect(formatSapMonth(null)).not.toBe(formatThb(0))
    expect(formatSapMonth(0)).toBe(formatThb(0))
    expect(formatSapMonth(1234.5)).toBe('1,234.50')
  })

  it('reads the visible months off the payload (a hidden month is null for every row)', () => {
    expect(visibleSapMonths([JAN_TO_MAR_ROW])).toEqual(['m01', 'm02', 'm03'])
  })

  it('treats an empty grid as nothing-hidden (no coverage caveat to show)', () => {
    expect(visibleSapMonths([])).toHaveLength(12)
    expect(sapCoverageLabel([])).toBeNull()
  })

  it('labels the SAP total with its coverage, using the grid header month names', () => {
    expect(sapCoverageLabel([JAN_TO_MAR_ROW])).toBe('Jan–Mar')
  })

  it('labels a single visible month without a range dash', () => {
    const janOnly = row({
      cost_center: 'CC1', gl_account: '5211800030',
      sap: sapLayer({ m01: 5, m02: null, m03: null, m04: null, m05: null, m06: null, m07: null, m08: null, m09: null, m10: null, m11: null, m12: null }),
    })
    expect(sapCoverageLabel([janOnly])).toBe('Jan')
  })

  it('adds no coverage caveat when all 12 months are shown', () => {
    expect(sapCoverageLabel([row({ cost_center: 'CC1', gl_account: '5211800030', sap: sapLayer({ m01: 1 }) })])).toBeNull()
  })

  it('keeps a hidden month null in the SAP subtotal instead of summing it as zero', () => {
    const totals = sectionTotals([JAN_TO_MAR_ROW, JAN_TO_MAR_ROW])
    expect(totals.sap.m01).toBe(200)
    expect(totals.sap.m04).toBeNull()
    expect(totals.sap.total_year).toBe(350)
  })

  it('never nulls the Approved or Pending subtotals (SAP-layer rule only)', () => {
    const r = row({
      cost_center: 'CC1', gl_account: '5211800030',
      sap: sapLayer({ m04: null }),
      board: { ...blankLayer({ m04: 400, total_year: 400 }), gl_name: null, gl_group: null, c_level: null, division: null, department: null },
      pending: { ...row({ cost_center: 'x', gl_account: 'y' }).pending, m04: 700, total_year: 700 },
    })
    const totals = sectionTotals([r])
    expect(totals.board.m04).toBe(400)
    expect(totals.pending.m04).toBe(700)
  })

  it('blocks delete for a row whose only SAP history sits in a hidden month', () => {
    const meta = { gl_group: 'Office expenses', gl_name: 'x', is_special: false, in_master: true }
    const aprilOnly = row({
      cost_center: 'CC1', gl_account: '5211800030', editable: true,
      sap: sapLayer({ m01: 0, m02: 0, m03: 0, m04: null, m05: null, m06: null, m07: null, m08: null, m09: null, m10: null, m11: null, m12: null, has_actuals: true }),
      pending: { ...row({ cost_center: 'x', gl_account: 'y' }).pending, updated_at: '2026-01-01T00:00:00Z' },
    })
    expect(isDeletableRow(aprilOnly, meta)).toBe(false)
  })

  it('still allows delete for a web-added row with no SAP history at all', () => {
    const meta = { gl_group: 'Office expenses', gl_name: 'x', is_special: false, in_master: true }
    const webAdded = row({
      cost_center: 'CC1', gl_account: '5211800030', editable: true,
      sap: sapLayer({ m04: null, m05: null, m06: null, m07: null, m08: null, m09: null, m10: null, m11: null, m12: null }),
      pending: { ...row({ cost_center: 'x', gl_account: 'y' }).pending, updated_at: '2026-01-01T00:00:00Z' },
    })
    expect(webAdded.sap.has_actuals).toBe(false)
    expect(isDeletableRow(webAdded, meta)).toBe(true)
  })

  it('formats the watermark as a Thai short date with a Buddhist-era year', () => {
    expect(formatThaiShortDate('2026-04-29')).toBe('29 เม.ย. 69')
    expect(formatThaiShortDate('2026-12-31')).toBe('31 ธ.ค. 69')
    expect(formatThaiShortDate('2027-01-23')).toBe('23 ม.ค. 70')
  })

  it('writes one freshness line naming the last complete month and the keyed-through date', () => {
    const line = sapFreshnessLine({
      fiscal_year: 2026,
      watermark_date: '2026-04-29',
      visible_months: [1, 2, 3],
      hidden_months: [4, 5, 6, 7, 8, 9, 10, 11, 12],
    })
    expect(line).toContain('ครบถึงเดือน 3/2026')
    expect(line).toContain('29 เม.ย. 69')
    expect(line).toContain('4–12/2026')
  })

  it('says so plainly when the year is complete', () => {
    const line = sapFreshnessLine({
      fiscal_year: 2025,
      watermark_date: '2026-04-29',
      visible_months: [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12],
      hidden_months: [],
    })
    expect(line).toContain('ครบทั้ง 12 เดือน')
    expect(line).not.toContain('ยังไม่แสดง')
  })

  it('says so plainly when not one month is complete yet', () => {
    const line = sapFreshnessLine({
      fiscal_year: 2026,
      watermark_date: '2026-01-05',
      visible_months: [],
      hidden_months: [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12],
    })
    expect(line).toContain('ยังไม่มีเดือน')
    expect(line).toContain('5 ม.ค. 69')
  })
})
