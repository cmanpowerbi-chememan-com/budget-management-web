# 21. Approved budget (`board_budget`) arrives as a yearly Excel file on SharePoint — the in-app CSV import/export is dropped

Date: 2026-07-12
Status: Accepted
Amends: ADR-0003 (the board_budget **import path** only — table shape, Replace-by-Year
semantics, and web-read-only rule are unchanged). Follows the ADR-0018
Excel-on-SharePoint pattern.

## Context

The mockup (0002.2) and the transactional-model spec §1c had an admin upload a
whole-year CSV through the web app (`importCSV()` / `exportApprovedCSV()` buttons).
Changed by jakkaritw 2026-07-11/12: the budget officer now **drops one Excel workbook
per fiscal year** into SharePoint site `CMANDWPRD`, folder
`Budgeting and Management/approved budget` — the same place and working style as the
six admin master workbooks (ADR-0018), so the officer never touches the web app to
load a budget.

The real file was inspected twice via Graph (2026-07-11 and 2026-07-12, SP
`cman-fabric-write`). Between the reads the owner deliberately **deleted the in-file
`year` column** and confirmed: read columns A–N only; the year comes from the
filename.

## Decision

- **Ingest contract** (verified against the real file `approved_budget_2026.xlsx`):
  - One file per fiscal year: `approved_budget_<year>.xlsx`, in the folder above.
  - Sheet `sheet1` (single sheet); read **columns A–N only** — 14 columns:
    `cost_center, gl_code, jan, feb, mar, apr, may, jun, jul, aug, sep, oct, nov, dec`.
  - **Fiscal year is parsed from the FILENAME only**, strict pattern
    `approved_budget_(\d{4})\.xlsx` — any other name is rejected. There is no in-file
    year column to cross-check anymore, so a wrongly named file is the single
    wrong-year failure mode; the strict name gate is load-bearing and must be
    documented for the budget officer.
  - The file carries **no** gl_name / gl_group / c_level / division / department /
    remark / template columns — every dimension column on `dbo.board_budget` is
    re-derived from the masters at import (model spec §4); `remark` stays NULL.
  - **Validate ALL rows first** (CC and GL exist in masters, months numeric), then
    **Replace-by-Year** (`DELETE WHERE fiscal_year=@yr` + bulk INSERT) in ONE
    transaction into `dbo.board_budget`. Any bad row rejects the whole file.
- **Target = Fabric SQL Database, not the Lakehouse.** Decided by the READ pattern:
  board_budget is read live on every page as the blue Approved layer, joined with
  `pending_budget` on `(cost_center, gl_account, fiscal_year)` — co-locating both in
  the SQL DB keeps that join local and read-your-writes-fresh. Writing 1–3×/year is
  trivial for OLTP. The raw file on SharePoint is the audit copy; the SQL DB
  auto-mirrors to OneLake for Phase-2 analytics anyway.
- The mockup's admin **CSV import/export buttons are removed** (applied to
  `0002.2budget-export.html` 2026-07-12, replacing an in-app read-only note).
  - **IMPORT** is replaced by the SharePoint file drop above — users upload the
    yearly `.xlsx` to library **`Budgeting and Management`**, folder
    **`approved budget`** (library confirmed by the user 2026-07-12), never via the app.
  - **EXPORT** (`exportApprovedCSV`, the 21-column enriched format) is **DELETED,
    not deferred** — no consumer was identified (the ไฟล์รวม Data consolidation is
    produced OFFLINE by the Budget dept, spec §1c/§1d), so it is removed as a dead
    surface rather than re-homed. If an export is ever needed it is a fresh
    read-path feature with its own justification.
- **Sync trigger: RESOLVED 2026-07-14 — BOTH an admin "Sync now" button AND a daily
  auto-sync.** The button applies the file immediately after the admin drops it; the daily
  auto-sync is the safety net if they forget the button. A Graph change-notification webhook
  was rejected as over-engineering (public callback endpoint + subscription renewal to babysit)
  for a file that changes 1–3×/year. Both reuse the existing Azure-Functions + Graph pattern.
  (The SharePoint→Fabric MASTER syncs run daily on the SAME cadence as `employee_master`, all
  landing in `[fabric_sql_database].[dbo]` — ADR-0022.)

## Consequences

- Budget officer works entirely in Excel + SharePoint; no upload UI to build, test,
  or train. Ingestion becomes one more instance of the reusable SharePoint→Fabric
  Graph-sync pattern (shared with ADR-0018), not a bespoke web feature.
- Filename is the only year authority — operational discipline required; the reject
  message must say exactly why a file was refused.
- The inspected workbook is a 13-row / 3-CC **test artifact**: the structure is
  confirmed, production scale is not. Validate performance assumptions when the real
  file arrives.
- **Amendment 2026-08-10 (jakkaritw, after the first real 4-file load):** three ingest
  behaviors changed in the DW lane (`budget_masters_lib`, repo 19.dw, commits
  42d9d09/c9052ff/ac49872): (1) fully-empty Excel "ghost rows" are skipped with a
  counted warning instead of tripping the blank-key reject (the 2023 file carried 262
  such rows and blocked ALL years for 2 nights); (2) every month cell is quantized to
  2dp ROUND_HALF_UP at ingest so the exact-equality SUM reconcile matches DECIMAL(18,2)
  storage (sub-satang Excel float artifacts otherwise fail the whole file); (3) a row
  whose cost_center is missing from the cc_filler_map master is now skipped PER-ROW
  with its exact THB total in the run-log warning + `rows_rejected`, instead of
  rejecting the whole file — blank-key-with-value, non-numeric amounts, and bad
  filename year remain whole-file rejects. "Validate ALL rows first / any bad row
  rejects the whole file" above is amended accordingly.
- Mockup `0002.2budget-export.html` updated 2026-07-12: import/export buttons removed,
  read-only "Approved comes from SharePoint" note added, and the ADR-0014 admin-mode
  toggle (accidentally dropped with the v2.2 nav-bar rewrite) restored in the page-head.
  **Sign-off doc 01 still renders the old import/export buttons** — regenerate via
  `requirement_spec/.../signoff_spec/_build/build_main_web_app_spec.py` before the next
  sign-off round so stakeholders aren't approving dead controls.
