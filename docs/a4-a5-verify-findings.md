# A4 + A5 exhaustive live-DB verification — confirmed defects (2026-07-15)

6 parallel lenses probed the LIVE consolidated Fabric SQL DB (`fabric_sql_database`) + gold warehouse
end-to-end (real FastAPI routes, real personas from live masters, sentinel fiscal_years 2090-2095,
cleaned up). The adversarial-verify stage did not run (session limit), so these are **probe findings**;
most carry live evidence (real query output / real numbers) and are treated as CONFIRMED. Deduped from
24 raw findings (4 lenses independently reported the per_diem column bug).

Mocks + the 6 prior A4/A5 gate rounds all PASSED while these bugs were live — same class as the earlier
`status` / `gl_group.group_name` column bugs. **Fix before A6.**

## SHOWSTOPPER
- **D1 [CRITICAL] `dbo.per_diem_rate` column is `job_level`, not `position`** — `write_model.py:791`
  `_lookup_per_diem_rate` does `WHERE position = ?`; live table has no `position` (cols: `job_level`,
  `rate_domestic`, `rate_asian`, `rate_other`, `_load_dt`, `_load_dttm`). Every `POST|PUT /budget/trip`
  raises pyodbc 42S22 → router 502. **Whole Travelling-Expense group (8 GLs) 100% dead.** Reported by 4
  independent lenses; live error reproduced. Fix: `WHERE job_level = ?`. (NOTE: the VALUES still equal
  the employee's `job_level_name_en`; only the column NAME assumption was wrong — the spec DBML said
  `position`.)

## NEVER-CUT financial (must fix + verify)
- **D2 [CRITICAL] SAP `assignment_number<>'TFRS16'` is not NULL-safe** — `sap.py:29`
  `NULL <> 'TFRS16'` = UNKNOWN → every NULL-assignment row is silently dropped. Live: FY2025 drops 706
  rows / -12,827,790.81 THB; FY2026 fabricates ~3.87M THB of PHANTOM actuals on balanced clearing
  accounts (GL 9110100020: the +NULL legs are dropped, the -PO legs kept, so a cell whose true actual
  is 0.00 shows -3.26M). Contradicts ADR-0020 "reversal pairs net to zero, no reversal filter needed."
  Fix: `AND (assignment_number IS NULL OR assignment_number <> 'TFRS16')`.
  ⚠️ **POLICY: this changes the ADR-0020 SAP contract → confirm with jakkaritw before editing.** (The
  earlier live "parity" test compared the code query to an identical hand-query — both dropped NULLs the
  same way, so it matched; it proved self-consistency, not correctness.)
- **D3 [CRITICAL] IDOR on `detail_id`** — `write_model.py:683` (+ D4)
  `PUT /budget/detail` authorizes on payload `cost_center` but the UPDATE keys on `detail_id` +
  `_updated_at` only. Live: filler `arayay` (fill=10SC012000) rewrote detail_id=30 belonging to
  10AC011000 → 999,999 THB, by declaring their own CC in the payload. `_updated_at` is a concurrency
  token, NOT a capability. Fix: the detail UPDATE + recompute must use the detail row's ACTUAL
  cost_center (read it), reject if it is outside the caller's Fill scope.
- **D4 [HIGH] parent-cell recompute uses payload CC, not the detail row's real CC** — `write_model.py:699`
  Non-malicious sibling of D3: a multi-CC filler (45% span >1 CC) whose client posts the wrong CC
  desyncs parent cell from SUM(detail) + writes a phantom all-zero parent row. Same fix as D3.
- **D5 [CRITICAL] parent-cell recompute has no optimistic lock** — `write_model.py:522`
  `_recompute_parent_cell` reads SUM(detail) then blindly UPDATEs. RCSI is ON, so two concurrent
  detail saves each see only their own line → last writer overwrites with a stale sum → money vanishes.
  Live natural race: 5/5 runs `SUM(detail)=300` but `parent=200` (or 100). Breaks never-cut
  `parent == SUM(detail)`. The IntegrityError-recovery branch re-runs the UPDATE with the SAME stale
  `months` → turns a conflict into silent corruption. Fix: recompute atomically (single
  `UPDATE ... SET mNN = (SELECT SUM ...)` or serialize under the row lock); never write a precomputed
  stale sum.
- **D6 [HIGH] float/DECIMAL total_year drift** — `write_model.py:377` (+ detail `:654`)
  Months cross as unbounded Pydantic `float`; `total_year` is summed in Python from UNROUNDED values
  while SQL rounds each month to DECIMAL(18,2). Live: `100.005+100.005` → total_year 200.01 but stored
  months sum 200.00. Breaks never-cut `total_year == SUM(m01..m12)` + control-number reconcile. Fix:
  quantize each month to 2dp (Decimal) at the boundary; compute total_year from the rounded months.
- **D7 [HIGH] `travel_months` unvalidated → silent per-diem corruption** — `per_diem.py:107-116`
  Live: `['99']` → 750 lands in total_year, m01..m12 all 0, parent=0 (total_year != SUM). `['03','03']`
  → amount HALVED (500 vs 1000). Non-numeric (`''`,`'abc'`,`'03,03'`) → uncaught 500. Fix: validate each
  entry ∈ 1..12, dedupe, reject malformed as per-item 400.
- **D8 [HIGH] trip side-flip strands the 3 manual travel lines** — `write_model.py:948`
  Side flip re-homes only the per-diem line; transport/accommodation/other keep the OLD side's GL +
  the now-flipped trip_id → one trip spanning COST AND SGA (the exact state the create path rejects).
  Live-proven. Fix: on side flip, re-home / recompute ALL of the trip's detail lines, not just per-diem.

## robustness / correctness
- **D9 [HIGH] NVARCHAR/DECIMAL overflow → uncaught 500 + PARTIAL batch** — `write_model.py:238,320`
  No Pydantic `max_length`/range. remark>500 chars → SQL 2628; m01≥1e16 → SQL 22003. Both are
  `pyodbc.Error` NOT in `_CAUGHT_PER_ITEM` → 500, no rollback, rows-before committed / rows-after not:
  breaks never-cut "one row's failure never blocks the others." Fix: Pydantic max_length + range → clean
  per-item 400; and catch these DB errors per-item with rollback.
- **D10 [MEDIUM] `department_filter` drops SAP-led rows** — `read_model.py:272`
  SAP-led (cc,gl) rows have no department on board/pending → `dept` is None → filter drops them. Live:
  Talent & Culture loses 10 SAP-led rows / 302,560.17 THB under the dept filter; user can't budget those
  GLs. Fix: derive department for SAP-led rows from cc→department (cc_filler_map) before filtering.
- **D11 [MEDIUM] `_lookup_cc_dims` nondeterministic** — `write_model.py:265`
  `SELECT TOP 1 department, division, c_level FROM dbo.cc_filler_map WHERE cost_center=?` with no
  ORDER BY, but grain is (cc, filler_email). CC 10OS011400 has 2 divisions → snapshot flips by scan
  order. Fix: deterministic pick (e.g. MIN/agreed rule) or resolve division from a single-valued source.
- **D13 [LOW] internal name leak** — `write_model.py:257` — 400 body echoes `dbo.gl_group`; make generic.

## POLICY calls for jakkaritw (block the financial fixes)
- **D2** SAP NULL-assignment: keep NULL rows (fix) — changes the ADR-0020 query + the SAP total. (Evidence
  strongly says keep: balanced clearing accounts must net to 0.)
- **D12** `dbo.per_diem_rate` rates are `NOT NULL DEFAULT 0`, so the `MissingPerDiemRateError`-on-NULL guard
  (`per_diem.py:51`) is unreachable; positions like Department Head / Operators have rate 0.00. Is 0.00 a
  VALID rate (those positions get no per-diem) or "unconfigured → fail loud"? If 0 is unconfigured, the
  guard must test for 0, not NULL. Business rule — confirm.

## proven GOOD on the live DB (real coverage, not assumed)
- SAP total FY2026 = 309,049,478.15 THB (code == an independent hand-query) — BUT both share the NULL
  bug (D2); parity ≠ correctness.
- RLS read: 0 rows outside See scope for real fillers; See-only rows editable=False; Fill rows editable.
- Year semantics off-by-one-proof (board_year derived once, passed to both board + SAP).
- FULL OUTER JOIN: board-only + pending-only rows persist; no dup / no NULL-key row.
- Same-row optimistic lock (normal pending rows) + fill-scope 403 + excluded-CC reject held under live races.
- Entertainment 1,000 → 1,000; +500 → 1,500 (parent==SUM for the SINGLE-writer detail path).
