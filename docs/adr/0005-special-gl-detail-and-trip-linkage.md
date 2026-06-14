# 5. Special-GL subform detail layer + Travelling trip linkage

Date: 2026-06-06
Status: Accepted
Extends: ADR-0003 (budget data model)

## Context

ADR-0003 modelled `working_budget` as one aggregated row per
`(cost_center, fiscal_year, gl_account, month)`. But Special GL groups (the six that
open "+ ใส่รายละเอียดงบทำการ") are entered through a subform with **multiple detail
lines per GL** (e.g. several trips, several lease items), each carrying group-specific
metadata (dropdowns/free-text) and its own monthly amounts. A single aggregated cell
cannot persist those lines, so reopening a subform would lose what the user typed.

Travelling Expense adds a twist: the 2026-06-05 redesign stores it as **8 GLs
(4 expense types × 2 accounting sides), 1 GL = 1 type**, each its own main-page row.
The non-per-diem types (พาหนะ/ที่พัก/อื่น) are different GLs from เบี้ยเลี้ยง, so the
DB needs a way to know that a พาหนะ line and a เบี้ยเลี้ยง line belong to the **same
trip** — both for the per-diem auto-calc and to avoid re-entering traveler/destination
in every GL's subform.

## Decision

Two layers:

- **Aggregate layer** — `budget.working_budget` (per ADR-0003), keyed
  `(cost_center, fiscal_year, gl_account, month)`. For a Special GL, this cell is a
  **read-only SUM** of its detail lines. The main page shows only this — **1 GL = 1
  row, no trip/detail concept visible** (so no conflict with the main-page model).
- **Detail layer** — `budget.working_budget_detail`: one row per subform line, tagged
  by `(cost_center, fiscal_year, gl_account)` + 12 monthly amounts + group-specific
  metadata (dropdown/free-text columns vary by group; store as typed columns or a
  small JSON/extension — to be finalised in the data model).

Travelling Expense additionally gets a **shared trip entity**:

- `budget.budget_trip` — trip header entered once: `trip_id` (PK),
  `cost_center, fiscal_year, traveler, position, destination, country_group, days,
  travel_months, purpose`.
- Each Travelling detail line references `trip_id` **and** its own `gl_account`. The
  เบี้ยเลี้ยง line is auto-calculated (`days × rate(position, country_group) × FX`,
  split evenly across `travel_months`); the other three types' lines are typed
  manually. `trip_id` lives ONLY in the detail layer — the main page never sees it.
- **Trips are created in the เบี้ยเลี้ยง (per-diem) subform.** That subform is where the
  user adds/edits trips (traveler/dest/days/months) and sees the auto-calc. The other
  three GL subforms (transport/lodging/other) only **read** those trips and type manual
  amounts against them. Ordering dependency: per-diem first (to define trips), then the
  others. If a manual subform is opened with no trips yet → prompt "เพิ่มทริปที่เบี้ยเลี้ยงก่อน".
  (A trip with zero per-diem — e.g. a C-level rate of 0 — is still defined here.)
- **Month lock follows the trip, per trip line.** In the manual subforms
  (transport/lodging/other), a trip's row is editable ONLY in that trip's
  `travel_months`; all other months are locked/greyed — exactly like the per-diem
  split. E.g. a trip in Feb only lets the user type into Feb for that traveler.

## Consequences

- Subform state persists; reopening shows prior lines/trips.
- "How does the DB know these belong together?" → `trip_id`. Re-entry of trip header
  is eliminated.
- The main page stays a pure per-GL aggregate view — the two-layer split is what keeps
  the GL-split main page and the trip-centric subform from conflicting.
- More tables than ADR-0003's two; justified — special-GL detail cannot be modelled by
  the aggregate alone. Non-trip special groups use `working_budget_detail` without
  `trip_id`.
- FX for per-diem comes from the Currency Master (Module 09, `cfg_master.master_currency_rate`,
  FY2026 = 34.20) — NOT the Excel template's hidden `B5=32` (superseded).
- Per-diem month-split rounding: each selected month gets the total floored to 2
  decimals; the **last selected month absorbs the remainder** so the 12-month sum
  equals the exact total. (DECIMAL(18,2).)
