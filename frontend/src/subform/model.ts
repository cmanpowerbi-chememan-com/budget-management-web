/** Pure logic for the A9 special-GL detail subforms + Trip Manager — no
 * DOM, no fetch. Field specs mirror `backend/app/special_gl.py`'s
 * GL-conditional validation exactly (parity-tested against the shared
 * fixture in `glDropdownConstants.test.ts`), so the UI never offers/submits
 * a value the server will reject (A9 never-cut). */
import type { BudgetRow, CountryOption, DetailLineInput, DetailLineState, TravelerOption, TripInput, TripListItem } from '../api/types'
import { MONTH_KEYS, type MonthKey } from '../grid/model'
import {
  ENTERTAINMENT_EXTERNAL_VALUES,
  ENTERTAINMENT_INTERNAL_VALUES,
  LEASE_MACHINERY_SUFFIX,
  LEASE_MACHINERY_TYPES,
  LEASE_PLANTS,
  LEASE_PLATE_OTHER,
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
  /** A select option that, when chosen, reveals a REQUIRED free-text input
   * whose typed value is what actually gets stored/sent (ทะเบียนรถ อื่นๆ →
   * custom plate; the literal trigger is never sent). The trigger itself is
   * stored only while the box is empty — `firstBlankFreeTextField` blocks
   * saving in that state. */
  freeTextOption?: string
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
      plateField = { key: 'ทะเบียนรถ', kind: 'select', options: LEASE_PLATES, freeTextOption: LEASE_PLATE_OTHER }
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

/** What the SELECT of a `freeTextOption` field should show for a stored
 * value: a listed option shows itself; anything else (a custom plate typed
 * earlier) shows the trigger option, with the actual value living in the
 * companion free-text box. Fields without `freeTextOption` pass through. */
export function fieldSelectValue(spec: DetailFieldSpec, value: string | null): string {
  if (value == null || value === '') return ''
  if (!spec.freeTextOption) return value
  return spec.options?.includes(value) ? value : spec.freeTextOption
}

/** The companion free-text box's content: the stored custom value, or empty
 * when a listed option is stored (incl. the bare trigger — nothing typed yet). */
export function fieldFreeText(spec: DetailFieldSpec, value: string | null): string {
  if (value == null || value === spec.freeTextOption || spec.options?.includes(value)) return ''
  return value
}

/** The free-text input is REQUIRED once its trigger option is picked — the
 * literal trigger ('อื่นๆ') must never be sent as the value. Returns the
 * first offending field key so the caller can block the save with a message
 * naming it, or `null` when every free-text field is satisfied. */
export function firstBlankFreeTextField(fields: readonly DetailFieldSpec[], meta: Record<string, string | null>): string | null {
  const offending = fields.find((f) => f.freeTextOption !== undefined && meta[f.key] === f.freeTextOption)
  return offending?.key ?? null
}

// ---------------------------------------------------------------------------
// Destination country options (Trip Manager) — country_group is DERIVED from
// the picked country, never chosen by hand (wrong group = wrong per-diem).
// ---------------------------------------------------------------------------

/** The one client-side extra destination — the API only serves groups 1
 * (domestic) and 2 (asian); anywhere else books at the group-3 rate. */
export const OTHER_COUNTRY_OPTION = 'อื่นๆ (Other)'

export interface DestinationOption {
  country: string
  country_group: 1 | 2 | 3
}

/** The full destination dropdown = the API's country master + อื่นๆ (Other). */
export function countryOptionsWithOther(countries: readonly CountryOption[]): DestinationOption[] {
  return [...countries, { country: OTHER_COUNTRY_OPTION, country_group: 3 }]
}

/** Resolves the per-diem country group for a picked destination; `null` for
 * a name outside the list (a legacy free-typed destination on an existing
 * trip — its stored group is kept until the user re-picks). */
export function countryGroupFor(options: readonly DestinationOption[], country: string): 1 | 2 | 3 | null {
  return options.find((o) => o.country === country)?.country_group ?? null
}

// ---------------------------------------------------------------------------
// Traveler display (Trip Manager) — name + position are shown from the
// traveler master; position is read-only (it drives per-diem server-side).
// ---------------------------------------------------------------------------

export interface TravelerDisplay {
  name: string | null
  position: string | null
}

/** Resolves the display name/position for a traveler empcode: the current
 * `/reference/travelers` list wins; an existing trip whose traveler is no
 * longer listed (left the company, changed CC) falls back to the values the
 * trip response itself carries — but ONLY while the empcode is unchanged. */
export function resolveTravelerDisplay(
  empcode: string,
  travelers: readonly TravelerOption[],
  serverTraveler: TravelerOption | null,
): TravelerDisplay {
  const listed = travelers.find((t) => t.empcode === empcode)
  if (listed) return { name: listed.name, position: listed.position }
  if (serverTraveler && empcode === serverTraveler.empcode) {
    return { name: serverTraveler.name, position: serverTraveler.position }
  }
  return { name: null, position: null }
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

export type TripSide = 'COST' | 'SGA'

/** Which accounting side(s) a ฝ่าย actually books travel to, aggregated from
 * the main grid's sap/board history (decided 2026-07-16, ฝ่าย grain — 85% of
 * ฝ่าย with travel history use exactly one side). Drives the Trip Manager's
 * side select: single side → hard-locked for non-admins; both → enabled,
 * defaulting to the larger total; none → no silent default, the user must
 * pick before save. */
export interface TravelSideHistory {
  sides: TripSide[]
  defaultSide: TripSide | null
}

const TRAVEL_GLS_OF_SIDE: Record<TripSide, string[]> = {
  COST: Object.values(TRAVEL_GL_BY_TYPE_SIDE).map((g) => g.COST),
  SGA: Object.values(TRAVEL_GL_BY_TYPE_SIDE).map((g) => g.SGA),
}

/** Aggregates travel-GL history for ALL cost centers of the trip CC's ฝ่าย
 * (`departmentCostCenters`) — a new/small CC with no history of its own
 * inherits its ฝ่าย's side. "History" = nonzero sap or board total_year;
 * Pending amounts never count (they are the numbers being drafted, not the
 * dept's real booking pattern). Tie on a both-side ฝ่าย defaults to SGA
 * (the org-wide majority side). */
export function deriveTravelSideHistory(rows: BudgetRow[], departmentCostCenters: readonly string[]): TravelSideHistory {
  const ccSet = new Set(departmentCostCenters)
  const totals: Record<TripSide, number> = { COST: 0, SGA: 0 }
  const hasHistory: Record<TripSide, boolean> = { COST: false, SGA: false }
  for (const row of rows) {
    if (!ccSet.has(row.cost_center)) continue
    for (const side of ['COST', 'SGA'] as const) {
      if (!TRAVEL_GLS_OF_SIDE[side].includes(row.gl_account)) continue
      if (row.sap.total_year !== 0 || row.board.total_year !== 0) {
        hasHistory[side] = true
        totals[side] += row.sap.total_year + row.board.total_year
      }
    }
  }
  const sides = (['COST', 'SGA'] as const).filter((s) => hasHistory[s])
  const defaultSide = sides.length === 1 ? sides[0] : sides.length === 2 ? (totals.COST > totals.SGA ? 'COST' : 'SGA') : null
  return { sides, defaultSide }
}

export interface TripDraft {
  trip_id: number | null
  cost_center: string
  fiscal_year: number
  traveler_empcode: string
  destination: string | null
  country_group: 1 | 2 | 3
  /** Generated ONCE when the new-trip card is created (one per create
   * intent, kept across error retries so the server dedups); null for an
   * existing trip — the server never dedups an edit. */
  client_token: string | null
  days: number
  travel_months: string[]
  project: string | null
  purpose: string | null
  /** null = the ฝ่าย has no travel history and the user has not picked yet
   * — save is blocked until set (never a silent default). */
  side: TripSide | null
  expected_updated_at: string | null
}

/** `side` comes from `deriveTravelSideHistory(...).defaultSide` — never a
 * hard-coded value: the caller must state what the ฝ่าย's history says
 * (null when there is none). */
export function blankTripDraft(costCenter: string, fiscalYear: number, side: TripSide | null): TripDraft {
  return {
    trip_id: null,
    cost_center: costCenter,
    fiscal_year: fiscalYear,
    traveler_empcode: '',
    destination: null,
    client_token: crypto.randomUUID(),
    country_group: 1,
    days: 0,
    travel_months: [],
    project: null,
    purpose: null,
    side,
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
    client_token: null,
    country_group: item.country_group,
    days: item.days,
    travel_months: item.travel_months,
    project: item.project ?? null,
    purpose: item.purpose,
    side: item.side,
    expected_updated_at: item.updated_at,
  }
}

export function buildTripPayload(draft: TripDraft): TripInput {
  const { side, ...rest } = draft
  if (side === null) throw new Error('trip side unset — validateTripDraft must pass before building the payload')
  return { ...rest, side }
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
  if (draft.side === null) return { ok: false, errorTh: 'กรุณาเลือกฝั่งบัญชี' }
  // country_group is derived from the picked destination (the manual group
  // select is gone) — a blank destination would silently book the domestic
  // per-diem rate, the exact wrong-group bug this dropdown exists to prevent.
  if (!draft.destination) return { ok: false, errorTh: 'กรุณาเลือกปลายทาง' }
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
