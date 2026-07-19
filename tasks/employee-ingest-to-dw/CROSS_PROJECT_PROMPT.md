# Cross-project prompt — migrate `mas_employee_data` ingestion into `cman-dw-ws`

> Paste the block below into the **CMAN DW project** (the repo/session that owns the
> `cman-dw-ws` Fabric workspace). It is self-contained: everything the DW agent needs
> (API contract, filters, column contract, existing lane names) is embedded, so it does
> not need access to the `budget_management_web` repo.
>
> Origin: `04.budget_management_web` · workspace `cman-dw-ws` = `adeb7108-689b-4ba0-af1c-7648970f5581`.

---

```prompt
TASK — Add "employee" (C-POP HR REST API) as a new master source in the cman-dw-ws
medallion master lane, and retire the old external Python sync.

## Why
Employee master (`mas_employee_data`, ~80 cols) is currently ingested OUTSIDE Fabric by an
external Python script (`sync_employees.py`, DELETE-all + INSERT) that hits the C-POP HR REST
API and writes a flat table into a Fabric SQL DB in another workspace, scheduled by a GitHub
Action at 06:00 Asia/Bangkok. We are consolidating into cman-dw-ws (adeb7108-…). Employee is a
MASTER table sourced from a REST API — a new source *kind* (existing kinds in this lane are
gateway-copy for SAP master and SharePoint-xlsx for non-SAP master `MNL_M_*`). It should ride
the existing registry-driven master medallion lane, land→bronze→silver→gold, on the daily
master schedule. Consumption target = cman-dw-ws (the app will repoint here).

## Reuse the lane that already exists (inspect first, don't reinvent)
Before adding anything, READ these existing items to learn the source-registry / source-spec
schema and the naming conventions, then extend them:
  - Notebooks: 01_NB_setup, nb_utils, NB_batch_orchestrator ("Bronze batch loop over source
    specs"), 02_NB_land_to_bronze_master_sap, 02_NB_land_to_bronze_master_non_sap,
    03_NB_bronze_to_silver_master_sap, 03_NB_bronze_to_silver_master_non_sap, 04_NB_vendor,
    NB_gold_asset_costcenter
  - Pipelines: pl_daily_master ("pl_copy_landing → pl_batch_ingest"), pl_copy_landing_master,
    pl_batch_ingest_master
  - Stores: Lakehouse modern_lh_cman_dw (schemas bronze_src.* / silver_master.* / gold_master.*),
    in-workspace OLTP fabric_sql_database
  - Config: VariableLibrary varlib_env, Environment env_spark
Match the existing schema/table naming (bronze_src.<name>, silver_master.<name>,
gold_master.<name>) and lineage columns (_file_*) — do NOT introduce a parallel convention.

## C-POP HR API contract (verified working)
  POST  <CPOP_HR_SYSTEM_API_URL>
  Headers: { "Authorization": "<CPOP_HR_SYSTEM_API_KEY>", "Content-Type": "application/json" }
  Body:    { "keyDate": "<today, YYYY-MM-DD, Asia/Bangkok>", "empCode": "" }
  Response JSON: { "success": bool, "errorMessage": str|null, "employeeList": [ {emp}, ... ] }
  Notes:
   - Fail if success != true (raise with errorMessage).
   - API key for hr_status has a SPACE: emp["hr status"] → column hr_status.
   - Empty string "" → NULL. Date fields: hiringdate, terminatedate, birthdate.
   - Full pull each run (no incremental key from the API); the current strategy is full refresh.

## Filter rules — apply at SILVER (not at landing; land raw for lineage)
Keep only budget-system-relevant employees:
   - keep   emp["hr status"] == "Active"
   - drop   empcode      startswith "4"    (Gritsman subsidiary)
   - drop   orgcode      startswith "117"  (Vietnam / Office of Affiliate)
   - drop   joblevelnameen in { "Operator 1","Operator 2","Operator 3","Driver","Maid" }  (L5)
Downstream consumers MUST NOT re-apply these filters (gold is already filtered).

## Gold column contract — gold_master.employee must equal today's mas_employee_data
(order preserved; this is the contract the app depends on):
  empcode, titlenameth, firstnameth, lastnameth, fullnameth,
  nickName, titlenameen, firstnameen, lastnameen, fullnameen,
  posstatus, poscode, posnameth, posnameen,
  emptypecode, emptypenameth, emptypenameen,
  empsubtypecode, empsubtypenameth, empsubtypenameen,
  compcode, compabbreviation, compnameth, compnameen,
  orgcode, orgnameth, orgnameen,
  jobcode, jobnameth, jobnameen,
  joblevelcode, joblevelnameth, joblevelnameen,
  managerposcode, managerposnameth, managerposnameen,
  managerempcode, managerfirstnameth, managerlastnameth,
  managerfirstnameen, managerlastnameen,
  action, reason, hr_status,
  areacode, areanameth, areanameen,
  subareacode, subareanameth, subareanameen,
  sex, nationalityname, email, mobile, idcard,
  hiringdate, terminatedate, birthdate, maritialstatus, religionname,
  pemail, addressno, roomno, floor, village, building,
  moo, soi, street, subdistrictname, districtname, provincename,
  countryname, postcode, addressnoen, roomnoen, flooren,
  villageen, buildingen, mooen, soien, streeten,
  subdistrictnameen, districtnameen, provincenameen, countrynameen, postcodeen
(An `id` surrogate is optional — the old table used a 1..N string id; a stable key on empcode
is preferred if you add one.)

## Build steps
1. Register a new master source spec "employee", kind = rest_api, in whatever registry
   01_NB_setup / NB_batch_orchestrator loop over (config table or notebook dict).
2. Landing: add NB_land_employee_api (or a pipeline Web activity in pl_copy_landing_master)
   that POSTs the API and writes the raw employeeList JSON to
   Files/landing/master/employee/employee_<yyyymmdd>.json (Overwrite).
3. Bronze: extend the 02_NB_land_to_bronze_master_* path to read the JSON →
   bronze_src.employee (raw, string-typed, + _file_* lineage).
4. Silver: extend 03_NB_bronze_to_silver_master_* → silver_master.employee (typed 1:1, apply
   the 4 filters above, dedup by empcode, cast hiringdate/terminatedate/birthdate).
5. Gold: gold_master.employee (same pattern as 04_NB_vendor / NB_gold_asset_costcenter),
   columns == the contract above.
6. Consumption (app reads from cman-dw-ws): make gold_master.employee the source of truth,
   readable via the Lakehouse SQL endpoint (R/O). IF the app needs an OLTP copy, also
   MERGE-upsert into fabric_sql_database.<schema>.mas_employee_data in THIS workspace with the
   identical column contract, so the app only changes server/database, not columns.
7. Schedule: register the source in pl_daily_master so it runs on the existing daily master
   trigger. Do NOT create a new standalone trigger unless the wrapper can't fit it.

## Secrets & permissions
  - Put CPOP_HR_SYSTEM_API_URL + CPOP_HR_SYSTEM_API_KEY in varlib_env (VariableLibrary) or a
    Key Vault referenced by the notebook — NOT hard-coded, NOT in GitHub secrets.
  - Ensure the Service Principal cman-fabric-write has Contributor/Member on cman-dw-ws so it
    can write, and that Fabric Spark has network egress to the C-POP API host.

## Constraints
  - Follow this project's fabric-deploy-gotchas discipline (pipeline-JSON shapes, Spark-runtime
    traps, headless deploy/verify — green-status ≠ correct).
  - TDD the silver transform: assert the 4 filters, dedup, date casts, and full column mapping.
  - All values in the source are strings from the API; type them at silver, not bronze.

## Acceptance
  - gold_master.employee row count ≈ current post-filter mas_employee_data (allow expected
    daily drift); spot-check several empcodes end-to-end.
  - No empcode LIKE '4%', no orgcode LIKE '117%', no L5 job levels, only hr_status='Active'.
  - Runs green as part of pl_daily_master.
  - App reads employee from cman-dw-ws with NO column or behavior change.

## After it runs green for a few days (do in the budget_management_web project, not here)
  - Retire .github/workflows/sync_employees.yml (the GitHub Action) and the external
    DELETE+INSERT write path in setup/sync_employees.py (keep only as a manual backfill if useful).
```

---

## How to use
1. Copy the fenced `prompt` block above into the CMAN DW project's Claude/agent session.
2. Because it's a DATA_WORK task, that project should route it through its own
   data-modeler → design → plan-reviewer → GATE → data-engineer flow.
3. The one open sub-decision left to the DW side: whether the app consumes `gold_master.employee`
   directly (R/O Lakehouse endpoint) **or** also gets a mirrored `fabric_sql_database.mas_employee_data`
   OLTP copy. Step 6 covers both; pick based on whether the app needs writes (it does not —
   employee is read-only reference for RLS + approval chain).
