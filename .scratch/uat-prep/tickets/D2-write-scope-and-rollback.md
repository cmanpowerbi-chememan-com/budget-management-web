# D2 — What is UAT allowed to write, and how does it get undone?

Type: `wayfinder:grilling` · Status: OPEN · Blocked by: nothing

## Question

UAT will write the live production database. Which fiscal year and which departments may it
touch, how far down the approval chain may it go, and what exactly is the way back?

## The constraint that removes the easy answers

- **FY2027 is the only writable year.** `dbo.submission_deadline` holds exactly one row
  (deadline `2026-10-07`, reminder `2026-09-22`). `write_model._ensure_year_open_for_write`
  refuses every other year for **everyone, admin included**.
- **The sentinel-year shield used by SIT does not apply.** 2093 / 2097 / 2099 cannot be selected
  in the YearPicker (range is 2020…current+1, deep-links checked ±5 years), and seeding a
  sentinel row into `dbo.submission_deadline` leaks a junk year into the picker of all 114
  departments. A previous 2099 attempt returned 403 until a real row was seeded.
- **`APPROVED` is terminal inside the app.** `backend/app/routers/approval.py` exposes only
  `/submit`, `/approve`, `/reject`, `/override-step`, `/pending-for-me`, `/locked-departments`,
  `/status`. There is **no reopen and no reset route**. `approval.py:692-695` refuses a filler
  resubmit unless the status is `REJECTED`. An admin can still edit the money rows of an
  APPROVED department (`write_model.py:551` returns before the lock check at `:558`) but
  **nothing in the app can un-APPROVE the status row.** Only a direct DB `UPDATE`/`DELETE` can.
- **The only restore scripts that exist are dead.** `plan/sit/restore_fy2027_testdata.sql` and
  `restore_stale_testdata_2026-08-07.sql` are 2026-08-05 snapshots of data that no longer exists.

## Live starting state (2026-09-06)

| | `Data & Analytic` | `Solution Delivery` |
|---|---|---|
| FY2027 approval_status | **REJECTED**, reason `test`, by Arthid 2026-09-05 18:03 | **no row — never submitted in any year** |
| FY2027 pending_budget | 3 rows / **42,040.00 THB** | **0 rows** (a submit today would be refused `department_empty`) |
| Trips | trip 43 China, remark `test111` | none |

Company-wide FY2027 is 17 rows / 147,140.00 THB across 6 departments, and only two departments
have any approval record at all.

## What must be decided

1. **The year.** FY2027 (the real cycle) or a seeded sandbox year, with the leak priced.
2. **How far the chain runs.** Reaching `APPROVED` end-to-end is the single most important thing
   UAT proves — but it is also the one state the app cannot undo.
3. **The restore contract.** A dated `SELECT`-export of all six `budget.*` tables for the UAT
   departments, plus the un-approve / delete statements **written and reviewed before the round,
   not improvised after it**.
4. **Whether the `Data & Analytic` REJECTED("test") state is cleared first**, so testers do not
   open the round looking at the word "test" as a rejection reason.

## Recommendation

FY2027, full chain including `APPROVED`, **conditional on T3 landing first** — the snapshot
exported and the un-approve script written and reviewed. A sandbox year does not test what UAT
exists to test and pollutes every department's picker. Stopping short of `APPROVED` throws away
the round's main proof.
