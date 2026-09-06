# D7 — When does UAT run, and what does "UAT passed" mean?

Type: `wayfinder:grilling` · Status: OPEN · Blocked by: **D1, D2, D3**

## Question

What are the dates, and what is the written entry / exit gate that makes "UAT passed" a fact
rather than an opinion?

## Why this is still open

- Nothing under `requirement_spec/` defines UAT criteria. `.claude/plan.md` mentions UAT exactly
  once, inside an ADR-0029 note.
- The Go/No-Go bullets were **promised to management** in
  `monthly_update/project_status_report_2026-08.html` but never turned into a checkable gate:
  zero blockers · all four mail types delivered to the right person · no cross-department
  visibility leak · department totals reconciled before and after · response time within
  standard · **written approval by jakkaritw**.
- `plan/sit/sit-test-plan.md:913-946` already has a strong entry/exit model to port, but its
  entry gate is built on the **sentinel-year contract**, which does not apply here — UAT writes
  real years on the shared production database, so the shield must become a
  **baseline-and-reconcile contract** instead.
- The only recorded go-live target — end of August 2026 — **has passed** with nothing
  superseding it.

## Hard dates the window must respect

| Date | What happens |
|---|---|
| **2026-09-22** | The real FY2027 deadline-reminder email fires to real fillers company-wide. |
| **2026-10-07** | The real FY2027 submission deadline. After it, fillers are locked out and only admins can write. |
| ~06:30 daily | The SharePoint → `dbo.cc_filler_map` sync runs, so any D3 master edit needs a full day of lead time. |

## What must be decided

1. The start and end dates, and how many working days.
2. Entry criteria — what must be true before day 1 (T1…T4 landed, baseline exported, restore
   script reviewed, both departments' SharePoint attachment folders created, one tester login
   proven).
3. Exit criteria — the numbers, ported from the SIT model and made concrete with the six
   management bullets.
4. What a `FAIL` on a P1 case does to the round.
5. Who signs, and on what artifact (see T5's acceptance sign-off sheet).

## Recommendation

Pick a 3–5 working-day window that **ends before 2026-09-22**, so no tester has to distinguish a
UAT mail from the genuine company-wide reminder. Port the SIT entry/exit structure verbatim,
swapping the sentinel-year contract for the baseline/reconcile contract, and make jakkaritw's
written approval on the sign-off sheet the single exit condition that cannot be waived.
