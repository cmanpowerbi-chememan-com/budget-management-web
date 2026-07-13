# Data Pipeline Plan — feed the Budget app's stores (SEPARATE project: data pipeline / DW)

This is the **DATA half** of the budget-app build, split out because the pipelines live in the DW
project (`19.dw_jakkaritw` / cman-dw-ws) which already owns the SharePoint→Fabric syncs,
`employee_master`, and `gold.fact_gl_trans`. The APP half is `docs/BUILD_PLAN.md`.

**Goal:** land ALL reference + actuals + board data into the exact stores the app reads — so the
app can be built against ready tables. **Owner = 04-data-engineer / 02-data-modeler.**

**Source of truth:** spec `docs/specs/budget-transactional-data-model.md` §1b/§3b/§4; ADR-0018 (Excel
on SharePoint), 0019 (CC↔Filler), 0020 (SAP read-through), 0021 (board_budget), 0022 (masters home);
memory `project_sharepoint_masters_inventory`, `project_cc_dept_xlsx`, `project_primary_manager_rule`,
`gotcha_fabric_sp_dw_gold_access`.

---

## 📦 Deliverables (the interface the APP consumes — must exist + be fresh before app RLS works)
1. `[fabric_sql_database].[dbo].*` — 7 master tables in **DW `cman-dw-ws`** (ws adeb7108, db `fabric_sql_database-a42ef9f3`), next to `employee_master` (ADR-0022, OLTP).
2. `budget.submission_deadline` — in the **app** Fabric SQL DB (`budget_management_web`), from the closing-date file.
3. `budget.board_budget` — in the **app** Fabric SQL DB, from the yearly approved-budget file.
4. A confirmed **SAP actuals query contract** on `gold.fact_gl_trans` (the app runs it read-through; this doc pins the columns/filters).
5. A confirmed **employee source** (unfiltered, contains 100% of the Filler list).

All syncs use the **`NB_employee_sync` pattern** — pyodbc → `fabric_sql_database` via SP
`cman-fabric-write` (`ActiveDirectoryServicePrincipal`, ODBC Driver 17) — **NOT** the DW
"SharePoint CSV" Lakehouse lane (that lands Delta in the Lakehouse; the app's per-request RLS reads
the OLTP SQL DB — ADR-0022). Reuse the Graph read (`/shares/{u!enc}/driveItem/content`, SP has
Sites.ReadWrite.All). Cadence = **DAILY, same job/schedule as `employee_master`**.

---

## ⛔ NEVER-CUT (data side)
- **SAP:** amount is already signed — **no sign flip**; `fact_gl_trans` is a 3-block UNION (SAP-native 1000/2000 vs HLL/GMAN with opposite sign) → the `company_code='1000'` filter is what keeps THB-only + no cross-company double-count + one sign. See item 7.
- **board Replace-by-Year** = one transaction (DELETE year + bulk INSERT); any bad row rejects the whole file.
- **Fail loud** on missing FX year (no 35.00 fallback) and on a revoked SAP grant (no silent-empty).
- **Cast, don't trust:** every master cell is TEXT in Excel — cast to int/decimal/date explicitly.

---

## Phase D0 — Prereqs
**1. Confirm the two homes + access (ADR-0022).** App store = Fabric SQL DB `budget_management_web` (8fbc17b7 / 036a3270, holds `budget.*`). Reference store = DW `fabric_sql_database` in cman-dw-ws (adeb7108 / a42ef9f3, holds `employee_master` + masters); literals in `19.dw_jakkaritw/notebooks/NB_employee_sync.py:148-149`. SAP = DW gold warehouse `cman_dw_wh_gold` (302668d3), host `v5o4qez3u4cupase7cogkwvyke-2nucmmcmvaiejgjtmxgk5gewea.datawarehouse.fabric.microsoft.com`; SP access WORKS (2026-07-13). **⚠️ Confirm with the DW owner who refreshes `gold.fact_gl_trans`** — it's an older build the DW dev-repo no longer tracks (ADR-0020).

**2. [GAP-fix] Confirm the employee source is truly UNFILTERED.** The app's RLS See-manager + approver1 must resolve against an object that contains **empcode 101930 (thanakorny) AND 100% of the ~100 Filler emails** in cc dept.xlsx. Verify WHICH object holds the unfiltered 649 (`employee_master_stg` per ADR-0019 build-note vs `employee_master`/`v_employee_primary` per memory — they disagree). Deliver: a named object + `v_employee_primary`-style Primary-only view that the app can join, proven to drop no Filler. (ADR-0019 build-note; `project_primary_manager_rule`.)

---

## Phase D1 — DDL for `dbo.*` masters (DW) — 02-data-modeler
**3. Create the 7 master tables in `[fabric_sql_database].[dbo]`** (spec §3b, ADR-0022):
- `cc_filler_map` — **EXPLODED** (1 row per cost_center × filler_email), PK (cc, filler_email), index (filler_email); + department/division/c_level/description.
- `per_diem_rate` (position PK; rate_domestic THB, rate_asian USD, rate_other USD), `country_group` (country PK, grp), `master_currency_rate` (fiscal_year PK, usd_thb).
- `gl_group` (gl_code → group_id **and** group_name — see item 5 GAP), `hide_document`, `orgcode_cost_center` (existing shapes; orgcode app-unused per ADR-0019).

**4. [GAP-fix] Home the GL-name + group-name reference.** `sap_gl_code_ref` (137 gl_code→name) and `gl_group_dim` (18 group_id→group_name) currently live in `cfg_master` (dies with the retiring master-tables module, ADR-0022) and are NOT among the 8 SharePoint files (ADR-0018). Board re-derive, pending re-derive, and the 137-GL picker all need gl_name/gl_group. **Decide + deliver:** either (a) seed them into DW `dbo.*` (`dbo.gl_account_ref`, `dbo.gl_group_dim`) from the existing `cfg_master` snapshot, or (b) add a GL-name SharePoint master file. Confirm the `dbo.gl_group` table covers gl_code→group_id, group_id→name, AND gl_code→name.

---

## Phase D2 — Master sync jobs (SharePoint Excel → tables) — 04-data-engineer  ⭐ GATES the app
**5. Master sync — 8 files, per-file transforms (decompose; this is the single biggest item on the critical path — multi-day, not "fill 2 gaps").** Site `CMANDWPRD`, library `Budgeting and Management`. Reuse the `NB_employee_sync` pyodbc→`fabric_sql_database.dbo` pattern (NOT the CSV lane). Daily.
  - **cc dept.xlsx → `dbo.cc_filler_map`:** UNION Filler emails across dup-CC rows (e.g. 10OS011400), then EXPLODE the comma-list to (cc, email) rows. Assert 210 CC / 114 ฝ่าย, 0 orphan, 0 multi-ฝ่าย.
  - **ค่าเบี่ยเลี้ยง.xlsx → `dbo.per_diem_rate`:** (note live filename tone-typo `เบี่ยง`) dedup the 5× C-Level rows; cast text→decimal; 0/blank = ฿0.
  - **country.xlsx → `dbo.country_group`:** map Thai labels (ในประเทศ/ต่างประเทศ-อาเซียน) → codes (domestic/asian); default-to-other (only those 2 groups listed).
  - **อัตราแลกเปลี่ยนเฉลี่ยรายปี.xlsx → `dbo.master_currency_rate`:** cast text→decimal; validate year=4-digit & rate>0.
  - **_m gl group / ซ่อนเอกสาร / cc orgcode → `dbo.gl_group`/`hide_document`/`orgcode_cost_center`.**
  - **Validations (WARN, don't fail the file):** Filler email not in the employee source; a ฝ่าย with non-uniform Filler sets across its CCs (invariant, currently 0); skip blank-Filler CC rows individually (ADR-0019).

**6. [split-fix] closing-date → `budget.submission_deadline` (app DB, NOT dbo).** From `วันปิดรับข้อมูลงบประมาณ.xlsx` (5 TEXT cols). Derive `deadline_date = DATE(closing_year, closing_month, closing_date)`, `reminder_date = DATE(closing_year, closing_month, reminder_day)`. **Validate `reminder_day < closing_date`.** One row per fiscal_year.

**7. SAP actuals query contract on `gold.fact_gl_trans`** (the app runs this read-through; pin it here). VERIFIED 2026-07-13/14:
```sql
SELECT cost_center, gl_account_number, fiscal_year, period_month, SUM(company_curr_amount) AS actual_thb
FROM gold.fact_gl_trans
WHERE company_code='1000' AND doc_type<>'CO'
  AND cost_center NOT IN ('CMRY01','CMKK01','CMPB01','MNLB00','MNLB01','MNLB02','MNLB03','MNLB04')  -- 10SC012000 KEPT
  AND assignment_number<>'TFRS16' AND fiscal_year=@year   -- NO doc_status filter; NO sign flip
GROUP BY cost_center, gl_account_number, fiscal_year, period_month
```
`company_code='1000'` is triply load-bearing (currency + double-count + sign). `period_month` is DW-derived. Reversals net to 0 (no filter). (ADR-0020)

**8. board_budget → `budget.board_budget` (app DB).** From `approved budget/approved_budget_<year>.xlsx`, sheet `sheet1`, **cols A–N only** (cost_center, gl_code, jan..dec); **year from FILENAME** (strict `approved_budget_(\d{4})\.xlsx`, else reject). **Validate-all-then-Replace-by-Year** (DELETE year + bulk INSERT, one txn). Re-derive dim cols from master (gl_name/gl_group/division/dept/c_level); remark NULL. Trigger = **admin "Sync now" button + daily auto-sync**. (ADR-0021)

---

## Handoff / interface to the APP project
- App RLS/approval **cannot function until item 5 (`dbo.cc_filler_map`) + item 2 (employee source) are live** — flag as the app's hard dependency.
- App reads: `dbo.*` (masters+employee) via the DW connection; `budget.board_budget`/`submission_deadline` via the app connection; SAP via item-7 read-through.
- Deliver the exact object names + connection strings + the confirmed `gold.fact_gl_trans` refresh owner to the app dev.
