# 23. One Fabric SQL Database, two schemas (`budget.*` + `dbo.*`) — DB1 retired

Date: 2026-07-14
Status: Accepted
Supersedes: the two-DB split of ADR-0022 (separate app DB vs DW DB) and the app-DB **name** of
ADR-0017 (`budget_management_web`). ADR-0017's Fabric-SQL-over-Azure-SQL choice still stands —
only the database identity changes.

## Context

Earlier today (2026-07-14) the store was modelled as TWO Fabric SQL Databases: an **app DB1**
`budget_management_web` (db id `036a3270`) holding the transactional tables, separate from the
**DW DB2** `fabric_sql_database` (db id `a42ef9f3`) holding the synced masters + `employee_master`.
That forced the app to open two Fabric SQL connections and to merge `board_budget` +
`pending_budget` + `cc_filler_map` **across two databases in FastAPI**, on top of the SAP
cross-store merge.

The DW's `fabric_sql_database` (workspace `cman-dw-ws`, ws id `adeb7108…`, db id `a42ef9f3…`)
already holds the synced masters and `employee_master` in `dbo`, and SP `cman-fabric-write`
already has R/W there (it runs the syncs). Keeping a second app database buys nothing and adds a
cross-DB merge to the hottest read path.

## Decision

Consolidate to **ONE** Microsoft Fabric SQL Database = **`fabric_sql_database`** (DW workspace
`cman-dw-ws`, ws id `adeb7108…`, db id `a42ef9f3…`). Inside that ONE database, **TWO schemas**:

- **`budget.*`** — the 5 TRANSACTIONAL tables the app WRITES: `pending_budget`,
  `pending_budget_detail`, `budget_trip`, `approval_status`, `approval_log`.
- **`dbo.*`** — the synced READ-ONLY reference already live there (verified against the live
  `dbo` 2026-07-14): `board_budget`, `submission_deadline`, `cc_filler_map`, `per_diem_rate`,
  `country_group`, `master_currency_rate`, `gl_group`, `hide_document`, `employee_master`
  (+ `employee_master_stg`), plus two employee VIEWS — `v_employee_primary` (Primary-row →
  RLS See-manager + approver1 resolution) and `v_employee_budget_01` (project-filtered employee
  scope, ~344). **`orgcode_cost_center` is NOT present** — app-unused per ADR-0019, never synced.

## Consequences

1. **DB1 `budget_management_web` (`036a3270`) is RETIRED / unused** — the app no longer connects
   to it. No infra is deleted; it is documented as retired only.
2. **env re-point:** `FABRIC_SQL_SERVER` / `FABRIC_SQL_DATABASE` now point to `fabric_sql_database`
   (the DW SQL DB) — the same connection `NB_employee_sync.py` uses. The exact FQDN comes from the
   DATA team / that notebook; do NOT invent a host string. Config change only (no `.env` edited here).
3. The app now uses **ONE Fabric SQL connection** (both schemas `budget` + `dbo`) + the **DW gold
   warehouse** (SAP read-through) — down from two SQL DBs.
4. The main read path `dbo.board_budget` + `budget.pending_budget` + `dbo.cc_filler_map` is now a
   **LOCAL cross-schema in-DB JOIN** (no cross-DB merge). Only **SAP (gold warehouse)** remains a
   cross-store merge in FastAPI.
5. SP `cman-fabric-write` already has R/W to `fabric_sql_database` (it runs the syncs), so the app
   writes `budget.*` there with no new grant.
6. **Supersedes** the two-DB split of ADR-0022 (transactional in DB1, masters in DB2) and the
   app-DB **name** of ADR-0017. No FK across the `budget`↔`dbo` schemas (validated at the app
   layer), same as before; the SAP warehouse join stays cross-store.
