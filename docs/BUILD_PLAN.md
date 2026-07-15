# Build Plan — Budget Management Web (APP half)

Handoff plan for the app dev (fable-5) to build the React+Vite + FastAPI app.
**The DATA half (SharePoint→Fabric syncs, masters, board_budget, SAP query) is a SEPARATE project:
`docs/DATA_PIPELINE_PLAN.md`.** This doc builds the app that CONSUMES those tables.

**Source of truth (build ONLY from these — old ADRs 0001/0003/0007/0009/0011 are superseded):**
- Spec `docs/specs/budget-transactional-data-model.md`; CURRENT ADRs 0002/0004/0005/0006/0008/0010/0012/0013/0014/0015/0016/0017/0019/0020/0021/0022; memory `project_*`/`gotcha_*`.
- **UI behavior source = `design/mockups/0002claude design/0002.3budget-export.html`** (canonical; 0002.2/0002.1 removed. Note: ADR-0012/0013/0014/0016 still text-cite the deleted `0002.1` — read them for the DECISION, use 0002.3 for the UI.)

**Owner tags:** `[DM]`=02-data-modeler · `[DEV]`=05-software-developer · `[DE]`=04-data-engineer. Main session never writes prod code — delegate. TDD: the never-cut tests are RED-first **inside** their build item, not batched at the end.

**Hard dependency on the DATA project:** app RLS/approval/read **cannot run until** `dbo.cc_filler_map` + the confirmed employee source (DATA #2/#5) and `dbo.board_budget`/`submission_deadline` (DATA #6/#8) are live. Get the object names + connection strings + the confirmed `gold.fact_gl_trans` refresh owner from the data team first.

**Spine:** `A1 DDL budget.* → A2 backend scaffold+auth → A3 RLS → A4 read path → A5 write → A6 approval → A7–A10 frontend → A11 scheduled jobs → A12 emails → A13 tests → A14 deploy`.

---

## ⛔ NEVER-CUT (app must enforce + unit-test RED-first)
- **SAP read-through** (query contract in DATA #7): run it verbatim — `company_code='1000'`, `doc_type<>'CO'`, excluded CCs (WITHOUT 10SC012000), `assignment<>'TFRS16'`, **no sign flip, no doc_status filter**. Missing/failed SAP → **loud error**, never a silent-empty green layer.
- **COST 5xxx vs SG&A 6xxx** budget totals never cross.
- **Per-diem rounding:** last selected month absorbs the remainder so `sum(m01..m12)`==exact total (DECIMAL 18,2). Mockup's round-every-month is a BUG. FX-derived per-diem is **recompute-on-read** (not stored) → missing FX year = **fail loud**, not 35.00. (ADR-0005/0015)
- **Control-number reconcile (deploy gate):** the check = SUM of pending/board per (ฝ่าย,year) before vs after a change matches, **compared at the SAME FX on both sides** (APPROVED per-diem is NOT frozen — it moves when Master FX is edited, ADR-0015). Define the control number = per-(ฝ่าย,fiscal_year) total; never treat APPROVED as immutable.
- **Row-grain optimistic lock** on every pending write (multi-Filler is common — 73% of CCs have ≥2 Fillers).
- **Deploy:** jakkaritw approval + verify-deploy-landed.

---

## Phase A0 — App DDL (the app owns the transactional store)
**A1. [DM] DDL `budget.*` transactional + `dbo.board_budget`/`dbo.submission_deadline` (7 tables) in Fabric SQL DB `fabric_sql_database`** (ONE DB, two schemas — spec §2/§3, ADR-0017/0023). Wide m01–m12; `pending_budget`/`board_budget` key (cc,gl,fiscal_year) + row-grain optimistic-lock `_updated_at` + re-derived dim snapshots + `template` USER/ADMIN; `pending_budget_detail` (meta_json, is_auto_calc); `budget_trip` (side per trip); `approval_status` **PK (department, fiscal_year)** + frozen approver1/2/3 empcodes + last_submitter; `approval_log` (append-only, keyed department,year, actions incl ADMIN_SUBMIT/ADMIN_OVERRIDE/AUTO_SUBMIT/AUTO_ESCALATE); `submission_deadline` (fiscal_year, deadline_date, reminder_date).
  *(Note: DATA #6/#8 syncs WRITE into `submission_deadline`/`board_budget` — this DDL must exist first.)*

---

## Phase A1 — Backend (FastAPI)  [DEV]  (ADR-0002)
**A2. Scaffold `backend/` + Entra Easy Auth.** `x-ms-client-principal-name` header = login email (trust anchor, ADR-0004). Connection helpers (split-connection; never one cross-store JOIN) — now just TWO stores (ADR-0023, down from three): (1) `fabric_sql_database` in DW `cman-dw-ws` = ONE DB, BOTH schemas — `budget.*` transactional (app-written) + `dbo.*` masters + employee; (2) DW gold warehouse (SAP). **env FABRIC_SQL_SERVER/FABRIC_SQL_DATABASE re-point to `fabric_sql_database`** (the DW SQL DB `NB_employee_sync` uses; DB1 `budget_management_web` retired). CC existence/name at write = from `dbo.cc_filler_map` + the DW GL-name ref (DATA #4) — NOT the retiring app Lakehouse.

**A3. RLS resolution** (ADR-0019, `project_primary_manager_rule`): employee source = **`dbo.v_employee_budget_01`** (497 rows — CONFIRMED 2026-07-15, real-data verified to cover 100% of Fillers + their approver1 managers). Fill = `cc_filler_map WHERE filler_email=@me`; See = Fill ∪ (CCs where @me = a Filler's Primary-row manager; Acting ignored) — ONE in-DB JOIN (cc_filler_map + `v_employee_budget_01` same DB). Approver1 email read DIRECTLY off the Filler's own row via the denormalized `manager_email` column — no secondary manager-row lookup. Filler-not-in-master → still Fills, no See-manager, approver1→Nipaporn. Admin overlay = ADMIN_EMAILS (before membership; toggle-gated, ADR-0012/0014); jakkaritw = external full admin. RED-first tests: **497-coverage invariant** (`A_fillers_missing_497=0` AND `C_mgrs_missing_497=0`, asserted on every employee-sync refresh) + scope resolution.

**A4. Main-table read** (ADR-0010/0020/0023): union on `(cost_center, gl_account)` — `dbo.board_budget`(fy=Y) LEFT JOIN `budget.pending_budget`(fy=Y+1) as a **LOCAL cross-schema JOIN inside `fabric_sql_database`**, RLS-filtered via `dbo.cc_filler_map` (board + pending + cc_filler all one DB); only **SAP** read-through (DATA #7 query) is a cross-store merge in FastAPI by (cc,gl). Approved-Y=reference; SAP-led (cc,gl) with no pending → show editable blank Pending-Y+1 row. RED-first: SAP SUM/sign/filter parity.

**A5. Budget write** (`pending_budget`+detail+trip): cell/row save with **row-grain optimistic lock** (`_updated_at`→reject stale that row); re-derive dim snapshots; validate CC∈fill-scope & not excluded, GL exists, m≥0. Special-GL detail (meta_json + dropdown validation vs GL-resolved set; cell=SUM of detail). Trip: budget_trip (1 side/trip), **per-diem DERIVED ON READ** = days×rate(position,country_group)×FX(year), **last-month absorbs rounding**, fail-loud on missing FX. Pending starts BLANK. RED-first: per-diem rounding parity.

**A6. Approval engine** (ADR-0006/0008/0012/0013/0016):
- `approval_status` (ฝ่าย,fiscal_year); at Submit FREEZE approver1/2/3 empcodes + last_submitter. approver1 = Primary-row managerempcode; approver2=Nipaporn(101032); approver3=Waraporn(100427).
- **Self-skip + dedup** (drop step=submitter; dedup; empty→Nipaporn). Reject at ANY step → REJECTED(editable) → resubmit restarts whole chain. Editing never changes status (ADR-0013). Year-lock: past-year Pending read-only for users; **admin edits any Pending freely** (ADR-0012).
- **[GAP-fix] Admin direct-approve branch (ADR-0012 / §1d):** `template=ADMIN` (Template-2 Budget-dept door) OR admin submit of an orphan/post-deadline ฝ่าย → write `APPROVED` directly, **no approver chain, no approval_status chain record**, log `ADMIN_SUBMIT` (Template-2) / `ADMIN_OVERRIDE` (admin override). Distinct from the user chain.
- RED-first: self-skip/dedup + snapshot + admin-direct-approve.

---

## Phase A2 — Frontend (React+Vite)  [DEV]  (mockup 0002.3 = behavior)
**A7.** Scaffold `frontend/` + auth; parse deep-link `?dept=<url-encoded ฝ่าย>&year=<year>` → pre-filter main page (ADR-0016).
**A8.** Main grid — 3 layers (🟢SAP RO / 🔵Approved RO / ⚫Pending edit), ฝ่าย picker (สายงาน›ฝ่าย›CC), year, sorted by gl_group, RLS-scoped, `+ เพิ่ม transaction`.
**A9.** Special-GL subforms (5 groups, GL-conditional dropdowns HARDCODED, grey-out) + Trip Manager (enter-once, per-diem auto, 8 GL = 4 type × 2 side).
**A10.** Approve/reject inline (`รออนุมัติ` badge, step-gated, ADR-0016); admin toggle (ADR-0014); scope-role UX (See-only read-only, approver-only queue, no-scope empty → "…ดูข้อมูลได้ที่ Dashboard"); attach files → SharePoint `เอกสาร ฝ่าย/<ฝ่าย>/<year>/` (folders pre-created; ฝ่าย→folder sanitize `/→-`).

---

## Phase A3 — Automations (Phase-1)  [DE for jobs / DEV for triggers]
**A11. Scheduled jobs** (GitHub Actions cron like sync_employees, OR Azure Function timer): **auto-submit** DRAFT ฝ่าย at deadline (approver1=last-editor's manager, log AUTO_SUBMIT); **30-day auto-escalate** (advance one step, budget-dept still reviews, log AUTO_ESCALATE). Use ONLY the current planning year's `submission_deadline`. **[RESOLVED 2026-07-16, jakkaritw]: DEFERRED to Phase 2** — ADR-0006's admin "stuck/overdue approvals view + departed-approver reassign (ADMIN_OVERRIDE)" is out of Phase-1; the 30-day auto-escalate covers the main stuck case. Same decision round: final-APPROVED confirmation email to the submitter = IN (built as an A12 follow-up); month cells = positive amounts only (no negative/reversal entry).
**A12. Emails** (Graph sendMail, SP cman-fabric-write Mail.Send, `send_signoff_email.py` pattern). All carry a **convenience-only deep-link** (access still enforced server-side, ADR-0016/0004): approver1/2/3 turn-notify → the approver; reject → the **LAST SUBMITTER only** (ADR-0008); reminder on `reminder_date` → Fillers of still-DRAFT ฝ่าย for the active planning year (grouped 1 email/Filler, submitted excluded).

---

## Phase A4 — Verify + deploy
**A13. Tests + gates.** Never-cut tests already RED-first in A3–A6; add coverage (board Replace-by-Year atomicity is DATA-side but the app's read must handle it; RLS scope; approval flows). Run 06 (review) → 07 (security: auth/RLS/secrets/PDPA) → 08 (tests).
**A14. Deploy** — React+Vite + FastAPI (Container Apps or SWA+Functions; no-install machine → Azure Cloud Shell). **jakkaritw approval before prod** + verify-deploy-landed + control-number reconcile (same-FX). Then decommission the retiring master-tables editors once the DATA sync is proven (ADR-0018).
