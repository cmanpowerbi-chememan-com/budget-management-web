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

/** 🟢 SAP · ใช้จริง — read-only, standing year Y.
 *
 * ADR-0026: a month whose SAP postings are not complete yet arrives as
 * `null`, nulled server-side — the grid renders it as a muted en-dash, never
 * as 0 (a month is still gaining month-close entries for ~23 days after it
 * ends, so an early figure reads several times too low). `total_year` covers
 * the VISIBLE months only, so it always reconciles with the cells on screen.
 *
 * `has_actuals` = this (cost_center, gl_account) has at least one non-zero
 * month in the full year, hidden months included. It is the ONLY thing the
 * client learns about a hidden month (never the amount) and exists so
 * delete-eligibility ("a row with SAP history was not added on the web")
 * keeps working while months are nulled. */
export interface SapLayer {
  m01: number | null
  m02: number | null
  m03: number | null
  m04: number | null
  m05: number | null
  m06: number | null
  m07: number | null
  m08: number | null
  m09: number | null
  m10: number | null
  m11: number | null
  m12: number | null
  total_year: number
  has_actuals: boolean
}

/** `GET /budget/sap-coverage?year=` (`app.sap.SapCoverage`) — how fresh the
 * SAP layer is (ADR-0026). `fiscal_year` is the SAP layer's own year
 * (planning year - 1); `watermark_date` is the newest SAP *entry* date
 * loaded in the warehouse, i.e. "ข้อมูลคีย์ถึง". Month numbers are 1..12. */
export interface SapCoverage {
  fiscal_year: number
  watermark_date: string
  visible_months: number[]
  hidden_months: number[]
}

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
 * "+ เพิ่ม transaction" picker can exclude the 6 special groups (ADR-0005).
 *
 * `edit_by` (GL edit_by admin-only lock, design v2, flag-gated): only
 * present when the backend flag is on. A non-admin caller never receives a
 * row where this would be `'admin'` — those GLs are stripped server-side
 * (secret), so no frontend hiding logic is needed; only an admin caller
 * ever sees `'admin'` here. */
export interface GlAccount {
  gl_code: string
  gl_group: string | null
  gl_name: string | null
  is_special: boolean
  edit_by?: 'user' | 'admin'
}

/** `GET /scope/departments` — one row per Cost Center in the caller's scope,
 * feeds the ฝ่าย picker's สายงาน›ฝ่าย›CC hierarchy (ADR-0019). */
export interface DepartmentRow {
  cost_center: string
  department: string | null
  division: string | null
  c_level: string | null
}

/** `GET /reference/travelers?cost_center=` — traveler picklist scoped to the
 * cost center being edited (its Filler(s) + manager chain, `position`
 * drives per-diem). `email` (added 2026-08-04) lets the frontend combobox
 * search by email, not just name — a fallback traveler built from a trip's
 * own response (`TripState`/`TripListItem` carry no email) uses `''`. */
export interface TravelerOption {
  empcode: string
  name: string
  position: string
  email: string
}

/** `GET /reference/countries` — destination master. The API returns groups
 * 1 (domestic) and 2 (asian) ONLY; the UI appends its own "อื่นๆ (Other)"
 * → group 3 entry (see `subform/model.countryOptionsWithOther`). */
export interface CountryOption {
  country: string
  country_group: 1 | 2
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
  project: string | null
  purpose: string | null
  side: 'COST' | 'SGA'
  expected_updated_at: string | null
  /** Idempotency token for CREATE only (one per new-trip intent) — a
   * network retry / double-click with the same token returns the existing
   * trip instead of a duplicate. Ignored by the server on update. */
  client_token: string | null
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
  project: string | null
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
  project: string | null
  purpose: string | null
  side: 'COST' | 'SGA'
  updated_at: string
  per_diem_months: Record<string, number> | null
  per_diem_error: string | null
}

/** `GET/POST /approval/*` state (`app.approval.ApprovalStatusState`) — one
 * `(department, fiscal_year)` approval record. `status=DRAFT` with every
 * other field `null` means "never submitted" (no DB row yet), not a 404. */
export interface ApprovalStatusState {
  department: string
  fiscal_year: number
  status: 'DRAFT' | 'PENDING_APPROVER1' | 'PENDING_APPROVER2' | 'PENDING_APPROVER3' | 'APPROVED' | 'REJECTED'
  submitter_empcode: string | null
  submitter_email: string | null
  submitted_at: string | null
  approver1_empcode: string | null
  approver1_actioned_at: string | null
  approver2_actioned_at: string | null
  approver3_actioned_at: string | null
  reject_reason: string | null
  rejected_by_empcode: string | null
  updated_at: string | null
  current_position: 1 | 2 | 3 | null
  current_approver_empcode: string | null
  /** Thai display name of the current approver (server-side lookup, ADR-0027)
   * — the override confirm dialog must NAME the approver being skipped. */
  current_approver_name: string | null
  can_act: boolean
  notification_warning: string | null
}

/** `GET /approval/pending-for-me` (`routers/approval.PendingForMeResponse`)
 * — the รออนุมัติ badge data source: departments where the CALLER is the
 * frozen current approver, for one fiscal_year. */
export interface PendingForMeResponse {
  departments: string[]
}

/** `GET /approval/locked-departments` (`routers/approval.LockedDepartmentsResponse`)
 * — "+ เพิ่ม Transaction" lock-awareness (2026-08-08 bug fix): every
 * department, among the CALLER's OWN Fill-scope departments, whose approval
 * status is currently locked (ADR-0013) for one fiscal_year. */
export interface LockedDepartmentsResponse {
  departments: string[]
}

/** `GET/POST /attachments*` (`routers/attachments.py`) — SharePoint file
 * metadata, no local DB row (the folder path is the index, spec R1). */
export interface AttachmentInfo {
  item_id: string
  name: string
  size: number
  created_by: string | null
  created_at: string | null
  web_url: string | null
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
