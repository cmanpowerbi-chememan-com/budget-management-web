# Current Phase (2026-07-12)

## Fabric SQL migration — Azure SQL retirement (ADR-0017)
- [x] `setup/sync_employees.py` → Fabric SQL DB via Service Principal (ActiveDirectoryServicePrincipal, ENTRA_CLIENT_ID/SECRET) — verified: SP auth OK, mas_employee_data = 343 rows, API 645 Active → 343 include (in sync)
- [x] `.github/workflows/sync_employees.yml` → drop Azure SQL firewall steps + DB_* env; pass FABRIC_SQL_* + ENTRA_* secrets
- [x] root `db/connection.py` (Azure SQL orphan) → archived to `bin/azure-sql-legacy/`
- [x] **USER: GitHub secrets** — already existed as `FABRIC_AAD_*` + `FABRIC_SQL_*`; yml repointed to them (no new secrets needed)
- [x] verify daily Action runs green — ✅ confirmed in prod 2026-06-14 (synced to Fabric SQL DB via SP)
- [ ] after green several days → delete Azure SQL server `cman-budget-mngt-web-sql` + GitHub secrets `DB_*` + `.env` `DB_*`

## Real build (next) — sequence grilled 2026-07-11/12 (see memory project_nextstep_design_decisions)
- [ ] **build sync `cc dept.xlsx` → Fabric** (single gating dependency: CC→ฝ่าย feeds approval unit AND CC→Filler feeds RLS; Filler = UNION across duplicate CC rows). Validation-on-ingest: (a) WARN per Filler email not found in the unfiltered employee source; (b) WARN if a ฝ่าย has non-uniform Filler sets across its CCs (currently 0 — invariant that keeps whole-ฝ่าย Submit safe per ADR-0008); skip blank-Filler CC rows individually (ADR-0019)
- [ ] **DDL `budget.*` 7 tables on Fabric SQL DB** from the reconciled spec (approval_status/log keyed (department, fiscal_year))
- [ ] **board_budget SharePoint-drop sync** (ADR-0021: `approved_budget_<year>.xlsx`, sheet `sheet1`, cols A–N, year from filename strict; trigger open: Sync-now button vs daily poll)
- [ ] scaffold frontend/ (React+Vite) + backend/ (FastAPI) — main budget app (mockup **0002.2** = source; 0002.1 superseded)
  - RLS must resolve via the Cost Center↔Filler map (ADR-0019), NOT the orgcode chain (ADR-0001/0007 superseded) — read this before coding auth/RLS
  - SAP actuals = read-through DW `cman_dw_wh_gold.gold.fact_gl_trans` ws 302668d3 (ADR-0020): DW-side GROUP BY → FastAPI merge; verify SP Viewer grant + exact col names at build
  - main-table read path (grill 2026-07-12): visible-row union key = `(cost_center, gl_account)` (layers carry different years: SAP=Y, Approved=Y, Pending=Y+1); Approved-Y = reference only; board+pending join inside Fabric SQL DB, SAP merged cross-store in FastAPI; requested-vs-granted = Phase-2 dashboard
  - approval engine (grill 2026-07-12, ADR-0006/0008): `approval_status` keyed (ฝ่าย, fiscal_year) with frozen approver1/2/3 empcodes + last_submitter_empcode snapshotted at Submit; reject at ANY step → REJECTED (editable) → resubmit restarts whole chain at PENDING_APPROVER1; **all automations are Phase-1**: (A) reject→email to last submitter, (B) auto-submit DRAFT ฝ่าย at deadline, (C) 30-day auto-escalate, (D) pre-deadline reminder email on `reminder_date` to Fillers of still-DRAFT ฝ่าย (grouped one email/Filler listing their pending ฝ่าย, submitted excluded) → needs scheduled jobs (GitHub Actions cron like sync_employees, or Azure Function timer) + Graph sendMail
- [ ] test env → prod folder (TBC)
- [ ] follow-up doc sweep: `.claude/project-context.md` + `docs/reference/data-platform-map.md`/`data-sources.md` still say `gold_sap_gl_trans`; mockup 0002.2 + signoff doc 01 still show the dropped CSV import/export buttons

## Master-tables → Excel migration (ADR-0018/0019, grilled 2026-07-11)
- [ ] design + build the Excel(SharePoint)→Fabric sync job (`cman-dw-ws` / `modern_lh_cman_dw`) — cadence, validation-on-ingest, skip-blank-Filler-row tolerance (02-data-modeler + 04-data-engineer). Land against the DW project's existing "SharePoint CSV" master lane (19.dw_jakkaritw ADR-0020, `cc-dept` already queued) — but that lane reads CSV only + has no per-cell Excel reader / no cross-row aggregation, so 2 gaps to fill: (a) Excel reader, (b) UNION-Filler aggregation
- [ ] **master_currency = Excel on SharePoint** (ADR-0018 dataset #4, file `อัตราแลกเปลี่ยนเฉลี่ยรายปี.xlsx`, cols `year | average rate usdthb` → `fiscal_year`/`usd_thb`; admin-maintained, values change freely). Sync must: coerce rate text→number (don't trust Excel cell type), validate year=4-digit-int & rate>0 (WARN/skip bad rows), and the app FAILS LOUD if the planning year's rate row is missing (never a silent 35.00 fallback). Supersedes ADR-0015's cfg_master/Module-09 web-edit plan
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
- Spec reconciled to post-dating decisions (2026-07-12): approval unit → (ฝ่าย, fiscal_year) per ADR-0008; RLS → CC↔Filler map per ADR-0019; SAP actuals → DW `fact_gl_trans` read-through (**new ADR-0020**); board_budget → yearly Excel SharePoint drop, 14-col A–N, year-from-filename (**new ADR-0021**); CONTEXT.md glossary fixed; gate 06 passed after 1 blocker fix. Real-data verification: cc dept.xlsx = 210 CC / 114 ฝ่าย, 0 orphan, 0 multi-ฝ่าย; approved_budget file structure confirmed.
- Sign-off specs (MS Word) built/rebuilt: main web app (v0.6), GL Group, master currency, web-access/submit (module 10) — all re-pointed to canonical mockup `0002.1budget-export.html`, validators green.
- SpecC (Master Tables) sign-off doc clarity polish (2026-06-25, version2/) — wording-only across all 5 modules via run-id OOXML edits (no install): colon-chains→bullets, tightened Context/Downstream/FX-impact prose, consistent phrasing; all facts/numbers/①–⑤/ADR/screenshots preserved (deterministic token check, 0 dropped). Per-module changelog+version bump (GL v0.2.2 · Closing v0.2.1 · OrgCC/Hide v0.3.1 · Currency v0.4.1). User added own `(L3/L4/L2 3 คน)` edit on the candidate, kept. Reusable tools: `tasks/signoff-spec-v2/_tools/{extract_runs,apply_runs,check_preservation,build_clarity_edits}.py`.
- SpecB (GL Subform) sign-off doc clarity polish (2026-06-26, version2/, commit 758d320 via **CC→Cursor handoff**) — SpecB is run-fragmented (no clean single-run paragraphs), so used a **paragraph-collapse** method (rebuild one run per paragraph, rPr preserves Thai `cs`+Latin `ascii` fonts). CC pre-built+proved tools `tasks/signoff-spec-v2/_tools/{extract_paras,apply_paras,check_paras}.py`; cs rewrote 40 paragraphs (colon-chains→bullets), version→v0.4.1 + changelog. Validate PASS: check_paras 0 dropped/0 wrong-index, images 14=14 untouched, markers/facts intact, commit scope clean.
- Repo cleanup (2026-06-26, commit 1a2d3fc via **CC→Cursor handoff**) — user-approved exact-list delete: temp junk (`tasks/_tmp_*`), 6 superseded one-off SpecB scripts, `bin/` verify throwaway (~1.8MB, gitignored); `git rm` 4 done v2 tools + `edits_specA.json`; `git rm` `version2/` SpecA/B/C docx (live on SharePoint, in git history). Committed stray CURSOR_PROMPT.md. Kept 9 reusable `_tools` + task records. Validate PASS: commit scope clean (only cleanup paths), pre-existing unrelated changes + `index.html` untouched.
- ADRs 0001–0017 written (RLS, see/fill/approval-unit, admin override/toggle, FX snapshot, Fabric SQL DB).
- master-tables `01frontend/index.html` rebuilt as a real Home/overview grid (2026-07-06) — replaces the old `<meta refresh>` redirect stub with 5 module cards (GL Group/Orgcode-CC/Hide Document/Master Currency/Closing Date), reusing budget-closing-date.html's design system verbatim (theme, fonts, nav). Playwright headless verify PASS (13/13 assertions: 5 cards, hrefs, module badges 03/07/08/09/10, downstream tags, nav active state, 0 console errors, theme toggle). No backend/data wiring — static presentational page only.
