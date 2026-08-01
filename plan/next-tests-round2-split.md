# Plan — Test Round 2 Split (Kimi × CC, parallel-safe)

**Date:** 2026-07-24 · **Owner of this split:** kimi (jakkaritw ordered)
**Predecessor:** `plan/remaining-tests-split.md` (all 4 items done + re-verified).
**Out of scope (unchanged):** staging `az acr build` = jakkaritw's gate in Cloud Shell.

## Lane assignment

| Item | Owner | Type | Writes |
|---|---|---|---|
| 1. 🏁 Concurrency races (live) | **Kimi** | API + DB, 2-actor orchestration | `10IT012000` **FY2094** (throwaway year) only |
| 2. ⚙️ Backend jobs E2E dry-run | **CC** | read-only dry-runs | none (NO `--run`/`--execute` flags) |
| 3. 🖥️ Viewport smoke (tablet/mobile) | **CC** | Playwright, read-only | none |
| 4. 🧹 e2e-stale-specs-fix | **CC** | already `willdo` in tracker | e2e spec files only (no app code, no DB) |

FY isolation is the collision killer: kimi races on **FY2094** (CC's own
throwaway-year pattern from the deadline-lock lane — no deadline row = open,
approval chain is per-dept not per-year so Solution Delivery's chain works),
CC's jobs dry-run reads the REAL **FY2027** undisturbed.

## Item 1 — Concurrency races, live (Kimi)

Unit tests cover the guards; this lane proves them under true simultaneity.
All on `10IT012000 / Solution Delivery / FY2094`, cleanup to 0 rows after
(pending_budget, approval_status, approval_log for that dept/FY):

- **R1 same user, two tabs, different rows:** suchanyay fires PUT row-A and PUT
  row-B concurrently (asyncio/two curls in parallel) → both 200, both rows in DB
  exactly as sent.
- **R2 same row, simultaneous duplicate PUTs:** same `expected_updated_at` fired
  twice at the same instant → exactly one 200, one 409 (Thai conflict message);
  DB has the winner's value only.
- **R3 approver double-fire:** submit the dept (suchanyay), then fire
  `/approval/approve` as arthids TWICE concurrently → exactly one advances the
  status (PENDING_APPROVER1 → PENDING_APPROVER2), the other gets the race-guard
  error (409 class), `approval_log` has exactly ONE APPROVE row for L1 (no
  double-advance, per approval.py's conditional-UPDATE "never-cut" design).
- **R4 FX job vs live user edit (design-doc R3):** create one overseas test trip
  on 10IT012000 **FY2027** (real FX exists; txn tables are empty so the job only
  touches this trip), run `python -m jobs.repersist_perdiem_fx --fiscal-year 2027 --run`
  WHILE suchanyay PUTs a trip-header edit → assert no error either side, final
  stored value is deterministic, and a job re-run converges to the same value
  (idempotent self-correction). Then cleanup the trip + restore 0 rows.
  NOTE: R4 is the only sub-test on FY2027 — safe because the whole txn space is
  currently empty; do NOT run R4 if any real FY2027 data has appeared.

Deliverable: tracker entry `concurrency-races-kimi` with per-race outcome +
cleanup verification.

## Item 2 — Backend jobs E2E dry-run (CC)

Never run the scheduled automations live before; dry-run them against REAL
FY2027 data and report what each WOULD do (candidates it finds, actions it
would take, emails it would send — notifications are dry_run=True by default,
confirm that flag before any run):
`auto_submit`, `send_reminders` (`auto_escalate` was deleted 2026-08-01,
ADR-0027 — check `backend/jobs/` for the
exact CLIs; use each job's dry-run default — never pass its execute flag).
Report per job: what it scanned, what it would act on, anything surprising
(e.g. a dept unexpectedly eligible for auto-submit).

Deliverable: tracker entry by CC.

## Item 3 — Viewport smoke (CC)

Playwright at tablet (~768px) and phone (~390px) widths as suchanyay on the
main grid: frozen identity columns stay put, 12-month area scrolls, the edit
flow (select dept → type a month cell → commit) remains usable at tablet width;
document anything unreadable/unusable at phone width (grid this wide may
legitimately be desktop-first — report, don't force-fix).

Deliverable: tracker entry by CC.

## Item 4 — e2e-stale-specs-fix (CC)

The 3 pre-existing Playwright failures (already tracked `e2e-stale-specs-fix`):
(a) approver-journey 2.1 — dept auto-select (2026-07-21 change) vs empty-picker
expectation; (b) edge-states 4.1 — 1 extra `/scope/departments` call (the
reproduce-live bug; decide: fix app code OR adjust expectation with the bug
documented — prefer fixing the app if the fix is small); (c) filler-journey
1.1 — stale `/ปีงบประมาณ/` locator vs renamed YearPicker aria-label. Update the
specs (or the small app fix for b) until the suite is green 23/23 — WITHOUT
weakening what the specs actually assert about behavior.

## Guardrails (binding)

1. **FY lanes:** Kimi = FY2094 (+ R4's single carefully-scoped trip on FY2027);
   CC = FY2027 read-only. Nobody touches other years.
2. **Approval endpoints:** only Kimi (item 1) may call `/approval/*`, only on
   Solution Delivery/FY2094, with full cleanup (status back to no-row,
   log rows deleted, verified by SELECT = 0).
3. **Jobs:** dry-run defaults only — CC must NOT pass any execute/run flag and
   must confirm `notifications_dry_run` is True in output before proceeding.
4. **e2e fix scope:** test files (+ at most one small app fix for the
   departments-double-fetch if CC takes it — that fix goes through its own
   commit, never bundled with spec edits).
5. **Servers:** shared read :3000/:8000; no restarts/kills without a tracker
   note first.
6. **Tracker rule (jakkaritw's standing order):** log `doing` before starting,
   `done` + results immediately after — each lane owns its entries.
7. Header injection: route-scoped (127.0.0.1 origins only) in every Playwright
   context.

## Done definition

All 4 tracker entries `done`; kimi re-verifies CC's items 2–3 results
(spot-check one job dry-run output + one viewport run) per the established
pattern; CC spot-checks nothing of Kimi's (races are DB-verified by definition).
Then: staging remains the only big gate left.
