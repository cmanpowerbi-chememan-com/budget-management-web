# Budget Management Web (CMAN)

Internal OPEX budget system for the budget department, replacing manual SAP exports and Excel consolidation.

> **Onboarding doc.** Read this first to understand *what* the project is and *how* to run it.
> For domain detail and rules → [`CONTEXT.md`](CONTEXT.md). For decisions → [`docs/adr/`](docs/adr/).
> For AI/dev working rules → [`CLAUDE.md`](CLAUDE.md).

---

## 1. Overview

Department users (L3/L4) fill next-year monthly OPEX budget by **ฝ่าย (department)**, the budget
goes through a 3-level approval chain, and approved budget is compared against SAP actuals.

```
User fills budget (by ฝ่าย, per GL, Jan–Dec)
    → approver1 (managerempcode)  →  Nipapornt (Budget Staff)  →  Warapornt (Budget Manager)
    → approved budget flows to Fabric Lakehouse (Gold) for dashboards vs SAP actuals
```

**Business goals:** cut manual SAP-export + Excel consolidation work; give departments
self-service visibility into their own budget vs actuals; give the budget team clean data for dashboards.

**Phase 1** = budget submission + approval (incl. deadline lock + email). **Dashboard = Phase 2.**

See [`CONTEXT.md`](CONTEXT.md) for the full domain model: see/fill/approval scope, special-GL
subforms, RLS, deadline behaviour.

---

## 2. Architecture (current)

| Part | Status |
|------|--------|
| **Master-tables module** (`03-edit-master-table/`) | **Deployed** — Azure Static Web App (frontend) + integrated Azure Functions (Python backend) |
| **Main budget app** (submit / approve) | **Not built yet** — exists as the wired mockup `design/mockups/0002claude design/0002.2budget-export.html`; planned as React + Vite frontend + FastAPI backend |
| **Dashboard** | Phase 2 — not started |

```
Browser
  │  (Entra ID — SWA Easy Auth, x-ms-client-principal-name)
  ▼
Frontend ──► Backend API ──► Fabric SQL DB        (transactional — ADR-0017)
                              cfg_master.* + dbo.mas_employee_data
                         └─► Fabric Lakehouse      (analytical — Bronze→Silver→Gold)
                              gold_* read-only via SQL Analytics Endpoint
Email: backend → Microsoft Graph sendMail (SP cman-fabric-write, Mail.Send)
```

- **Transactional store = Microsoft Fabric SQL Database** (ADR-0017 — replaces the retired Azure SQL).
- **Analytical store = Fabric Lakehouse** medallion (Bronze → Silver → Gold). SAP actuals land here monthly.
- **Auth = Entra ID** (SWA Easy Auth today) + RLS by ฝ่าย/cost-center (ADR-0004).
- **Email = Microsoft Graph API** (`sendMail`, background task) — no Power Automate, no Fabric-notebook hop.

---

## 3. Tech stack

| Layer | Tool | Notes |
|-------|------|-------|
| Frontend (main app) | React + Vite | Planned — pending scaffold |
| Frontend (master-tables) | Vanilla HTML + JS | Deployed on Azure Static Web Apps |
| Backend (main app) | FastAPI (Python) | Planned — pending scaffold |
| Backend (master-tables) | Azure Functions v2 (Python) | Deployed, `pyodbc` |
| OLTP database | **Fabric SQL DB** | `cfg_master.*`, `dbo.*` — ADR-0017 |
| Analytics database | **Fabric Lakehouse** | Gold via SQL Analytics Endpoint (read-only) |
| Auth | Azure Entra ID | SWA Easy Auth + RLS |
| Email | Microsoft Graph API | `sendMail` via service principal |
| Deploy | Azure | master-tables = SWA + Functions today; main app TBC |

> **Not used:** Streamlit (archived to `bin/streamlit-scaffold/`), Azure SQL Database (retired per ADR-0017),
> Azure Container Apps / ACR are no longer the live target for the deployed module.

---

## 4. Repo map

```
01-landing-page/                        ← landing page assets
02-budget-input/                        ← main budget-input work area
03-edit-master-table/master-tables/     ← DEPLOYED module: Azure Functions backend + Static Web App frontend
  01frontend/   master-table editors (html + shared/*.js, wired to API):
                gl-group, master-currency, orgcode-costcenter, budget-closing-date, hide-document
  02backend/    Azure Functions REST API (function_app.py + auth.py + db.py + modules/)
  03sql/ · 05deploy/ · tests/           schema · deploy config · pytest (run from tests/backend)
design/mockups/0002claude design/
  0002.2budget-export.html              ← WIRED prototype of the main budget app — source for sign-off specs
requirement_spec/1_software_dev/1.1_frontend/signoff_spec/
  *.docx + _build/build_*.py + assets/  ← user sign-off specs (modules) + generators + screenshots
docs/adr/                               ← architecture decision records (0001–0017)
db/
  connection.py                         ← pyodbc connection factory (ODBC Driver 17)
  schema.sql                            ← canonical table definitions (the source of truth — not this README)
setup/                                  ← ops scripts: sync_employees, create_weekly_update, send_signoff/monthly_email, seed_*
fabric/                                 ← PySpark scripts — copy into Fabric Notebook UI only (do NOT run locally)
.github/workflows/                      ← CI: sync_employees (daily 06:00 BKK) · master-tables-deploy
bin/                                    ← ARCHIVED: streamlit-scaffold, old mockups, style refs, diagnostic scripts, azure-sql-legacy
CONTEXT.md · CLAUDE.md                  ← domain model · AI/dev working rules
```

Mirrors the "Actual Code Structure" section in [`CLAUDE.md`](CLAUDE.md).

---

## 5. Prerequisites

Installed on the developer machine:

| Tool | Version |
|------|---------|
| Python | 3.14 |
| Node.js | (for React frontend) |
| Git | 2.52+ |
| VS Code | latest |
| ODBC Driver 17 for SQL Server | required for Fabric SQL DB connection |

> **No local Docker or Azure CLI** — the machine has no admin rights. Use **Azure Cloud Shell**
> (portal.azure.com) for anything that needs `az` or `docker`.

Python deps: `pip install -r requirements.txt`. Secrets live in a local `.env` (never committed) —
see [`CLAUDE.md`](CLAUDE.md) for the required env vars (`FABRIC_SQL_SERVER`, `ENTRA_*`, etc.).

---

## 6. Local dev

### master-tables module (deployed — has real tests)

```bash
# Backend unit tests — run from the tests/backend folder
cd 03-edit-master-table/master-tables/tests/backend
pytest

# Run the SWA + Functions locally (no admin install needed)
func start     # Azure Functions backend
swa start      # Static Web App frontend
```

### Ops scripts

```bash
# Employee sync — dry run (shows diff, no DB writes)
python setup/sync_employees.py --dry-run

# Employee sync — live write to Fabric SQL DB
python setup/sync_employees.py
```

### Main budget app (React + FastAPI)

**Pending scaffold** — `frontend/` (React + Vite) and `backend/` (FastAPI) do not exist yet.
Run commands will be added here once the scaffold lands. Until then the app exists only as the
wired mockup `design/mockups/0002claude design/0002.1budget-export.html`.

---

## 7. Deploy

| Target | How |
|--------|-----|
| **master-tables** | Automatic via `.github/workflows/master-tables-deploy.yml` — push to `main` touching `03-edit-master-table/master-tables/**` runs unit tests then deploys to Azure Static Web App + Functions. |
| **Main budget app** | **TBC** — deploy target for the React + FastAPI app is not finalised. |

Anything requiring `az` / `docker` runs in **Azure Cloud Shell** (no local install).

---

## 8. Where to look next

| For… | Go to |
|------|-------|
| Domain model, business rules, see/fill/approval scope | [`CONTEXT.md`](CONTEXT.md) |
| Why a decision was made | [`docs/adr/`](docs/adr/) (e.g. `0017` = Fabric SQL DB store, `0002` = React+FastAPI) |
| Table definitions / schema | [`db/schema.sql`](db/schema.sql) |
| AI / developer working rules, env vars, RTK | [`CLAUDE.md`](CLAUDE.md) |
| Master-tables module specifics | `03-edit-master-table/master-tables/README.md` |

---

All monetary values in **THB**. Fiscal year = **January – December**.
