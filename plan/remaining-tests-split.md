# Plan — Remaining Test Items, Split for Parallel Execution (Kimi × CC)

**Date:** 2026-07-24 · **Owner of this split:** kimi (jakkaritw ordered)
**Scope:** the 4 remaining test items from kimi's own list. Everything is local; the
big staging gate (`az acr build`) stays with jakkaritw in Cloud Shell — NOT part of this plan.

## Lane assignment

| Item | Owner | Type | DB writes | Server load |
|---|---|---|---|---|
| 1. 🔐 Easy Auth trust review | **Kimi** | read-only review (code + docs) | none | none |
| 2. 🔁 Mini-regression: 2 merged fixes | **Kimi** | Playwright + small write/cleanup | `10IT012000` FY2027 only | medium |
| 3. 🌐 Font-blocked degradation | **CC** | Playwright, route-abort fonts | none | medium |
| 4. ⏱️ Performance smoke | **CC** | timing requests + render timing | none | **needs quiet box** |

Rationale: items 1–2 go to kimi because kimi raised the auth concern (independent
security eye) and the 2 fixes were authored by CC (author must not be the only
verifier). Items 3–4 go to CC (fresh functional checks + the perf pass needs one
coordinated quiet window, simpler to sequence inside one lane).

## Item 1 — Easy Auth trust review (Kimi)

**Question:** in production, can a caller spoof identity by hitting the container
directly with a self-made `x-ms-client-principal-name` header?

Steps:
1. Read `backend/app/auth.py` + `backend/app/main.py` middleware: does anything
   validate the header beyond presence (e.g. Easy Auth's additional headers,
   `APP_ENV` gating behavior)?
2. Read `docs/deploy/A14_RUNBOOK.md` + `.github/workflows/*deploy*` + `backend/Dockerfile`:
   is Container Apps ingress documented as external or limited to the Easy Auth front?
   Is Easy Auth enabled on the container app itself (platform layer)?
3. Produce a verdict: SAFE / GAP, with evidence per file. If GAP: recommend the
   minimal fix (e.g. ingress internal-only, or validate an Easy-Auth-only header
   like `x-ms-client-principal-idp` + principal id) — **report only, no code change
   in this pass** (a fix becomes its own task).
4. Include a short Cloud Shell checklist for jakkaritw to confirm the live ingress/
   Easy Auth config (no az CLI on this machine).

Deliverable: tracker entry `easy-auth-trust-review-kimi` with verdict + evidence.

## Item 2 — Mini-regression of 2 merged fixes (Kimi)

Read each fix commit FIRST, then verify the NEW behavior (not the old one I tested
before the fix):

- `a02ec3c` deep-link `?year=` ↔ YearPicker label alignment (off-by-one):
  load `/?dept=Solution Delivery&year=<label-year>` as suchanyay via Playwright
  (route-scoped header) → the YearPicker shows the same year as the URL, and the
  `/budget` call fires with the fixed mapping. Document the new mapping explicitly
  (it changed from the pre-fix semantics I tested earlier).
- `e575d58` month-cell 2dp decimals: as suchanyay on 10IT012000 FY2027, PUT one
  pending row with 2-decimal values (e.g. `m01=123.45`, `m02=67.89`) via API →
  DB stores the decimals exactly → grid displays decimals **only when fractional**
  (123.45 shown, 100 shown as 100) → cleanup row → verify 0 left.
  If UI input is easier than API for the display check, use it; API is enough for
  the storage check.

Deliverable: tracker entry `mini-regression-2fixes-kimi` with per-fix PASS/FAIL.

## Item 3 — Font-blocked degradation (CC)

Playwright with `page.route` aborting `fonts.googleapis.com` + `fonts.gstatic.com`
(simulating a corporate network that blocks Google Fonts): load the app as any
persona → UI must stay readable and fully functional with fallback fonts (no blank
text, no broken layout beyond cosmetic font differences), zero blocking errors.
Bonus datapoint: measure load time with vs without fonts blocked (blocked should
not be *slower* beyond a small margin — hung font requests would be a finding).

Deliverable: tracker entry by CC.

## Item 4 — Performance smoke (CC)

**Requires the quiet window (see guardrails).** Capture the first-ever perf numbers:
- `GET /budget?year=2027` response time: single CC (10IT012000) vs a wide scope
  (admin or khattariyas 121 CCs) — 5 samples each, report median/p95.
- Grid render time for the biggest dept (DOM ready → grid interactive) via
  Playwright tracing/performance API.
- Payload sizes (KB) for both /budget calls.

Deliverable: tracker entry by CC with the numbers table.

## Guardrails (binding — กันชนกัน)

1. **Quiet window for perf:** item 4 runs ONLY after both Playwright lanes (items
   2, 3) report done — concurrent browser load makes timing numbers meaningless.
   CC sequences this internally; kimi posts "lane-2 done" in tracker when finished.
2. **DB writes:** only item 2 writes (10IT012000 FY2027, one row, cleanup to 0
   verified by SELECT). Everything else is read-only. Nobody touches
   `/approval/*` or any other CC/FY.
3. **Files:** this pass produces reports/tracker entries only — **no code edits**
   (item 1's fix, if any, is a separate task decided after the verdict).
4. **Servers:** shared read on :3000/:8000; no restarts/kills without announcing
   in tracker first (the hung-:3000 incident is still fresh).
5. **Tracker rule (jakkaritw's standing order):** log your item as `doing` BEFORE
   starting and `done` + results immediately after finishing. Each lane owns its
   own entries.
6. Header injection: Playwright runs use route-scoped
   `x-ms-client-principal-name` for 127.0.0.1 origins only (never context-wide —
   the font-CORS artifact + the debris-row lesson).

## Done definition

All 4 tracker entries `done` with results; kimi re-verifies CC's two numbers
tables (spot-check one /budget timing + the fonts run) the way kimi verified
earlier rounds; summary reported to jakkaritw. Remaining after this plan:
staging `az acr build` (jakkaritw, Cloud Shell) + `e2e-stale-specs-fix` (willdo).
