"""Unit tests for app.sap — SAP actuals read-through (ADR-0020, A4).

Fully mocked cursor/connection — no live DB. The query text itself is the
never-cut financial contract: verbatim, no sign flip, no doc_status filter,
excluded-CC list WITHOUT 10SC012000, and any failure must raise (never a
silent-empty actuals layer).
"""
import pyodbc
import pytest

from app.sap import SAP_ACTUALS_SQL, SapActualsFetchError, fetch_sap_actuals


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
