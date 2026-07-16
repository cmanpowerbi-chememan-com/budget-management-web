# Staging Test Plan — Budget Management Web (toward 100% coverage)

Target: `cman-budget-web-stg` (image `subform-fix`). Written 2026-07-16.
Owner of execution: Fable-5 subagents (assignment table at the bottom).

## Context — what is ALREADY proven (97 checks, 5 suites, all app-correct)

| Suite | n | Covered |
|---|---|---|
| read-only differential | 35 | RLS fill/see exact + disjoint + no-leak, SAP grid per-cell == `gold.fact_gl_trans`, board == board_budget, gl master 142, admin overlay, editable pre-deadline |
| mutation | 28 | write+auto-sum, per-diem (domestic + rounding), subform→main rollup, full 3-tier approval, department_locked, reject→resubmit, pending-for-me, upload+list+download, file-type validation |
| suite 2 (deep) | 19 | IDOR (trip-delete, detail owner-mismatch 409), approval-status view authz, admin_view no-widen, header case, negative/overflow, FX-with-rate 4970, side-mismatch 400, see_only role, sibling-CC lock, approve-unsubmitted 404 / approved 409, self-skip |
| deadline | 9 | filler write/trip/submit past-deadline 403, admin bypass 200, admin submit→APPROVED override + audit, deadline-day inclusive |
| null-manager | 6 | approver1 fallback → Nipaporn, dedup pos2, chain to APPROVED |

Bug found+fixed en route: `GET /budget/detail`+`/budget/trip` 500 on non-empty rows (updated_at str→datetime), committed `356570e`.

## Test tooling / safety rules (MANDATORY for every executor)

1. **Easy-Auth-OFF window** — spoof identity via header `x-ms-client-principal-name: <email>`. Frontend E2E: inject the same header via Playwright `extraHTTPHeaders` on the browser context.
2. **Oracle** = live DB re-derived with the app's OWN code (`from app.sap import fetch_sap_actuals`, direct `dbo.*` queries). Compare per-cell to the deployed API.
3. **Ephemeral seed + cleanup + reconcile** — any seed row (submission_deadline, cc_filler_map, pending_budget) is INSERTed under a namespace, and DELETEd in `finally`. Reconcile = the executor's OWN namespace back to baseline (NOT global-zero — other agents run in parallel).
4. **Namespacing (parallel-safe)**: each agent owns a distinct `fiscal_year` + a distinct `cost_center` prefix (see assignment table). NEVER delete outside your namespace. NEVER touch real rows (real deadlines fy 2024–2027, real cc_filler_map).
5. **Notifications stay dry-run** (config default). Never set `NOTIFICATIONS_DRY_RUN=false`.
6. **No prod deploy, no Easy-Auth changes, no git push** — jakkaritw-gated.
7. Every executor runs `python -X utf8`, `open(..., encoding="utf-8")`, writes temp scripts to scratchpad, deletes them after.

---

## Layer 1 — FRONTEND (React SPA)  [BIGGEST GAP — zero browser coverage so far]

Tool: Python Playwright headless vs the staging URL, `extraHTTPHeaders={"x-ms-client-principal-name": "<email>"}`. Verify computed values via `page.evaluate()`; screenshots to disk only (do NOT read images — per CLAUDE.md verify rule; hand path to user).

- **FE1 App shell / routing** — root loads SPA (not JSON), deep-link + hard-reload returns index.html (SPA fallback), unknown route handled, no console errors on load.
- **FE2 Login-bar hierarchy** — สายงาน › ฝ่าย(count) › Cost Center(count) renders from `/scope`; counts match API; email in switcher (login bar V3, doc 01 v0.4).
- **FE3 Main grid render** — grid shows SAP/board/pending 3-layer per row for a filler; numbers match `/budget` API exactly; THB formatting; row count matches.
- **FE4 Grid edit → save → reflect** — type into a Pending cell, save, grid total auto-sums, value persists on reload (writes → namespace CC, clean up).
- **FE5 Special-GL subform open** — click a special GL cell opens the correct subform; existing lines listed (exercises the GET /budget/detail fix in the UI); total in subform == main cell.
- **FE6 Trip Manager (Travelling)** — add a trip, per-diem auto-computes and displays; main grid per-diem cell updates; side COST/SGA selector; edit existing trip (uses the updated_at lock token from GET).
- **FE7 Submit flow** — Submit button visibility = fill-scope; submit → status badge changes; locked cells become read-only after submit.
- **FE8 Approver view** — ฝ่าย-picker + รออนุมัติ badge count; approve/reject buttons for the current approver only; reject requires reason.
- **FE9 Admin zone** — division scope-picker (no "all"), admin can view/edit any division's grid.
- **FE10 Attachments UI** — upload control accepts pdf/xls/png/jpg, rejects others client-side, lists files, download link.
- **FE11 Deadline/lock UX** — behavior when a dept is locked / past deadline (does the UI disable inputs, or only fail on save? — cross-check the known gap: `editable` flag is fill-scope-only, not deadline-aware).
- **FE12 Error surfaces** — 403/409/422 from the API render a human message, not a raw stack; loading + empty states.
- **FE13 Accessibility/i18n smoke** — Thai text renders (no tofu), keyboard focus order on the grid, basic ARIA on buttons.

## Layer 2 — BACKEND (remaining branches / error codes not yet hit)

Namespace: `fiscal_year=2022`, CC-prefix `ZZBE*`.

- **BE1 Optimistic-lock 409** — PUT `/budget/rows`: create → read `updated_at` → write again with the STALE token → 409 conflict. Same for PUT `/budget/detail` and PUT `/budget/trip` (stale `expected_updated_at`), and DELETE with wrong token → 409.
- **BE2 Admin submit — Template-2 door** — seed a `pending_budget` row with `template='ADMIN'` for a seeded dept; admin (non-filler of it) submits → direct APPROVED, audit `ADMIN_SUBMIT`.
- **BE3 Admin submit — orphan dept** — admin submits a department with NO cc_filler_map rows → APPROVED, audit `ADMIN_OVERRIDE_ORPHAN`.
- **BE4 admin_cannot_submit_in_cycle** — admin submits an OPEN normal dept they don't fill (not orphan, no ADMIN rows, before deadline) → 403.
- **BE5 mid_chain_admin_overwrite** — dept already PENDING_APPROVER1; admin ADMIN_SUBMIT on it → 409.
- **BE6 Excluded cost center** — write to a structurally-excluded CC (e.g. `CMKK01`) → 400 `excluded_cost_center` (even as admin).
- **BE7 per-diem country_group=3 ("other") with FX** — trip cg=3, rate_other, FX year → total = days·rate_other·usd_thb; verify.
- **BE8 per-diem rate=0 vs missing rate** — traveler whose job_level rate_domestic=0 (e.g. "Department Head") → per-diem 0, NOT an error; traveler whose job_level has NO per_diem_rate row → 500 `missing_per_diem_rate`.
- **BE9 travel_months validators** — `['03','03']` dedups (no halved split), `['13']`/`['3']`/`['03,03']` → 422, too-many-distinct-months (CSV > 40 chars) → 422.
- **BE10 Trip side-flip re-home** — create COST trip with manual transport/accommodation/other lines → PUT trip side→SGA → assert per-diem re-derived on SGA GL and the 3 manual lines re-homed 5xxx→6xxx, none left on the old side.
- **BE11 Resubmit clears prior state** — reject → resubmit → assert approver1/2/3 `_actioned_at` all NULL and reject_reason cleared.
- **BE12 /budget filters** — `department=` and `cost_center=` query params return the correctly-narrowed subset within scope; out-of-scope filter returns [] (not a leak).
- **BE13 Attachments edges** — 11 MB file → 400 `file_too_large`; download-url with bogus item_id → 502; reserved/illegal filename sanitized.
- **BE14 Batch per-item isolation** — (internal `save_pending_rows` is batch-shaped though HTTP is 1/req) — call `save_pending_rows` directly with a mixed valid/invalid list; assert valid persists, invalid returns its error, no cross-abort.

## Layer 3 — DATABASE (integrity / constraints / concurrency)

Namespace: `fiscal_year=2021`, CC-prefix `ZZDB*`.

- **DB1 NOT-NULL / PK / dedup key** — confirm `pending_budget` PK/unique on `(cost_center, gl_account, fiscal_year)` rejects a duplicate INSERT; `approval_status` unique on `(department, fiscal_year)`.
- **DB2 DECIMAL(18,2) overflow (`data_overflow` 400)** — a month value that passes the Pydantic `lt=1e16` guard but overflows the summed `total_year` DECIMAL(18,2) → 400 `data_overflow` (not a 500).
- **DB3 Concurrency / last-write-wins vs optimistic-lock** — two near-simultaneous PUT `/rows` (grid = last-write-wins per ADR) both succeed and the later wins; two concurrent approvals of the same step → exactly one wins, other → 409 `concurrent_approval` (no double-advance).
- **DB4 RLS parity at the DB** — the CC set a user can write (app 403 boundary) equals `dbo.cc_filler_map` for that filler; no app path can write a CC outside it (re-assert via a spoof sweep of N users).
- **DB5 Referential sanity** — deleting a trip cascades/uses recompute so no orphan `pending_budget_detail` per-diem lines remain; parent cell == SUM(children) invariant holds after every mutation (property check over a random sequence of writes/deletes).
- **DB6 Transaction atomicity** — a detail write + parent recompute commit together (already coded "recompute BEFORE commit"); simulate a mid-write failure path if reachable, else assert the invariant post-commit.
- **DB7 Charset / Thai** — Thai `gl_name`/`department`/`line_label` round-trip through write→read with no mojibake (NVARCHAR).

## Layer 4 — DATA CORRECTNESS (financial never-cut)

Read-only (no namespace needed — pure oracle comparison).

- **DC1 SAP parity re-run** — full per-cell `/budget.sap` == `fetch_sap_actuals(gold, Y-1)` across ALL cost centers of ≥3 users, ≥2 years; assert the `company_code='1000'`, `doc_type<>'CO'`, TFRS16-NULL-safe, excluded-CC, NULL-CC filters all hold (the ADR-0020 never-cut query).
- **DC2 FX matrix** — per-diem for every (country_group ∈ {1,2,3}) × (FX year 2025=40, 2026=35.5) × a rate-bearing job_level; assert THB = days·rate·(fx or 1) with correct rounding + monthly split.
- **DC3 Rounding invariants** — for a battery of random month vectors: `total_year == round(Σ round(mNN,2), 2)` at the API AND after persist+read; cent-boundary (x.xx5) cases.
- **DC4 Control-number reconcile** — SUM of pending per `(ฝ่าย, fiscal_year)` at the SAME FX before vs after a submit/approve cycle == unchanged (approval never mutates money); board vs pending isolation (writing pending never touches board layer).
- **DC5 Cross-year isolation** — writing pending fy=Y leaves sap/board of Y-1 and any other year untouched.
- **DC6 gl master reconcile** — the 142 vs old-spec-137 delta: enumerate the 5 extra `gl_group` codes, confirm each is a legitimate live account (report list), and `is_special` classification matches the special-group rules for all 142.

## Layer 5 — OTHER (suggested, for real 100%)

- **O1 Performance / load** — p50/p95 latency of `/budget` for the 120-CC filler (943 rows) and the admin-wide view (1915 rows); 20 concurrent readers; cold-start time (min-replicas). Flag anything > a sane budget.
- **O2 Security hardening** — headers (HSTS, X-Content-Type-Options, no `Server: uvicorn` leak — known minor), no secret/stack in any error body, `/docs` + `/openapi.json` exposure (must be behind Easy Auth once ON — retest post-Easy-Auth), rate-limit / large-payload rejection, SQL-injection probes on every string param.
- **O3 Deploy / rollback drill** — activate the previous revision and confirm the app serves, then restore; verify `/health?deep=1` gates on DB; confirm token auto-refresh over a >1h window (already spot-checked).
- **O4 Notifications content (dry-run)** — trigger submit/approve/reject/reminder and assert the dry-run PREVIEW payloads (recipient, subject, body) are correct WITHOUT sending — the go-live flip only changes `dry_run`, so content must be right now.
- **O5 Resilience / fault injection** — SAP gold unreachable → `/budget` 502 loud (never silent-empty actuals, ADR-0020); Fabric SQL blip → 502 not 500; Graph/SharePoint down → attachments 502, not a crash.
- **O6 Auto-jobs (A11/A12)** — call `auto_submit_department` (deadline) and `auto_escalate_step` (30-day stale) functions directly against seeded rows; assert they mirror a human submit/escalate and log `AUTO_SUBMIT`/`AUTO_ESCALATE`. (cron stays disabled.)
- **O7 Idempotency / retry** — same POST/PUT retried (network retry) does not double-apply (per-key upsert).

---

## Assignment — Fable-5 executors (parallel-safe via namespaces)

| Agent | Layer(s) | fiscal_year | CC-prefix | Notes |
|---|---|---|---|---|
| **F5-A backend** | Layer 2 (BE1–BE14) | 2022 | ZZBE | seed `pending_budget` template='ADMIN', ephemeral cc_filler_map dept |
| **F5-B database** | Layer 3 (DB1–DB7) | 2021 | ZZDB | constraint + concurrency (threads) + property checks |
| **F5-C data** | Layer 4 (DC1–DC6) | — (read-only) | — | pure oracle diff, no writes, no cleanup |
| **F5-D frontend** | Layer 1 (FE1–FE13) | 2020 | ZZFE | Playwright + spoofed header; screenshots→disk, do NOT read images |
| **F5-E other** | Layer 5 (O1–O7) | 2019 | ZZOT | perf, security headers, resilience, notifications dry-run, auto-jobs |

Each agent: write suite → run vs staging → namespace-scoped cleanup + reconcile (own fiscal_year/CC back to baseline) → report PASS/FAIL with real numbers + any app bug root-caused. Any real bug → STOP and report (do not fix inline; main session routes the fix through the lean gate).
