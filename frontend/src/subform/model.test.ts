import { describe, expect, it } from 'vitest'
import type { DetailLineState, TripListItem } from '../api/types'
import { MONTH_KEYS } from '../grid/model'
import { blankLayer, makeRow } from '../grid/testUtils'
import {
  blankDetailDraft,
  blankManualLineDraft,
  blankTripDraft,
  buildDetailLinePayload,
  buildManualLinePayload,
  buildTripPayload,
  deriveTravelSideHistory,
  detailFieldsFor,
  detailLineTotal,
  draftFromServerLine,
  draftFromTripListItem,
  indexDetailLinesByTrip,
  isTripMonthActive,
  manualLineDraftFromServerLine,
  manualLineTotal,
  manualTravelTypeForGl,
  validateTripDraft,
} from './model'

describe('detailFieldsFor', () => {
  it('Entertainment external GL (…900030) shows the 4-option external dropdown', () => {
    const fields = detailFieldsFor('Entertainment', '5211900030')
    const dd = fields.find((f) => f.key === 'ประเภทการรับรอง')
    expect(dd?.kind).toBe('select')
    expect(dd?.options).toContain('หน่วยงานราชการ')
    expect(fields.some((f) => f.key === 'รายละเอียด' && f.kind === 'text')).toBe(true)
  })

  it('Entertainment internal GL (…900031) shows the 2-option internal dropdown', () => {
    const fields = detailFieldsFor('Entertainment', '6211900031')
    const dd = fields.find((f) => f.key === 'ประเภทการรับรอง')
    expect(dd?.options).toEqual(['พนักงานบริษัท', 'กรรมการบริษัท'])
  })

  it('Lease & Rental vehicle suffix (…060) shows both dropdowns editable', () => {
    const fields = detailFieldsFor('Lease & Rental', '6211200060')
    expect(fields.find((f) => f.key === 'ประเภทรถ')?.kind).toBe('select')
    expect(fields.find((f) => f.key === 'ทะเบียนรถ')?.kind).toBe('select')
  })

  it('Lease & Rental machinery suffix (…030) greys out ทะเบียนรถ only', () => {
    const fields = detailFieldsFor('Lease & Rental', '6211200030')
    expect(fields.find((f) => f.key === 'ประเภทรถ')?.kind).toBe('select')
    expect(fields.find((f) => f.key === 'ทะเบียนรถ')?.kind).toBe('locked')
  })

  it('Lease & Rental non-vehicle suffix (…020 Building) greys out both, keeps plant + activity', () => {
    const fields = detailFieldsFor('Lease & Rental', '6211200020')
    expect(fields.find((f) => f.key === 'ประเภทรถ')?.kind).toBe('locked')
    expect(fields.find((f) => f.key === 'ทะเบียนรถ')?.kind).toBe('locked')
    expect(fields.find((f) => f.key === 'สถานที่ใช้งาน')?.kind).toBe('select')
    expect(fields.find((f) => f.key === 'กิจกรรม')?.kind).toBe('text')
  })

  it('Professional & Legal Fee is 2 free-text fields, no dropdown', () => {
    const fields = detailFieldsFor('Professional & Legal Fee', '6210700030')
    expect(fields).toEqual([
      { key: 'Project', kind: 'text' },
      { key: 'รายละเอียด', kind: 'text' },
    ])
  })

  it('Public Relation & Donation is a single free-text field', () => {
    const fields = detailFieldsFor('Public Relation & Donation', '6211700030')
    expect(fields).toEqual([{ key: 'รายละเอียด', kind: 'text' }])
  })

  it('Training & Seminar is a text field + a Method dropdown', () => {
    const fields = detailFieldsFor('Training & Seminar', '6210100150')
    expect(fields.find((f) => f.key === 'หลักสูตรอบรม')?.kind).toBe('text')
    expect(fields.find((f) => f.key === 'Method')?.options).toEqual(['Inhouse', 'Public'])
  })

  it('returns an empty list for an unrecognised group', () => {
    expect(detailFieldsFor('Office Expenses', '6211800030')).toEqual([])
  })
})

describe('detail line draft <-> payload round trip', () => {
  it('blankDetailDraft starts at all-zero months with expected_updated_at null (create path)', () => {
    const draft = blankDetailDraft('CC1', 'GL1', 2027)
    expect(draft.detail_id).toBeNull()
    expect(draft.expected_updated_at).toBeNull()
    expect(detailLineTotal(draft)).toBe(0)
  })

  it('draftFromServerLine carries over detail_id/meta/months/updated_at for editing', () => {
    const serverLine: DetailLineState = {
      detail_id: 5, cost_center: 'CC1', gl_account: 'GL1', fiscal_year: 2027, trip_id: null,
      gl_group: 'Entertainment', line_label: null,
      ...(blankLayer({ m01: 500 }) as unknown as Record<string, number>),
      total_year: 500, meta_json: { ประเภทการรับรอง: 'Customer' }, updated_at: '2026-01-01T00:00:00',
    } as unknown as DetailLineState
    const draft = draftFromServerLine(serverLine)
    expect(draft.detail_id).toBe(5)
    expect(draft.expected_updated_at).toBe('2026-01-01T00:00:00')
    expect(draft.meta.ประเภทการรับรอง).toBe('Customer')
    expect(draft.months.m01).toBe(500)
  })

  it('buildDetailLinePayload maps the draft into the PUT /budget/detail shape', () => {
    const draft = blankDetailDraft('CC1', 'GL1', 2027)
    draft.meta = { รายละเอียด: 'lunch with client' }
    draft.months.m01 = 100
    const payload = buildDetailLinePayload(draft)
    expect(payload.cost_center).toBe('CC1')
    expect(payload.gl_account).toBe('GL1')
    expect(payload.trip_id).toBeNull()
    expect(payload.meta_json).toEqual({ รายละเอียด: 'lunch with client' })
    expect(payload.m01).toBe(100)
    expect(payload.detail_id).toBeNull()
    expect(payload.expected_updated_at).toBeNull()
  })
})

describe('trip draft <-> payload round trip', () => {
  it('blankTripDraft starts empty with no trip_id (create path)', () => {
    const draft = blankTripDraft('CC1', 2027, 'SGA')
    expect(draft.trip_id).toBeNull()
    expect(draft.expected_updated_at).toBeNull()
    expect(draft.travel_months).toEqual([])
  })

  it('blankTripDraft no longer hard-codes SGA — the side comes from the caller (ฝ่าย history)', () => {
    expect(blankTripDraft('CC1', 2027, 'COST').side).toBe('COST')
    expect(blankTripDraft('CC1', 2027, null).side).toBeNull()
  })

  it('draftFromTripListItem carries over every field for editing an existing trip', () => {
    const item: TripListItem = {
      trip_id: 10, cost_center: 'CC1', fiscal_year: 2027, traveler_empcode: 'E1',
      traveler_name: 'สมชาย', position: 'Supervisor', destination: 'Japan',
      country_group: 2, days: 5, travel_months: ['02', '03'], purpose: 'visit',
      side: 'COST', updated_at: '2026-01-01T00:00:00',
      per_diem_months: { m02: 1000, m03: 1000 } as Record<string, number>, per_diem_error: null,
    }
    const draft = draftFromTripListItem(item)
    expect(draft.trip_id).toBe(10)
    expect(draft.expected_updated_at).toBe('2026-01-01T00:00:00')
    expect(draft.side).toBe('COST')
    expect(draft.travel_months).toEqual(['02', '03'])
  })

  it('buildTripPayload maps the draft into the POST|PUT /budget/trip shape', () => {
    const draft = blankTripDraft('CC1', 2027, 'SGA')
    draft.traveler_empcode = 'E1'
    draft.days = 5
    draft.travel_months = ['03']
    draft.country_group = 1
    const payload = buildTripPayload(draft)
    expect(payload.cost_center).toBe('CC1')
    expect(payload.traveler_empcode).toBe('E1')
    expect(payload.travel_months).toEqual(['03'])
  })

  it('buildTripPayload refuses an unset side (validateTripDraft guards the UI path)', () => {
    expect(() => buildTripPayload(blankTripDraft('CC1', 2027, null))).toThrow()
  })

  it('blankTripDraft generates a fresh client_token per new-trip intent (idempotent create)', () => {
    const a = blankTripDraft('CC1', 2027, 'SGA')
    const b = blankTripDraft('CC1', 2027, 'SGA')
    expect(a.client_token).toBeTruthy()
    expect(b.client_token).toBeTruthy()
    expect(a.client_token).not.toBe(b.client_token)
  })

  it('draftFromTripListItem carries NO client_token (an existing trip never dedups an edit)', () => {
    const item: TripListItem = {
      trip_id: 10, cost_center: 'CC1', fiscal_year: 2027, traveler_empcode: 'E1',
      traveler_name: 'สมชาย', position: 'Supervisor', destination: 'Japan',
      country_group: 2, days: 5, travel_months: ['02', '03'], purpose: 'visit',
      side: 'COST', updated_at: '2026-01-01T00:00:00',
      per_diem_months: { m02: 1000, m03: 1000 } as Record<string, number>, per_diem_error: null,
    }
    expect(draftFromTripListItem(item).client_token).toBeNull()
  })

  it('buildTripPayload includes the client_token so the server can dedup a retry', () => {
    const draft = blankTripDraft('CC1', 2027, 'SGA')
    expect(buildTripPayload(draft).client_token).toBe(draft.client_token)
  })
})

describe('validateTripDraft', () => {
  it('rejects a blank traveler', () => {
    const draft = blankTripDraft('CC1', 2027, 'SGA')
    draft.days = 5
    draft.travel_months = ['03']
    expect(validateTripDraft(draft).ok).toBe(false)
  })

  it('rejects zero days', () => {
    const draft = blankTripDraft('CC1', 2027, 'SGA')
    draft.traveler_empcode = 'E1'
    draft.travel_months = ['03']
    expect(validateTripDraft(draft).ok).toBe(false)
  })

  it('rejects no selected months', () => {
    const draft = blankTripDraft('CC1', 2027, 'SGA')
    draft.traveler_empcode = 'E1'
    draft.days = 5
    expect(validateTripDraft(draft).ok).toBe(false)
  })

  it('rejects an unset side (no-history ฝ่าย, user has not picked yet)', () => {
    const draft = blankTripDraft('CC1', 2027, null)
    draft.traveler_empcode = 'E1'
    draft.days = 5
    draft.travel_months = ['03']
    const result = validateTripDraft(draft)
    expect(result.ok).toBe(false)
    expect(result.errorTh).toBe('กรุณาเลือกฝั่งบัญชี')
  })

  it('accepts a fully filled draft', () => {
    const draft = blankTripDraft('CC1', 2027, 'SGA')
    draft.traveler_empcode = 'E1'
    draft.days = 5
    draft.travel_months = ['03']
    expect(validateTripDraft(draft).ok).toBe(true)
  })
})

describe('deriveTravelSideHistory (ฝ่าย grain — decided 2026-07-16)', () => {
  const CCS = ['CC1', 'CC2'] // the ฝ่าย's cost centers; CC1 is the trip CC

  it('SGA-only history across the ฝ่าย → single side, defaults SGA', () => {
    const rows = [makeRow({ cost_center: 'CC1', gl_account: '6210400010', sap: blankLayer({ m01: 100, total_year: 100 }) })]
    expect(deriveTravelSideHistory(rows, CCS)).toEqual({ sides: ['SGA'], defaultSide: 'SGA' })
  })

  it('COST-only history → single side, defaults COST', () => {
    const rows = [makeRow({ cost_center: 'CC1', gl_account: '5210400020', board: { ...makeRow({ cost_center: 'x', gl_account: 'y' }).board, m03: 50, total_year: 50 } })]
    expect(deriveTravelSideHistory(rows, CCS)).toEqual({ sides: ['COST'], defaultSide: 'COST' })
  })

  it('a CC with no travel history of its OWN inherits the side its ฝ่าย siblings use', () => {
    const rows = [
      makeRow({ cost_center: 'CC1', gl_account: '6210400010' }), // trip CC — all zero
      makeRow({ cost_center: 'CC2', gl_account: '6210400030', sap: blankLayer({ m05: 900, total_year: 900 }) }),
    ]
    expect(deriveTravelSideHistory(rows, CCS)).toEqual({ sides: ['SGA'], defaultSide: 'SGA' })
  })

  it('both sides in the ฝ่าย → both offered, default = larger summed total (sap+board)', () => {
    const rows = [
      makeRow({ cost_center: 'CC1', gl_account: '5210400010', sap: blankLayer({ m01: 2000, total_year: 2000 }) }),
      makeRow({ cost_center: 'CC2', gl_account: '6210400010', sap: blankLayer({ m01: 577263, total_year: 577263 }) }),
    ]
    expect(deriveTravelSideHistory(rows, CCS)).toEqual({ sides: ['COST', 'SGA'], defaultSide: 'SGA' })
  })

  it('both sides, COST larger → default COST', () => {
    const rows = [
      makeRow({ cost_center: 'CC1', gl_account: '5210400999', sap: blankLayer({ m01: 9000, total_year: 9000 }) }),
      makeRow({ cost_center: 'CC2', gl_account: '6210400010', sap: blankLayer({ m01: 100, total_year: 100 }) }),
    ]
    expect(deriveTravelSideHistory(rows, CCS)).toEqual({ sides: ['COST', 'SGA'], defaultSide: 'COST' })
  })

  it('no travel history anywhere in the ฝ่าย → no sides, no default (user must pick)', () => {
    const rows = [
      makeRow({ cost_center: 'CC1', gl_account: '6210400010' }), // travel GL, zero history
      makeRow({ cost_center: 'CC1', gl_account: '5211800030', sap: blankLayer({ m01: 999, total_year: 999 }) }), // non-travel GL — irrelevant
    ]
    expect(deriveTravelSideHistory(rows, CCS)).toEqual({ sides: [], defaultSide: null })
  })

  it('pending-only amounts are NOT history (only sap/board count)', () => {
    const base = makeRow({ cost_center: 'CC1', gl_account: '6210400010' })
    const rows = [{ ...base, pending: { ...base.pending, m01: 500, total_year: 500 } }]
    expect(deriveTravelSideHistory(rows, CCS)).toEqual({ sides: [], defaultSide: null })
  })

  it("rows of another ฝ่าย's CC are excluded from the aggregation", () => {
    const rows = [makeRow({ cost_center: 'CC9', gl_account: '6210400010', sap: blankLayer({ m01: 100, total_year: 100 }) })]
    expect(deriveTravelSideHistory(rows, CCS)).toEqual({ sides: [], defaultSide: null })
  })
})

describe('manualTravelTypeForGl', () => {
  it('resolves the manual type for a COST or SGA GL', () => {
    expect(manualTravelTypeForGl('5210400020')).toBe('transport')
    expect(manualTravelTypeForGl('6210400030')).toBe('accommodation')
    expect(manualTravelTypeForGl('5210400999')).toBe('other')
  })

  it('never resolves the per-diem GL (system-managed via /budget/trip only)', () => {
    expect(manualTravelTypeForGl('5210400010')).toBeUndefined()
    expect(manualTravelTypeForGl('6210400010')).toBeUndefined()
  })

  it('returns undefined for an unrelated GL', () => {
    expect(manualTravelTypeForGl('6211800030')).toBeUndefined()
  })
})

describe('indexDetailLinesByTrip', () => {
  function line(overrides: Partial<DetailLineState>): DetailLineState {
    const months = Object.fromEntries(MONTH_KEYS.map((m) => [m, 0])) as Record<string, number>
    return {
      detail_id: 1, cost_center: 'CC1', gl_account: '5210400020', fiscal_year: 2027, trip_id: 10,
      gl_group: 'Travelling Expense', line_label: null, ...months, total_year: 0, meta_json: null,
      updated_at: '2026-01-01T00:00:00', ...overrides,
    } as DetailLineState
  }

  it('groups lines by trip_id then travel type', () => {
    const lines = [
      line({ detail_id: 1, trip_id: 10, gl_account: '5210400020' }), // transport, COST
      line({ detail_id: 2, trip_id: 10, gl_account: '5210400030' }), // accommodation, COST
      line({ detail_id: 3, trip_id: 20, gl_account: '6210400999' }), // other, SGA
    ]
    const index = indexDetailLinesByTrip(lines)
    expect(index[10]?.transport?.detail_id).toBe(1)
    expect(index[10]?.accommodation?.detail_id).toBe(2)
    expect(index[20]?.other?.detail_id).toBe(3)
  })

  it('skips a line with no trip_id (defensive — should never happen for these GLs)', () => {
    const lines = [line({ trip_id: null })]
    expect(indexDetailLinesByTrip(lines)).toEqual({})
  })
})

describe('isTripMonthActive', () => {
  it('is true only for months in the trip travel_months list', () => {
    expect(isTripMonthActive(['02', '03'], 'm02')).toBe(true)
    expect(isTripMonthActive(['02', '03'], 'm01')).toBe(false)
  })
})

describe('manual line draft helpers', () => {
  it('blankManualLineDraft starts at all-zero with no lock token (create path)', () => {
    const draft = blankManualLineDraft()
    expect(draft.detail_id).toBeNull()
    expect(draft.expected_updated_at).toBeNull()
    expect(manualLineTotal(draft)).toBe(0)
  })

  it('manualLineDraftFromServerLine carries over detail_id/months/updated_at', () => {
    const serverLine = {
      detail_id: 7, cost_center: 'CC1', gl_account: '5210400020', fiscal_year: 2027, trip_id: 10,
      gl_group: 'Travelling Expense', line_label: null,
      ...(Object.fromEntries(MONTH_KEYS.map((m) => [m, m === 'm02' ? 400 : 0])) as Record<string, number>),
      total_year: 400, meta_json: null, updated_at: '2026-02-01T00:00:00',
    } as unknown as DetailLineState
    const draft = manualLineDraftFromServerLine(serverLine)
    expect(draft.detail_id).toBe(7)
    expect(draft.months.m02).toBe(400)
    expect(draft.expected_updated_at).toBe('2026-02-01T00:00:00')
  })

  it('buildManualLinePayload attaches trip_id and the correct type/side GL', () => {
    const draft = blankManualLineDraft()
    draft.months.m02 = 500
    const payload = buildManualLinePayload(draft, 'CC1', '5210400020', 2027, 10)
    expect(payload.trip_id).toBe(10)
    expect(payload.gl_account).toBe('5210400020')
    expect(payload.m02).toBe(500)
  })
})
