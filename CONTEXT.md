# CONTEXT — Budget Management Web (CMAN)

Glossary of the ubiquitous language for this project. Definitions only — no implementation
detail. Updated during grilling sessions as terms are sharpened.

## Terms

### Cost Center (CC)
Uppercase alphanumeric SAP code, the atomic unit of budget ownership and Row-Level
Security. Usually 10 chars (e.g. `10CS000000`) but **not always** — short codes exist
(`PBAW01`, `KKAW01`, `CMRY01`). Validate a CC by **existence in the cost-center master**,
never by length. Every budget row, access check, and submit scope resolves to a CC.

### orgcode
7-digit numeric string (e.g. `1120000`) identifying a person's org unit in the HR system
(`mas_employee_data`). Does NOT match Cost Center format — the two are bridged by the
orgcode↔CC map (file 09), which is **many-to-many**. **No longer used for RLS** (see
RLS scope) since ADR-0019 — file 09 still exists as its own admin-edited master dataset,
just not read for access resolution anymore.

### Filler
A person authorized to fill (enter numbers into) one or more Cost Centers, identified by
email and assigned **directly** in the Cost Center↔Filler map (`cc dept.xlsx`, admin-edited
Excel on SharePoint) — not derived from orgcode or ฝ่าย. A CC may have ≥1 Filler. Introduced
by ADR-0019, replacing the derived Submitter concept below for RLS purposes.
_Avoid_: "คนกรอกข้อมูล" untranslated — use Filler.

### Cost Center ↔ Filler map
Admin-maintained master table (dataset #6 of ADR-0018), synced from `cc dept.xlsx` into
Fabric (`cman-dw-ws` / `modern_lh_cman_dw`). One row per Cost Center; its Filler column
holds ≥1 email, comma-separated. Single source of truth for both See-scope and Fill-scope
(ADR-0019) — a CC with zero Fillers has **no owner**: nobody can fill or see it until an
email is added to that row (there is no automatic admin-fallback ownership; the general
`ADMIN_EMAILS` overlay still exists per ADR-0012 but empty CCs are not specially routed to it).

### RLS scope (Row-Level Security)
The set of Cost Centers a logged-in user may **see**. Resolved (per ADR-0019) as:
`(CC↔Filler map → this user's CCs) ∪ (CC↔Filler map → each of those CCs' Fillers' direct
manager's CCs) ∪ admin-overlay`. In plain terms: you see the CCs you fill, plus the CCs
filled by anyone whose direct manager you are. To fix a wrong permission, edit the CC↔Filler
map (`cc dept.xlsx`) — never hard-code.
(Superseded & dead: the orgcode↔CC-map union design of ADR-0001/ADR-0007, the single-chain
orgcode-only design, the `get_visible_ccs` string-prefix design, and `capps_m_employee`.)
**Seeing a CC ≠ being able to fill it** — see Filler and See-scope vs Fill-scope.

### Submitter
A user allowed to **fill and submit** budget. **Since ADR-0019, "allowed to fill" =
listed as a Filler for that CC in the Cost Center↔Filler map — full stop.** Confirmed
2026-07-11: the old L3/L4/special-L2 actor-table role gate is gone; there is no separate
HR-level check layered on top. Being listed in the Filler map IS sufficient to fill,
regardless of position level. The approval unit a submitter acts on is still one
`(ฝ่าย/department, fiscal_year)` (ADR-0008, unaffected by ADR-0019) — the UI batches all
CCs of a ฝ่าย into one "report"-style submit/approve. A submitter spanning multiple ฝ่าย
submits each ฝ่าย separately (N units).

### See-scope vs Fill-scope
- **Fill** = the CCs where the user's email is listed as a **Filler** in the Cost
  Center↔Filler map (ADR-0019). Replaces the old `ฝ่าย → file02 → cost_center` derivation.
- **See** = **a CC's Filler(s) ∪ each Filler's direct manager's CCs** (ADR-0019) —
  `mas_employee_data.managerempcode` looked up per Filler. Replaces the old
  `(orgcode → file09 → CC) ∪ (ฝ่าย → file02 → CC)` union. The invariant **FILL ⊆ SEE**
  still holds (a Filler always sees their own CC).
- Seeing a CC does NOT grant filling it (fill = listed as that CC's Filler; a Filler's
  manager sees but does not fill, unless also separately listed as a Filler).

### ฝ่าย (department)
The department grouping of a Cost Center. Single source = file 09's `Cost Center Name`
(equals the cost-center master's `ฝ่าย`). Drives Fill-scope. Distinct from สายงาน
(division) and from a CC's `Description` (its own name).

### Admin
A small allowlist of budget-dept users (checked against `ADMIN_EMAILS`). Sees ALL Cost
Centers as a role overlay sitting OUTSIDE the file-09 map. **The admin check runs BEFORE the
mas-membership gate** — an admin with no `mas_employee_data` row (e.g. an external/outsourced
member like jakkaritw) is still allowed in and never hits the "not in HR → blocked" path. Can
edit any CC's Pending budget. Also the fallback filler for **orphan ฝ่าย** (a ฝ่าย with CCs but
no submitter — 8 ฝ่าย/10 CC: CFO, COO, Company Secretary, General, KK/PBB Factory-node,
Security KK/TK).
**Edit any Pending, always; Submit = direct APPROVED, narrowly (ADR-0012, supersedes ADR-0009's
admin-submit):** an Admin may **edit** any CC's Pending at any time (oversight), but may **Submit**
only (a) **orphan ฝ่าย** during the open cycle, and (b) **any ฝ่าย after the deadline** (cycle
closed, admin is the only operator — also resolves the post-deadline deadlock). When an admin
Submits, the budget goes **straight to `APPROVED` — NO approval chain** (no managerempcode, no
Nipaporn/Waraporn, no admin-loop). Admin **cannot** Submit a normal owned ฝ่าย while the cycle is
open (only edit it). Logged `ADMIN_OVERRIDE`. Submit/approve act on the whole `(ฝ่าย, year)` block.
`board_budget` file sync (SharePoint drop, ADR-0021) is the admin's separate lane (unaffected by the lock).
**jakkaritw** = external (Data-Analytics) admin with no `mas_employee_data` row, but a **FULL
production admin** — MAY Submit→APPROVED like the budget authorities (decided 2026-06-13, ADR-0012:
internal tool, trusted; no separate system-vs-budget admin tier). In the mockup jakkaritw is a
`superTest` persona that can Submit any ฝ่าย.

### Turn
The period during which one ฝ่าย's approval sits with one approver — from the moment the
step opens (submit, or the previous step being actioned) until that approver approves or
rejects. "Whose turn is it" is always exactly one person: the frozen occupant of the current
`PENDING_APPROVER1/2/3` step. A turn has no deadline of its own.

### Turn reminder
The repeat nudge sent to the approver whose Turn has gone unactioned — every 7 days, one
mail per person listing every ฝ่าย waiting on them, **repeating indefinitely** until they act
(ADR-0027). Distinct from the **Deadline reminder**, which goes to Fillers who have not
submitted yet and stops when the cycle closes.
_Avoid_: calling either one "escalation" — a reminder never moves a budget.

### Step override
An Admin advancing a stuck approval **one step** without being its frozen approver
(ADR-0027). Position 1 only, available immediately, no reason required, logged with the
acting admin's real email, and it can never land final `APPROVED`. Replaced the retired
auto-escalation below.
_Avoid_: "approve on behalf" — the admin is not approving the budget, only releasing the
step so the chain continues to the real reviewers.

### Auto-escalation — RETIRED 2026-08-01
The former rule where a step untouched for 30 days was advanced by a scheduled job and
logged `AUTO_ESCALATE`. Deleted with ADR-0027; nothing in the system now moves an approval
without a human action. Kept here only so the term is recognised in old documents — do not
reintroduce it as a synonym for Step override or Turn reminder.

### SAP / Actuals
Read-only realised spend, read live (read-through) from the central DW gold warehouse
`cman_dw_wh_gold.gold.fact_gl_trans` (workspace `cman-dw-prod-ws`), pre-aggregated
DW-side and merged into the page by the backend (ADR-0020 — supersedes the older
`gold_sap_gl_trans` app-Lakehouse reference). Shown green. Nobody types it.

### Approved budget — code name `board_budget`
Board-approved budget owned by the budget dept. Arrives as **one Excel file per year**
(`approved_budget_<year>.xlsx`, year taken from the filename) dropped on SharePoint and
synced whole-year Replace-by-Year (ADR-0021 — replaces the old in-app `.csv` upload) —
**web entry/editing disabled entirely** (confirmed 2026-06-12); it goes **straight to
the DB with NO in-app approval loop**. Shown blue. The UI/sign-off label
stays "Approved · งบ" (stakeholders signed off), but **code, tables and columns use
`board_budget`** to avoid the back-to-front confusion (this "Approved" never passes the
in-app workflow). NOT a snapshot of Pending — a separate dataset Budget dept adjusts
offline from the user-fill data (requested vs granted).

### Pending budget — code name `pending_budget` (renamed from `working_budget` 2026-06-12)
User-entered monthly budget (Jan–Dec) per CC × GL. Shown black/dark. The ONLY data that
travels the in-app **approval chain** (Submitter L3/L4 → managerempcode → Nipaporn → Waraporn).
UI/sign-off label stays "Pending · รออนุมัติ"; **code uses `pending_budget`**.
(ADR-0003/0005/0006/0008 say `working_budget` — same table, old name; ADRs are immutable.)
Two entry doors, `template` flag: `USER` (Template 1.1, full chain) / `ADMIN` (Template 2,
Budget dept, submit = APPROVED instantly). Rows stay here permanently after approval —
no conversion into `board_budget`.

### Transaction (main-table row)
One row group in the main budget table = a single `(cost_center, gl_account, fiscal_year)`
triple, showing its three layers (SAP / Approved / Pending) stacked. The UI/code call it a
"transaction" (the `+ เพิ่ม transaction` button adds one), but it is a **budget line**, NOT an
accounting posting. Adding one for a Special-GL group routes that GL into its subform / Trip
Manager (see Special GL group). Stored across `pending_budget` / `board_budget` keyed by the
same triple.

### Row visibility (which GL rows appear)
**SAP Actuals are the leader.** On first open, the table shows the `(cost_center, gl_account,
fiscal_year)` rows that have a SAP actual that year — Approved/Pending appear alongside, waiting
to be filled. A row also appears if it has data in EITHER of the other two layers, so the
effective visible set for a CC × year is the **union of three sources**:
- **SAP actual** rows (the leader / most common initial source), `fact_gl_trans` (ADR-0020);
- **Approved** rows — incl. a brand-new GL or CC introduced by an Approved file import that has
  no SAP actual: the imported row still shows (Approved filled · SAP empty · Pending waiting);
- **Pending** rows — incl. a GL **or CC** the user added by hand with `+ เพิ่ม transaction`
  (picks CC + GL freely from the cost-center / GL masters, within fill-scope).

Once a row exists in ANY layer it **persists** and reappears on later opens (else entered or
imported budget would vanish). "No SAP actual" is just one reason a GL must be added by hand —
not the whole rule. RLS still applies to every source (a user sees only their own CCs).

"Has a SAP actual" means **at least one individual month is non-zero** (per-month rule,
2026-08-11, ADR-0010 amendment). A key where every month nets to exactly 0.00 — e.g. an
accrual and its reversal posted in the same month — is noise and stays hidden (unless an
Approved/Pending row exists). A pair that crosses months (e.g. accrual +13,150 in March,
reversal −13,150 in April) shows BOTH legs, matching SAP's posting-period view.

### Detail line (subform line)
One row a user enters inside a Special-GL subform — its own monthly amounts plus
group-specific metadata. The main-page Pending cell for that GL is the read-only SUM
of its detail lines. Lives in the detail layer, below the aggregate `pending_budget`.

### Trip
A single planned journey in Travelling Expense — one traveler, destination, day-count,
and the months it spans, entered once. The four Travelling expense types (per-diem,
transport, lodging, other) are separate GLs whose detail lines all reference the same
trip; per-diem is auto-calculated from the trip. A trip is a detail-layer concept only —
never shown on the main page.

### Schema namespaces (Fabric SQL DB)
- `dbo` — read-only sync data; written by scripts/pipelines, app only reads
  (e.g. `mas_employee_data` synced daily from C-POP, `gold_*`).
- `cfg_master` — config/master tables admin edits in-app (small reference sets,
  e.g. `gl_group_mapping`, `orgcode_costcenter_map`).
- `budget` — transactional budget data the user writes through the app
  (`pending_budget`, `board_budget`, `approval_status`, `approval_log`).

### Special GL group
A GL group whose Pending amount is NOT typed monthly but produced by a detail subform
(button "+ ใส่รายละเอียดงบทำการ"); the summed total flows back read-only. Six groups —
Travelling Expense (per-diem engine), Entertainment, Lease & Rental, Professional & Legal
Fee, Public Relation & Donation, Training & Seminar. See spec doc 02.

### Login session
The period during which a logged-in user may use the app without authenticating again.
**Fixed-length, not sliding**: it is counted from the moment of login and is NOT extended
by activity — 14 hours since ADR-0028 (previously 8). When it ends the user is not logged
out mid-action by the app; the next request the app makes simply fails, and the app then
shows the session-expiry dialog. Distinct from "the server is down" and from "the network
is offline" — all three look similar to the user and must be worded differently.
_Avoid_: "token หมดอายุ" for this — the user-facing concept is the session, and the
service-principal token the backend uses to reach the database is an unrelated thing that
renews itself.

### Draft (unsaved input)
Numbers a user has typed into the grid or a subform but has not yet saved. Not yet budget
data — nothing downstream sees it, and it belongs to no layer (Approved / SAP / Pending).
A draft lives only in the open page: it is **not** persisted anywhere and does **not**
survive a session expiry, a reload, or a closed tab (ADR-0028 — the loss was priced and
accepted rather than designed around). Saving is what turns a draft into budget data.
