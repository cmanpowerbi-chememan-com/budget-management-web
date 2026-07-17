import { describe, expect, it } from 'vitest'
import type { GlAccount, PendingRowState } from '../api/types'
import {
  applyMonthEdit,
  buildNewRowPayload,
  buildSavePayload,
  formatThb,
  glMetaFor,
  groupAndSortBySide,
  groupChipClass,
  isEditableCell,
  mergeSavedRow,
  sectionTotals,
  sideOfGl,
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

describe('formatThb', () => {
  it('formats a number with thousands separators', () => {
    expect(formatThb(1234567)).toBe('1,234,567')
  })
  it('formats zero as a dash placeholder', () => {
    expect(formatThb(0)).toBe('—')
  })
})
