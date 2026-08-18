import { describe, expect, it } from 'vitest'
import type { CountryOption, DetailLineState, TripListItem } from '../api/types'
import { MONTH_KEYS } from '../grid/model'
import { blankLayer } from '../grid/testUtils'
import { ENTERTAINMENT_EXTERNAL_VALUES } from './glDropdownConstants'
import {
  blankDetailDraft,
  blankManualLineDraft,
  blankTripDraft,
  buildDetailLinePayload,
  buildManualLinePayload,
  buildTripPayload,
  countryGroupFor,
  countryOptionsWithOther,
  deriveTravelSideFromGl,
  detailFieldsFor,
  detailLineTotal,
  draftFromServerLine,
  draftFromTripListItem,
  fieldFreeText,
  fieldSelectValue,
  firstBlankFreeTextField,
  firstUnselectedRequiredField,
  indexDetailLinesByTrip,
  isTripMonthActive,
  manualLineDraftFromServerLine,
  manualLineTotal,
  manualTravelTypeForGl,
  OTHER_COUNTRY_OPTION,
  resolveTravelerDisplay,
  validateTripDraft,
  type DetailFieldSpec,
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

  it('Lease & Rental vehicle ทะเบียนรถ carries freeTextOption อื่นๆ (custom plate); ประเภทรถ does not', () => {
    const fields = detailFieldsFor('Lease & Rental', '6211200060')
    expect(fields.find((f) => f.key === 'ทะเบียนรถ')?.freeTextOption).toBe('อื่นๆ')
    expect(fields.find((f) => f.key === 'ประเภทรถ')?.freeTextOption).toBeUndefined()
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

  describe('Lease & Rental สถานที่ใช้งาน — required, ประเภทรถ is not (bug-lease-blank-dropdown-400)', () => {
    it('marks สถานที่ใช้งาน as required for every sub-category — vehicle, machinery, and non-vehicle', () => {
      for (const gl of ['6211200060', '6211200030', '6211200020']) {
        const fields = detailFieldsFor('Lease & Rental', gl)
        expect(fields.find((f) => f.key === 'สถานที่ใช้งาน')?.required).toBe(true)
      }
    })

    it('does NOT mark ประเภทรถ as required, even when it is an enterable select (vehicle/machinery)', () => {
      // สถานที่ใช้งาน applies to every sub-category and is the row's one
      // universal classification field (parity with Entertainment's single
      // required dropdown); ประเภทรถ is a refinement the backend explicitly
      // allows blank (test_lease_meta_with_no_values_yet_is_valid_all_none) —
      // marking it required would also be undemandable for the 5 suffixes
      // where it renders `locked`, so it stays optional everywhere.
      expect(detailFieldsFor('Lease & Rental', '6211200060').find((f) => f.key === 'ประเภทรถ')?.required).toBeFalsy()
      expect(detailFieldsFor('Lease & Rental', '6211200030').find((f) => f.key === 'ประเภทรถ')?.required).toBeFalsy()
      expect(detailFieldsFor('Lease & Rental', '6211200020').find((f) => f.key === 'ประเภทรถ')?.required).toBeFalsy()
    })
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

describe('free-text plate helpers (ทะเบียนรถ อื่นๆ)', () => {
  const plateSpec: DetailFieldSpec = {
    key: 'ทะเบียนรถ',
    kind: 'select',
    options: ['6ขผ-3918', 'อื่นๆ'],
    freeTextOption: 'อื่นๆ',
  }

  it('a listed plate keeps the select on that plate with no free text', () => {
    expect(fieldSelectValue(plateSpec, '6ขผ-3918')).toBe('6ขผ-3918')
    expect(fieldFreeText(plateSpec, '6ขผ-3918')).toBe('')
  })

  it('อื่นๆ itself selects อื่นๆ with an empty free-text box', () => {
    expect(fieldSelectValue(plateSpec, 'อื่นๆ')).toBe('อื่นๆ')
    expect(fieldFreeText(plateSpec, 'อื่นๆ')).toBe('')
  })

  it('a custom plate (not in the list) round-trips as อื่นๆ + the plate in the free-text box', () => {
    expect(fieldSelectValue(plateSpec, 'กข-1234')).toBe('อื่นๆ')
    expect(fieldFreeText(plateSpec, 'กข-1234')).toBe('กข-1234')
  })

  it('an unset value shows the empty placeholder, and a spec WITHOUT freeTextOption passes values through', () => {
    expect(fieldSelectValue(plateSpec, null)).toBe('')
    const plainSpec: DetailFieldSpec = { key: 'สถานที่ใช้งาน', kind: 'select', options: ['BK'] }
    expect(fieldSelectValue(plainSpec, 'BK')).toBe('BK')
    expect(fieldSelectValue(plainSpec, null)).toBe('')
  })

  it('firstBlankFreeTextField blocks the bare อื่นๆ (nothing typed) and passes a typed plate / listed plate / unset', () => {
    const fields = [plateSpec, { key: 'กิจกรรม', kind: 'text' } as DetailFieldSpec]
    expect(firstBlankFreeTextField(fields, { ทะเบียนรถ: 'อื่นๆ' })).toBe('ทะเบียนรถ')
    expect(firstBlankFreeTextField(fields, { ทะเบียนรถ: 'กข-1234' })).toBeNull()
    expect(firstBlankFreeTextField(fields, { ทะเบียนรถ: '6ขผ-3918' })).toBeNull()
    expect(firstBlankFreeTextField(fields, {})).toBeNull()
  })
})

// ---------------------------------------------------------------------------
// firstUnselectedRequiredField — bug-entertainment-blank-type-400: a
// `required` select field left on the blank placeholder must block the save
// the same way a blank free-text field does, BEFORE any network call.
// ---------------------------------------------------------------------------

describe('firstUnselectedRequiredField', () => {
  const requiredSelect: DetailFieldSpec = { key: 'ประเภทการรับรอง', kind: 'select', options: ['Customer'], required: true }
  const optionalText: DetailFieldSpec = { key: 'รายละเอียด', kind: 'text' }
  const fields = [requiredSelect, optionalText]

  it('blocks when the required field is missing entirely (never touched)', () => {
    expect(firstUnselectedRequiredField(fields, {})).toBe('ประเภทการรับรอง')
  })

  it('blocks when the required field is an explicit empty string (picked, then reset to "— เลือก —")', () => {
    expect(firstUnselectedRequiredField(fields, { ประเภทการรับรอง: '' })).toBe('ประเภทการรับรอง')
  })

  it('passes once a value is chosen, and a non-required blank field never blocks', () => {
    expect(firstUnselectedRequiredField(fields, { ประเภทการรับรอง: 'Customer' })).toBeNull()
    expect(firstUnselectedRequiredField([optionalText], {})).toBeNull()
  })
})

describe('detailFieldsFor Entertainment — external/internal split is driven by the shared GL list', () => {
  it('marks ประเภทการรับรอง as required (bug-entertainment-blank-type-400)', () => {
    const fields = detailFieldsFor('Entertainment', '5211900030')
    expect(fields.find((f) => f.key === 'ประเภทการรับรอง')?.required).toBe(true)
  })

  it('classifies by membership in the shared ENTERTAINMENT_INTERNAL_GLS constant, not an independently-derived suffix guess', () => {
    // Regression pin for the frontend/backend asymmetry (endsWith('900031')
    // vs exact-set membership): a GL that merely ENDS WITH '900031' but is
    // NOT in the parity-tested ENTERTAINMENT_INTERNAL_GLS list must render
    // the EXTERNAL dropdown — the same set the backend's `special_gl.py`
    // (validated against the identical fixture-backed list) would accept
    // for it. The old suffix-based rule would have wrongly rendered the
    // internal (2-option) dropdown here, an asymmetry that only surfaces
    // when the two sides' classification rules can diverge.
    const unlistedGlEndingIn900031 = '5211900031'
    const fields = detailFieldsFor('Entertainment', unlistedGlEndingIn900031)
    const dd = fields.find((f) => f.key === 'ประเภทการรับรอง')
    expect(dd?.options).toEqual(Array.from(ENTERTAINMENT_EXTERNAL_VALUES))
  })
})

describe('destination country options (auto country_group)', () => {
  const API_COUNTRIES: CountryOption[] = [
    { country: 'ประเทศไทย', country_group: 1 },
    { country: 'ญี่ปุ่น', country_group: 2 },
  ]

  it('appends อื่นๆ (Other) as group 3 after the API list, preserving order', () => {
    const options = countryOptionsWithOther(API_COUNTRIES)
    expect(options).toEqual([
      { country: 'ประเทศไทย', country_group: 1 },
      { country: 'ญี่ปุ่น', country_group: 2 },
      { country: OTHER_COUNTRY_OPTION, country_group: 3 },
    ])
  })

  it('countryGroupFor resolves 1/2/3 by country name and null for an unknown (legacy) name', () => {
    const options = countryOptionsWithOther(API_COUNTRIES)
    expect(countryGroupFor(options, 'ประเทศไทย')).toBe(1)
    expect(countryGroupFor(options, 'ญี่ปุ่น')).toBe(2)
    expect(countryGroupFor(options, OTHER_COUNTRY_OPTION)).toBe(3)
    expect(countryGroupFor(options, 'Japan')).toBeNull()
  })
})

describe('resolveTravelerDisplay', () => {
  const TRAVELERS = [
    { empcode: 'E1', name: 'สมชาย ใจดี', position: 'Supervisor', email: 'somchai.j@chememan.com' },
    { empcode: 'E2', name: 'สมหญิง มั่นคง', position: 'Manager', email: 'somying.m@chememan.com' },
  ]

  it('resolves name + position from the traveler list when the empcode is listed', () => {
    expect(resolveTravelerDisplay('E2', TRAVELERS, null)).toEqual({ name: 'สมหญิง มั่นคง', position: 'Manager' })
  })

  it('falls back to the trip response values for an empcode no longer in the list', () => {
    const server = { empcode: 'E9', name: 'อดีตพนักงาน', position: 'Officer', email: '' }
    expect(resolveTravelerDisplay('E9', TRAVELERS, server)).toEqual({ name: 'อดีตพนักงาน', position: 'Officer' })
  })

  it('returns nulls when nothing matches (blank pick, or empcode changed away from the server one)', () => {
    expect(resolveTravelerDisplay('', TRAVELERS, null)).toEqual({ name: null, position: null })
    const server = { empcode: 'E9', name: 'อดีตพนักงาน', position: 'Officer', email: '' }
    expect(resolveTravelerDisplay('E8', TRAVELERS, server)).toEqual({ name: null, position: null })
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
      country_group: 2, days: 5, travel_months: ['02', '03'], project: 'PRJ-A', purpose: 'visit',
      side: 'COST', updated_at: '2026-01-01T00:00:00',
      per_diem_months: { m02: 1000, m03: 1000 } as Record<string, number>, per_diem_error: null,
    }
    const draft = draftFromTripListItem(item)
    expect(draft.trip_id).toBe(10)
    expect(draft.expected_updated_at).toBe('2026-01-01T00:00:00')
    expect(draft.side).toBe('COST')
    expect(draft.travel_months).toEqual(['02', '03'])
    expect(draft.project).toBe('PRJ-A')
    expect(draft.purpose).toBe('visit')
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

  it('blankTripDraft starts with project null and buildTripPayload carries project + purpose', () => {
    const draft = blankTripDraft('CC1', 2027, 'SGA')
    expect(draft.project).toBeNull()
    draft.traveler_empcode = 'E1'
    draft.project = 'โครงการ A'
    draft.purpose = 'เยี่ยมลูกค้า'
    const payload = buildTripPayload(draft)
    expect(payload.project).toBe('โครงการ A')
    expect(payload.purpose).toBe('เยี่ยมลูกค้า')
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
      country_group: 2, days: 5, travel_months: ['02', '03'], project: null, purpose: 'visit',
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

  it('rejects a missing destination — country_group is derived from it, so it can no longer be blank', () => {
    const draft = blankTripDraft('CC1', 2027, 'SGA')
    draft.traveler_empcode = 'E1'
    draft.days = 5
    draft.travel_months = ['03']
    const result = validateTripDraft(draft)
    expect(result.ok).toBe(false)
    expect(result.errorTh).toBe('กรุณาเลือกปลายทาง')
  })

  it('accepts a fully filled draft', () => {
    const draft = blankTripDraft('CC1', 2027, 'SGA')
    draft.traveler_empcode = 'E1'
    draft.days = 5
    draft.travel_months = ['03']
    draft.destination = 'ประเทศไทย'
    expect(validateTripDraft(draft).ok).toBe(true)
  })
})

describe('deriveTravelSideFromGl (2026-08-04 — replaces the old ฝ่าย-history heuristic)', () => {
  it('resolves every one of the 8 travel GLs to its own side, per-diem included', () => {
    expect(deriveTravelSideFromGl('5210400010')).toBe('COST') // per_diem COST
    expect(deriveTravelSideFromGl('6210400010')).toBe('SGA') // per_diem SGA
    expect(deriveTravelSideFromGl('5210400020')).toBe('COST') // transport COST
    expect(deriveTravelSideFromGl('6210400999')).toBe('SGA') // other SGA
  })

  it('returns null for a GL outside the 8 travel accounts (defensive — never a real caller)', () => {
    expect(deriveTravelSideFromGl('5211800030')).toBeNull()
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
