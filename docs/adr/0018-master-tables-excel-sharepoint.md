# 18. Master-table editing moves to Excel on SharePoint; the 5 admin web editors retire

Date: 2026-07-11
Status: Accepted

## Context

The `03-edit-master-table/master-tables/` module was built as a Static Web App +
Azure Functions + Fabric SQL DB CRUD stack for admins to edit 5 reference datasets.
Only 3 of 5 ever reached a working backend (GL Account Group, Org Code↔Cost Center,
Hide Document Number); Budget Closing Date and Master Currency stayed frontend-only
mockups with no DB wiring.

Grilled 2026-07-11: for a dataset edited by 4 admins occasionally, a full web CRUD
stack (Entra-gated RBAC, Azure Functions cold starts, CI/CD pipeline, hand-built
validation) is disproportionate machinery. Excel on SharePoint gives admins a UI
they already know, plus SharePoint's built-in version history and file permissions,
at a fraction of the build/maintenance cost.

## Decision

- All 6 admin-maintained master datasets are edited **exclusively via Excel
  workbooks on SharePoint** (site `CMANDWPRD`) — no web UI for any of them:

  | # | Dataset | SharePoint file |
  |---|---------|------------------|
  | 1 | GL Account Group | `.../IQC_moVDDg3hTLkmVE8i-KYBAeVh14KV4uhYkSRbGEVa_ms` |
  | 2 | Org Code ↔ Cost Center | `.../IQDVasYILWvzSaH8sgE9lqUAAcJPgGg0B1xBJJpPZBwc1gk` |
  | 3 | Budget Closing Date | `.../IQDwbW1vIBaHQbSIzrv7vwo9AfTn_dPM9PmCx2FokcR9HGg` |
  | 4 | Master Currency | `.../IQA0wcT05ktLSrjC-K-gadGmAd7yL95o84OkEBkTsZK0pzo` |
  | 5 | Hide Document Number | `.../IQCKsUvacFkxR7bsed47XApVAbIvUW7EUHdQ5JqDVI4v83U` |
  | 6 | Cost Center ↔ Filler (**new**, ADR-0019) | `cc dept.xlsx` |

- The 3 already-deployed editors (`01frontend/{gl-group,orgcode-costcenter,
  hide-document}.html` + their `02backend/modules/*` handlers + the `cfg_master.*`
  write path) are **retired permanently** — decommissioned, not kept as a fallback.
- A sync job (design deferred — see Consequences) reads each workbook via Microsoft
  Graph, the same auth pattern already proven in `setup/create_weekly_update.py`
  (service principal `cman-fabric-write`, app role `Sites.ReadWrite.All`), and lands
  the data in **Fabric workspace `cman-dw-ws`, lakehouse `modern_lh_cman_dw`**.

## Consequences

- Lost on retirement: server-side Fail-Fast validation (duplicate-key rejection,
  reference-existence checks against `cfg_master.sap_gl_code_ref` etc.), Entra-gated
  RBAC, search-able dropdowns. SharePoint version history + file permissions are the
  substitute; the sync job must add its own validation-on-ingest if any is needed.
- `03-edit-master-table/master-tables/{01frontend,02backend,03sql,tests,05deploy}`
  becomes dead code — archive once the Excel→Fabric sync is live and proven; don't
  delete first (would leave a data-entry gap with nothing reading the Excel yet).
- The sync job's cadence, validation, conflict handling, and exact
  `modern_lh_cman_dw` schema are **open** — next step is a `02-data-modeler` +
  `04-data-engineer` session. This ADR records WHERE and WHY, not HOW.
- `.claude/project-context.md`'s "master-tables module" section needs a retiring
  notice (same pattern as ADR-0017's Azure SQL note).
