/** Pure logic for the A9 special-GL detail subforms + Trip Manager — no
 * DOM, no fetch. Field specs mirror `backend/app/special_gl.py`'s
 * GL-conditional validation exactly (parity-tested against the shared
 * fixture in `glDropdownConstants.test.ts`), so the UI never offers/submits
 * a value the server will reject (A9 never-cut). */
import type { CountryOption, DetailLineInput, DetailLineState, TravelerOption, TripInput, TripListItem } from '../api/types'
import { MONTH_KEYS, type MonthKey } from '../grid/model'
import {
  ENTERTAINMENT_EXTERNAL_VALUES,
  ENTERTAINMENT_INTERNAL_GLS,
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
  /** A select option that, when chosen, reveals a free-text input whose
   * typed value is what actually gets stored/sent (ทะเบียนรถ อื่นๆ → custom
   * plate; the literal trigger is never sent). The trigger itself is stored
   * only while the box is empty — `firstIncompleteField` treats that as
   * "not filled yet" the same as a blank field. */
  freeTextOption?: string
}

/** Resolves the special-GL group's detail columns for ONE gl_account —
 * Entertainment's dropdown options and Lease & Rental's dropdown/grey-out
 * both switch on the GL code (spec §4a), exactly like
 * `special_gl.validate_entertainment_meta`/`validate_lease_meta`.
 *
 * Entertainment's external/internal split reads `ENTERTAINMENT_INTERNAL_GLS`
 * — the SAME parity-tested constant `special_gl.py`'s
 * `_ENTERTAINMENT_INTERNAL_GLS` is checked against
 * (`test_special_gl_fixture_parity.py`/`glDropdownConstants.test.ts` both
 * assert it matches `docs/reference/special-gl-dropdown-fixture.json`) —
 * rather than re-deriving a `.endsWith('900031')` suffix guess. The old
 * suffix guess happened to agree with the fixture for today's 3 known GLs,
 * but a future Entertainment GL added only to the fixture (not
 * necessarily 900031-suffixed) would silently render the WRONG dropdown
 * under the guess; reading the list directly can't drift from what the
 * server actually validates. */
export function detailFieldsFor(glGroup: string, glAccount: string): DetailFieldSpec[] {
  if (glGroup === 'Entertainment') {
    const isInternal = (ENTERTAINMENT_INTERNAL_GLS as readonly string[]).includes(glAccount)
    return [
      {
        key: 'ประเภทการรับรอง',
        kind: 'select',
        options: isInternal ? ENTERTAINMENT_INTERNAL_VALUES : ENTERTAINMENT_EXTERNAL_VALUES,
      },
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
      // สถานที่ใช้งาน is the ONE field every Lease & Rental sub-category
      // renders as an enterable select (never locked) — every OTHER
      // enterable field is required too now (jakkaritw 2026-08-20,
      // firstIncompleteField below); ประเภทรถ/ทะเบียนรถ simply render
      // `locked` (never demanded) for the suffixes where they don't apply.
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

/** Whether a field can actually be interacted with for this GL — a `locked`
 * field renders as an em-dash (greyed, "ไม่ใช้กับ GL นี้") and must NEVER be
 * demanded; every other kind is enterable. The one place that answers "is
 * this field enterable" — `firstIncompleteField` below is its only caller. */
export function isFieldEnterable(field: DetailFieldSpec): boolean {
  return field.kind !== 'locked'
}

/** Whether an ENTERABLE field's current value counts as "filled": a plain
 * text/select value must be non-blank, and a free-text-behind-a-trigger
 * field (ทะเบียนรถ อื่นๆ → custom plate) must additionally not still be
 * sitting on the bare trigger literal with nothing typed into the
 * companion box — the trigger string itself is truthy, so a plain blank
 * check alone would miss that case. */
function isFieldFilled(field: DetailFieldSpec, value: string | null): boolean {
  if (!value) return false
  if (field.freeTextOption !== undefined && value === field.freeTextOption) return false
  return true
}

/** jakkaritw, 2026-08-20, verbatim: "SPECIAL FORM บังคับกรอก หรือ เลือกดรอปดาว
 * ทั้งหมด ไม่งั้น ไม่ไห้บันทึก" — every ENTERABLE field (`isFieldEnterable`)
 * must be filled/chosen before a row can save. A `locked` field is never
 * checked, because it can never be filled in the first place — that is
 * exactly what made a naive "make everything required" pass dangerous:
 * blocking on ประเภทรถ/ทะเบียนรถ would have made saving impossible for 5 of
 * Lease & Rental's 7 GL suffixes, where those two render `locked`.
 *
 * Replaces `firstBlankFreeTextField` + `firstUnselectedRequiredField` (both
 * removed) with the ONE completeness guard for every field kind;
 * `DetailFieldSpec.required` is gone too — after this change every
 * enterable field is required by default, and an audit of all 5 non-travel
 * groups (`detailFieldsFor`) found no field that still needs to opt OUT.
 * Should a genuinely optional field turn up later, that is a fresh,
 * disclosed decision (e.g. an explicit `optional` flag inverting this
 * default) — not something to pre-build speculatively now.
 *
 * Returns the first offending FIELD (not just its key) so the caller can
 * pick the right Thai verb from `kind` — "กรุณาเลือก" for a select
 * (including one stuck on a free-text trigger — it IS still an incomplete
 * select), "กรุณากรอก" for text — or `null` when the row is complete. */
export function firstIncompleteField(fields: readonly DetailFieldSpec[], meta: Record<string, string | null>): DetailFieldSpec | null {
  return fields.find((f) => isFieldEnterable(f) && !isFieldFilled(f, meta[f.key] ?? null)) ?? null
}

// ---------------------------------------------------------------------------
// Destination country options (Trip Manager) — country_group is DERIVED from
// the picked country, never chosen by hand (wrong group = wrong per-diem).
// ---------------------------------------------------------------------------
//
// 2026-08-22: until today the API only ever served groups 1 (domestic)/2
// (asian), so this module appended its own synthetic "อื่นๆ (Other)" -> group
// 3 entry (`OTHER_COUNTRY_OPTION`/`countryOptionsWithOther`, both now
// removed). The SharePoint master (country.xlsx) grew 16 real tier-3 country
// rows the same day, so the API's own `CountryOption` list is the WHOLE
// picker now — nothing left to append. `countryOptionsWithOther` would have
// become a pure identity function (`(x) => x`), so it is deleted rather than
// kept as a hollow wrapper; callers use the `CountryOption[]` from
// `fetchCountries` directly.

/** Resolves the per-diem country group for a picked destination; `null` for
 * a name outside the list (a legacy destination on an existing trip — one
 * saved under the old synthetic "อื่นๆ (Other)" option, or any country an
 * admin later removes from the master — its stored group is kept until the
 * user re-picks). */
export function countryGroupFor(options: readonly CountryOption[], country: string): 1 | 2 | 3 | null {
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

/** Reverse-lookup: which accounting side does this GL belong to, across all
 * 4 travel types (per-diem included). Trip Manager is now opened FROM a
 * specific grid row (jakkaritw, 2026-08-04 — final decision, applies to
 * every user incl. admins) and locks its side select to that row's own
 * side, so the trip's GLs always match the row the user clicked — offering
 * the other side could only create a mismatch. `null` is defensive-only:
 * every GL that can open Trip Manager (`gl_group === 'Travelling Expense'`)
 * is one of these 8, so a real caller never sees it. Replaces the old
 * ฝ่าย-booking-history heuristic (`deriveTravelSideHistory`, removed —
 * nothing needs an inferred default once the side is always known
 * up front). */
export function deriveTravelSideFromGl(glAccount: string): TripSide | null {
  for (const sides of Object.values(TRAVEL_GL_BY_TYPE_SIDE)) {
    if (sides.COST === glAccount) return 'COST'
    if (sides.SGA === glAccount) return 'SGA'
  }
  return null
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
  /** Kept nullable defensively (`validateTripDraft` still blocks save on
   * null) but in practice always set: Trip Manager locks every card — new
   * and existing — to the side derived from the GL row it was opened from
   * (`deriveTravelSideFromGl`), so a caller never has "no side yet" to
   * silently default. */
  side: TripSide | null
  expected_updated_at: string | null
}

/** `side` is the Trip Manager's locked side (`deriveTravelSideFromGl` of the
 * GL row the modal was opened from) — never a hard-coded value, and never
 * the ฝ่าย-history heuristic this used to read (removed, see
 * `deriveTravelSideFromGl`'s docstring). */
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

/** Decides whether `saveAll` writes ONE manual line, given its `dirty` flag
 * (`TripCardState.manualDirty[type]`, set by `setManualMonth`):
 * - NEW line (`detail_id === null`): write only when dirty AND non-zero —
 *   a never-persisted, all-zero line (blank, or typed then cleared back to
 *   0) is skipped, so no spurious zero row is ever created.
 * - EXISTING line (`detail_id` set): write whenever dirty, INCLUDING an
 *   edit down to all-zero — the persisted row must be zeroed server-side
 *   (never-cut: skipping it would leave a stale nonzero amount behind).
 * An untouched existing line (`dirty` false) is skipped — no needless PUT. */
export function shouldWriteManualLine(draft: ManualLineDraft, dirty: boolean): boolean {
  if (draft.detail_id === null) return dirty && manualLineTotal(draft) > 0
  return dirty
}
