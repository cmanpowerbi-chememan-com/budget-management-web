"""Unit tests for app.sap — SAP actuals read-through (ADR-0020, A4) and the
entry-day watermark that hides incomplete months (ADR-0026).

Fully mocked cursor/connection — no live DB. The query text itself is the
never-cut financial contract: verbatim, no sign flip, no doc_status filter,
excluded-CC list WITHOUT 10SC012000, and any failure must raise (never a
silent-empty actuals layer).
"""
from datetime import date

import pyodbc
import pytest

from app.sap import (
    SAP_ACTUALS_SQL,
    SAP_ENTRY_DAYS_SQL,
    SapActualsFetchError,
    entry_day_watermark,
    fetch_sap_actuals,
    fetch_sap_entry_days,
    resolve_sap_coverage,
    visible_sap_months,
)


def _make_conn(rows: list[tuple]) -> "pyodbc.Connection":
    from unittest.mock import MagicMock

    cursor = MagicMock()
    cursor.fetchall.return_value = rows
    conn = MagicMock()
    conn.cursor.return_value = cursor
    return conn


def test_sap_query_contains_all_mandatory_filters_verbatim():
    assert "company_code='1000'" in SAP_ACTUALS_SQL
    assert "doc_type<>'CO'" in SAP_ACTUALS_SQL
    assert "assignment_number<>'TFRS16'" in SAP_ACTUALS_SQL
    assert "fiscal_year=?" in SAP_ACTUALS_SQL
    assert "SUM(company_curr_amount) AS actual_thb" in SAP_ACTUALS_SQL
    assert "GROUP BY cost_center, gl_account_number, fiscal_year, period_month" in SAP_ACTUALS_SQL


def test_sap_query_keeps_null_assignment_rows():
    """D2 fix (confirmed policy call): a bare `assignment_number<>'TFRS16'`
    is not NULL-safe — `NULL <> 'TFRS16'` is SQL UNKNOWN, so every
    NULL-assignment row was silently dropped (never-cut: balanced clearing
    accounts must net to ~0.00, not show a phantom actual). The filter must
    explicitly keep NULLs."""
    assert "assignment_number IS NULL OR assignment_number<>'TFRS16'" in SAP_ACTUALS_SQL


def test_sap_query_excludes_cost_centers_without_10sc012000():
    assert "'CMRY01'" in SAP_ACTUALS_SQL
    assert "'CMKK01'" in SAP_ACTUALS_SQL
    assert "'CMPB01'" in SAP_ACTUALS_SQL
    assert "'MNLB00'" in SAP_ACTUALS_SQL
    assert "'MNLB01'" in SAP_ACTUALS_SQL
    assert "'MNLB02'" in SAP_ACTUALS_SQL
    assert "'MNLB03'" in SAP_ACTUALS_SQL
    assert "'MNLB04'" in SAP_ACTUALS_SQL
    assert "10SC012000" not in SAP_ACTUALS_SQL


def test_sap_query_makes_the_null_cost_center_exclusion_explicit():
    """2026-07-16 D2 follow-up: `NULL NOT IN (...)` is already UNKNOWN, so
    NULL-cost_center rows were always excluded — but only as a side effect of
    NULL semantics. This must now be an explicit, deliberate predicate.
    Behavior-identical: adding it changes nothing about which rows match."""
    assert "cost_center IS NOT NULL" in SAP_ACTUALS_SQL


def test_sap_query_no_other_filter_changed_alongside_the_null_hardening():
    """Guards against the D2-style mistake happening again: this new
    predicate must sit ALONGSIDE the existing filters, not replace or alter
    any of them."""
    assert "company_code='1000'" in SAP_ACTUALS_SQL
    assert "doc_type<>'CO'" in SAP_ACTUALS_SQL
    assert (
        "cost_center NOT IN ('CMRY01','CMKK01','CMPB01','MNLB00','MNLB01','MNLB02','MNLB03','MNLB04')"
        in SAP_ACTUALS_SQL
    )
    assert "assignment_number IS NULL OR assignment_number<>'TFRS16'" in SAP_ACTUALS_SQL
    assert "fiscal_year=?" in SAP_ACTUALS_SQL
    assert "SUM(company_curr_amount) AS actual_thb" in SAP_ACTUALS_SQL
    assert "GROUP BY cost_center, gl_account_number, fiscal_year, period_month" in SAP_ACTUALS_SQL
    assert "doc_status" not in SAP_ACTUALS_SQL
    assert "-1" not in SAP_ACTUALS_SQL
    assert "CASE" not in SAP_ACTUALS_SQL.upper()


def test_sap_query_has_no_sign_flip_and_no_doc_status_filter():
    assert "doc_status" not in SAP_ACTUALS_SQL
    assert "-1" not in SAP_ACTUALS_SQL
    assert "CASE" not in SAP_ACTUALS_SQL.upper()


def test_fetch_sap_actuals_passes_fiscal_year_as_the_only_parameter():
    conn = _make_conn(rows=[])
    fetch_sap_actuals(conn, fiscal_year=2026)
    cursor = conn.cursor.return_value
    args = cursor.execute.call_args.args
    assert args[0] == SAP_ACTUALS_SQL
    assert args[1] == 2026


def test_fetch_sap_actuals_pivots_period_month_to_wide_m_columns():
    conn = _make_conn(
        rows=[
            ("10CA013000", "5211900030", 2026, "01", 1000.0),
            ("10CA013000", "5211900030", 2026, "04", 2500.5),
            ("10CA013000", "5211900030", 2026, 12, 300.0),
        ]
    )
    result = fetch_sap_actuals(conn, fiscal_year=2026)
    months = result[("10CA013000", "5211900030")]
    assert months["m01"] == 1000.0
    assert months["m04"] == 2500.5
    assert months["m12"] == 300.0
    assert months["m02"] == 0.0


def test_fetch_sap_actuals_total_year_is_sum_of_the_12_months():
    conn = _make_conn(
        rows=[
            ("CC1", "GL1", 2026, "01", 100.0),
            ("CC1", "GL1", 2026, "02", 50.0),
        ]
    )
    result = fetch_sap_actuals(conn, fiscal_year=2026)
    assert result[("CC1", "GL1")]["total_year"] == 150.0


def test_fetch_sap_actuals_keeps_different_gl_accounts_separate_cost_sga_never_cross():
    conn = _make_conn(
        rows=[
            ("CC1", "5211900030", 2026, "01", 100.0),  # COST 5xxx
            ("CC1", "6211900030", 2026, "01", 200.0),  # SG&A 6xxx
        ]
    )
    result = fetch_sap_actuals(conn, fiscal_year=2026)
    assert result[("CC1", "5211900030")]["m01"] == 100.0
    assert result[("CC1", "6211900030")]["m01"] == 200.0
    assert len(result) == 2


def test_fetch_sap_actuals_raises_loud_error_on_query_failure_not_silent_empty():
    conn = _make_conn(rows=[])
    conn.cursor.return_value.execute.side_effect = pyodbc.Error("HYT00", "timeout")
    with pytest.raises(SapActualsFetchError):
        fetch_sap_actuals(conn, fiscal_year=2026)


def test_fetch_sap_actuals_closes_cursor_even_on_failure():
    conn = _make_conn(rows=[])
    conn.cursor.return_value.execute.side_effect = pyodbc.Error("HYT00", "timeout")
    with pytest.raises(SapActualsFetchError):
        fetch_sap_actuals(conn, fiscal_year=2026)
    conn.cursor.return_value.close.assert_called_once()


def test_fetch_sap_actuals_wraps_a_connection_level_failure_too():
    """`conn.cursor()` itself can raise (closed connection, dropped session)
    -- this must ALSO become SapActualsFetchError, not a raw pyodbc.Error,
    or a connection drop silently bypasses the loud-failure contract
    (live-DB finding, 2026-07-15: this used to escape unwrapped)."""
    from unittest.mock import MagicMock

    conn = MagicMock()
    conn.cursor.side_effect = pyodbc.Error("08S01", "Attempt to use a closed connection.")
    with pytest.raises(SapActualsFetchError):
        fetch_sap_actuals(conn, fiscal_year=2026)


def test_fetch_sap_actuals_never_masks_months_itself():
    """ADR-0026 is a DISPLAY rule applied by `read_model._sap_layer`, not by
    this fetch: the raw mirror of the DW must stay complete (the DB->web
    parity harness compares it month by month, including months the grid
    hides). A None here would silently break that harness."""
    conn = _make_conn(rows=[("CC1", "GL1", 2026, "04", 22_008_580.0)])
    months = fetch_sap_actuals(conn, fiscal_year=2026)[("CC1", "GL1")]
    assert months["m04"] == 22_008_580.0
    assert months["total_year"] == 22_008_580.0


# ---------------------------------------------------------------------------
# ADR-0026 — visible_sap_months (pure, no DB)
# ---------------------------------------------------------------------------

def test_visible_months_today_fy2026_watermark_20260429_shows_jan_to_mar_only():
    """The live case the ADR was measured on: entry-days loaded through
    2026-04-29, so March (31 Mar + 23d = 23 Apr) is complete but April
    (30 Apr + 23d = 23 May) is not."""
    assert visible_sap_months(date(2026, 4, 29), 2026) == (1, 2, 3)


def test_visible_months_hidden_set_is_the_complement():
    visible = visible_sap_months(date(2026, 4, 29), 2026)
    assert [m for m in range(1, 13) if m not in visible] == [4, 5, 6, 7, 8, 9, 10, 11, 12]


def test_visible_months_boundary_march_appears_exactly_on_watermark_day_23():
    assert 3 in visible_sap_months(date(2026, 4, 23), 2026)


def test_visible_months_boundary_march_still_hidden_one_day_before():
    assert 3 not in visible_sap_months(date(2026, 4, 22), 2026)


def test_visible_months_prior_fiscal_year_is_fully_visible():
    """FY2025's last cut-off (31 Dec 2025 + 23d = 23 Jan 2026) is long past,
    so the reference year a planner compares against stays complete."""
    assert visible_sap_months(date(2026, 4, 29), 2025) == tuple(range(1, 13))


def test_visible_months_december_needs_a_watermark_in_the_next_calendar_year():
    assert 12 not in visible_sap_months(date(2027, 1, 22), 2026)
    assert 12 in visible_sap_months(date(2027, 1, 23), 2026)


def test_visible_months_february_uses_the_real_month_length_in_a_leap_year():
    """2028 is a leap year: 29 Feb + 23d = 23 Mar, not 22 Mar."""
    assert 2 not in visible_sap_months(date(2028, 3, 22), 2028)
    assert 2 in visible_sap_months(date(2028, 3, 23), 2028)


def test_visible_months_watermark_before_the_year_hides_everything():
    assert visible_sap_months(date(2025, 6, 30), 2026) == ()


# ---------------------------------------------------------------------------
# ADR-0026 — entry_day_watermark (pure, no DB)
# ---------------------------------------------------------------------------

def _days(*iso: str) -> list[date]:
    return [date.fromisoformat(d) for d in iso]


def test_entry_day_watermark_is_the_newest_day_of_a_contiguous_run():
    days = _days("2026-04-26", "2026-04-27", "2026-04-28", "2026-04-29")
    assert entry_day_watermark(days) == date(2026, 4, 29)


def test_entry_day_watermark_ignores_an_island_load_above_a_long_gap():
    """The pathology contiguity exists for: a loader that lands 2026-05-23
    while skipping 2026-05-01..22 must NOT reveal April (April needs
    23 May) — the watermark truncates back to the run below the gap."""
    days = _days("2026-04-27", "2026-04-28", "2026-04-29", "2026-05-23")
    watermark = entry_day_watermark(days)
    assert watermark == date(2026, 4, 29)
    assert 4 not in visible_sap_months(watermark, 2026)


def test_entry_day_watermark_tolerates_a_one_or_two_day_hole():
    """Threshold is 4 consecutive missing days — a short hole (a day with no
    postings at all) must never truncate. Live check 2026-08-01: zero holes
    in 850 entry-days, so any hole at all is already unexpected."""
    assert entry_day_watermark(_days("2026-04-20", "2026-04-22", "2026-04-23")) == date(2026, 4, 23)
    assert entry_day_watermark(_days("2026-04-20", "2026-04-23", "2026-04-24")) == date(2026, 4, 24)


def test_entry_day_watermark_tolerates_a_three_day_hole_but_not_a_four_day_one():
    assert entry_day_watermark(_days("2026-04-20", "2026-04-24", "2026-04-25")) == date(2026, 4, 25)
    assert entry_day_watermark(_days("2026-04-20", "2026-04-25", "2026-04-26")) == date(2026, 4, 20)


def test_entry_day_watermark_truncates_at_every_gap_not_just_the_newest():
    """Two islands above the real run: both are untrustworthy, so the
    watermark falls back to the oldest contiguous run (hide is the safe
    direction)."""
    days = _days("2026-04-28", "2026-04-29", "2026-05-23", "2026-05-24", "2026-06-20")
    assert entry_day_watermark(days) == date(2026, 4, 29)


def test_entry_day_watermark_dedups_and_sorts_its_input():
    days = _days("2026-04-29", "2026-04-27", "2026-04-29", "2026-04-28")
    assert entry_day_watermark(days) == date(2026, 4, 29)


def test_entry_day_watermark_is_none_when_nothing_is_loaded():
    assert entry_day_watermark([]) is None


# ---------------------------------------------------------------------------
# ADR-0026 — fetch_sap_entry_days / resolve_sap_coverage (mocked cursor)
# ---------------------------------------------------------------------------

def test_entry_days_sql_reads_the_entry_timestamp_not_posting_or_doc_date():
    """`utc_timestamp` (varchar(14) YYYYMMDDHHMMSS) is the SAP entry stamp.
    `doc_date` is garbage in live data (MAX = 2206-03-25), `posting_date`
    answers a different question, and `prcs_data_dt` holds ONE value for the
    whole table."""
    assert "LEFT(utc_timestamp, 8)" in SAP_ENTRY_DAYS_SQL
    assert "DISTINCT" in SAP_ENTRY_DAYS_SQL
    assert "company_code='1000'" in SAP_ENTRY_DAYS_SQL
    assert "doc_date" not in SAP_ENTRY_DAYS_SQL
    assert "posting_date" not in SAP_ENTRY_DAYS_SQL
    assert "prcs_data_dt" not in SAP_ENTRY_DAYS_SQL


def test_entry_days_sql_is_windowed_so_it_never_scans_the_whole_table():
    """Both bounds are parameterized: `fiscal_year >=` (the pruning predicate
    that took the live query from 3.0s to 1.2s) and a `utc_timestamp >=`
    window start."""
    assert "fiscal_year >= ?" in SAP_ENTRY_DAYS_SQL
    assert "utc_timestamp >= ?" in SAP_ENTRY_DAYS_SQL


def test_fetch_sap_entry_days_windows_from_january_of_the_previous_fiscal_year():
    conn = _make_conn(rows=[("20260429",)])
    fetch_sap_entry_days(conn, fiscal_year=2026)
    args = conn.cursor.return_value.execute.call_args.args
    assert args[0] == SAP_ENTRY_DAYS_SQL
    assert args[1] == 2025
    assert args[2] == "20250101000000"


def test_fetch_sap_entry_days_parses_the_yyyymmdd_prefix_into_dates():
    conn = _make_conn(rows=[("20260427",), ("20260428",), ("20260429",)])
    assert fetch_sap_entry_days(conn, fiscal_year=2026) == [
        date(2026, 4, 27),
        date(2026, 4, 28),
        date(2026, 4, 29),
    ]


def test_fetch_sap_entry_days_raises_loud_error_on_query_failure():
    conn = _make_conn(rows=[])
    conn.cursor.return_value.execute.side_effect = pyodbc.Error("HYT00", "timeout")
    with pytest.raises(SapActualsFetchError):
        fetch_sap_entry_days(conn, fiscal_year=2026)


def test_fetch_sap_entry_days_closes_cursor_even_on_failure():
    conn = _make_conn(rows=[])
    conn.cursor.return_value.execute.side_effect = pyodbc.Error("HYT00", "timeout")
    with pytest.raises(SapActualsFetchError):
        fetch_sap_entry_days(conn, fiscal_year=2026)
    conn.cursor.return_value.close.assert_called_once()


def test_fetch_sap_entry_days_raises_on_an_unparsable_entry_day():
    conn = _make_conn(rows=[("notadate",)])
    with pytest.raises(SapActualsFetchError):
        fetch_sap_entry_days(conn, fiscal_year=2026)


def test_resolve_sap_coverage_reports_watermark_and_both_month_lists():
    conn = _make_conn(rows=[("20260427",), ("20260428",), ("20260429",)])
    coverage = resolve_sap_coverage(conn, fiscal_year=2026)
    assert coverage.fiscal_year == 2026
    assert coverage.watermark_date == date(2026, 4, 29)
    assert coverage.visible_months == [1, 2, 3]
    assert coverage.hidden_months == [4, 5, 6, 7, 8, 9, 10, 11, 12]


def test_resolve_sap_coverage_fails_closed_and_loud_when_no_entry_days_exist():
    """Never-cut: an undeterminable watermark must NOT degrade into
    "everything visible" — it raises, the router turns it into a 502, and no
    possibly-incomplete number ever reaches the grid."""
    conn = _make_conn(rows=[])
    with pytest.raises(SapActualsFetchError):
        resolve_sap_coverage(conn, fiscal_year=2026)
