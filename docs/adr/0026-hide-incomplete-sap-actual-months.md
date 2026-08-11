# 26. Hide incomplete SAP-actual months (entry-date watermark + 23 days)

Date: 2026-08-01
Status: Accepted
Relates to: ADR-0020 (actuals read-through — its SQL contract is NOT touched by this ADR),
ADR-0010 (row visibility — unchanged), plan/sap-actuals-dw-gap-fix.md §4.A.1a

## Context

The SAP · ใช้จริง layer reads `gold.fact_gl_trans` live (ADR-0020). That table is fed by
**daily ENTRY-date files** `SAP_T_GL_TRANS_<bukrs>_<YYYYMMDD>.TXT`, where the file dated D
carries documents **entered** on D-1 — regardless of posting date. Month-close accruals,
reversals and late invoices for posting-month M are therefore entered days-to-weeks *after*
M ends, and a posting month is materially incomplete until that tail has landed.

Measured 2026-07-31/08-01 (task `#apr-entrydate-spill`, `#hide-incomplete-sap-months`;
company 1000; every landing file 2026-03-01..2026-07-31 scanned, fiscal period from raw
field `f[5]`):

| posting month | last entry-date file still carrying one of its docs | completeness at month-end |
|---|---|---|
| 2026-02 | `..._20260321.TXT` (day 21) | — |
| 2026-03 | `..._20260423.TXT` (day 23) | 78.2% (30,960 / 39,567 docs) |
| 2026-04 | `..._20260523.TXT` (day 23) | — |

March's curve: month-end 78.2% → 3 Apr 92.9% → 5 Apr 98.8% → 15 Apr 99.98% → **23 Apr 100.0%**
(39,567 docs). Nothing appears after day 23 in any of the three months.

The live consequence of showing an incomplete month: FY2026 April currently sums to
**22,008,580 THB** against 157,832,827 / 153,166,038 / 129,700,892 for Jan/Feb/Mar — ~15% of a
normal month, because the missing 8,907 documents are exactly the large month-close entries. A
user reading that as a budget reference would plan ~6× too low. The web query itself is correct
(verified: `SAP_ACTUALS_SQL` reproduces gold exactly); the DW is short of source documents.

Alternatives considered:

- **Hide the newest month that has any data.** Simplest, but un-hides a month the moment the
  *next* month gets its first posting — e.g. it would reveal July on 1 Aug, when July is ~10%
  complete. Rejected.
- **Hide through the last day of the following month** (jakkaritw's first proposal). Safe, but
  1 day too conservative against today's watermark: it would also hide March, which the parity
  harness proves is defect-free. Rejected after the day-23 measurement.
- **Drive the cut-off from the calendar** (`today`) instead of the data. Rejected: with the
  loader stalled it would reveal April (15% complete) and show May–July as 0.00, i.e. reproduce
  the exact defect this ADR exists to prevent.

## Decision

A month of the SAP · ใช้จริง layer is displayed only when the loaded entry-date watermark has
passed that month's end by **23 days**:

```
visible(year Y, month M)  ⟺  watermark  >=  last_day(Y, M) + 23 days
```

- **Watermark = the end of the CONTIGUOUS run of entry-days present in the data**, derived from
  `MAX(LEFT(utc_timestamp, 8))` walking back over the distinct entry-days
  (`utc_timestamp` is `varchar(14)`, `YYYYMMDDHHMMSS`; today `20260429235125` → watermark
  `2026-04-29`). A gap of **≥ 4 consecutive missing entry-days** truncates the watermark to the
  day before that gap. Contiguity is load-bearing: loading `202605{23}` while skipping
  `202605{01..22}` must NOT reveal April.
  `prcs_data_dt` is *not* used as the primary source — it holds a single value for the entire
  table (`2026-04-30` across all 4M rows, all fiscal years) and depends on the DW team stamping
  it correctly. `posting_date` and `doc_date` are unusable (`MAX(doc_date)` = `2206-03-25`).
- **Hidden months are nulled server-side**, not merely hidden in the UI — no response may carry
  a number that must not be displayed.
- **`total_year` sums visible months only** and is labelled with its coverage
  (e.g. "รวม ม.ค.–มี.ค."). A total spanning hidden months cannot be reconciled against the
  cells on screen.
- Scope: **the SAP · ใช้จริง layer only.** Approved · งบอนุมัติ and Pending · รออนุมัติ are
  untouched, and row visibility stays exactly as ADR-0010 defines it (a row whose only actual
  falls in a hidden month still appears).
- `SAP_ACTUALS_SQL` and its filters are **not modified** — this is a post-query display rule.
  ADR-0020's never-cut financial contract stands unchanged.

## Implementation notes

- **The mask is applied where the display layer is built** (`read_model._sap_layer`), never
  inside `fetch_sap_actuals`. Two reasons: the DB→web parity harness reads that fetch month by
  month and needs it to stay a complete mirror of gold, and `merge_budget_rows` needs the FULL
  year to decide row visibility — `sap_nonzero_keys` is computed *before* any masking so the
  net-zero row-hide rule (per-month since 2026-08-11 — see the ADR-0010 amendment, its
  canonical spec) cannot change its answer just because months are hidden.
- **The mask applies even to a key with no SAP row at all** — rendering "0.00" in an incomplete
  month is a claim about that month too.
- `SapLayer` re-declares its 12 months as `float | None` (Approved/Pending never can be
  incomplete, so `LayerAmounts` is untouched) and carries `has_actuals`, the only thing a client
  learns about a hidden month — needed so delete-eligibility ("a row with SAP history was not
  added on the web") does not silently flip when months are nulled.
- **Freshness is its own endpoint**, `GET /budget/sap-coverage?year=<planning year>` →
  `SapCoverage {fiscal_year, watermark_date, visible_months, hidden_months}`. Coverage depends
  on the year alone, so switching ฝ่าย / cost center / admin mode re-reads the grid without
  re-reading it, and no existing response shape changes. It carries no financial figures and no
  per-user data: auth yes, RLS no.
- **Fails closed and loud.** An undeterminable watermark (no loaded entry-days in the window,
  all-`NULL` `utc_timestamp`, unparsable day) raises `SapActualsFetchError` → 502, matching
  ADR-0020's rule that a broken DW read must never look like "no actuals".
- `SAP_ENTRY_DAYS_SQL` bounds itself to the trailing ~2 fiscal years and carries
  `fiscal_year >= ?` purely as a pruning predicate (live: 3.02s → 1.22s on the same result set),
  so it never becomes a full 4M-row scan.
- Gap constant = **4 days**. Live 2026-08-01 there are 850 consecutive entry-days
  (2024-01-01..2026-04-29) with zero holes, so a hole of any size is already abnormal; 4 keeps a
  short posting-free stretch from tripping it.

## Consequences

- Applied to today's watermark (`2026-04-29`), FY2026 shows **Jan/Feb/Mar and hides Apr–Dec** —
  which matches the parity harness verdict exactly (m01–m03 zero defects, m04 nine defects,
  m05–m12 zero rows in gold). FY2025 stays fully visible (its cut-off, 23 Jan 2026, has passed).
- The rule **self-heals**: when the daily loader (`PLD_SAP_T_GL_TRANS_D`, still never run) is
  enabled, the watermark advances daily and months appear on their own. No code change is needed
  when the DW gap is fixed, and if the loader stalls again the grid hides itself instead of
  showing wrong numbers.
- In steady state exactly **two months are hidden**: the current month (not finished) and the
  previous month (until day 23). During the FY2027 planning season the SAP reference column will
  legitimately show ~6 of 12 months of FY2026; the existing YearPicker (SAP layer =
  `planning_year - 1`) remains the way to see a complete reference year.
- Day 23 is measured on three months of one company (1000; the web filters
  `company_code='1000'`). If a future month's tail runs longer, the constant — not the rule —
  is what changes.
