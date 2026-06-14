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
orgcode↔CC map (file 09), which is **many-to-many**.

### RLS scope (Row-Level Security)
The set of Cost Centers a logged-in user may **see**. Resolved by a **union** (per ADR-0007):
`(orgcode → file09 → CC) ∪ (ฝ่าย → file02 → CC) ∪ admin-overlay`. The orgcode↔CC map
(file 09) is many-to-many and broad — one CC is reachable from many orgcodes, so higher
tiers see their subordinates' CCs too — but it must be UNIONed with the user's ฝ่าย CCs
(file 02), else ~29 users could fill a CC they cannot see (FILL ⊄ SEE). The orgcode lookup
uses **both Primary AND Acting** posstatus. To fix a wrong permission, edit file 09 / file 02
— never hard-code. (Superseded & dead: the single-chain orgcode-only design, the
`get_visible_ccs` string-prefix design, and `capps_m_employee`.)
**Seeing a CC ≠ being able to fill it** — see Submitter and See-scope vs Fill-scope.

### Submitter
A user allowed to **fill and submit** budget — the 254-person submitter set (L3 + L4 +
the 3 special L2 + Nipaporn + Waraporn), identified by role in the actor table. Filling is
gated by this role, NOT by visibility: an `approver1_only` user (L1/L2 manager) can SEE a
CC to approve it but the fill form is locked for them. The approval unit a submitter acts
on is one `(ฝ่าย/department, fiscal_year)` (per ADR-0008 — was per-CC; CC→ฝ่าย is 1:1 so
ฝ่าย is a clean partition); the UI batches all CCs of a ฝ่าย into one "report"-style
submit/approve. A submitter spanning multiple ฝ่าย submits each ฝ่าย separately (N units).

### See-scope vs Fill-scope
- **Fill** = the CCs of one's own **ฝ่าย (department)** — `ฝ่าย → file02 → cost_center`.
  A submitter's ฝ่าย comes from the curated `user_fill_dept` map (empcode → ฝ่าย).
- **See** = **`(orgcode → file09 → CC) ∪ (ฝ่าย → file02 → CC)`** — orgcode access UNION
  your ฝ่าย's CCs. The union guarantees the invariant **FILL ⊆ SEE** (you always see what
  you can fill); without it, file09 and file02 diverge and ~29 users could fill unseen CCs.
- Seeing a CC does NOT grant filling it (fill is the narrower ฝ่าย set, role-gated).

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
`board_budget` CSV import/export is the admin's separate lane (unaffected by the lock).
**jakkaritw** = external (Data-Analytics) admin with no `mas_employee_data` row, but a **FULL
production admin** — MAY Submit→APPROVED like the budget authorities (decided 2026-06-13, ADR-0012:
internal tool, trusted; no separate system-vs-budget admin tier). In the mockup jakkaritw is a
`superTest` persona that can Submit any ฝ่าย.

### SAP / Actuals
Read-only realised spend pulled from Lakehouse `gold_sap_gl_trans.company_curr_amount`.
Shown green. Nobody types it.

### Approved budget — code name `board_budget`
Board-approved budget owned by the budget dept. Admin imports it (`.csv` whole-year,
Replace-by-Year) — **web entry/editing disabled entirely** (confirmed 2026-06-12); it
goes **straight to the DB with NO in-app approval loop**. Shown blue. The UI/sign-off label
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
- **SAP actual** rows (the leader / most common initial source), `gold_sap_gl_trans`;
- **Approved** rows — incl. a brand-new GL or CC introduced by an Approved CSV import that has
  no SAP actual: the imported row still shows (Approved filled · SAP empty · Pending waiting);
- **Pending** rows — incl. a GL **or CC** the user added by hand with `+ เพิ่ม transaction`
  (picks CC + GL freely from the cost-center / GL masters, within fill-scope).

Once a row exists in ANY layer it **persists** and reappears on later opens (else entered or
imported budget would vanish). "No SAP actual" is just one reason a GL must be added by hand —
not the whole rule. RLS still applies to every source (a user sees only their own CCs).

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
