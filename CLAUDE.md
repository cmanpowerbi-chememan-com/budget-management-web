# CLAUDE.md

Auto-read at the start of every conversation in this folder. This is a lean operating
manual — it POINTS to the detailed docs, it does not duplicate them. Do NOT delete this file.

---

## Where things live (read these, don't restate them)

| Topic | Lives in |
|-------|----------|
| Dream-team agent rules + master-tables module + shared env vars | `.claude/project-context.md` (read first) |
| Domain glossary / terms (CC, orgcode, see/fill, ฝ่าย, board_budget, schemas) | `CONTEXT.md` |
| Decisions + the "why" (architecture, DB, auth, scope, FX) | `docs/adr/` (0001–0017) |
| Reference detail (workflow, GL master, templates, data sources, B→S map) | `docs/reference/` |
| Forward build plan, Phase-1 scope, open questions | `.claude/plan.md` |

Pointers to specific reference files:
- Approval workflow / special cases / C-Level map / email triggers / approval unit / subsidiary exclusion → `docs/reference/approval-workflow.md` + ADR-0006/0008/0012/0016
- GL Account Groups (18 groups / 137 accounts) → `docs/reference/gl-master.md`
- Budget templates 1.1 / 1.2 subforms / ไฟล์รวม Data → `docs/reference/budget-templates.md` + ADR-0005
- Data sources / Accruals 26-col / actuals filter rules / Replace-by-Month → `docs/reference/data-sources.md`
- Bronze→Silver→Gold column mapping → `docs/reference/data-platform-map.md`
- RLS / see-fill scope / approval unit → ADR-0001/0007/0008/0009; FX → ADR-0011/0015

---

## Project Philosophy (Non-negotiable)

> **Lean, easy to use, not too complex — for users, developers, and approvers — while keeping performance at standard.**

- Prefer simple **and** clever — elegant, not just minimal.
- **Decrease manual tasks** — auto-fill, pre-populate, auto-calculate (prior-year budget, auto-sum totals, division/dept from login).
- Minimize clicks and screens for every role; approver experience matters as much as user experience.
- No feature that adds complexity without clear business value — when in doubt, do less, do it well.
- Developer should maintain and extend without deep ramp-up.

---

## Tech Stack (one line)

React + Vite (frontend) · FastAPI (backend) · **Fabric SQL Database** (transactional, R/W) ·
Fabric Lakehouse (analytical, medallion Bronze→Silver→Gold, R/O) · Entra ID (auth + RLS) ·
Microsoft Graph API (email, no Power Automate). Full rationale → `docs/adr/` (0002 app, 0004 auth, 0017 DB).

> **DB = Microsoft Fabric SQL Database**, NOT Azure SQL. Azure SQL is retiring (ADR-0017) —
> do not write new code against it. Use the Service-Principal pyodbc pattern (global CLAUDE.md
> "Fabric SQL DB — Local Connection Pattern"). Always `ODBC Driver 17 for SQL Server` (not 18).

---

## Developer Commands

```bash
# Master-tables backend tests — run from tests/backend, name unit files explicitly
#   (integration tests need a live DB, else "no tests ran" — see gotcha memory)
cd 03-edit-master-table/master-tables/tests/backend && pytest <unit_file>.py -v

# Employee sync — dry run (shows diff, no DB writes)
python setup/sync_employees.py --dry-run

# Employee sync — live write
python setup/sync_employees.py

# Weekly update — download SharePoint → merge (upsert by Action name) → re-upload
python setup/create_weekly_update.py

# Send sign-off / monthly email (probe by default; --send actually delivers)
python setup/send_signoff_email.py            # probe only
python setup/send_signoff_email.py --send     # send
```

Local dev for master-tables module: `func start` (backend) + `swa start` (frontend).

---

## Send Outlook Email from Scripts (Microsoft Graph sendMail)

Send company email + attachments programmatically — **no MCP Outlook send exists** (M365 connector is read-only). Use Microsoft Graph `sendMail`.

**Reusable script:** `setup/send_signoff_email.py` (probe vs `--send` above).

**How it works:**
- Auth = service principal **`cman-fabric-write`** (`ENTRA_CLIENT_ID` / `ENTRA_TENANT_ID` / `ENTRA_CLIENT_SECRET` in `.env`), client-credentials, scope `https://graph.microsoft.com/.default`.
- App roles granted (verified 2026-06-05): **`Sites.ReadWrite.All`, `Mail.Send`** → `POST /users/{sender}/sendMail` works tenant-wide.
- App has **NO** `User.Read.All` → `GET /users/{x}` returns **403** (can't pre-verify a mailbox). Expected, NOT a blocker — just call `sendMail`; **202 Accepted** = sent OK. To check perms without sending, decode the access-token JWT `roles` claim.
- **Sender** = `jakkaritw@chememan.com`. Company email pattern = firstname + last-initial (warapornt, nipapornt, laddawan**k**).
- **Attachments** = base64 `#microsoft.graph.fileAttachment`; docx MIME `application/vnd.openxmlformats-officedocument.wordprocessingml.document`; `saveToSentItems: true`.
- To send a different email: copy the script, edit `RECIPIENT` / `SUBJECT` / `BODY_HTML` / `FILES`, run `--send`. Always confirm recipient + sender before `--send` (outward-facing, not reversible).

---

## Actual Code Structure (Current State)

> **Streamlit scaffold archived** to `bin/streamlit-scaffold/` (2026-06-14) — superseded by React + FastAPI (ADR-0002). `app.py`, `utils/`, root `Dockerfile` moved there; `pages/` was never built. One-time diagnostic setup scripts → `bin/diagnostic-scripts/`. Old mockups + style refs → `bin/old-mockups/`, `bin/style_reference/`.

Current real layout:

```
03-edit-master-table/master-tables/   ← DEPLOYED module — Azure Functions (Python) backend + Static Web App frontend
  01frontend/                          ← master-table editors (html + shared/*.js, wired to API):
                                          gl-group, master-currency, orgcode-costcenter, budget-closing-date, hide-document
  02backend/                           ← Azure Functions REST API for master tables
  03sql/ · 05deploy/ · tests/          ← schema · deploy config · pytest
design/mockups/0002claude design/
  0002.1budget-export.html             ← WIRED prototype of the main budget app (submit/approve) — source for sign-off specs
requirement_spec/1_software_dev/1.1_frontend/signoff_spec/
  *.docx + _build/build_*.py + assets/ ← user sign-off specs (8 modules) + generators + screenshots
docs/adr/                              ← 17 ADRs (architecture decisions)
docs/reference/                        ← reference detail (workflow, templates, data sources, B→S map, GL master)
db/
  schema.sql                           ← canonical table defs (Azure SQL era — retiring; connection.py archived to bin/azure-sql-legacy/)
setup/                                 ← ops scripts: sync_employees, create_weekly_update, send_signoff/monthly_email, seed_*
fabric/                                ← PySpark scripts — copy into Fabric Notebook UI only (do not run locally)
.github/workflows/                     ← CI: sync_employees (daily 06:00 BKK), master-tables-deploy
graphify-out/                          ← knowledge-graph (gitignored); nightly Task Scheduler rebuild
```

> **React + FastAPI main app: NOT yet built.** The budget submit/approve/dashboard app exists only as the wired mockup `0002.1budget-export.html`. Next phase scaffolds `frontend/` (React+Vite) + `backend/` (FastAPI). Auth = Entra ID Easy Auth + RLS layer (ADR-0004); old Streamlit MSAL flow archived with the scaffold.

### Fabric Notebook scripts
`fabric/` scripts use `spark` (Fabric built-in) and `abfss://` paths — they **do not run locally**. Copy into a Fabric Notebook cell and attach the `lakehouse` Lakehouse.

---

## Deployment

- **Current deploy** = master-tables SWA + Azure Functions via `.github/workflows/master-tables-deploy.yml` (push → GitHub Actions).
- **No-install machine** — developer has NO admin rights; cannot install Docker, Azure CLI, or any system tool (UAC + antivirus block it). All manual deploy via **Azure Cloud Shell** (portal.azure.com — Docker + az pre-installed).
- Production main-app target (Phase 2+) = React+Vite + FastAPI on Container Apps — see `.claude/plan.md`.
- *(Archived: the old Streamlit deploy via ACR `cmanbudgetacr` + Container App `cman-budget-mngt-web` is dead; superseded by the React+FastAPI plan and the master-tables SWA.)*

---

## Live Resource IDs

| Resource | Value |
|----------|-------|
| Fabric Workspace | `budget_management_web` — ID `8fbc17b7-c67d-4c55-94cd-7364e33d1de9` |
| Fabric Lakehouse | `lakehouse` — ID `5cf438dc-6268-4ec1-b088-c6b5c311339d` |
| master-tables SWA (prod URL) | `witty-meadow-01107f500.7.azurestaticapps.net` |
| GitHub repo | https://github.com/cmanpowerbi-chememan-com/budget-management-web |

Env-var names + the Fabric SQL DB / Lakehouse endpoint split → `.claude/project-context.md`.
(Azure SQL connection details retired — ADR-0017.)

---

## Who I Am

- Developer: tanasedw (tanasedbsn@gmail.com); sign emails/docs as **Jakkaritw** (`jakkaritw@chememan.com`).
- Background: familiar with Microsoft Fabric / OneLake / Lakehouse — can use that as analogy when explaining SQL concepts.
- Machine: Python 3.14, Git 2.52, VS Code, ODBC Driver 17 installed. Azure CLI + Docker NOT installed (use Cloud Shell).

---

## Important Notes for Claude

- Always use `ODBC Driver 17 for SQL Server` (not 18) in connection strings.
- **NEVER install any tool/package/software on the developer machine** — no admin rights; UAC + antivirus block it (incident 2026-04-24). For installs/deploys, direct the user to Azure Cloud Shell.
- All monetary values in THB. Fiscal year: January–December.
- Internal company tool — security and RLS by division/department are non-negotiable.
- **Verify to save tokens — never Read screenshots into context.** Reading a PNG burns vision tokens; generating one is cheap.
  - **Logic/calc changes:** run Playwright headless, assert computed values via `page.evaluate()`, print only a compact PASS/FAIL. No screenshot.
  - **Visual/layout changes:** verify logic headless as above, then save a screenshot to disk (`page.screenshot(path=...)`) **without Reading it**, tell the user the path, and **STOP — wait for the user to open it and confirm before proceeding.** The user is the visual reviewer; never load the image.
  - Delete temp verify scripts/images after (keep only if the user wants them).

<!-- rtk-instructions v2 -->
# RTK (Rust Token Killer) - Token-Optimized Commands

## Golden Rule

**Always prefix commands with `rtk`**. If RTK has a dedicated filter, it uses it. If not, it passes through unchanged. This means RTK is always safe to use.

**Important**: Even in command chains with `&&`, use `rtk`:
```bash
# ❌ Wrong
git add . && git commit -m "msg" && git push

# ✅ Correct
rtk git add . && rtk git commit -m "msg" && rtk git push
```

## RTK Commands by Workflow

### Build & Compile (80-90% savings)
```bash
rtk cargo build         # Cargo build output
rtk cargo check         # Cargo check output
rtk cargo clippy        # Clippy warnings grouped by file (80%)
rtk tsc                 # TypeScript errors grouped by file/code (83%)
rtk lint                # ESLint/Biome violations grouped (84%)
rtk prettier --check    # Files needing format only (70%)
rtk next build          # Next.js build with route metrics (87%)
```

### Test (60-99% savings)
```bash
rtk cargo test          # Cargo test failures only (90%)
rtk go test             # Go test failures only (90%)
rtk jest                # Jest failures only (99.5%)
rtk vitest              # Vitest failures only (99.5%)
rtk playwright test     # Playwright failures only (94%)
rtk pytest              # Python test failures only (90%)
rtk rake test           # Ruby test failures only (90%)
rtk rspec               # RSpec test failures only (60%)
rtk test <cmd>          # Generic test wrapper - failures only
```

### Git (59-80% savings)
```bash
rtk git status          # Compact status
rtk git log             # Compact log (works with all git flags)
rtk git diff            # Compact diff (80%)
rtk git show            # Compact show (80%)
rtk git add             # Ultra-compact confirmations (59%)
rtk git commit          # Ultra-compact confirmations (59%)
rtk git push            # Ultra-compact confirmations
rtk git pull            # Ultra-compact confirmations
rtk git branch          # Compact branch list
rtk git fetch           # Compact fetch
rtk git stash           # Compact stash
rtk git worktree        # Compact worktree
```

Note: Git passthrough works for ALL subcommands, even those not explicitly listed.

### GitHub (26-87% savings)
```bash
rtk gh pr view <num>    # Compact PR view (87%)
rtk gh pr checks        # Compact PR checks (79%)
rtk gh run list         # Compact workflow runs (82%)
rtk gh issue list       # Compact issue list (80%)
rtk gh api              # Compact API responses (26%)
```

### JavaScript/TypeScript Tooling (70-90% savings)
```bash
rtk pnpm list           # Compact dependency tree (70%)
rtk pnpm outdated       # Compact outdated packages (80%)
rtk pnpm install        # Compact install output (90%)
rtk npm run <script>    # Compact npm script output
rtk npx <cmd>           # Compact npx command output
rtk prisma              # Prisma without ASCII art (88%)
```

### Files & Search (60-75% savings)
```bash
rtk ls <path>           # Tree format, compact (65%)
rtk read <file>         # Code reading with filtering (60%)
rtk grep <pattern>      # Search grouped by file (75%). Format flags (-c, -l, -L, -o, -Z) run raw.
rtk find <pattern>      # Find grouped by directory (70%)
```

### Analysis & Debug (70-90% savings)
```bash
rtk err <cmd>           # Filter errors only from any command
rtk log <file>          # Deduplicated logs with counts
rtk json <file>         # JSON structure without values
rtk deps                # Dependency overview
rtk env                 # Environment variables compact
rtk summary <cmd>       # Smart summary of command output
rtk diff                # Ultra-compact diffs
```

### Infrastructure (85% savings)
```bash
rtk docker ps           # Compact container list
rtk docker images       # Compact image list
rtk docker logs <c>     # Deduplicated logs
rtk kubectl get         # Compact resource list
rtk kubectl logs        # Deduplicated pod logs
```

### Network (65-70% savings)
```bash
rtk curl <url>          # Compact HTTP responses (70%)
rtk wget <url>          # Compact download output (65%)
```

### Meta Commands
```bash
rtk gain                # View token savings statistics
rtk gain --history      # View command history with savings
rtk discover            # Analyze Claude Code sessions for missed RTK usage
rtk proxy <cmd>         # Run command without filtering (for debugging)
rtk init                # Add RTK instructions to CLAUDE.md
rtk init --global       # Add RTK to ~/.claude/CLAUDE.md
```

## Token Savings Overview

| Category | Commands | Typical Savings |
|----------|----------|-----------------|
| Tests | vitest, playwright, cargo test | 90-99% |
| Build | next, tsc, lint, prettier | 70-87% |
| Git | status, log, diff, add, commit | 59-80% |
| GitHub | gh pr, gh run, gh issue | 26-87% |
| Package Managers | pnpm, npm, npx | 70-90% |
| Files | ls, read, grep, find | 60-75% |
| Infrastructure | docker, kubectl | 85% |
| Network | curl, wget | 65-70% |

Overall average: **60-90% token reduction** on common development operations.
<!-- /rtk-instructions -->
