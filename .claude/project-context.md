# Project Context — Budget Management Web (CMAN)

Read by **every dream-team agent**. Owns only: dream-team customization, the master-tables
module, and shared env vars. Everything else links out — do not restate it here.

- **Domain glossary / terms** → `CONTEXT.md`
- **Decisions (the "why")** → `docs/adr/`
- **Reference detail** → `docs/reference/`
- **Forward build plan** → `.claude/plan.md` (**tracked in git** — see Plan sync below)

---

## Plan sync (mandatory — every agent, every session)

`.claude/plan.md` is the **single forward checklist**. It is **git-tracked** — stale checkboxes are a bug.

**On session start:** read `plan.md`; resume from first unchecked item in Current Phase.

**Before claiming a milestone done OR before any commit:**
1. Tick `[x]` every item you actually finished in this session.
2. Move finished phase/section to **Done (archive)** (one line each); keep **Current Phase** forward-only.
3. Bump `# Current Phase (YYYY-MM-DD)` date when Current Phase changes.
4. **Same commit** as the code/docs the milestone tracks — never "plan update later".

**Session end gate:** if you touched deliverables tied to `plan.md` items, `plan.md` diff must be non-empty and consistent. Do not end with `[ ]` on work you just shipped.

---

## Dream-team customization (project-specific agent rules)

- **Read this file + `CONTEXT.md` first** in every agent before any query or logic.
- **DB is Microsoft Fabric SQL Database**, not Azure SQL (ADR-0017). Azure SQL is retiring —
  do not write new code against it. Use the Service-Principal pyodbc pattern (below).
- **No-install machine** (see below) — never `pip install` system tools, Docker, or Azure CLI
  from an agent. Deploy = Azure Cloud Shell; local dev = `func start` + `swa start`.
- **Verify silently to save tokens** — never Read screenshots into context. Logic →
  headless Playwright assert, print PASS/FAIL. Visual → save image to disk + STOP for the
  user to review. (Global rule, repeated here because agents skip it.)
- **Edit Master Table tables: NO audit columns, hard-delete is fine** — see master-tables
  rules below. Do not spend effort on soft-delete / temporal / audit logic for those tables.

---

## master-tables module — `03-edit-master-table/master-tables/`

Single deployed SWA hosting 3 admin master-edit pages (+ a 4th, currency, in progress):

| Page | Table |
|------|-------|
| GL Group (`gl-group.html`) | `cfg_master.gl_group_mapping` |
| Orgcode-CostCenter (`orgcode-costcenter.html`) | `cfg_master.orgcode_costcenter_map` |
| Hide Document (`hide-document.html`) | `cfg_master.hide_document_number` |
| Master Currency (`master-currency.html`) | `cfg_master.master_currency_rate` (planned) |

Production URL: `witty-meadow-01107f500.7.azurestaticapps.net`
(Test phase = **per-module SWA**; production target React+Vite + FastAPI on Container Apps — see plan.md.)

```
03-edit-master-table/master-tables/
├── 01frontend/  index.html + page HTMLs + shared/ (api-client + page JS)
├── 02backend/   function_app.py (routes) + auth.py + db.py + modules/
│   └── modules/{gl_group,orgcode_costcenter,hide_document}/
│         ├── models.py
│         └── *_handler.py   (list/save/delete + reference|validate_docs)
├── 03sql/       one .sql per module
├── tests/       backend/ + frontend/
├── 05deploy/    static-web-app config templates
├── docs/        per-module markdown
└── README.md

Deploy workflow: .github/workflows/master-tables-deploy.yml
```

### API route pattern
```
GET    /api/master/<module>/list
POST   /api/master/<module>/save
DELETE /api/master/<module>/delete
GET    /api/master/<module>/reference/<name>   (e.g. orgcodes, cost-centers)
```

### DB access — `02backend/db.py` (pyodbc + Service Principal)
- `get_conn()`           → **Fabric SQL DB** (R/W) → `cfg_master.*`, `dbo.mas_employee_data`
- `get_lakehouse_conn()` → **Fabric Lakehouse SQL Analytics Endpoint** (R/O) →
  `dbo.gold_sap_gl_trans`, `dbo.gold_sap_m_cost_center`, …
- Both share the workspace prefix; only the host suffix differs: `.database.` (SQL DB) vs
  `.datawarehouse.` (Lakehouse). **Lakehouse schema = `dbo`** — the `gold_`/`silver_`
  prefix is part of the table NAME, not the schema.
- Auth = `ActiveDirectoryServicePrincipal` (silent, no browser popup) — see global
  CLAUDE.md "Fabric SQL DB — Local Connection Pattern".

### master-tables rules (non-negotiable)
- **4 admins, same set across both apps** (master-tables + main budget app), via the
  `ADMIN_EMAILS` env-var allowlist checked against the SWA principal email:
  `jakkaritw@chememan.com, nipapornt@chememan.com, warapornt@chememan.com, piyadad@chememan.com`.
- **No audit columns** (`created_by/at`, `deleted_by/at`) — traceability not required at this scale.
- **Hard delete** is fine — no soft-delete pattern.
- `dbo.mas_employee_data` is **pre-filtered at sync time** by `setup/sync_employees.py`
  (Active only; no Gritsman `empcode LIKE '4%'`; no Vietnam `orgcode LIKE '117%'`; no L5
  Operator/Driver/Maid). **Do NOT re-apply these filters in queries.**

---

## Shared env vars (names only — values in `.env` / GitHub secrets, never here)

| Var | Use |
|-----|-----|
| `FABRIC_SQL_SERVER`, `FABRIC_SQL_DATABASE` | Fabric SQL DB (transactional, R/W) |
| `FABRIC_LAKEHOUSE_SERVER`, `FABRIC_LAKEHOUSE_DATABASE` | Lakehouse SQL Endpoint (analytical, R/O) |
| `ENTRA_CLIENT_ID`, `ENTRA_CLIENT_SECRET`, `ENTRA_TENANT_ID` | Service Principal `cman-fabric-write` (DB auth + Graph sendMail) |
| `CPOP_HR_SYSTEM_API_URL`, `CPOP_HR_SYSTEM_API_KEY` | C-POP HR API → `mas_employee_data` sync |
| `ADMIN_EMAILS` | master-tables admin allowlist |
| `DB_SERVER`, `DB_NAME`, `DB_USER`, `DB_PASSWORD` | **RETIRING (ADR-0017)** — Azure SQL legacy, do not use |

---

## No-install constraint
Developer machine has NO admin rights — cannot install Docker, Azure CLI, or any system
tool (UAC + antivirus block it). All deployment via Azure Cloud Shell. Local dev = `func
start` + `swa start`.

---

## Where the rest lives (links, not copies)

- **See / Fill / Approval-unit model** → ADR-0007 (see-fill scope, shared CC), ADR-0008
  (approval unit = ฝ่าย), ADR-0006/0009 (routing, escalation, admin override),
  ADR-0012/0013/0016 (admin direct-approve, edit-never-changes-status, approve-on-main-page).
- **Email notifications** → `docs/reference/approval-workflow.md` (mechanism, triggers, failure handling).
- **Budget form / special-GL subforms / per-diem engine** → `docs/reference/budget-templates.md`
  + ADR-0005 (special-GL detail + trip linkage), ADR-0011/0015 (FX snapshot + recompute-on-read).
- **Phase-1 scope, budget cycle, deadline lock** → `.claude/plan.md`. (One line: Phase-1 =
  budget submission + approval only, incl. deadline lock + email; Dashboard = Phase 2.)
- **SAP actuals filter rules, data sources, Bronze→Silver→Gold map** → `docs/reference/data-sources.md`.
- **Domain conventions** (schemas `cfg_master` vs `dbo`, CC/orgcode formats, THB, FY Jan–Dec,
  `gold_*` = Lakehouse gold) → `CONTEXT.md`.

## Out of scope (for the master-tables module)
Budget submission form, approval workflow, dashboard, and ETL/pipeline code are separate
modules (the last handled by `04-data-engineer`).

---

## CC ↔ Cursor Handoff (multi-file features)

Multi-file features use skill `36-cc-cursor-handoff`. Quick fixes (1–2 files, 1–2 edits) stay in CC directly.

- **Handoff:** CC writes `tasks/<feature>/{TODO.md,CURSOR_PROMPT.md}` → runs `handoff_to_cursor.ps1 -Project "C:\04.budget_management_web" -Feature <feature> -Wait` via Bash (agent CLI; **CC executes — never "paste in Cursor"**). Clipboard+GUI is fallback ONLY if the script exits non-zero / `agent` missing.
- **Completion signal:** poll `git log` every 60s (max 1800s) for commit matching `[cursor-done] TASK-<NNN>`.
- **Branch:** `main`, remote `origin/main` on GitHub.
