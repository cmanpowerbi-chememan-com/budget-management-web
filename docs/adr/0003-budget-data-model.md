# 3. Budget data model — two aligned tables, CC×year approval unit

Date: 2026-06-06
Status: Accepted
Supersedes: the Azure-SQL `db/schema.sql` (division-based 4-level chain — now stale)

## Context

`db/schema.sql` modelled budget on Azure SQL with a single `budget_submissions`
table and a division-based approval flow (`PENDING_VP → PENDING_BUDGET_STAFF →
PENDING_MANAGER`, `approval_status` unique on `(fiscal_year, division)`). The project
has since: dropped Azure SQL for **Fabric SQL DB**; replaced the division chain with
a **per-person `managerempcode`** chain (Submitter → managerempcode → Nipaporn →
Waraporn); and made everything **Cost-Center-centric** (RLS, submit scope, dedup all
key on `cost_center`). The schema no longer matches, and it has nowhere to store the
board-approved (import) budget, whose lifecycle differs entirely from user-entered
budget.

## Decision

- **Schema namespace `budget.*`** in Fabric SQL DB — a NEW schema, distinct from
  `dbo` (read-only sync data: mas_employee_data, gold_*) and `cfg_master` (admin-edited
  config/master). Budget is high-volume transactional user data, a third category.
- **Two tables, identical column layout**: `budget.working_budget` (UI "Pending") and
  `budget.board_budget` (UI "Approved"). Same columns (CC, gl_account, gl_name, gl_group,
  c_level, division, department, remark, fiscal_year, m01–m12, total_year,
  `budget_type`) so a future merge is a trivial UNION.
  - `working_budget`: has `status`, travels the approval chain.
  - `board_budget`: no status, no approval; admin import direct-to-table with
    control columns `_load_dt`, `_load_dttm`, `_user`; **Replace-by-Year** on import.
- **Wide format, row key = `(cost_center, gl_account, fiscal_year)`** with 12 monthly
  amount columns `m01`–`m12` in one row (NOT one row per month). Both tables share this
  shape — matches the Approved export/import CSV (jan–dec as 12 columns) and keeps the
  two tables mergeable. No empcode/orgcode in the key; one CC = one budget set.
- **Concurrency = optimistic lock** (decided 2026-06-07, supersedes the earlier
  last-write-wins). On save, the app checks `_updated_at` against the value loaded; if it
  changed, reject with "someone edited — reload". Protects the multi-owner CC case (two
  people owning the same CC editing the same `(cc, gl, year)` row). No extra schema —
  `_updated_at` already exists.
- **Monthly amounts (`working_budget`) must be ≥ 0** (forward plan; app validation).
  `board_budget` mirrors whatever the admin CSV holds (admin authority — may differ).
- **`total_year` is NOT stored** — computed on read (`SUM(m01..m12)`); the frontend
  already auto-sums. Removes drift risk; no persisted/computed column needed.
- **Approval `status` lives ONLY on `approval_status`** (keyed `(cost_center,
  fiscal_year)`), NOT denormalised onto `working_budget`. GL rows join by cc+year. One
  approval unit covers ALL GL rows of that CC+year (package approval — no GL in the key).
- **Approval status enum = neutral** `DRAFT → PENDING_APPROVER1 → _2 → _3 → APPROVED /
  REJECTED` — not tied to person names (people change; approver1 = the submitter's
  `managerempcode`, different per submitter). Who each approver is + special-case skips
  (Nipaporn/Waraporn self-submit, C-level) live in **backend routing, not the schema**.
- **Approved import (`board_budget`) — validate-then-replace, atomic:**
  - Export filename = `approved_budget_{yyyy}.csv`; `{yyyy}` comes from the year filter
    (forced single year — no "all"). The CSV `year` column must equal the filename year
    AND be the same for every row; mismatch → reject the whole file.
  - Validate ALL rows first (numeric amounts, `cost_center` + `gl_code` exist in master,
    single consistent year). Any bad row → reject the entire file with an error report;
    nothing is written.
  - Then **Replace-by-Year inside one transaction**: `DELETE WHERE fiscal_year = X`
    then bulk `INSERT`; on any failure → rollback (the year's data is never left
    half-deleted). Row identity in the file = `(cost_center, gl_code, year)`.
  - **Trust only the source columns** `cost_center, gl_code, remark, year, m01–m12`.
    The five derived columns in the CSV (`gl_name, gl_group, c_level, division,
    department`) are **re-derived from master** at import (lookup by cost_center +
    gl_code) and the file's values discarded — they drift if admin edits the CSV or
    master changed since export (observed in the sample: gl_group mixes Thai/English,
    c_level is "C-1/C-2" vs master full text).
  - Validate `cost_center` and `gl_code` **by existence in master**, NOT by string
    shape — cost centers are not always 10 chars (e.g. `PBAW01`, `KKAW01`, `CMRY01`).
  - Read the file as **`utf-8-sig`** (it has a BOM); use a real CSV parser (fields may
    be quoted / contain commas). Amounts: DECIMAL(18,2), reject non-numeric.
  - **Import is the round-trip of Export.** Locate the needed columns **by header
    name**, take only `cost_center, gl_code, remark, year, m01–m12`, and **ignore
    everything else** — the derived columns, any extra columns, and any stray cells the
    admin scribbled outside the table area (scratch math, notes) are silently dropped,
    NOT rejected. Reject only when a **required** column is missing or a value is
    invalid (year mismatch, non-numeric amount, cc/gl not in master).
    Provenance ("came from the Export button") cannot be cryptographically enforced;
    only admins reach Import, and only the known columns are ever read.
- **Approval unit** = `(cost_center, fiscal_year)`; `approval_status` PK on that.
  **⚠️ SUPERSEDED by ADR-0008: approval unit is now `(ฝ่าย/department, fiscal_year)`** —
  `approval_status` PK = `(ฝ่าย, fiscal_year)`. The per-CC machinery below is obsolete.
  A user owning multiple CCs submits per CC (N approval records). For a multi-owner
  CC, the **last submitter is the owner of record** and the chain routes to their
  `managerempcode`; re-submit replaces the approval record.
- Keep `approval_log` (append-only history). Drop `user_division_map` /
  division-based `approval_status`.

## Consequences

- Clean lifecycle separation (board never touches the approval engine) without
  schema divergence — merge stays cheap.
- Optimistic locking trades a tiny bit of friction (a rare "reload" prompt) for never
  silently losing a co-owner's edit. `_user`/`_updated_at` also serve audit.
- `db/schema.sql` is rewritten/retired; no Azure SQL dependency remains.
