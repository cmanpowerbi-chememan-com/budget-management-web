# T3 — Export the baseline and pre-write the restore

Type: `wayfinder:task` (AFK) · Status: OPEN · Blocked by: **D2, D3**

## Question

Before anything is written, capture exactly what the UAT departments look like, and write the
statements that put them back — including the one the application itself cannot do.

## Why this is a blocker, not paperwork

`APPROVED` is terminal. `backend/app/routers/approval.py` has no reopen and no reset route, and
`approval.py:692-695` refuses a filler resubmit unless the status is `REJECTED`. If UAT drives a
department to `APPROVED`, only a direct database write frees it — and no such script has ever
been written or reviewed in this project. The two restore scripts that exist
(`plan/sit/restore_fy2027_testdata.sql`, `restore_stale_testdata_2026-08-07.sql`) are 2026-08-05
snapshots of data that no longer exists.

## Work

1. `SELECT`-export, to a dated file under `plan/uat/`, every row for the UAT departments and the
   fiscal year D2 chose, from all six tables: `budget.pending_budget`,
   `budget.pending_budget_detail`, `budget.budget_trip`, `budget.approval_status`,
   `budget.approval_log`, `budget.reminder_log`. Include a control number per (department, year):
   `SUM(total_year)` and a row count.
2. Also snapshot the two `dbo.*` rows the round depends on: the `submission_deadline` row for
   that year, and the `cc_filler_map` rows for the three cost centers.
3. Write `plan/uat/restore_<dept>_<fy>_baseline.sql` — the exact `DELETE` / `UPDATE` statements
   that return each table to the snapshot, **every statement carrying an explicit
   `fiscal_year` predicate** (an unqualified `DELETE` can destroy other departments' real data).
4. Include the un-approve statement explicitly, with its target verified before it is ever run.
5. Have the script reviewed before the round, not after.

## Constraints

- `setup/truncate_pending_tables.py` truncates three tables without looking at the year. It is
  **not** a test tool and must not be used.
- Financial rule: reconcile with `SUM` and `DISTINCT` and a control number, before and after.
- Do not dump employee names or reporting lines into the evidence file — PDPA. Report counts
  plus one example row.

## Definition of done

The dated export exists · the restore script exists and has been read by a second pass · the
control numbers are recorded · the un-approve statement's target has been verified by `SELECT`
first.
