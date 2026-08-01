"""SAP actuals read-through (ADR-0020, A4) — the DW `gold.fact_gl_trans`
warehouse is queried live on every request; nothing is copied into the app's
own store. The query below is a **never-cut financial contract** — do not
edit its filters/columns without a matching ADR-0020 update:

- `company_code='1000'` is TRIPLY load-bearing (THB-only + no cross-company
  double-count + one consistent sign convention) — never remove/loosen.
- `doc_type<>'CO'` drops CO postings that double-count the FI side.
- The excluded cost-center list intentionally does NOT include `10SC012000`
  (removed from the exclusion list 2026-07-14 — it is a valid CC).
- `(assignment_number IS NULL OR assignment_number <> 'TFRS16')` and
  `fiscal_year=?` (the caller's year). **Fixed 2026-07-16 (D2, confirmed
  policy call):** the bare `assignment_number<>'TFRS16'` is NOT NULL-safe —
  in SQL, `NULL <> 'TFRS16'` evaluates to UNKNOWN, so every NULL-assignment
  row was silently dropped by the WHERE clause. Live evidence: FY2025 lost
  706 rows / -12,827,790.81 THB; FY2026 fabricated ~3.87M THB of PHANTOM
  actuals on balanced clearing accounts (e.g. GL 9110100020, CC 10QC011000 —
  the +NULL legs were dropped while the -PO legs were kept, so a cell whose
  true actual is ~0.00 showed a multi-million THB balance). This also
  contradicted this same module's own "reversal pairs net to zero" note —
  they only appeared to hold because the earlier live parity test compared
  the code's query to an IDENTICAL hand-written query that dropped NULLs the
  same way (self-consistency, not correctness). NULL-assignment rows are now
  explicitly KEPT.
- No sign flip: `company_curr_amount` already carries the correct sign.
- No `doc_status` filter: verified 2026-07-14 that including/excluding the
  only other value ('U') never moves any SUM at any grain.
- `AND cost_center IS NOT NULL`: added 2026-07-16 (D2 follow-up audit) purely
  to make an EXISTING, INTENTIONAL exclusion explicit — it is **behavior-
  identical**, not a fix. `NULL NOT IN (...)` already evaluates to SQL
  UNKNOWN, so NULL-cost_center rows were already dropped by the `NOT IN`
  clause above. That drop is correct and required: the budget grid is keyed
  by `(cost_center, gl_account)`, so a posting with no cost center belongs to
  no user's scope and cannot be displayed. Live volume audited 2026-07-16:
  FY2025 = 2,249,381 such rows / -1,138,962,985.31 THB; FY2026 = 515,775 rows
  / -132,909,268.58 THB. **DO NOT "NULL-safe" this predicate** the way
  `assignment_number` was fixed above — unlike that column, keeping
  NULL-cost_center rows would pull ~1.1 BILLION THB of postings with no
  cost center into the actuals and corrupt every cell. See ADR-0020.

A missing/failed DW connection or query must surface as a loud error to the
caller (never a silently empty green actuals layer) — see `SapActualsFetchError`.

ADR-0026 (hide incomplete months) lives in this module too, as a SEPARATE
post-query rule: `SAP_ACTUALS_SQL` above is frozen, so the entry-day
watermark is a second, small read (`SAP_ENTRY_DAYS_SQL`) and the month
masking itself is applied where the display layer is built
(`read_model._sap_layer`), never inside `fetch_sap_actuals` — the DB->web
parity harness depends on that fetch staying a complete mirror of gold.
"""
import calendar
import logging
from collections.abc import Iterable
from datetime import date, datetime, timedelta

import pyodbc
from pydantic import BaseModel

logger = logging.getLogger(__name__)

MONTH_COLUMNS: tuple[str, ...] = tuple(f"m{m:02d}" for m in range(1, 13))

# Per ADR-0020 / BUILD_PLAN A4, corrected 2026-07-16 (D2 — see module
# docstring): the assignment_number filter is now NULL-safe. Do not
# reformat/reorder/edit without a matching ADR-0020 update.
#
# `cost_center IS NOT NULL` (added 2026-07-16, D2 follow-up) is a deliberate,
# behavior-identical restatement of the exclusion `cost_center NOT IN (...)`
# already produces via NULL semantics (NULL NOT IN (...) = UNKNOWN). Unlike
# `assignment_number` above, do NOT make this NULL-safe — see the module
# docstring: NULL-cost_center rows have no scope owner and must stay excluded.
SAP_ACTUALS_SQL = """
SELECT cost_center, gl_account_number, fiscal_year, period_month, SUM(company_curr_amount) AS actual_thb
FROM gold.fact_gl_trans
WHERE company_code='1000' AND doc_type<>'CO'
  AND cost_center NOT IN ('CMRY01','CMKK01','CMPB01','MNLB00','MNLB01','MNLB02','MNLB03','MNLB04')
  AND cost_center IS NOT NULL
  AND (assignment_number IS NULL OR assignment_number<>'TFRS16') AND fiscal_year=?
GROUP BY cost_center, gl_account_number, fiscal_year, period_month
"""


class SapActualsFetchError(RuntimeError):
    """Raised when the SAP gold-warehouse read-through query fails (missing
    grant, connection drop, timeout, etc). Callers MUST turn this into a
    loud 5xx response — never swallow it into an empty actuals layer
    (ADR-0020 Consequences: a revoked grant must not look like "no actuals")."""


def fetch_sap_actuals(
    conn: pyodbc.Connection, fiscal_year: int
) -> dict[tuple[str, str], dict[str, float]]:
    """Fetch + pivot one fiscal year of SAP actuals.

    Returns `{(cost_center, gl_account): {"m01":.., ..., "m12":.., "total_year":..}}`.
    Different `gl_account` values for the same `cost_center` are always kept
    as separate keys — COST (5xxx) and SG&A (6xxx) totals never cross.
    """
    cursor = None
    try:
        cursor = conn.cursor()
        cursor.execute(SAP_ACTUALS_SQL, fiscal_year)
        rows = cursor.fetchall()
    except pyodbc.Error as exc:
        # `conn.cursor()` itself can raise (closed connection, dropped
        # session) -- must wrap that too, not just execute()/fetchall()
        # failures, or a connection-level drop bypasses SapActualsFetchError
        # entirely (live-DB finding, 2026-07-15).
        raise SapActualsFetchError(
            f"SAP actuals read-through failed for fiscal_year={fiscal_year}: {exc}"
        ) from exc
    finally:
        if cursor is not None:
            cursor.close()

    result: dict[tuple[str, str], dict[str, float]] = {}
    for cost_center, gl_account_number, _fiscal_year, period_month, actual_thb in rows:
        key = (cost_center, gl_account_number)
        months = result.setdefault(key, {col: 0.0 for col in MONTH_COLUMNS})
        months[f"m{int(period_month):02d}"] = float(actual_thb)

    for months in result.values():
        months["total_year"] = round(sum(months[col] for col in MONTH_COLUMNS), 2)

    return result


# ---------------------------------------------------------------------------
# ADR-0026 — hide incomplete SAP-actual months (entry-day watermark + 23 days)
# ---------------------------------------------------------------------------

# Measured tail (ADR-0026, three months of company 1000): a posting month is
# still gaining documents for ~23 days after it ends (March 2026 was 78.2%
# complete at month-end, 100.0% on 23 Apr — nothing lands after day 23). If a
# future month's tail runs longer, THIS CONSTANT changes, not the rule.
SAP_MONTH_VISIBLE_LAG_DAYS = 23

# A run of this many consecutive missing entry-days truncates the watermark:
# the loader landing an ISLAND of days (e.g. 2026-05-23 while 05-01..22 are
# still missing) must not reveal April. Live 2026-08-01: 850 consecutive
# entry-days 2024-01-01..2026-04-29 with ZERO holes, so a hole of any size is
# already abnormal; 4 keeps a short posting-free stretch from tripping it.
SAP_ENTRY_DAY_MAX_GAP_DAYS = 4

# Distinct SAP ENTRY-days present in the DW, newest-window first. `fiscal_year
# >= ?` is a pruning predicate, not a semantic filter (live: 3.02s -> 1.22s on
# the same result set); `utc_timestamp >= ?` bounds the window to the trailing
# ~2 fiscal years so this never becomes a full 4M-row scan. `utc_timestamp` is
# varchar(14) 'YYYYMMDDHHMMSS', so the window start is passed as a 14-char
# string and compared lexicographically.
SAP_ENTRY_DAYS_SQL = """
SELECT DISTINCT LEFT(utc_timestamp, 8) AS entry_day
FROM gold.fact_gl_trans
WHERE company_code='1000' AND fiscal_year >= ? AND utc_timestamp >= ?
"""


class SapCoverage(BaseModel):
    """Which months of one fiscal year the SAP · ใช้จริง layer may display,
    and the load freshness that decided it (ADR-0026). Returned as-is by
    `GET /budget/sap-coverage` so the grid can label its own coverage."""

    fiscal_year: int
    #: Newest entry-day of the contiguous loaded run (SAP keying date, not a
    #: posting date) — "ข้อมูลคีย์ถึง <date>" in the UI.
    watermark_date: date
    visible_months: list[int]
    hidden_months: list[int]


def visible_sap_months(
    watermark_date: date, fiscal_year: int, lag_days: int = SAP_MONTH_VISIBLE_LAG_DAYS
) -> tuple[int, ...]:
    """Months of `fiscal_year` complete enough to display (ADR-0026):

        visible(Y, M) <=> watermark >= last_day(Y, M) + lag_days

    Pure — no DB, no clock. December of Y therefore needs a watermark in
    January of Y+1, and February's cut-off follows the real month length
    (leap years included)."""
    visible = []
    for month in range(1, 13):
        last_day = date(fiscal_year, month, calendar.monthrange(fiscal_year, month)[1])
        if watermark_date >= last_day + timedelta(days=lag_days):
            visible.append(month)
    return tuple(visible)


def entry_day_watermark(
    entry_days: Iterable[date], max_gap_days: int = SAP_ENTRY_DAY_MAX_GAP_DAYS
) -> date | None:
    """End of the CONTIGUOUS run of loaded entry-days (ADR-0026). Pure.

    Walks back from the newest day; a gap of `max_gap_days` or more missing
    calendar days truncates the watermark to the day below that gap, and the
    walk continues — so two stacked islands both get discarded. `None` when
    nothing is loaded at all (the caller MUST treat that as a loud failure,
    never as "everything visible")."""
    days = sorted(set(entry_days))
    if not days:
        return None
    watermark = days[-1]
    # Newest pair first: every gap re-truncates, so with two stacked islands
    # the OLDEST gap wins and the watermark lands on the newest day of the
    # last run that is contiguous all the way down.
    for older, newer in reversed(list(zip(days, days[1:]))):
        if (newer - older).days - 1 >= max_gap_days:
            watermark = older
    return watermark


def fetch_sap_entry_days(conn: pyodbc.Connection, fiscal_year: int) -> list[date]:
    """Distinct SAP entry-days loaded in the window that matters for
    `fiscal_year` (ADR-0026), ascending. Same loud-failure contract as
    `fetch_sap_actuals` — a broken DW read raises `SapActualsFetchError`."""
    window_start_year = fiscal_year - 1
    window_start = f"{window_start_year}0101000000"
    cursor = None
    try:
        cursor = conn.cursor()
        cursor.execute(SAP_ENTRY_DAYS_SQL, window_start_year, window_start)
        rows = cursor.fetchall()
    except pyodbc.Error as exc:
        raise SapActualsFetchError(
            f"SAP entry-day read failed for fiscal_year={fiscal_year}: {exc}"
        ) from exc
    finally:
        if cursor is not None:
            cursor.close()

    days: list[date] = []
    for (raw,) in rows:
        try:
            days.append(datetime.strptime(str(raw)[:8], "%Y%m%d").date())
        except ValueError as exc:
            # Loud, never skipped: a silently dropped day could open a fake
            # gap and hide a complete month (or close a real one).
            raise SapActualsFetchError(
                f"unparsable SAP entry-day {raw!r} in gold.fact_gl_trans.utc_timestamp"
            ) from exc
    return sorted(days)


def resolve_sap_coverage(conn: pyodbc.Connection, fiscal_year: int) -> SapCoverage:
    """One DW read + the two pure rules above = which months of `fiscal_year`
    the SAP layer may display (ADR-0026).

    Fails CLOSED and LOUD: if the watermark cannot be determined (no loaded
    entry-days in the window, or an all-NULL `utc_timestamp`), this raises
    `SapActualsFetchError` -> 502, so the grid shows nothing rather than
    numbers that may be materially incomplete."""
    entry_days = fetch_sap_entry_days(conn, fiscal_year)
    watermark = entry_day_watermark(entry_days)
    if watermark is None:
        raise SapActualsFetchError(
            "SAP entry-day watermark is undeterminable for fiscal_year="
            f"{fiscal_year} (no loaded entry-days since {fiscal_year - 1}-01-01) — "
            "refusing to display possibly incomplete actuals (ADR-0026, fail closed)"
        )
    visible = visible_sap_months(watermark, fiscal_year)
    logger.info(
        "SAP coverage fiscal_year=%s watermark=%s visible_months=%s", fiscal_year, watermark, list(visible)
    )
    return SapCoverage(
        fiscal_year=fiscal_year,
        watermark_date=watermark,
        visible_months=list(visible),
        hidden_months=[month for month in range(1, 13) if month not in visible],
    )
