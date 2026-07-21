import { afterEach, describe, expect, it, vi } from 'vitest'
import type { GlAccount, PendingRowState } from '../api/types'
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
  formatThb,
  freezeOffsets,
  fullRowColSpan,
  glMetaFor,
  groupAndSortBySide,
  groupChipClass,
  hasStoredColumnWidthsOverride,
  identityColSpan,
  isDeletableRow,
  isEditableCell,
  loadStoredColumnWidths,
  mergeSavedRow,
  MONTH_LABELS,
  nowMonthKey,
  persistColumnWidths,
  sectionTotals,
  selectMeasureCandidates,
  sideOfGl,
  subtotalLabelColSpan,
  validateNewTransaction,
} from './model'
import { makeRow as row } from './testUtils'

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

  it('rejects a special-GL account (routes through a subform, not a plain cell — A9)', () => {
    const result = validateNewTransaction({
      costCenter: 'CC1', glAccount: '5211900030', fillCostCenters: ['CC1'], glRef: GL_REF, existingRows: existing,
    })
    expect(result.ok).toBe(false)
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

  it('fullRowColSpan: 18 expanded (4 identity + status + 12 months + action), 15 collapsed (2 identity + 12 months + action)', () => {
    expect(fullRowColSpan(false)).toBe(18)
    expect(fullRowColSpan(true)).toBe(15)
  })

  it('subtotalLabelColSpan: identityColSpan + 1 for the Status band expanded, no +1 collapsed', () => {
    expect(subtotalLabelColSpan(false)).toBe(5)
    expect(subtotalLabelColSpan(true)).toBe(2)
  })
})

describe('formatThb', () => {
  it('formats a number with thousands separators', () => {
    expect(formatThb(1234567)).toBe('1,234,567')
  })
  it('formats zero as a dash placeholder', () => {
    expect(formatThb(0)).toBe('—')
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
