/** GL-conditional dropdown option sets for the special-GL detail subforms
 * (ADR-0005, `docs/13Template Special/_dropdown_summary.md`).
 *
 * Entertainment + Lease & Rental MUST mirror `backend/app/special_gl.py`'s
 * validation exactly (`glDropdownConstants.test.ts` asserts parity against
 * the SAME fixture file the backend's `test_special_gl_fixture_parity.py`
 * checks: `docs/reference/special-gl-dropdown-fixture.json`) — the UI must
 * never offer/submit a value the server will reject.
 *
 * Training & Seminar's Method dropdown is NOT in that fixture: `special_gl.py`
 * does not validate it server-side (free-form `meta_json` — A5 gate flagged
 * this as non-blocking). It stays here as a UI-only convenience list so
 * users don't free-type "Inhouse"/"Public" inconsistently, but a mismatch
 * here would only affect UX, never cause a 400 from the server. */

export const ENTERTAINMENT_EXTERNAL_GLS = ['5211900030', '6211900030'] as const
export const ENTERTAINMENT_INTERNAL_GLS = ['6211900031'] as const
export const ENTERTAINMENT_EXTERNAL_VALUES = ['Customer', 'Business partner', 'หน่วยงานราชการ', 'อื่นๆ'] as const
export const ENTERTAINMENT_INTERNAL_VALUES = ['พนักงานบริษัท', 'กรรมการบริษัท'] as const

export const LEASE_VEHICLE_SUFFIX = '060'
export const LEASE_MACHINERY_SUFFIX = '030'
export const LEASE_NONVEHICLE_SUFFIXES = ['010', '020', '040', '050', '999'] as const

export const LEASE_VEHICLE_TYPES = ['Car', 'Van', 'Trucks'] as const
export const LEASE_MACHINERY_TYPES = [
  'Mobile Scalper', 'Dumper', 'Tractors', 'Backhoe', 'Forklift', 'Tractor',
  'Excavator', 'Loader', 'Crane', 'Water Truck', 'Road Sweeper Truck',
] as const
export const LEASE_PLANTS = ['BK', 'TK', 'KK', 'PB', 'RY'] as const
export const LEASE_PLATES = [
  '6ขผ-3918', '1นจ-3508', '6ขจ-3513', '5ขง-5712', '1นจ-1468', '6ขผ-8150', '7ขถ-9660', 'ไม่ระบุ',
] as const

/** UI-only — not backend-validated (see file docstring). */
export const TRAINING_METHOD_VALUES = ['Inhouse', 'Public'] as const

/** Travelling Expense — 8 GL = 4 types x 2 sides (mirrors
 * `write_model.TRAVEL_GL_BY_TYPE_SIDE` exactly; parity-tested below). Trip
 * Manager needs this to know which GL's detail lines to fetch/save for the
 * 3 manual expense types (per-diem is never addressed via `/budget/detail`
 * — it is system-managed via `/budget/trip` only, ADR-0005). */
export const TRAVEL_GL_BY_TYPE_SIDE = {
  per_diem: { COST: '5210400010', SGA: '6210400010' },
  transport: { COST: '5210400020', SGA: '6210400020' },
  accommodation: { COST: '5210400030', SGA: '6210400030' },
  other: { COST: '5210400999', SGA: '6210400999' },
} as const

export type TravelExpenseType = keyof typeof TRAVEL_GL_BY_TYPE_SIDE
/** The 3 manually-entered types (per-diem is auto, handled by TripManager
 * directly via its per_diem_months, never through /budget/detail). */
export const MANUAL_TRAVEL_TYPES: readonly Exclude<TravelExpenseType, 'per_diem'>[] = [
  'transport', 'accommodation', 'other',
]
export const TRAVEL_TYPE_LABEL_TH: Record<TravelExpenseType, string> = {
  per_diem: 'เบี้ยเลี้ยง',
  transport: 'ค่าพาหนะเดินทาง',
  accommodation: 'ค่าที่พัก',
  other: 'ค่าใช้จ่ายเดินทางอื่น',
}
