/** Response shapes returned by the FastAPI backend endpoints this SPA calls
 * (see backend/app/routers/{me,scope,budget,budget_write,reference}.py).
 * Kept in lock-step with those Pydantic models — do not add fields
 * speculatively. */

export interface MeResponse {
  email: string
  app_env: string
}

export type ScopeRole = 'admin' | 'filler' | 'see_only' | 'none'

export interface ScopeResponse {
  email: string
  is_admin: boolean
  role: ScopeRole
  fill_cost_centers: string[]
  see_cost_centers: string[]
}

/** The 12 month cells (m01=Jan..m12=Dec) + the stored yearly total, common
 * to all 3 grid layers (backend `read_model.LayerAmounts`). */
export interface LayerAmounts {
  m01: number
  m02: number
  m03: number
  m04: number
  m05: number
  m06: number
  m07: number
  m08: number
  m09: number
  m10: number
  m11: number
  m12: number
  total_year: number
}

/** 🟢 SAP · ใช้จริง — read-only, standing year Y. */
export type SapLayer = LayerAmounts

/** 🔵 Approved · งบอนุมัติ — read-only reference, standing year Y. */
export interface BoardLayer extends LayerAmounts {
  gl_name: string | null
  gl_group: string | null
  c_level: string | null
  division: string | null
  department: string | null
}

/** ⚫ Pending · งบรออนุมัติ — the editable planning-year (Y+1) layer.
 * `updated_at` is the optimistic-lock token for `PUT /budget/rows`'
 * `expected_updated_at`; `null` means no `pending_budget` row exists yet
 * (the next save is a CREATE, not an UPDATE). */
export interface PendingLayer extends LayerAmounts {
  template: string | null
  remark: string | null
  gl_name: string | null
  gl_group: string | null
  c_level: string | null
  division: string | null
  department: string | null
  updated_at: string | null
}

/** One visible `(cost_center, gl_account)` row of the main grid — always
 * carries all 3 layers (zero-filled when a layer has no data). */
export interface BudgetRow {
  cost_center: string
  gl_account: string
  sap: SapLayer
  board: BoardLayer
  pending: PendingLayer
  editable: boolean
}

/** `GET /budget/gl-accounts` — the GL master, flagged `is_special` so the
 * "+ เพิ่ม transaction" picker can exclude the 6 special groups (ADR-0005). */
export interface GlAccount {
  gl_code: string
  gl_group: string | null
  gl_name: string | null
  is_special: boolean
}

/** `GET /scope/departments` — one row per Cost Center in the caller's scope,
 * feeds the ฝ่าย picker's สายงาน›ฝ่าย›CC hierarchy (ADR-0019). */
export interface DepartmentRow {
  cost_center: string
  department: string | null
  division: string | null
  c_level: string | null
}

/** `PUT /budget/rows` request body (`write_model.PendingRowInput`). All 12
 * months are always sent — the endpoint replaces the whole row, it does not
 * patch individual months. `expected_updated_at: null` = create a new row. */
export interface PendingRowInput {
  cost_center: string
  gl_account: string
  fiscal_year: number
  m01: number
  m02: number
  m03: number
  m04: number
  m05: number
  m06: number
  m07: number
  m08: number
  m09: number
  m10: number
  m11: number
  m12: number
  remark: string | null
  expected_updated_at: string | null
}

/** A9 special-GL detail line — `GET/PUT /budget/detail`
 * (`write_model.DetailLineInput`/`DetailLineState`, `routers/subform.py`'s
 * `DetailLineRow` for the GET shape). `detail_id: null` + no
 * `expected_updated_at` = create; both required together to update an
 * existing line (mirrors `PendingRowInput`'s create/update convention). */
export interface DetailLineInput {
  detail_id: number | null
  cost_center: string
  gl_account: string
  fiscal_year: number
  trip_id: number | null
  line_label: string | null
  meta_json: Record<string, string | null> | null
  m01: number
  m02: number
  m03: number
  m04: number
  m05: number
  m06: number
  m07: number
  m08: number
  m09: number
  m10: number
  m11: number
  m12: number
  expected_updated_at: string | null
}

export interface DetailLineState {
  detail_id: number
  cost_center: string
  gl_account: string
  fiscal_year: number
  trip_id: number | null
  gl_group: string
  line_label: string | null
  m01: number
  m02: number
  m03: number
  m04: number
  m05: number
  m06: number
  m07: number
  m08: number
  m09: number
  m10: number
  m11: number
  m12: number
  total_year: number
  meta_json: Record<string, string | null> | null
  updated_at: string
}

/** A9 Trip Manager — `POST|PUT /budget/trip` request body
 * (`write_model.TripInput`). `trip_id: null` = create. `country_group`:
 * 1=domestic, 2=asian, 3=other (matches `per_diem.py`). */
export interface TripInput {
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

/** `POST|PUT /budget/trip` success response (`write_model.TripState`).
 * `per_diem_months` is always present here (the save just derived it). */
export interface TripState {
  trip_id: number
  cost_center: string
  fiscal_year: number
  traveler_empcode: string
  traveler_name: string
  position: string
  destination: string | null
  country_group: 1 | 2 | 3
  days: number
  travel_months: string[]
  purpose: string | null
  side: 'COST' | 'SGA'
  updated_at: string
  per_diem_months: Record<string, number>
}

/** `GET /budget/trip` list item (`routers/subform.py`'s `TripRow`) —
 * per-diem is recomputed on every read (ADR-0015/0011); `per_diem_months`
 * is `null` + `per_diem_error` set when the current rate/FX config can't
 * derive it for THIS trip (never blocks the rest of the list). */
export interface TripListItem {
  trip_id: number
  cost_center: string
  fiscal_year: number
  traveler_empcode: string
  traveler_name: string
  position: string
  destination: string | null
  country_group: 1 | 2 | 3
  days: number
  travel_months: string[]
  purpose: string | null
  side: 'COST' | 'SGA'
  updated_at: string
  per_diem_months: Record<string, number> | null
  per_diem_error: string | null
}

/** `PUT /budget/rows` success response (`write_model.PendingRowState`). */
export interface PendingRowState {
  cost_center: string
  gl_account: string
  fiscal_year: number
  m01: number
  m02: number
  m03: number
  m04: number
  m05: number
  m06: number
  m07: number
  m08: number
  m09: number
  m10: number
  m11: number
  m12: number
  total_year: number
  remark: string | null
  template: string
  gl_name: string | null
  gl_group: string | null
  c_level: string | null
  division: string | null
  department: string | null
  updated_at: string
}
