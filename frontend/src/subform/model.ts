/** Pure logic for the A9 special-GL detail subforms + Trip Manager — no
 * DOM, no fetch. Field specs mirror `backend/app/special_gl.py`'s
 * GL-conditional validation exactly (parity-tested against the shared
 * fixture in `glDropdownConstants.test.ts`), so the UI never offers/submits
 * a value the server will reject (A9 never-cut). */
import type { DetailLineInput, DetailLineState, TripInput, TripListItem } from '../api/types'
import { MONTH_KEYS, type MonthKey } from '../grid/model'
import {
  ENTERTAINMENT_EXTERNAL_VALUES,
  ENTERTAINMENT_INTERNAL_VALUES,
  LEASE_MACHINERY_SUFFIX,
  LEASE_MACHINERY_TYPES,
  LEASE_PLANTS,
  LEASE_PLATES,
  LEASE_VEHICLE_SUFFIX,
  LEASE_VEHICLE_TYPES,
  MANUAL_TRAVEL_TYPES,
  TRAINING_METHOD_VALUES,
  TRAVEL_GL_BY_TYPE_SIDE,
  type TravelExpenseType,
} from './glDropdownConstants'

/** The 5 non-travel special groups DetailSubform renders. Travelling
 * Expense is a structurally different entity (trip-centric) handled by
 * TripManager instead — never by DetailSubform. */
export const NON_TRAVEL_SPECIAL_GROUPS = [
  'Entertainment',
  'Lease & Rental',
  'Professional & Legal Fee',
  'Public Relation & Donation',
  'Training & Seminar',
] as const

export type DetailFieldKind = 'text' | 'select' | 'locked'

export interface DetailFieldSpec {
  key: string
  kind: DetailFieldKind
  options?: readonly string[]
}

const ENTERTAINMENT_INTERNAL_GL_SUFFIX = '900031'

/** Resolves the special-GL group's detail columns for ONE gl_account —
 * Entertainment's dropdown options and Lease & Rental's dropdown/grey-out
 * both switch on the GL code (spec §4a), exactly like
 * `special_gl.validate_entertainment_meta`/`validate_lease_meta`. */
export function detailFieldsFor(glGroup: string, glAccount: string): DetailFieldSpec[] {
  if (glGroup === 'Entertainment') {
    const isInternal = glAccount.endsWith(ENTERTAINMENT_INTERNAL_GL_SUFFIX)
    return [
      { key: 'ประเภทการรับรอง', kind: 'select', options: isInternal ? ENTERTAINMENT_INTERNAL_VALUES : ENTERTAINMENT_EXTERNAL_VALUES },
      { key: 'รายละเอียด', kind: 'text' },
    ]
  }
  if (glGroup === 'Lease & Rental') {
    const suffix = glAccount.slice(-3)
    let typeField: DetailFieldSpec
    let plateField: DetailFieldSpec
    if (suffix === LEASE_VEHICLE_SUFFIX) {
      typeField = { key: 'ประเภทรถ', kind: 'select', options: LEASE_VEHICLE_TYPES }
      plateField = { key: 'ทะเบียนรถ', kind: 'select', options: LEASE_PLATES }
    } else if (suffix === LEASE_MACHINERY_SUFFIX) {
      typeField = { key: 'ประเภทรถ', kind: 'select', options: LEASE_MACHINERY_TYPES }
      plateField = { key: 'ทะเบียนรถ', kind: 'locked' }
    } else {
      typeField = { key: 'ประเภทรถ', kind: 'locked' }
      plateField = { key: 'ทะเบียนรถ', kind: 'locked' }
    }
    return [
      typeField,
      plateField,
      { key: 'สถานที่ใช้งาน', kind: 'select', options: LEASE_PLANTS },
      { key: 'กิจกรรม', kind: 'text' },
    ]
  }
  if (glGroup === 'Professional & Legal Fee') {
    return [
      { key: 'Project', kind: 'text' },
      { key: 'รายละเอียด', kind: 'text' },
    ]
  }
  if (glGroup === 'Public Relation & Donation') {
    return [{ key: 'รายละเอียด', kind: 'text' }]
  }
  if (glGroup === 'Training & Seminar') {
    return [
      { key: 'หลักสูตรอบรม', kind: 'text' },
      { key: 'Method', kind: 'select', options: TRAINING_METHOD_VALUES },
    ]
  }
  return []
}

// ---------------------------------------------------------------------------
// Detail line draft (5 non-travel groups)
// ---------------------------------------------------------------------------

export interface DetailLineDraft {
  detail_id: number | null
  cost_center: string
  gl_account: string
  fiscal_year: number
  meta: Record<string, string | null>
  months: Record<MonthKey, number>
  expected_updated_at: string | null
}

function blankMonths(): Record<MonthKey, number> {
  return Object.fromEntries(MONTH_KEYS.map((m) => [m, 0])) as Record<MonthKey, number>
}

export function blankDetailDraft(costCenter: string, glAccount: string, fiscalYear: number): DetailLineDraft {
  return {
    detail_id: null,
    cost_center: costCenter,
    gl_account: glAccount,
    fiscal_year: fiscalYear,
    meta: {},
    months: blankMonths(),
    expected_updated_at: null,
  }
}

/** Loads an EXISTING server line into an editable draft (the lock token
 * `updated_at` becomes `expected_updated_at` for the next save). */
export function draftFromServerLine(line: DetailLineState): DetailLineDraft {
  const months = Object.fromEntries(MONTH_KEYS.map((m) => [m, line[m]])) as Record<MonthKey, number>
  return {
    detail_id: line.detail_id,
    cost_center: line.cost_center,
    gl_account: line.gl_account,
    fiscal_year: line.fiscal_year,
    meta: line.meta_json ?? {},
    months,
    expected_updated_at: line.updated_at,
  }
}

export function buildDetailLinePayload(draft: DetailLineDraft): DetailLineInput {
  return {
    detail_id: draft.detail_id,
    cost_center: draft.cost_center,
    gl_account: draft.gl_account,
    fiscal_year: draft.fiscal_year,
    trip_id: null,
    line_label: null,
    meta_json: draft.meta,
    ...draft.months,
    expected_updated_at: draft.expected_updated_at,
  }
}

export function detailLineTotal(draft: DetailLineDraft): number {
  return MONTH_KEYS.reduce((sum, m) => sum + (draft.months[m] || 0), 0)
}

// ---------------------------------------------------------------------------
// Trip draft (Travelling Expense)
// ---------------------------------------------------------------------------

export interface TripDraft {
  trip_id: number | null
  cost_center: string
  fiscal_year: number
  traveler_empcode: string
  destination: string | null
  country_group: 1 | 2 | 3
  days: number
  travel_months: string[]
  purpose: string | null
  side: 'COST' | 'SGA'
  expected_updated_at: string | null
}

export function blankTripDraft(costCenter: string, fiscalYear: number): TripDraft {
  return {
    trip_id: null,
    cost_center: costCenter,
    fiscal_year: fiscalYear,
    traveler_empcode: '',
    destination: null,
    country_group: 1,
    days: 0,
    travel_months: [],
    purpose: null,
    side: 'SGA',
    expected_updated_at: null,
  }
}

export function draftFromTripListItem(item: TripListItem): TripDraft {
  return {
    trip_id: item.trip_id,
    cost_center: item.cost_center,
    fiscal_year: item.fiscal_year,
    traveler_empcode: item.traveler_empcode,
    destination: item.destination,
    country_group: item.country_group,
    days: item.days,
    travel_months: item.travel_months,
    purpose: item.purpose,
    side: item.side,
    expected_updated_at: item.updated_at,
  }
}

export function buildTripPayload(draft: TripDraft): TripInput {
  return { ...draft }
}

export interface TripValidationResult {
  ok: boolean
  errorTh?: string
}

/** Client-side sanity check BEFORE calling the API — the server re-checks
 * everything anyway (traveler exists, rate/FX configured), but this catches
 * the obviously-incomplete case with an immediate message. */
export function validateTripDraft(draft: TripDraft): TripValidationResult {
  if (!draft.traveler_empcode.trim()) return { ok: false, errorTh: 'กรุณาระบุผู้เดินทาง' }
  if (draft.days <= 0) return { ok: false, errorTh: 'จำนวนวันต้องมากกว่า 0' }
  if (draft.travel_months.length === 0) return { ok: false, errorTh: 'กรุณาเลือกเดือนที่เดินทางอย่างน้อย 1 เดือน' }
  return { ok: true }
}

// ---------------------------------------------------------------------------
// Manual travel-type detail lines (transport/accommodation/other) — each
// attaches to a trip via `trip_id` and is saved through the SAME
// `/budget/detail` endpoint the 5 non-travel groups use (ADR-0005: only the
// per-diem line is system-managed via `/budget/trip`).
// ---------------------------------------------------------------------------

/** Reverse-lookup: which manual travel type does this GL belong to (if
 * any), regardless of side. `undefined` for per_diem's GL (never addressed
 * via /budget/detail) or an unrelated GL. */
export function manualTravelTypeForGl(glAccount: string): Exclude<TravelExpenseType, 'per_diem'> | undefined {
  return MANUAL_TRAVEL_TYPES.find(
    (type) => TRAVEL_GL_BY_TYPE_SIDE[type].COST === glAccount || TRAVEL_GL_BY_TYPE_SIDE[type].SGA === glAccount,
  )
}

/** Groups a flat list of detail lines (fetched across both sides x 3 manual
 * types) by `trip_id` then by travel type — `undefined` trip_id lines
 * (impossible for these GLs per the write-path contract, but defensive)
 * are skipped. */
export function indexDetailLinesByTrip(
  lines: DetailLineState[],
): Record<number, Partial<Record<Exclude<TravelExpenseType, 'per_diem'>, DetailLineState>>> {
  const index: Record<number, Partial<Record<Exclude<TravelExpenseType, 'per_diem'>, DetailLineState>>> = {}
  for (const line of lines) {
    if (line.trip_id == null) continue
    const type = manualTravelTypeForGl(line.gl_account)
    if (!type) continue
    index[line.trip_id] = { ...index[line.trip_id], [type]: line }
  }
  return index
}

/** A trip's manual-type row is editable ONLY in that trip's selected
 * `travel_months` (ADR-0005 "month lock follows the trip") — all other
 * months stay locked/greyed, mirroring the per-diem split. */
export function isTripMonthActive(travelMonths: string[], month: MonthKey): boolean {
  return travelMonths.includes(month.slice(1))
}

export interface ManualLineDraft {
  detail_id: number | null
  months: Record<MonthKey, number>
  expected_updated_at: string | null
}

export function blankManualLineDraft(): ManualLineDraft {
  return { detail_id: null, months: blankMonths(), expected_updated_at: null }
}

export function manualLineDraftFromServerLine(line: DetailLineState): ManualLineDraft {
  const months = Object.fromEntries(MONTH_KEYS.map((m) => [m, line[m]])) as Record<MonthKey, number>
  return { detail_id: line.detail_id, months, expected_updated_at: line.updated_at }
}

export function buildManualLinePayload(
  draft: ManualLineDraft,
  costCenter: string,
  glAccount: string,
  fiscalYear: number,
  tripId: number,
): DetailLineInput {
  return {
    detail_id: draft.detail_id,
    cost_center: costCenter,
    gl_account: glAccount,
    fiscal_year: fiscalYear,
    trip_id: tripId,
    line_label: null,
    meta_json: null,
    ...draft.months,
    expected_updated_at: draft.expected_updated_at,
  }
}

export function manualLineTotal(draft: ManualLineDraft): number {
  return MONTH_KEYS.reduce((sum, m) => sum + (draft.months[m] || 0), 0)
}
