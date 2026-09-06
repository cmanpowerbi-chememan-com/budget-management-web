# T6 — Write the engineering companion in `plan/uat/`

Type: `wayfinder:task` (AFK) · Status: OPEN · Blocked by: **D2, D6, D7, T3**

## Question

The business pack tells testers what to click. What tells the operator how to run the round
safely, and where do results and evidence land?

## Why it is a separate artifact

The project already separates these deliberately: `requirement_spec/4_sit/` holds one
business-facing file, while `plan/sit/` holds 18 engineering files. Reproduce that split.

## Proposed contents

```
plan/uat/
├── uat-run-plan.md                        waves, safety rules, the baseline/reconcile contract
├── uat-run-log.md                         round header + per-case results + evidence paths
├── evidence/<CASE-ID>/                    png · txt · sql · json per case
└── restore_<dept>_<fy>_baseline.sql       from T3
```

## What the run plan must contain that no existing document does

1. **A baseline-and-reconcile contract replacing the sentinel-year contract.** SIT's 2093 / 2097 /
   2099 shield does not apply — UAT writes real years on the shared production database. The
   substitute is T3's snapshot plus a control number per (department, year) compared before and
   after.
2. **The two facts no current document states**: that `APP_ENV=local` + `DEV_AUTH_EMAIL` is live
   on staging so an unauthenticated staging browser *is* Pornthip; and that with
   `NOTIFICATIONS_DRY_RUN=false` and no label or redirect, a UAT click writes production data and
   mails real colleagues with no visible marker.
3. **The forbidden list**, ported and updated: no unqualified `DELETE`; no
   `setup/truncate_pending_tables.py`; no manual `workflow_dispatch` of `budget-automations.yml`
   or `fx-repersist.yml` during the window; no cookie values, attachment download URLs or secrets
   in any report; no employee-list dumps (PDPA).
4. **The known-issues table**, so testers do not file defects that are already decided: the
   accepted FX-change staleness; the SAP `–` months hidden by ADR-0026; per-diem 0 baht for some
   job levels; step-2/3 approvers reaching departments only via the ADR-0029 overlay; attachments
   deliberately not locked by approval status; the English UI with Thai emails; **and the session
   dialog saying "ระบบให้ล็อกอินได้ครั้งละ 14 ชั่วโมง" while the cookie is actually 1 hour**
   (accepted by jakkaritw 2026-09-06, D5 — this line is what stops five testers filing the same
   report, so it is not optional).
5. **Verdict vocabulary**: `PASS` / `FAIL` / `BLOCKED` / `N/A` / `OBSERVE` / `AWAITING-EYE-CHECK`
   / `NO-FIXTURE`, with no blank result cells allowed.
6. **The abort rule** and who may call it.

## Definition of done

Both markdown files exist · the restore script is linked from the run plan · the round header
table has every environment value filled in from a live read on the day, not copied from here.
