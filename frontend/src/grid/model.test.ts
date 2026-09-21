import { afterEach, describe, expect, it, vi } from 'vitest'
import type { GlAccount, PendingRowState } from '../api/types'
import {
  addTransactionBlockedReasonTh,
  admitRows,
  applyMonthEdit,
  BLANK_COLUMN_FILTERS,
  buildNewRowPayload,
  buildSavePayload,
  clampColumnWidth,
  clearStoredColumnWidths,
  COLUMN_WIDTH_MIN,
  COLUMN_WIDTHS_STORAGE_KEY,
  CC_RESTRICTED_GL_REASON_TH,
  CC_RESTRICTED_GLS,
  DEFAULT_COLUMN_WIDTHS,
  DEPARTMENT_UNKNOWN_ADD_REASON_TH,
  emptyGridMessage,
  filterRows,
  fitColumnWidth,
  formatChipDate,
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
  isGlPickableForCostCenter,
  loadStoredColumnWidths,
  lockedAddReasonTh,
  lockReasonTooltipTh,
  LOCK_STATUS_UNAVAILABLE_ADD_REASON_TH,
  mergeSavedRow,
  MONTH_KEYS,
  MONTH_LABELS,
  noFillCostCentersAddReasonTh,
  nowMonthKey,
  persistColumnWidths,
  pendingAmountNoticeTh,
  roundPendingAmount,
  sanitizeMonthInput,
  sapFreshnessLine,
  sectionTotals,
  selectMeasureCandidates,
  sideOfGl,
  subtotalLabelColSpan,
  validateNewTransaction,
  YEAR_NOT_OPEN_ADD_REASON_TH,
} from './model'
import { makeRow as row, sapLayer } from './testUtils'

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
  it('keeps digits only', () => {
    expect(sanitizeMonthInput('51000')).toBe('51000')
  })

  it('strips a decimal point — no decimals allowed (2026-08-19, supersedes 7ba8f49)', () => {
    expect(sanitizeMonthInput('51000.50')).toBe('5100050')
  })

  it('strips every dot when multiple are typed (1.2.3 -> 123)', () => {
    expect(sanitizeMonthInput('1.2.3')).toBe('123')
  })

  it('strips letters', () => {
    expect(sanitizeMonthInput('1a2b3')).toBe('123')
  })

  it('strips a leading minus sign — negatives are not allowed', () => {
    expect(sanitizeMonthInput('-50')).toBe('50')
  })

  it('a lone "." sanitizes to an empty string (caller resolves it to 0 at commit time)', () => {
    expect(sanitizeMonthInput('.')).toBe('')
  })

  it('does not round or clamp — that is the commit-time job of roundPendingAmount', () => {
    expect(sanitizeMonthInput('123456789')).toBe('123456789')
  })
})

describe('roundPendingAmount — jakkaritw 2026-08-19: round to nearest 100, half-up, capped at 100,000,000', () => {
  it.each([
    // [typed, expected] — half-up: <50 rounds down, >=50 rounds up (jakkaritw: "50 พอดี ปัดขึ้น")
    [123, 100],
    [138, 100],
    [146, 100],
    [149, 100],
    [150, 200], // the named half-up boundary — must round UP, not down
    [158, 200],
    [179, 200],
    [186, 200],
  ])('%i -> %i', (typed, expected) => {
    expect(roundPendingAmount(typed)).toBe(expected)
  })

  it.each([
    [5, 0],
    [30, 0],
    [49, 0],
    [50, 100], // the units/tens digits jakkaritw named as unreachable (5,6,7 / 10,20,30) land on 0 by design
  ])('sub-100 value %i -> %i', (typed, expected) => {
    expect(roundPendingAmount(typed)).toBe(expected)
  })

  it('0 stays 0', () => {
    expect(roundPendingAmount(0)).toBe(0)
  })

  it('a round-hundred value is unchanged', () => {
    expect(roundPendingAmount(1200)).toBe(1200)
  })

  it('proves rounding happens on commit, not per keystroke: 1234 -> 1200', () => {
    expect(roundPendingAmount(1234)).toBe(1200)
  })

  it('accepts exactly the 100,000,000 cap', () => {
    expect(roundPendingAmount(100_000_000)).toBe(100_000_000)
  })

  it('a value that rounds down to exactly the cap is accepted, not clamped (100,000,001 -> 100,000,000)', () => {
    // 1 is < 50 of the next hundred, so half-up rounding alone lands this
    // exactly on the cap — the clamp is never actually invoked for this
    // specific value named in the task brief. See the next test for a case
    // that genuinely exercises the clamp.
    expect(roundPendingAmount(100_000_001)).toBe(100_000_000)
  })

  it('a value that rounds UP past the cap is clamped to 100,000,000 (100,000,060 -> 100,000,100 -> clamped)', () => {
    expect(roundPendingAmount(100_000_060)).toBe(100_000_000)
  })

  it('a value far over the cap is still clamped, not rejected client-side', () => {
    expect(roundPendingAmount(999_999_999)).toBe(100_000_000)
  })
})

describe('pendingAmountNoticeTh — jakkaritw 2026-08-29: say what the commit-time correction did', () => {
  it('is silent when the typed number survived untouched (the overwhelmingly common case)', () => {
    expect(pendingAmountNoticeTh(1200, 1200)).toBeNull()
    expect(pendingAmountNoticeTh(0, 0)).toBeNull()
  })

  it('names the rounding, quoting both the typed and the committed number', () => {
    expect(pendingAmountNoticeTh(146, 100)).toBe('กรอก 146 · ระบบปรับเป็น 100 (ปัดเศษเป็นหลักร้อย)')
  })

  it('covers the half-up direction too — rounding UP is just as surprising as down', () => {
    expect(pendingAmountNoticeTh(150, 200)).toBe('กรอก 150 · ระบบปรับเป็น 200 (ปัดเศษเป็นหลักร้อย)')
  })

  it('a sub-100 value landing on 0 gets its OWN message — losing the amount is not the same surprise as rounding it', () => {
    expect(pendingAmountNoticeTh(30, 0)).toBe('กรอก 30 ซึ่งต่ำกว่า 100 · ระบบบันทึกเป็น 0 (กรอกได้ตั้งแต่ 100 ขึ้นไป)')
  })

  it('the cap clamp names the cap, with both numbers grouped for readability', () => {
    expect(pendingAmountNoticeTh(999_999_999, 100_000_000)).toBe(
      'กรอก 999,999,999 ซึ่งเกินเพดาน 100 ล้านต่อช่อง · ระบบบันทึกเป็น 100,000,000',
    )
  })

  it('never renders a committed 0 as formatThb would (em-dash) — the user must see their own keystrokes', () => {
    expect(pendingAmountNoticeTh(5, 0)).toContain('กรอก 5 ')
  })

  it('reports every rounding decision roundPendingAmount actually makes, and only those', () => {
    for (const typed of [1, 49, 50, 99, 123, 150, 1234, 100_000_060]) {
      const committed = roundPendingAmount(typed)
      const notice = pendingAmountNoticeTh(typed, committed)
      expect(typed === committed ? notice === null : typeof notice === 'string').toBe(true)
    }
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

  // Issue #13, decision F (2026-09-17): a picked Cost Center AFFIRMATIVELY
  // known to belong to a DIFFERENT ฝ่าย than `selectedDepartment` is rejected
  // here, BEFORE ever calling the API — same pattern as the existing
  // duplicate-row check above. Defense-in-depth: the combobox itself is
  // already scoped to the selected ฝ่าย's own Cost Centers.
  it('rejects a Cost Center known (via departments) to belong to a different ฝ่าย, naming the selected ฝ่าย in the Thai reason', () => {
    const result = validateNewTransaction({
      costCenter: 'CC1', glAccount: '5210400010', fillCostCenters: ['CC1'], glRef: GL_REF, existingRows: existing,
      selectedDepartment: 'Accounting',
      departments: [{ cost_center: 'CC1', department: 'IT', division: null, c_level: null }],
    })
    expect(result.ok).toBe(false)
    expect(result.errorTh).toContain('Accounting')
  })

  it('accepts a Cost Center known to belong to the selected ฝ่าย', () => {
    const result = validateNewTransaction({
      costCenter: 'CC1', glAccount: '5210400010', fillCostCenters: ['CC1'], glRef: GL_REF, existingRows: existing,
      selectedDepartment: 'Accounting',
      departments: [{ cost_center: 'CC1', department: 'Accounting', division: null, c_level: null }],
    })
    expect(result.ok).toBe(true)
  })

  it('accepts a Cost Center absent from departments — unknown is never treated as a mismatch', () => {
    const result = validateNewTransaction({
      costCenter: 'CC1', glAccount: '5210400010', fillCostCenters: ['CC1'], glRef: GL_REF, existingRows: existing,
      selectedDepartment: 'Accounting',
      departments: [],
    })
    expect(result.ok).toBe(true)
  })

  it('selectedDepartment is optional — omitting it entirely skips the ฝ่าย check', () => {
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

  // Gate finding LOW-4: a GL code that vanished from `dbo.gl_group` between the
  // pick and the save (glRef refetches on the admin-hat toggle) used to fall
  // through EVERY remaining check — restriction and duplicate alike — and reach
  // the API.
  it('rejects a picked GL that is no longer in the GL master', () => {
    const result = validateNewTransaction({
      costCenter: 'CC1', glAccount: '9999999999', fillCostCenters: ['CC1'], glRef: GL_REF, existingRows: existing,
    })
    expect(result.ok).toBe(false)
    expect(result.errorTh).toBe('GL นี้ไม่มีอยู่ในรายการ GL แล้ว กรุณาเลือกใหม่')
  })

  // Cost-center-restricted GLs (jakkaritw 2026-09-17/18 — supersedes the
  // department-keyed rule shipped 2026-08-29). The picker already hides
  // these, so this check only catches a STALE selection (pick an eligible
  // cost center + the GL, then switch to an ineligible one). Keyed on the
  // Cost Center directly now, so `departments` plays no part in this rule.
  describe('cost-center-restricted GLs (GL 6210100150)', () => {
    const glRef: GlAccount[] = [
      ...GL_REF,
      { gl_code: '6210100150', gl_group: 'Training & Seminar', gl_name: 'ค่าอบรมและสัมมนา - ค่าธรรมเนียม', is_special: true, edit_by: 'user' },
    ]
    const fillCostCenters = ['10OS010000', '10HR012000', '10HR011000', '10AC012000']

    it('rejects the GL on 10HR011000 — the cost center that lost it', () => {
      const result = validateNewTransaction({
        costCenter: '10HR011000', glAccount: '6210100150', fillCostCenters, glRef, existingRows: [],
      })
      expect(result.ok).toBe(false)
      expect(result.errorTh).toBe('GL ค่าอบรมและสัมมนา ใช้ได้เฉพาะ Cost Center 10OS010000 และ 10HR012000')
      expect(result.errorTh).toBe(CC_RESTRICTED_GL_REASON_TH)
      expect(result.errorTh).toContain('10OS010000')
      expect(result.errorTh).toContain('10HR012000')
    })

    it('accepts the GL on 10OS010000 — the cost center that gained it', () => {
      const result = validateNewTransaction({
        costCenter: '10OS010000', glAccount: '6210100150', fillCostCenters, glRef, existingRows: [],
      })
      expect(result.ok).toBe(true)
    })

    it('accepts the GL on 10HR012000 — unchanged from before', () => {
      const result = validateNewTransaction({
        costCenter: '10HR012000', glAccount: '6210100150', fillCostCenters, glRef, existingRows: [],
      })
      expect(result.ok).toBe(true)
    })

    it('an admin may pick the GL on 10HR011000', () => {
      const result = validateNewTransaction({
        costCenter: '10HR011000', glAccount: '6210100150', fillCostCenters, glRef, existingRows: [],
        isAdmin: true,
      })
      expect(result.ok).toBe(true)
    })

    it('leaves every GL outside the table alone on the very same cost center', () => {
      const result = validateNewTransaction({
        costCenter: '10HR011000', glAccount: '5210400010', fillCostCenters, glRef, existingRows: [],
      })
      expect(result.ok).toBe(true)
    })
  })
})

describe('isGlPickableForCostCenter', () => {
  const seminarGl: GlAccount = {
    gl_code: '6210100150', gl_group: 'Training & Seminar', gl_name: 'ค่าอบรมและสัมมนา - ค่าธรรมเนียม', is_special: true, edit_by: 'user',
  }
  const plainGl: GlAccount = { gl_code: '5211800030', gl_group: 'Office expenses', gl_name: 'Office COST', is_special: false }

  it('keys the restriction on GL code 6210100150, to exactly 10OS010000 and 10HR012000', () => {
    expect(CC_RESTRICTED_GLS['6210100150']).toEqual(['10OS010000', '10HR012000'])
  })

  it('true for the restricted GL on 10OS010000', () => {
    expect(isGlPickableForCostCenter(seminarGl, '10OS010000')).toBe(true)
  })

  it('true for the restricted GL on 10HR012000', () => {
    expect(isGlPickableForCostCenter(seminarGl, '10HR012000')).toBe(true)
  })

  it('false for the restricted GL on 10HR011000 — lost it under the new rule', () => {
    expect(isGlPickableForCostCenter(seminarGl, '10HR011000')).toBe(false)
  })

  it('false for the restricted GL on any other cost center', () => {
    expect(isGlPickableForCostCenter(seminarGl, '10AC012000')).toBe(false)
  })

  it('false for the restricted GL while no cost center is picked yet — it must never appear and then vanish', () => {
    expect(isGlPickableForCostCenter(seminarGl, '')).toBe(false)
  })

  it('true for the restricted GL when the caller is an admin, on any cost center', () => {
    expect(isGlPickableForCostCenter(seminarGl, '10HR011000', true)).toBe(true)
    expect(isGlPickableForCostCenter(seminarGl, '', true)).toBe(true)
  })

  it('true for a GL outside the table in every case — no cost center, any cost center', () => {
    expect(isGlPickableForCostCenter(plainGl, '')).toBe(true)
    expect(isGlPickableForCostCenter(plainGl, '10HR011000')).toBe(true)
  })

  it('true for a GL with no group at all (never crashes on a null gl_group)', () => {
    const noGroup: GlAccount = { gl_code: '9999999999', gl_group: null, gl_name: null, is_special: false }
    expect(isGlPickableForCostCenter(noGroup, '10AC012000')).toBe(true)
  })
})

// Issue #13, decision E (2026-09-17): the ONE row-admission point.
describe('admitRows', () => {
  it('selectedDepartment=null admits every row unchanged (admin-wide "all departments" view)', () => {
    const rows = [row({ cost_center: 'CC1', gl_account: 'GL1', department: 'Accounting' }), row({ cost_center: 'CC2', gl_account: 'GL2', department: 'IT' })]
    expect(admitRows(rows, null)).toEqual(rows)
  })

  it('keeps only rows whose department matches the selected one', () => {
    const rows = [
      row({ cost_center: 'CC1', gl_account: 'GL1', department: 'Accounting' }),
      row({ cost_center: 'CC2', gl_account: 'GL2', department: 'IT' }),
    ]
    const result = admitRows(rows, 'Accounting')
    expect(result.map((r) => r.cost_center)).toEqual(['CC1'])
  })

  it('drops a row whose department is null when a specific ฝ่าย is selected', () => {
    const rows = [row({ cost_center: 'CC1', gl_account: 'GL1', department: null })]
    expect(admitRows(rows, 'Accounting')).toEqual([])
  })
})

describe('lockReasonTooltipTh', () => {
  it('returns undefined for lock_reason "none" (editable — no tooltip)', () => {
    expect(lockReasonTooltipTh({ lock_reason: 'none', department: 'Accounting' })).toBeUndefined()
  })

  it('names the department for "department_locked"', () => {
    const text = lockReasonTooltipTh({ lock_reason: 'department_locked', department: 'Accounting' })
    expect(text).toContain('Accounting')
  })

  it('falls back to a generic department phrase when department is null', () => {
    const text = lockReasonTooltipTh({ lock_reason: 'department_locked', department: null })
    expect(text).toBeTruthy()
  })

  it('reuses the year-not-open copy for "year_not_open"', () => {
    expect(lockReasonTooltipTh({ lock_reason: 'year_not_open', department: null })).toBe(YEAR_NOT_OPEN_ADD_REASON_TH)
  })

  it('returns a short read-only sentence for "not_in_fill_scope"', () => {
    const text = lockReasonTooltipTh({ lock_reason: 'not_in_fill_scope', department: null })
    expect(text).toBeTruthy()
  })
})

describe('noFillCostCentersAddReasonTh', () => {
  // MED gate finding (2026-09-21): renamed from `seeOnlyAddReasonTh` — the
  // old "คุณมีสิทธิ์ดูอย่างเดียว" (you have view-only rights) wording is false
  // for a dual-role admin viewing a foreign ฝ่าย with admin mode ON (they ARE
  // an admin, just with no personal Fill Cost Center there) and for a ฝ่าย
  // simply missing from cc dept.xlsx (a master-data gap, not a rights
  // question). Reworded in Cost Center terms, which is true for every case.
  it('names the department in Cost Center terms, asserting nothing about the caller\'s role', () => {
    const text = noFillCostCentersAddReasonTh('Accounting')
    expect(text).toContain('Accounting')
    expect(text).toContain('Cost Center')
    expect(text).not.toContain('สิทธิ์')
    expect(text).not.toContain('ดูอย่างเดียว')
  })
})

describe('addTransactionBlockedReasonTh (issue #32 — the Add button + emptyGridMessage share this)', () => {
  const OPEN: Parameters<typeof addTransactionBlockedReasonTh>[0] = {
    yearNotOpen: false,
    departmentUnknown: false,
    lockStatusUnavailable: false,
    departmentLocked: false,
    department: 'Accounting',
    hasFillCostCenters: true,
  }

  it('returns null (nothing blocks the click) when every condition is open', () => {
    expect(addTransactionBlockedReasonTh(OPEN)).toBeNull()
  })

  it('yearNotOpen wins over every other reason', () => {
    expect(
      addTransactionBlockedReasonTh({
        ...OPEN, yearNotOpen: true, departmentUnknown: true, departmentLocked: true, hasFillCostCenters: false,
      }),
    ).toBe(YEAR_NOT_OPEN_ADD_REASON_TH)
  })

  it('departmentUnknown wins over lockStatusUnavailable/departmentLocked/hasFillCostCenters', () => {
    expect(
      addTransactionBlockedReasonTh({
        ...OPEN, departmentUnknown: true, lockStatusUnavailable: true, departmentLocked: true, hasFillCostCenters: false,
      }),
    ).toBe(DEPARTMENT_UNKNOWN_ADD_REASON_TH)
  })

  it('lockStatusUnavailable wins over departmentLocked/hasFillCostCenters', () => {
    expect(
      addTransactionBlockedReasonTh({ ...OPEN, lockStatusUnavailable: true, departmentLocked: true, hasFillCostCenters: false }),
    ).toBe(LOCK_STATUS_UNAVAILABLE_ADD_REASON_TH)
  })

  it('departmentLocked wins over hasFillCostCenters, naming the department', () => {
    expect(
      addTransactionBlockedReasonTh({ ...OPEN, departmentLocked: true, hasFillCostCenters: false }),
    ).toBe(lockedAddReasonTh('Accounting'))
  })

  it('departmentLocked falls back to a generic department phrase when department is null', () => {
    expect(
      addTransactionBlockedReasonTh({ ...OPEN, department: null, departmentLocked: true }),
    ).toBe(lockedAddReasonTh('ฝ่ายนี้'))
  })

  it('!hasFillCostCenters is the last-resort reason, naming the department', () => {
    expect(
      addTransactionBlockedReasonTh({ ...OPEN, hasFillCostCenters: false }),
    ).toBe(noFillCostCentersAddReasonTh('Accounting'))
  })

  // HIGH gate finding: before `GET /scope/departments` resolves, `department`
  // is still `null` and `departmentUnknown` is deliberately `false` (it is
  // gated on `deptResolved`, which has not flipped yet) — a pre-fix reading
  // of `!hasFillCostCenters` alone fell all the way through to the See-only
  // reason for the 2-3s of every mount, mislabeling every caller as
  // view-only. The branch must require a RESOLVED department, same as
  // `departmentUnknown` already does, so this window returns null instead.
  it('mirrors the null-department precedence: pre-resolve (department null, every flag false incl. hasFillCostCenters) blocks nothing yet', () => {
    expect(
      addTransactionBlockedReasonTh({
        yearNotOpen: false,
        departmentUnknown: false,
        lockStatusUnavailable: false,
        departmentLocked: false,
        department: null,
        hasFillCostCenters: false,
      }),
    ).toBeNull()
  })
})

describe('emptyGridMessage (issue #32 item 1 — the empty-grid states the real situation)', () => {
  it('can-add: names the fiscal year and hints at "+ เพิ่ม Transaction"', () => {
    const result = emptyGridMessage({
      fiscalYear: 2027, department: 'Accounting', canAddTransaction: true, addBlockedReasonTh: null,
    })
    expect(result.title).toBe('ฝ่ายนี้ยังไม่มีรายการงบประมาณปี 2027')
    expect(result.hint).toContain('เพิ่ม Transaction')
  })

  it('cannot-add: the hint is the SAME reason the disabled Add button already shows', () => {
    const reason = lockedAddReasonTh('Accounting')
    const result = emptyGridMessage({
      fiscalYear: 2027, department: 'Accounting', canAddTransaction: false, addBlockedReasonTh: reason,
    })
    expect(result.title).toBe('ฝ่ายนี้ยังไม่มีรายการงบประมาณปี 2027')
    expect(result.hint).toBe(reason)
  })

  it('year-not-open: title always renders, hint carries the year-wide reason', () => {
    const result = emptyGridMessage({
      fiscalYear: 2027, department: 'Accounting', canAddTransaction: false, addBlockedReasonTh: YEAR_NOT_OPEN_ADD_REASON_TH,
    })
    expect(result.title).toBeTruthy()
    expect(result.hint).toBe(YEAR_NOT_OPEN_ADD_REASON_TH)
  })

  it('department-locked: hint names the ฝ่าย that is mid-approval/approved', () => {
    const result = emptyGridMessage({
      fiscalYear: 2027, department: 'Accounting', canAddTransaction: false, addBlockedReasonTh: lockedAddReasonTh('Accounting'),
    })
    expect(result.hint).toContain('Accounting')
  })

  it('no Fill Cost Center: hint says so in Cost Center terms, never the Add-button call to action', () => {
    const result = emptyGridMessage({
      fiscalYear: 2027, department: 'Accounting', canAddTransaction: false, addBlockedReasonTh: noFillCostCentersAddReasonTh('Accounting'),
    })
    expect(result.hint).toContain('Cost Center')
    expect(result.hint).not.toContain('เพิ่ม Transaction')
  })

  it('is total: cannot-add with no resolved reason (defensive edge case) still returns a title and simply omits the hint', () => {
    const result = emptyGridMessage({
      fiscalYear: 2027, department: 'Accounting', canAddTransaction: false, addBlockedReasonTh: null,
    })
    expect(result.title).toBeTruthy()
    expect(result.hint).toBeUndefined()
  })

  it('never learns the department name into the title — the ฝ่าย picker already shows it', () => {
    const withDept = emptyGridMessage({ fiscalYear: 2027, department: 'Accounting', canAddTransaction: true, addBlockedReasonTh: null })
    const withoutDept = emptyGridMessage({ fiscalYear: 2027, department: null, canAddTransaction: true, addBlockedReasonTh: null })
    expect(withDept.title).toBe(withoutDept.title)
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
// ADR-0030 — SAP actuals shown as-is (supersedes ADR-0026's month mask)
// ---------------------------------------------------------------------------

describe('SAP actuals shown as-is (ADR-0030)', () => {
  it('formats the watermark as a short English date with a 2-digit Gregorian year', () => {
    expect(formatChipDate('2026-04-29')).toBe('29 Apr 26')
    expect(formatChipDate('2026-12-31')).toBe('31 Dec 26')
    expect(formatChipDate('2027-01-23')).toBe('23 Jan 27')
  })

  it('does not pad a single-digit day, and zero-pads a year ending before 10 (2005 -> 05)', () => {
    expect(formatChipDate('2026-09-05')).toBe('5 Sep 26')
    expect(formatChipDate('2005-01-01')).toBe('1 Jan 05')
  })

  describe('sapFreshnessLine — 3 states, all decided by the backend', () => {
    it('healthy: the plain keyed-through date, no warning', () => {
      const line = sapFreshnessLine({ fiscal_year: 2026, watermark_date: '2026-09-11', days_behind: 1, is_stale: false })
      expect(line).toEqual({ text: 'ข้อมูลอัปเดตล่าสุด 11 Sep 26', isWarn: false })
    })

    it('stale: warns and marks the date stale, following the server verdict — never computed here', () => {
      const line = sapFreshnessLine({ fiscal_year: 2026, watermark_date: '2026-09-11', days_behind: 3, is_stale: true })
      expect(line).toEqual({ text: '⚠ ข้อมูลอัปเดตล่าสุด 11 Sep 26', isWarn: true })
    })

    it('unknown: no date at all warns with a different message, not a blank chip', () => {
      const line = sapFreshnessLine({ fiscal_year: 2026, watermark_date: null, days_behind: null, is_stale: false })
      expect(line).toEqual({ text: '⚠ ไม่ทราบวันที่ข้อมูล', isWarn: true })
    })

    it('a null watermark wins over an is_stale flag — there is no date to qualify either way', () => {
      const line = sapFreshnessLine({ fiscal_year: 2026, watermark_date: null, days_behind: null, is_stale: true })
      expect(line).toEqual({ text: '⚠ ไม่ทราบวันที่ข้อมูล', isWarn: true })
    })

    it('isWarn is data, not a string to re-parse — a caller never string-sniffs the text for "⚠"', () => {
      const healthy = sapFreshnessLine({ fiscal_year: 2026, watermark_date: '2026-09-11', days_behind: 1, is_stale: false })
      const stale = sapFreshnessLine({ fiscal_year: 2026, watermark_date: '2026-09-11', days_behind: 3, is_stale: true })
      expect(healthy.isWarn).toBe(false)
      expect(stale.isWarn).toBe(true)
    })
  })

  it('sums every SAP month as a plain number, never null', () => {
    const r = row({ cost_center: 'CC1', gl_account: '5211800030', sap: sapLayer({ m01: 100, m02: 50, m03: 25 }) })
    const totals = sectionTotals([r, r])
    expect(totals.sap.m01).toBe(200)
    expect(totals.sap.m04).toBe(0)
    expect(totals.sap.total_year).toBe(350)
    MONTH_KEYS.forEach((m) => expect(typeof totals.sap[m]).toBe('number'))
  })

  it('blankSapTotals regression: an empty section grand total is all zeros, never null or NaN', () => {
    const totals = sectionTotals([])
    expect(totals.sap.total_year).toBe(0)
    MONTH_KEYS.forEach((m) => expect(totals.sap[m]).toBe(0))
    // The bug this guards: formatThb(null) used to render the string "null"
    // (or throw) for an empty side/group's SAP grand total — never caught by
    // an existing test because every other fixture always had rows.
    expect(formatThb(totals.sap.total_year)).toBe('—')
  })

  it('blocks delete for a row with real SAP history', () => {
    const meta = { gl_group: 'Office expenses', gl_name: 'x', is_special: false, in_master: true }
    const withHistory = row({
      cost_center: 'CC1', gl_account: '5211800030', editable: true,
      sap: sapLayer({ m04: 500, has_actuals: true }),
      pending: { ...row({ cost_center: 'x', gl_account: 'y' }).pending, updated_at: '2026-01-01T00:00:00Z' },
    })
    expect(isDeletableRow(withHistory, meta)).toBe(false)
  })

  it('still allows delete for a web-added row with no SAP history at all', () => {
    const meta = { gl_group: 'Office expenses', gl_name: 'x', is_special: false, in_master: true }
    const webAdded = row({
      cost_center: 'CC1', gl_account: '5211800030', editable: true,
      sap: sapLayer(),
      pending: { ...row({ cost_center: 'x', gl_account: 'y' }).pending, updated_at: '2026-01-01T00:00:00Z' },
    })
    expect(webAdded.sap.has_actuals).toBe(false)
    expect(isDeletableRow(webAdded, meta)).toBe(true)
  })
})
