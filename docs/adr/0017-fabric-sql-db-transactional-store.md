# 17. Fabric SQL Database is the transactional store — replaces Azure SQL Database

Date: 2026-06-14
Status: Accepted
Revises the transactional-store choice (Azure SQL Database) recorded in early `CLAUDE.md` prose and assumed by ADR-0003 (budget data model). The medallion/lakehouse decisions stand — only the **OLTP store** changes from Azure SQL to Fabric SQL DB.

## Context

The project originally split storage: **Azure SQL Database** (`cman-budget-mngt-web-sql` / `budget-mngt-web-db`) for transactional CRUD (master tables, `mas_employee_data`), and **Microsoft Fabric Lakehouse** (workspace `budget_management_web`) for analytical actuals (Bronze→Silver→Gold).

Running Azure SQL as a second platform means: a second auth model, GitHub Actions must whitelist/remove the runner IP in the Azure SQL firewall on every run, a separate resource to pay for and patch, and a network hop away from the OneLake actuals it joins against. Fabric now offers **Fabric SQL Database** — full T-SQL OLTP living in the same workspace as the lakehouse, reachable with the same Entra **Service Principal** already used for OneLake/Graph (`cman-fabric-write`), and mirrored into OneLake automatically.

By 2026-06 the master-tables backend already ran entirely on Fabric SQL DB (`cfg_master`) + Lakehouse SQL endpoint (`gold_*`/`silver_*`). Keeping Azure SQL alive only for the daily employee sync was the last tie to the old platform.

## Decision

**Fabric SQL Database is the single transactional store.** Workspace `budget_management_web` (`8fbc17b7-…`), database `036a3270-…`. It holds `cfg_master.*` (master-table editors) and `mas_employee_data`. The Lakehouse SQL endpoint (read-only) serves `gold_*`/`silver_*` actuals.

Azure SQL Database (`cman-budget-mngt-web-sql`) is **retired**.

CI/automation auth = Entra **Service Principal** (`ActiveDirectoryServicePrincipal`, `ENTRA_CLIENT_ID`/`ENTRA_CLIENT_SECRET`) — silent, no MFA prompt, no IP firewall. `ActiveDirectoryPassword` is **not** used in automated jobs (it fails under MFA in GitHub Actions).

## Consequences

- **+** One platform (Fabric) for both OLTP and lakehouse; one SP auth; no per-run IP-firewall dance; OneLake proximity to actuals.
- **+** master-tables backend and employee sync both target Fabric SQL DB; one set of connection env vars (`FABRIC_SQL_*`).
- **−** Fabric SQL DB is newer than Azure SQL for OLTP — watch service limits / quotas as transaction volume grows.
- **Migration is not fully complete** (tracked in `.claude/plan.md`):
  - `setup/sync_employees.py` reads `FABRIC_SQL_*` ✅, but its `get_conn()` still uses `ActiveDirectoryPassword` — switch to Service Principal for CI.
  - `.github/workflows/sync_employees.yml` is **stale/broken**: it still whitelists the Azure SQL firewall and passes `DB_*` secrets, and never passes `FABRIC_SQL_*` → the daily Action cannot reach Fabric. Must drop the firewall steps and pass `FABRIC_SQL_SERVER/DATABASE` + `ENTRA_CLIENT_ID/SECRET`.
  - Root `db/connection.py` (Azure SQL helper) is orphaned — master-tables uses its own `02backend/db.py`. Archived to `bin/`.
  - After the daily Fabric sync runs green for several days: delete the Azure SQL server + database, remove GitHub secrets `DB_SERVER/DB_NAME/DB_USER/DB_PASSWORD`, and strip the same from `.env`.
