# Current Phase (2026-06-16)

## Fabric SQL migration — Azure SQL retirement (ADR-0017)
- [x] `setup/sync_employees.py` → Fabric SQL DB via Service Principal (ActiveDirectoryServicePrincipal, ENTRA_CLIENT_ID/SECRET) — verified: SP auth OK, mas_employee_data = 343 rows, API 645 Active → 343 include (in sync)
- [x] `.github/workflows/sync_employees.yml` → drop Azure SQL firewall steps + DB_* env; pass FABRIC_SQL_* + ENTRA_* secrets
- [x] root `db/connection.py` (Azure SQL orphan) → archived to `bin/azure-sql-legacy/`
- [x] **USER: GitHub secrets** — already existed as `FABRIC_AAD_*` + `FABRIC_SQL_*`; yml repointed to them (no new secrets needed)
- [x] verify daily Action runs green — ✅ confirmed in prod 2026-06-14 (synced to Fabric SQL DB via SP)
- [ ] after green several days → delete Azure SQL server `cman-budget-mngt-web-sql` + GitHub secrets `DB_*` + `.env` `DB_*`

## Real build (next)
- [ ] scaffold frontend/ (React+Vite) + backend/ (FastAPI) — main budget app (mockup 0002.1 = source)
- [ ] test env → prod folder (TBC)

---

## Done (archive)

Completed milestones — one line each. Detail lives in git history.

- Docs consolidation (PR #1 / commit 3800e32, 2026-06-14) — CLAUDE.md slimmed (~1300→305 lines, points to CONTEXT/ADR/reference); README rewritten onboarding (~619→182); project-context deduped; reference payload → `docs/reference/` (approval-workflow, budget-templates, data-platform-map, data-sources, gl-master); stale Azure SQL/Streamlit/ACR scrubbed.
- Fabric SQL migration code path (ADR-0017) — sync_employees + daily workflow on Fabric SP; Azure SQL helper archived.
- 0007 Orgcode↔CostCenter frontend fix — CC multi-select, API-wired list/save/delete, Lakehouse cost-center reference. Code-review fixes applied (409 on dup, event delegation/XSS, stale handlers removed).
- gl-group.html wired to real backend (`/api/master/gl-group/*`, Export CSV) — code review APPROVE.
- master-currency.html created from mockup (4th master-edit page); nav hrefs repointed across all pages.
- Budget transactional data model — `docs/specs/budget-transactional-data-model.md` (7 `budget.*` tables + refs, managerempcode chain).
- Sign-off specs (MS Word) built/rebuilt: main web app (v0.6), GL Group, master currency, web-access/submit (module 10) — all re-pointed to canonical mockup `0002.1budget-export.html`, validators green.
- ADRs 0001–0017 written (RLS, see/fill/approval-unit, admin override/toggle, FX snapshot, Fabric SQL DB).
