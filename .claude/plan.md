# Current Phase (2026-06-25)

## Fabric SQL migration — Azure SQL retirement (ADR-0017)
- [x] `setup/sync_employees.py` → Fabric SQL DB via Service Principal (ActiveDirectoryServicePrincipal, ENTRA_CLIENT_ID/SECRET) — verified: SP auth OK, mas_employee_data = 343 rows, API 645 Active → 343 include (in sync)
- [x] `.github/workflows/sync_employees.yml` → drop Azure SQL firewall steps + DB_* env; pass FABRIC_SQL_* + ENTRA_* secrets
- [x] root `db/connection.py` (Azure SQL orphan) → archived to `bin/azure-sql-legacy/`
- [x] **USER: GitHub secrets** — already existed as `FABRIC_AAD_*` + `FABRIC_SQL_*`; yml repointed to them (no new secrets needed)
- [x] verify daily Action runs green — ✅ confirmed in prod 2026-06-14 (synced to Fabric SQL DB via SP)
- [ ] after green several days → delete Azure SQL server `cman-budget-mngt-web-sql` + GitHub secrets `DB_*` + `.env` `DB_*`

## Real build (next)
- [ ] scaffold frontend/ (React+Vite) + backend/ (FastAPI) — main budget app (mockup 0002.1 = source)
  - RLS must resolve via the Cost Center↔Filler map (ADR-0019), NOT the orgcode chain (ADR-0001/0007 superseded) — read this before coding auth/RLS
- [ ] test env → prod folder (TBC)

## Master-tables → Excel migration (ADR-0018/0019, grilled 2026-07-11)
- [ ] design + build the Excel(SharePoint)→Fabric sync job (`cman-dw-ws` / `modern_lh_cman_dw`) — cadence, validation-on-ingest, skip-blank-Filler-row tolerance (02-data-modeler + 04-data-engineer)
- [ ] once sync is live and proven: decommission `03-edit-master-table/master-tables/01frontend/{gl-group,orgcode-costcenter,hide-document}.html` + their backend modules
- [ ] open question carried from ADR-0019: does the direct-manager See-scope lookup need Primary+Acting posstatus (like the old orgcode lookup did)?

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
- SpecC (Master Tables) sign-off doc clarity polish (2026-06-25, version2/) — wording-only across all 5 modules via run-id OOXML edits (no install): colon-chains→bullets, tightened Context/Downstream/FX-impact prose, consistent phrasing; all facts/numbers/①–⑤/ADR/screenshots preserved (deterministic token check, 0 dropped). Per-module changelog+version bump (GL v0.2.2 · Closing v0.2.1 · OrgCC/Hide v0.3.1 · Currency v0.4.1). User added own `(L3/L4/L2 3 คน)` edit on the candidate, kept. Reusable tools: `tasks/signoff-spec-v2/_tools/{extract_runs,apply_runs,check_preservation,build_clarity_edits}.py`.
- SpecB (GL Subform) sign-off doc clarity polish (2026-06-26, version2/, commit 758d320 via **CC→Cursor handoff**) — SpecB is run-fragmented (no clean single-run paragraphs), so used a **paragraph-collapse** method (rebuild one run per paragraph, rPr preserves Thai `cs`+Latin `ascii` fonts). CC pre-built+proved tools `tasks/signoff-spec-v2/_tools/{extract_paras,apply_paras,check_paras}.py`; cs rewrote 40 paragraphs (colon-chains→bullets), version→v0.4.1 + changelog. Validate PASS: check_paras 0 dropped/0 wrong-index, images 14=14 untouched, markers/facts intact, commit scope clean.
- Repo cleanup (2026-06-26, commit 1a2d3fc via **CC→Cursor handoff**) — user-approved exact-list delete: temp junk (`tasks/_tmp_*`), 6 superseded one-off SpecB scripts, `bin/` verify throwaway (~1.8MB, gitignored); `git rm` 4 done v2 tools + `edits_specA.json`; `git rm` `version2/` SpecA/B/C docx (live on SharePoint, in git history). Committed stray CURSOR_PROMPT.md. Kept 9 reusable `_tools` + task records. Validate PASS: commit scope clean (only cleanup paths), pre-existing unrelated changes + `index.html` untouched.
- ADRs 0001–0017 written (RLS, see/fill/approval-unit, admin override/toggle, FX snapshot, Fabric SQL DB).
- master-tables `01frontend/index.html` rebuilt as a real Home/overview grid (2026-07-06) — replaces the old `<meta refresh>` redirect stub with 5 module cards (GL Group/Orgcode-CC/Hide Document/Master Currency/Closing Date), reusing budget-closing-date.html's design system verbatim (theme, fonts, nav). Playwright headless verify PASS (13/13 assertions: 5 cards, hrefs, module badges 03/07/08/09/10, downstream tags, nav active state, 0 console errors, theme toggle). No backend/data wiring — static presentational page only.
