# 22. Master/reference data lives in the DW Fabric SQL Database (`dbo`), read cross-DB by the app

Date: 2026-07-13
Status: Accepted
Amends: ADR-0018 (the masters LAND in the DW's Fabric SQL **Database** `dbo` — the OLTP SQL DB
that already holds `employee_master` — NOT the Lakehouse `modern_lh_cman_dw`). Resolves the
"runtime read location TBD" left open in `docs/specs/budget-transactional-data-model.md`.

Amended 2026-07-14 by ADR-0023: the app DB is now `fabric_sql_database` (DW ws `cman-dw-ws`) with `budget.*` transactional + `dbo.*` synced in ONE database; DB1 `budget_management_web` retired.

## Context

All 8 admin masters are edited as Excel on SharePoint (ADR-0018) and synced to Fabric. Two
things were open: WHERE they land, and where the app READS them at runtime — RLS runs on
**every request**, so the read store must be fast (OLTP), not OLAP.

- ADR-0018 named the Lakehouse `modern_lh_cman_dw`. A Lakehouse SQL analytics endpoint is
  OLAP-shaped (cold-start + higher per-query latency) — wrong for a per-request RLS lookup.
- The DW workspace `cman-dw-ws` (`adeb7108-689b-4ba0-af1c-7648970f5581`) already has a Fabric
  SQL **Database** `fabric_sql_database-a42ef9f3-...` (OLTP) holding `dbo.employee_master`,
  `dbo.employee_master_stg`, `dbo.v_employee_primary` — which the app must read anyway for
  See-scope manager + approver1. Verified 2026-07-13: those 3 employee objects are the ONLY
  objects there today; the masters are new.

## Decision

- **Master/reference data home = `[fabric_sql_database].[dbo]` in `cman-dw-ws`** (OLTP),
  colocated with `employee_master`. Each SharePoint Excel → one `dbo.*` snake_case table:
  `dbo.cc_filler_map`, `dbo.per_diem_rate`, `dbo.country_group`, `dbo.master_currency_rate`,
  `dbo.gl_group`, `dbo.hide_document`, `dbo.orgcode_cost_center` (kept but app-unused per
  ADR-0019), plus the closing-date feeding `dbo.submission_deadline`.
- **The app reads ALL reference data (employee + masters) from `fabric_sql_database` (OLTP,
  fast).** Because `cc_filler_map` and the employee tables are in the SAME DB, the RLS
  resolution (Filler ∪ Filler's Primary-row manager) is ONE in-DB JOIN; only the final filter
  against `dbo.*` (the app's OWN Fabric SQL DB, `budget_management_web`) is cross-DB, merged
  in FastAPI — same split-connection pattern as the SAP read-through (ADR-0020).
- **Excel on SharePoint stays the EDIT surface**; `fabric_sql_database.dbo` is the synced
  READ copy (admins never touch the DB; the sync keeps it fresh).
- **Supersedes**: ADR-0018's Lakehouse landing for these masters (a OneLake/Lakehouse copy is
  optional — Phase-2 dashboard/audit only; the app does NOT depend on it); and the app's own
  `cfg_master.*` (the 3 tables from the retiring master-tables module die with it, ADR-0018).

## Consequences

- One reference DB (employee + masters), OLTP → fast per-request RLS; no cross-store hop for
  the RLS JOIN.
- The app opens a connection to the DW `fabric_sql_database` (cross-workspace) — it already
  must for `employee_master`, so this adds no new coupling; SP `cman-fabric-write` already has
  access there.
- The master sync WRITES to this SQL DB (like `NB_employee_sync`), not the DW "SharePoint CSV"
  Lakehouse lane. That lane may still land a OneLake copy for the dashboard, but the app's read
  source is the SQL DB.
- `dbo.*` transactional data stays in the app's own Fabric SQL DB; the two DBs are joined
  only in FastAPI, never in one SQL statement.
