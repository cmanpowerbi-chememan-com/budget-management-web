"""Unit tests for app.write_model — budget WRITE path (A5): pending_budget +
detail + trip. DB always mocked (`conn.cursor.return_value` is the ONE shared
cursor mock, matching the convention in test_rls.py / test_read_model.py).

Covers the never-cut rules (BUILD_PLAN A5 / task brief):
- row-grain optimistic lock (stale -> 409, no write; row created concurrently -> conflict)
- CC must be in Fill scope (See-only / out-of-scope -> forbidden); admin bypasses
- GL must exist; special-GL cells cannot be edited directly (route to detail/trip)
- trip side never crosses COST/SGA
- missing FX / missing per-diem rate fail loud (propagate, never silently 0)
- editing never touches budget.approval_status / pending_budget.status
  (except the A10 gap-close read-only *lock check* below — never a write)
- total_year stays in sync with SUM(months); parent cell == SUM(detail)
- A10 gap close: non-admin writes are rejected while the row's department is
  mid-approval (PENDING_APPROVER1/2/3) or APPROVED; admin always bypasses;
  DRAFT/REJECTED/no-row are not locked
"""
import itertools
from datetime import date, datetime, timezone
from unittest.mock import MagicMock

import pyodbc
import pytest
from pydantic import ValidationError

from app.approval import APPROVED, PENDING_APPROVER1, PENDING_APPROVER2, PENDING_APPROVER3, REJECTED
from app.config import Settings
from app.per_diem import MissingFxRateError, MissingPerDiemRateError
from app.rls import Scope
from app.write_model import (
    AdminOnlyGlError,
    DepartmentLockedError,
    DetailLineInput,
    ExcludedCostCenterError,
    ForbiddenScopeError,
    NegativeMonthError,
    NotSpecialGlError,
    PastDeadlineError,
    PendingRowInput,
    PerDiemDirectEditError,
    RowConflictError,
    SpecialGlDirectEditError,
    TravelerNotFoundError,
    TripInput,
    TripNotFoundError,
    TripSideMismatchError,
    UnknownGlAccountError,
    delete_detail_line,
    delete_pending_row,
    delete_trip,
    save_detail_lines,
    save_pending_rows,
    save_trip,
)

STALE = datetime(2026, 1, 1, tzinfo=timezone.utc)


def _scope(**overrides) -> Scope:
    defaults = dict(email="filler@chememan.com", is_admin=False, role="filler",
                     fill_cost_centers=["CC1"], see_cost_centers=["CC1"])
    defaults.update(overrides)
    return Scope(**defaults)


def _admin_scope() -> Scope:
    return Scope(email="admin@chememan.com", is_admin=True, role="admin", fill_cost_centers=[], see_cost_centers=[])


def _flag_on() -> Settings:
    """GL edit_by admin-only lock (design v2) flag ON, for tests exercising
    that path — never mutates the process-wide cached get_settings()."""
    return Settings(_env_file=None, gl_edit_by_enabled=True)


def _row(**overrides) -> PendingRowInput:
    defaults = dict(cost_center="CC1", gl_account="GL1", fiscal_year=2027,
                     m01=0, m02=0, m03=0, m04=0, m05=0, m06=0, m07=0, m08=0, m09=0, m10=0, m11=0, m12=0,
                     remark=None, template="USER", expected_updated_at=None)
    defaults.update(overrides)
    return PendingRowInput(**defaults)


# ---------------------------------------------------------------------------
# save_pending_rows
# ---------------------------------------------------------------------------

def test_forbidden_when_cost_center_outside_fill_scope_no_db_call():
    conn = MagicMock()
    scope = _scope(fill_cost_centers=[], see_cost_centers=["CC1"])  # See-only, not Fill
    results = save_pending_rows(conn, [_row(cost_center="CC1")], "user@chememan.com", scope)
    assert results[0].ok is False
    assert results[0].error == "forbidden"
    conn.cursor.assert_not_called()


def test_forbidden_when_cost_center_not_in_scope_at_all():
    conn = MagicMock()
    scope = _scope(fill_cost_centers=[], see_cost_centers=[])
    results = save_pending_rows(conn, [_row(cost_center="OUTSIDE")], "user@chememan.com", scope)
    assert results[0].error == "forbidden"
    conn.cursor.assert_not_called()


def test_admin_bypasses_fill_scope_restriction():
    conn = MagicMock()
    cursor = conn.cursor.return_value
    cursor.fetchone.side_effect = [
        (1,),                                    # CC-existence check (admin bypass still validates the CC exists)
        ("Bank Charge", "Bank Charge Fee"), ("deptA", "divA", "clA"),
    ]
    scope = _admin_scope()
    results = save_pending_rows(conn, [_row(cost_center="ANY-CC", m01=100)], "admin@chememan.com", scope)
    assert results[0].ok is True


def test_excluded_cost_center_rejected_even_for_admin():
    conn = MagicMock()
    scope = _admin_scope()
    results = save_pending_rows(conn, [_row(cost_center="CMRY01")], "admin@chememan.com", scope)
    assert results[0].error == "excluded_cost_center"
    conn.cursor.assert_not_called()


def test_negative_month_rejected_no_db_call():
    conn = MagicMock()
    scope = _scope()
    results = save_pending_rows(conn, [_row(m01=-5)], "filler@chememan.com", scope)
    assert results[0].error == "negative_month"
    conn.cursor.assert_not_called()


def test_unknown_gl_account_rejected():
    conn = MagicMock()
    cursor = conn.cursor.return_value
    cursor.fetchone.side_effect = [None]  # gl_group lookup finds nothing
    scope = _scope()
    results = save_pending_rows(conn, [_row(gl_account="NOPE")], "filler@chememan.com", scope)
    assert results[0].error == "unknown_gl_account"


def test_unknown_gl_account_error_message_does_not_leak_internal_table_name():
    """D13: the 400 body reaches the client via `detail` — must never echo
    `dbo.gl_group` (an internal implementation detail)."""
    conn = MagicMock()
    cursor = conn.cursor.return_value
    cursor.fetchone.side_effect = [None]
    scope = _scope()
    results = save_pending_rows(conn, [_row(gl_account="NOPE")], "filler@chememan.com", scope)
    assert "dbo.gl_group" not in results[0].detail


def test_lookup_cc_dims_query_is_deterministic_order_by_filler_email():
    """D11: a cost_center can have more than one row in dbo.cc_filler_map
    (one per filler_email) with DIFFERENT department/division/c_level — the
    lookup must pick deterministically, not by whatever order the DB scans
    rows in."""
    from app.write_model import _lookup_cc_dims

    conn = MagicMock()
    cursor = conn.cursor.return_value
    cursor.fetchone.return_value = ("deptA", "divA", "clA")
    _lookup_cc_dims(conn, "10OS011400")
    sql_text = cursor.execute.call_args.args[0]
    assert "ORDER BY filler_email" in sql_text


def test_special_gl_cell_cannot_be_edited_directly():
    conn = MagicMock()
    cursor = conn.cursor.return_value
    cursor.fetchone.side_effect = [("Entertainment", "Entertainment Expense"), ("deptA", "divA", "clA")]
    scope = _scope()
    results = save_pending_rows(conn, [_row(gl_account="5211900030")], "filler@chememan.com", scope)
    assert results[0].error == "special_gl_direct_edit"


# ---------------------------------------------------------------------------
# GL edit_by admin-only lock (design v2, flag-gated) — pending row
# ---------------------------------------------------------------------------

def test_pending_row_flag_off_never_selects_edit_by():
    """Flag OFF (default, no settings passed): the gl_group lookup must stay
    a plain 2-tuple query — zero behavior/SQL change from before this
    feature."""
    conn = MagicMock()
    cursor = conn.cursor.return_value
    cursor.fetchone.side_effect = [("Bank Charge", "Bank Charge Fee"), ("deptA", "divA", "clA"), None, None]
    scope = _scope()
    results = save_pending_rows(conn, [_row(m01=100)], "filler@chememan.com", scope)
    assert results[0].ok is True
    gl_lookup_sql = cursor.execute.call_args_list[0].args[0]
    assert "edit_by" not in gl_lookup_sql


def test_pending_row_admin_only_gl_rejected_for_non_admin_when_flag_enabled():
    conn = MagicMock()
    cursor = conn.cursor.return_value
    cursor.fetchone.side_effect = [("Insurance Premium", "ค่าเบี้ยประกันภัย", "admin"), ("deptA", "divA", "clA")]
    scope = _scope()
    results = save_pending_rows(conn, [_row(gl_account="5210100010")], "filler@chememan.com", scope, settings=_flag_on())
    assert results[0].error == "admin_only_gl"
    conn.commit.assert_not_called()


def test_pending_row_admin_only_gl_allowed_for_admin_when_flag_enabled():
    conn = MagicMock()
    cursor = conn.cursor.return_value
    cursor.fetchone.side_effect = [
        (1,),  # CC-existence check (admin bypass)
        ("Insurance Premium", "ค่าเบี้ยประกันภัย", "admin"),
        ("deptA", "divA", "clA"),
        None, None,
    ]
    scope = _admin_scope()
    results = save_pending_rows(
        conn, [_row(cost_center="ANY-CC", gl_account="5210100010", m01=100)], "admin@chememan.com", scope,
        settings=_flag_on(),
    )
    assert results[0].ok is True


def test_pending_row_normal_gl_still_succeeds_when_flag_enabled():
    """Flag ON but the GL is a normal (non-admin) GL — must behave exactly
    like flag OFF."""
    conn = MagicMock()
    cursor = conn.cursor.return_value
    cursor.fetchone.side_effect = [("Bank Charge", "Bank Charge Fee", "user"), ("deptA", "divA", "clA"), None, None]
    scope = _scope()
    results = save_pending_rows(conn, [_row(m01=100)], "filler@chememan.com", scope, settings=_flag_on())
    assert results[0].ok is True


def test_new_row_insert_succeeds_and_total_year_is_sum_of_months():
    conn = MagicMock()
    cursor = conn.cursor.return_value
    cursor.fetchone.side_effect = [("Bank Charge", "Bank Charge Fee"), ("deptA", "divA", "clA"), None, None]
    scope = _scope()
    row = _row(m01=100, m02=200, expected_updated_at=None)
    results = save_pending_rows(conn, [row], "filler@chememan.com", scope)
    result = results[0]
    assert result.ok is True
    assert result.row.total_year == 300
    assert result.row.gl_group == "Bank Charge"
    assert result.row.gl_name == "Bank Charge Fee"  # resolved from dbo.gl_group (2026-07-15 GAP fix)
    assert result.row.department == "deptA"
    conn.commit.assert_called_once()
    insert_sql = cursor.execute.call_args_list[-1].args[0]
    assert "INSERT INTO budget.pending_budget" in insert_sql
    assert "approval_status" not in insert_sql


def test_insert_conflict_when_row_already_exists_concurrently():
    """expected_updated_at=None means 'create new' — if the PK already exists
    (another Filler created it first), the DB integrity error becomes a 409,
    never a silent overwrite."""
    conn = MagicMock()
    cursor = conn.cursor.return_value
    cursor.fetchone.side_effect = [("Bank Charge", "Bank Charge Fee"), ("deptA", "divA", "clA"), None, None]
    cursor.execute.side_effect = [None, None, None, None, pyodbc.IntegrityError("23000", "PK violation")]
    scope = _scope()
    results = save_pending_rows(conn, [_row(expected_updated_at=None)], "filler@chememan.com", scope)
    assert results[0].error == "conflict"
    conn.commit.assert_not_called()


def test_stale_optimistic_lock_returns_conflict_and_does_not_write():
    conn = MagicMock()
    cursor = conn.cursor.return_value
    cursor.fetchone.side_effect = [("Bank Charge", "Bank Charge Fee"), ("deptA", "divA", "clA"), None, None]
    cursor.rowcount = 0  # WHERE _updated_at = ? matched nothing -> stale
    scope = _scope()
    results = save_pending_rows(conn, [_row(expected_updated_at=STALE)], "filler@chememan.com", scope)
    assert results[0].error == "conflict"
    conn.commit.assert_not_called()


def test_update_succeeds_when_lock_matches():
    conn = MagicMock()
    cursor = conn.cursor.return_value
    cursor.fetchone.side_effect = [("Bank Charge", "Bank Charge Fee"), ("deptA", "divA", "clA"), None, None]
    cursor.rowcount = 1
    scope = _scope()
    results = save_pending_rows(conn, [_row(m01=50, expected_updated_at=STALE)], "filler@chememan.com", scope)
    assert results[0].ok is True
    conn.commit.assert_called_once()
    update_sql = cursor.execute.call_args_list[-1].args[0]
    assert "UPDATE budget.pending_budget" in update_sql
    assert "status = ?" not in update_sql  # editing never touches status (ADR-0013)


def test_two_rows_in_one_batch_succeed_and_fail_independently():
    """Never-cut: multi-Filler is common — one row's conflict must not affect
    the other row's save (each row is its own optimistic-lock unit)."""
    conn = MagicMock()
    cursor = conn.cursor.return_value
    cursor.fetchone.side_effect = [
        ("Bank Charge", "Bank Charge Fee"), ("deptA", "divA", "clA"), None, None,  # row A dims + lock + deadline (open)
        ("Bank Charge", "Bank Charge Fee"), ("deptB", "divB", "clB"), None, None,  # row B dims + lock + deadline (open)
    ]
    cursor.rowcount = 0  # only consumed by row B's UPDATE (row A does a plain INSERT)
    scope = _scope(fill_cost_centers=["CC1", "CC2"], see_cost_centers=["CC1", "CC2"])
    row_a = _row(cost_center="CC1", gl_account="GLA", m01=10, expected_updated_at=None)
    row_b = _row(cost_center="CC2", gl_account="GLB", m01=20, expected_updated_at=STALE)
    results = save_pending_rows(conn, [row_a, row_b], "filler@chememan.com", scope)
    assert results[0].ok is True
    assert results[0].cost_center == "CC1"
    assert results[1].ok is False
    assert results[1].error == "conflict"
    assert results[1].cost_center == "CC2"


def test_pending_row_month_amounts_are_quantized_and_total_year_matches_sum():
    """D6 fix: incoming floats are quantized to DECIMAL(18,2) (ROUND_HALF_UP)
    BEFORE summing — total_year must equal the SUM of the ROUNDED months,
    never a float sum of the raw unrounded inputs. Live-observed bug:
    100.005 + 100.005 -> total_year 200.01 while the DB-stored months summed
    to 200.00 (each individually rounds to 100.00)."""
    conn = MagicMock()
    cursor = conn.cursor.return_value
    cursor.fetchone.side_effect = [("Bank Charge", "Bank Charge Fee"), ("deptA", "divA", "clA"), None, None]
    scope = _scope()
    row = _row(m01=100.005, m02=100.005, expected_updated_at=None)
    results = save_pending_rows(conn, [row], "filler@chememan.com", scope)
    result = results[0]
    assert result.ok is True
    assert result.row.m01 == 100.00
    assert result.row.m02 == 100.00
    assert result.row.total_year == 200.00


def test_detail_line_month_amounts_are_quantized_and_total_year_matches_sum():
    """Same D6 fix, for save_detail_lines (write_model.py:654 in the finding)."""
    conn = MagicMock()
    cursor = conn.cursor.return_value
    cursor.fetchone.side_effect = [
        ("Entertainment", "Entertainment Expense"), ("deptA", "divA", "clA"),  # dims
        None,  # department-lock check -> no approval_status row, not locked
        None,  # deadline check -> no row, open
    ]
    scope = _scope()
    results = save_detail_lines(
        conn, [_detail(m01=100.005, m02=100.005)], "filler@chememan.com", scope,
    )
    result = results[0]
    assert result.ok is True
    assert result.line.m01 == 100.00
    assert result.line.m02 == 100.00
    assert result.line.total_year == 200.00


def test_data_overflow_pyodbc_error_becomes_per_item_400_not_500_and_batch_continues():
    """D9: a value that still overflows at the DB layer (e.g. a string
    truncation SQL Server catches that slipped past the Pydantic guards)
    must become a per-item 400 with rollback — the OTHER item in the same
    batch must still succeed, never an uncaught 500 that aborts everything."""
    conn = MagicMock()
    cursor = conn.cursor.return_value
    cursor.fetchone.side_effect = [
        ("Bank Charge", "Bank Charge Fee"), ("deptA", "divA", "clA"), None, None,  # row A dims + lock + deadline (open)
        ("Bank Charge", "Bank Charge Fee"), ("deptA", "divA", "clA"), None, None,  # row B dims + lock + deadline (open)
    ]
    cursor.execute.side_effect = [
        None, None,  # row A dims lookups
        None,  # row A department-lock check
        None,  # row A deadline check
        pyodbc.DataError("22001", "string or binary data would be truncated"),  # row A INSERT overflow
        None, None,  # row B dims lookups
        None,  # row B department-lock check
        None,  # row B deadline check
        None,  # row B INSERT succeeds
    ]
    scope = _scope(fill_cost_centers=["CC1", "CC2"], see_cost_centers=["CC1", "CC2"])
    row_a = _row(cost_center="CC1", gl_account="GLA", remark="ok", expected_updated_at=None)
    row_b = _row(cost_center="CC2", gl_account="GLB", m01=10, expected_updated_at=None)
    results = save_pending_rows(conn, [row_a, row_b], "filler@chememan.com", scope)
    assert results[0].ok is False
    assert results[0].error == "data_overflow"
    assert results[1].ok is True
    assert conn.rollback.call_count == 1


def test_admin_write_to_nonexistent_cost_center_is_rejected():
    """A5 gate cheap fix: admin bypasses Fill-scope (ADR-0012) but that must
    not also bypass CC existence — before this fix an admin (or a bug) could
    silently create a pending_budget row for a cost_center that doesn't
    exist at all in dbo.cc_filler_map."""
    conn = MagicMock()
    cursor = conn.cursor.return_value
    cursor.fetchone.side_effect = [None]  # CC-existence lookup finds nothing
    scope = _admin_scope()
    results = save_pending_rows(conn, [_row(cost_center="GHOST-CC")], "admin@chememan.com", scope)
    assert results[0].error == "unknown_cost_center"


def test_stale_lock_conflict_triggers_rollback():
    """A5 gate cheap fix: a caught per-item business error must roll back
    the connection so a partial transaction from one item never leaks into
    the next item's work on the same shared connection."""
    conn = MagicMock()
    cursor = conn.cursor.return_value
    cursor.fetchone.side_effect = [("Bank Charge", "Bank Charge Fee"), ("deptA", "divA", "clA"), None, None]
    cursor.rowcount = 0
    scope = _scope()
    results = save_pending_rows(conn, [_row(expected_updated_at=STALE)], "filler@chememan.com", scope)
    assert results[0].error == "conflict"
    conn.rollback.assert_called_once()


# ---------------------------------------------------------------------------
# A5 gap close — deadline lock on the write path (final A6 gate flag, ADR-0012):
# after dbo.submission_deadline has passed, only admin may keep editing.
# Reuses app.deadline.is_post_deadline (same check A6's submit already uses).
# ---------------------------------------------------------------------------

def test_pending_row_rejected_when_deadline_has_passed_no_db_write():
    conn = MagicMock()
    cursor = conn.cursor.return_value
    cursor.fetchone.side_effect = [
        ("Bank Charge", "Bank Charge Fee"), ("deptA", "divA", "clA"),  # dims
        None,  # department-lock check -> no approval_status row, not locked
        (date(2020, 1, 1),),  # dbo.submission_deadline -> already passed
    ]
    scope = _scope()
    results = save_pending_rows(conn, [_row(m01=100, expected_updated_at=None)], "filler@chememan.com", scope)
    assert results[0].ok is False
    assert results[0].error == "past_deadline"
    conn.commit.assert_not_called()
    executed_sql = [c.args[0] for c in cursor.execute.call_args_list]
    assert not any("INSERT INTO budget.pending_budget" in s or "UPDATE budget.pending_budget" in s for s in executed_sql)


def test_pending_row_admin_bypasses_deadline_check_and_never_queries_it():
    """ADR-0012: admin may keep editing after the deadline — and the gate is
    skipped entirely for admin (no dbo.submission_deadline query at all)."""
    conn = MagicMock()
    cursor = conn.cursor.return_value
    cursor.fetchone.side_effect = [(1,), ("Bank Charge", "Bank Charge Fee"), ("deptA", "divA", "clA")]
    scope = _admin_scope()
    results = save_pending_rows(conn, [_row(cost_center="ANY-CC", m01=100)], "admin@chememan.com", scope)
    assert results[0].ok is True
    executed_sql = [c.args[0] for c in cursor.execute.call_args_list]
    assert not any("submission_deadline" in s for s in executed_sql)


def test_pending_row_missing_deadline_row_is_treated_as_open():
    """Matches A6's exact missing-row policy: no configured deadline for this
    fiscal_year -> the cycle is OPEN, never silently locked."""
    conn = MagicMock()
    cursor = conn.cursor.return_value
    cursor.fetchone.side_effect = [("Bank Charge", "Bank Charge Fee"), ("deptA", "divA", "clA"), None, None]
    scope = _scope()
    results = save_pending_rows(conn, [_row(m01=100, expected_updated_at=None)], "filler@chememan.com", scope)
    assert results[0].ok is True


def test_two_rows_different_fiscal_years_one_past_deadline_blocks_independently():
    """Batch semantics: one item's past_deadline never blocks another item
    targeting an open fiscal_year (never-cut, multi-Filler batches)."""
    conn = MagicMock()
    cursor = conn.cursor.return_value
    cursor.fetchone.side_effect = [
        ("Bank Charge", "Bank Charge Fee"), ("deptA", "divA", "clA"), None, (date(2020, 1, 1),),  # row A: not locked, past deadline
        ("Bank Charge", "Bank Charge Fee"), ("deptB", "divB", "clB"), None, None,                  # row B: not locked, no deadline row
    ]
    scope = _scope(fill_cost_centers=["CC1", "CC2"], see_cost_centers=["CC1", "CC2"])
    row_a = _row(cost_center="CC1", gl_account="GLA", fiscal_year=2020, m01=10, expected_updated_at=None)
    row_b = _row(cost_center="CC2", gl_account="GLB", fiscal_year=2028, m01=20, expected_updated_at=None)
    results = save_pending_rows(conn, [row_a, row_b], "filler@chememan.com", scope)
    assert results[0].ok is False
    assert results[0].error == "past_deadline"
    assert results[1].ok is True


# ---------------------------------------------------------------------------
# save_detail_lines
# ---------------------------------------------------------------------------

def _detail(**overrides) -> DetailLineInput:
    defaults = dict(detail_id=None, cost_center="CC1", gl_account="5211900030", fiscal_year=2027,
                     trip_id=None, line_label="a line", meta_json={"ประเภทการรับรอง": "Customer"},
                     m01=0, m02=0, m03=0, m04=0, m05=0, m06=0, m07=0, m08=0, m09=0, m10=0, m11=0, m12=0,
                     expected_updated_at=None)
    defaults.update(overrides)
    return DetailLineInput(**defaults)


def test_detail_line_forbidden_scope_no_db_call():
    conn = MagicMock()
    scope = _scope(fill_cost_centers=[], see_cost_centers=[])
    results = save_detail_lines(conn, [_detail()], "user@chememan.com", scope)
    assert results[0].error == "forbidden"
    conn.cursor.assert_not_called()


def test_detail_line_excluded_cost_center_rejected():
    """A5 re-gate BLOCKER: _save_one_detail_line must reject an excluded CC
    (spec DATA_MODEL 654/827) the same as the other two write paths — for a
    normal user AND for admin (whose Fill-scope check is bypassed per
    ADR-0012, leaving only a CC-existence check). Without this, an admin
    could save a detail line for an excluded CC and _recompute_parent_cell's
    auto-create INSERT would silently create a pending_budget row for it,
    which the SAP-actuals exclusion means can never reconcile."""
    conn = MagicMock()
    scope = _scope()
    results = save_detail_lines(conn, [_detail(cost_center="CMRY01")], "filler@chememan.com", scope)
    assert results[0].error == "excluded_cost_center"
    conn.cursor.assert_not_called()

    conn_admin = MagicMock()
    results_admin = save_detail_lines(conn_admin, [_detail(cost_center="CMRY01")], "admin@chememan.com", _admin_scope())
    assert results_admin[0].error == "excluded_cost_center"
    conn_admin.cursor.assert_not_called()


def test_detail_line_on_a_normal_gl_group_is_rejected():
    conn = MagicMock()
    cursor = conn.cursor.return_value
    cursor.fetchone.side_effect = [("Bank Charge", "Bank Charge Fee"), ("deptA", "divA", "clA")]
    scope = _scope()
    results = save_detail_lines(conn, [_detail(gl_account="NORMALGL")], "filler@chememan.com", scope)
    assert results[0].error == "not_special_gl"


def test_detail_line_admin_only_gl_rejected_for_non_admin_when_flag_enabled():
    """Defense in depth (rule 4): an admin-only GL is also never a special
    GL, so this would already be rejected as not_special_gl — but the
    admin_only_gl choke point sits before that classification, so a
    non-admin gets the more accurate error."""
    conn = MagicMock()
    cursor = conn.cursor.return_value
    cursor.fetchone.side_effect = [("Bank Charge", "Bank Charge Fee", "admin"), ("deptA", "divA", "clA")]
    scope = _scope()
    results = save_detail_lines(
        conn, [_detail(gl_account="5210100010")], "filler@chememan.com", scope, settings=_flag_on()
    )
    assert results[0].error == "admin_only_gl"


def test_detail_line_flag_off_never_selects_edit_by():
    conn = MagicMock()
    cursor = conn.cursor.return_value
    cursor.fetchone.side_effect = [("Bank Charge", "Bank Charge Fee"), ("deptA", "divA", "clA")]
    scope = _scope()
    results = save_detail_lines(conn, [_detail(gl_account="NORMALGL")], "filler@chememan.com", scope)
    assert results[0].error == "not_special_gl"
    gl_lookup_sql = cursor.execute.call_args_list[0].args[0]
    assert "edit_by" not in gl_lookup_sql


def test_entertainment_detail_line_insert_succeeds():
    conn = MagicMock()
    cursor = conn.cursor.return_value
    cursor.fetchone.side_effect = [
        ("Entertainment", "Entertainment Expense"), ("deptA", "divA", "clA"),  # dims
        None,  # department-lock check -> no approval_status row, not locked
        None,  # deadline check -> no row, open
    ]
    scope = _scope()
    results = save_detail_lines(conn, [_detail(m01=1000)], "filler@chememan.com", scope)
    assert results[0].ok is True
    conn.commit.assert_called_once()


def test_entertainment_detail_line_invalid_meta_rejected():
    conn = MagicMock()
    cursor = conn.cursor.return_value
    cursor.fetchone.side_effect = [("Entertainment", "Entertainment Expense"), ("deptA", "divA", "clA")]
    scope = _scope()
    results = save_detail_lines(
        conn, [_detail(gl_account="6211900031", meta_json={"ประเภทการรับรอง": "Customer"})],
        "filler@chememan.com", scope,
    )
    assert results[0].error == "invalid_meta"


def test_direct_edit_of_per_diem_gl_via_detail_endpoint_is_rejected():
    """Per-diem lines are managed only through save_trip (ADR-0005 ordering: trips created in the per-diem subform)."""
    conn = MagicMock()
    cursor = conn.cursor.return_value
    cursor.fetchone.side_effect = [("Travelling Expense", "Travelling Expense - Test"), ("deptA", "divA", "clA")]
    scope = _scope()
    results = save_detail_lines(
        conn, [_detail(gl_account="5210400010", trip_id=1, meta_json=None)], "filler@chememan.com", scope,
    )
    assert results[0].error == "per_diem_direct_edit"


def test_trip_not_found_for_a_referenced_trip_id():
    conn = MagicMock()
    cursor = conn.cursor.return_value
    cursor.fetchone.side_effect = [("Travelling Expense", "Travelling Expense - Test"), ("deptA", "divA", "clA"), None]
    scope = _scope()
    results = save_detail_lines(
        conn, [_detail(gl_account="5210400020", trip_id=99, meta_json=None)], "filler@chememan.com", scope,
    )
    assert results[0].error == "trip_not_found"


def test_trip_side_mismatch_rejects_a_sga_gl_on_a_cost_trip():
    """Never-cut: COST 5xxx vs SG&A 6xxx never cross on one trip."""
    conn = MagicMock()
    cursor = conn.cursor.return_value
    cursor.fetchone.side_effect = [
        ("Travelling Expense", "Travelling Expense - Test"), ("deptA", "divA", "clA"),
        ("CC1", "COST", 2027),  # trip row: cost_center, side, fiscal_year
    ]
    scope = _scope()
    results = save_detail_lines(
        conn, [_detail(gl_account="6210400020", trip_id=1, meta_json=None)],  # SGA GL on a COST trip
        "filler@chememan.com", scope,
    )
    assert results[0].error == "trip_side_mismatch"


def test_trip_side_match_succeeds_and_recomputes_parent_cell():
    conn = MagicMock()
    cursor = conn.cursor.return_value
    cursor.fetchone.side_effect = [
        ("Travelling Expense", "Travelling Expense - Test"), ("deptA", "divA", "clA"),  # dims
        ("CC1", "COST", 2027),                                 # trip row: cost_center, side, fiscal_year
        None,                                                   # department-lock check -> not locked
        None,                                                   # deadline check -> no row, open
    ]
    scope = _scope()
    line = _detail(gl_account="5210400020", trip_id=1, meta_json=None, m01=500)  # transport GL, COST side
    results = save_detail_lines(conn, [line], "filler@chememan.com", scope)
    assert results[0].ok is True
    conn.commit.assert_called_once()
    all_sql = " ".join(c.args[0] for c in cursor.execute.call_args_list)
    assert "pending_budget_detail" in all_sql
    assert "SUM(" in all_sql


def test_detail_line_stale_lock_conflict():
    conn = MagicMock()
    cursor = conn.cursor.return_value
    cursor.fetchone.side_effect = [
        ("CC1", "5211900030", 2027),  # owner lookup (D3/D4 IDOR fix) — matches the payload, in-scope
        ("Entertainment", "Entertainment Expense"), ("deptA", "divA", "clA"),
        None,  # department-lock check -> no approval_status row, not locked
        None,  # deadline check -> no row, open
    ]
    cursor.rowcount = 0
    scope = _scope()
    results = save_detail_lines(
        conn, [_detail(detail_id=5, expected_updated_at=STALE)], "filler@chememan.com", scope,
    )
    assert results[0].error == "conflict"
    conn.commit.assert_not_called()


def test_detail_line_idor_owner_mismatch_rejected_without_touching_the_row():
    """D3/D4 IDOR fix: an attacker cannot rewrite an existing detail_id that
    belongs to a DIFFERENT cost_center, even by declaring their OWN in-scope
    cost_center in the payload — the fix reads the row's ACTUAL owner from
    the DB and authorizes/compares against that, not the payload."""
    conn = MagicMock()
    cursor = conn.cursor.return_value
    cursor.fetchone.side_effect = [("VICTIM-CC", "5211900030", 2027)]  # owner lookup: real row belongs elsewhere
    scope = _scope(fill_cost_centers=["CC1"], see_cost_centers=["CC1"])  # attacker's OWN in-scope CC
    results = save_detail_lines(
        conn,
        [_detail(detail_id=30, cost_center="CC1", expected_updated_at=STALE, m01=999999)],
        "attacker@chememan.com", scope,
    )
    assert results[0].ok is False
    assert results[0].error in ("forbidden", "conflict")
    executed_sql = [c.args[0] for c in cursor.execute.call_args_list]
    assert not any("UPDATE budget.pending_budget_detail" in s for s in executed_sql), (
        "the victim's row must never be touched"
    )


def test_detail_line_owner_lookup_authorizes_against_actual_cc_not_payload():
    """Non-malicious sibling (D4): even when the payload's declared
    cost_center IS in scope, a mismatch against the row's real owner must
    still be rejected before any write (prevents parent-cell desync for a
    multi-CC filler who posts the wrong CC)."""
    conn = MagicMock()
    cursor = conn.cursor.return_value
    cursor.fetchone.side_effect = [("CC9", "5211900030", 2027)]  # actual owner CC differs from the payload's CC1
    scope = _scope(fill_cost_centers=["CC1", "CC9"], see_cost_centers=["CC1", "CC9"])  # in scope for BOTH
    results = save_detail_lines(
        conn, [_detail(detail_id=30, cost_center="CC1", expected_updated_at=STALE)],
        "filler@chememan.com", scope,
    )
    assert results[0].ok is False
    assert results[0].error == "conflict"


def test_detail_line_not_found_by_detail_id_is_conflict_not_500():
    conn = MagicMock()
    cursor = conn.cursor.return_value
    cursor.fetchone.side_effect = [None]  # owner lookup finds nothing
    scope = _scope()
    results = save_detail_lines(
        conn, [_detail(detail_id=999, expected_updated_at=STALE)], "filler@chememan.com", scope,
    )
    assert results[0].error == "conflict"


def test_detail_line_commit_happens_after_parent_cell_recompute_not_before():
    """A5 gate MUST-FIX 1 (silent data loss): conn.commit() must fire AFTER
    _recompute_parent_cell, not right after the detail-line write. db.py
    closes the connection without an implicit commit, so a commit placed
    before the recompute silently rolled back the parent-cell UPDATE/INSERT
    every time — asserts ORDER, not just call count."""
    conn = MagicMock()
    cursor = conn.cursor.return_value
    cursor.fetchone.side_effect = [
        ("Entertainment", "Entertainment Expense"), ("deptA", "divA", "clA"),  # dims
        None,  # department-lock check -> no approval_status row, not locked
        None,  # deadline check -> no row, open
    ]
    scope = _scope()
    results = save_detail_lines(conn, [_detail(m01=1000)], "filler@chememan.com", scope)
    assert results[0].ok is True
    assert conn.commit.call_count == 1

    def _is_detail_table_write(sql: str) -> bool:
        s = sql.strip()
        return s.startswith("INSERT INTO budget.pending_budget_detail") or s.startswith("UPDATE budget.pending_budget_detail")

    def _is_parent_table_write(sql: str) -> bool:
        # D5: the atomic recompute UPDATE embeds a `pending_budget_detail`
        # SUM subquery in its SET clause, so a plain substring check for
        # "pending_budget_detail" would wrongly match it too — distinguish
        # by which table is being written (the statement's own prefix),
        # not by what the statement merely references.
        s = sql.strip()
        return (
            s.startswith("INSERT INTO budget.pending_budget") or s.startswith("UPDATE budget.pending_budget")
        ) and not _is_detail_table_write(sql)

    commit_idx = detail_write_idx = parent_write_idx = None
    for i, call in enumerate(conn.mock_calls):
        name, args = call[0], call[1]
        if name == "commit":
            commit_idx = i
        elif name.endswith("execute") and args:
            sql = args[0]
            if _is_detail_table_write(sql):
                detail_write_idx = i
            elif _is_parent_table_write(sql):
                parent_write_idx = i

    assert commit_idx is not None, "conn.commit() was never called"
    assert detail_write_idx is not None, "detail-line write not found"
    assert parent_write_idx is not None, "parent-cell recompute write not found"
    assert detail_write_idx < commit_idx
    assert parent_write_idx < commit_idx  # the bug: today the parent-cell write happens AFTER commit


def test_parent_cell_insert_pk_collision_becomes_conflict_not_500():
    """A5 gate MUST-FIX 2: two concurrent FIRST-EVER writes to the same
    parent cell both see rowcount==0 on the UPDATE and both try INSERT; the
    loser hits a PK violation. pyodbc.IntegrityError is not in
    _CAUGHT_PER_ITEM, so before this fix it escaped the batch as a raw
    exception (-> 502 at the router) instead of a per-item 409 conflict."""
    conn = MagicMock()
    cursor = conn.cursor.return_value
    cursor.fetchone.side_effect = [
        ("Entertainment", "Entertainment Expense"), ("deptA", "divA", "clA"),  # dims
        None,                                                                    # department-lock check -> not locked
        None,                                                                    # deadline check -> no row, open
        (1000.0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0),        # SUM(...) recompute
    ]
    cursor.fetchval.return_value = 999  # OUTPUT INSERTED.detail_id
    cursor.rowcount = 0  # parent row does not exist yet -> UPDATE matches nothing
    cursor.execute.side_effect = [
        None, None,          # gl_group + cc_dims lookups
        None,                 # department-lock check
        None,                 # deadline check
        None,                 # detail line INSERT
        None,                 # parent UPDATE (rowcount==0 -> falls to INSERT)
        None,                 # SUM(...) recompute select
        pyodbc.IntegrityError("23000", "PK violation"),  # first INSERT attempt -> collision
        None,                 # retry UPDATE after catching the collision
    ]
    scope = _scope()
    results = save_detail_lines(conn, [_detail(m01=1000)], "filler@chememan.com", scope)
    assert results[0].ok is False
    assert results[0].error == "conflict"


def test_parent_cell_insert_pk_collision_retry_succeeds():
    """Companion to the collision test above: the same PK-collision path,
    but this time the retry UPDATE (after catching the collision) MATCHES
    a row and succeeds — the common case, since the concurrent winner's
    row is now visible. Proves the bounded retry actually recovers instead
    of always falling through to the 409 (a static rowcount=0 mock cannot
    tell 'retry succeeds' from 'retry also fails' apart)."""
    conn = MagicMock()
    cursor = conn.cursor.return_value
    cursor.fetchone.side_effect = [
        ("Entertainment", "Entertainment Expense"), ("deptA", "divA", "clA"),  # dims
        None,                                                                    # department-lock check -> not locked
        None,                                                                    # deadline check -> no row, open
        (1000.0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0),        # SUM(...) recompute
    ]
    cursor.fetchval.return_value = 999  # OUTPUT INSERTED.detail_id

    call_count = {"n": 0}

    def _execute_side_effect(sql, *params):
        call_count["n"] += 1
        # Call order: gl-lookup(1), cc-dims(2), department-lock-check(3),
        # deadline-check(4), detail-INSERT(5), parent atomic UPDATE(6),
        # SUM-recompute-select(7), parent INSERT/collision(8), retry UPDATE(9).
        if call_count["n"] == 6:
            cursor.rowcount = 0  # first atomic UPDATE (D5) matches nothing -> falls to INSERT
        elif call_count["n"] == 8:
            raise pyodbc.IntegrityError("23000", "PK violation")  # concurrent INSERT collision
        elif call_count["n"] == 9:
            cursor.rowcount = 1  # retry of the atomic UPDATE now matches the winner's row -> succeeds
        return None

    cursor.execute.side_effect = _execute_side_effect
    scope = _scope()
    results = save_detail_lines(conn, [_detail(m01=1000)], "filler@chememan.com", scope)
    assert results[0].ok is True
    conn.commit.assert_called_once()


def test_travel_gl_detail_line_without_trip_id_is_rejected():
    """A5 gate MUST-FIX 3 (NEVER-CUT COST/SGA): the 3 non-per-diem
    Travelling GLs (transport/lodging/other) must attach to an existing
    trip. Before this fix trip_id=None silently bypassed the side-check
    entirely and saved an orphan line."""
    conn = MagicMock()
    cursor = conn.cursor.return_value
    cursor.fetchone.side_effect = [("Travelling Expense", "Travelling Expense - Test"), ("deptA", "divA", "clA")]
    scope = _scope()
    results = save_detail_lines(
        conn, [_detail(gl_account="5210400020", trip_id=None, meta_json=None)],
        "filler@chememan.com", scope,
    )
    assert results[0].error == "invalid_request"
    executed_sql = [c.args[0] for c in cursor.execute.call_args_list]
    assert not any("INSERT INTO budget.pending_budget_detail" in s for s in executed_sql), (
        "the orphan line must never be written"
    )


def test_non_travelling_detail_line_with_trip_id_is_rejected():
    """Defense-in-depth (A5 re-gate item 2): only the 3 non-per-diem
    Travelling GLs may reference a trip_id (checked above). A non-Travelling
    detail line (e.g. Entertainment) carrying an arbitrary trip_id had zero
    cross-validation — reject it before any trip lookup, instead of silently
    trusting an unrelated trip_id."""
    conn = MagicMock()
    cursor = conn.cursor.return_value
    cursor.fetchone.side_effect = [("Entertainment", "Entertainment Expense"), ("deptA", "divA", "clA")]
    scope = _scope()
    results = save_detail_lines(
        conn, [_detail(gl_account="5211900030", trip_id=1)], "filler@chememan.com", scope,
    )
    assert results[0].error == "invalid_request"
    executed_sql = [c.args[0] for c in cursor.execute.call_args_list]
    assert not any("budget_trip" in s for s in executed_sql), "must not look up an unrelated trip_id"


def test_detail_line_rejected_when_deadline_has_passed_no_db_write():
    conn = MagicMock()
    cursor = conn.cursor.return_value
    cursor.fetchone.side_effect = [
        ("Entertainment", "Entertainment Expense"), ("deptA", "divA", "clA"),  # dims
        None,  # department-lock check -> no approval_status row, not locked
        (date(2020, 1, 1),),  # dbo.submission_deadline -> already passed
    ]
    scope = _scope()
    results = save_detail_lines(conn, [_detail(m01=1000)], "filler@chememan.com", scope)
    assert results[0].ok is False
    assert results[0].error == "past_deadline"
    conn.commit.assert_not_called()
    executed_sql = [c.args[0] for c in cursor.execute.call_args_list]
    assert not any("pending_budget_detail" in s for s in executed_sql)


# ---------------------------------------------------------------------------
# save_trip
# ---------------------------------------------------------------------------

def _trip(**overrides) -> TripInput:
    defaults = dict(trip_id=None, cost_center="CC1", fiscal_year=2027, traveler_empcode="E1",
                     destination="Bangkok", country_group=1, days=5, travel_months=["03"],
                     purpose="site visit", side="COST", expected_updated_at=None)
    defaults.update(overrides)
    return TripInput(**defaults)


def test_trip_input_rejects_invalid_country_group():
    """A5 gate cheap fix: out-of-range country_group must be rejected at the
    Pydantic/input layer, before it can reach derive_per_diem's plain
    ValueError (which today surfaces as a generic 500)."""
    with pytest.raises(ValidationError):
        _trip(country_group=99)


def test_trip_input_rejects_negative_days():
    """A5 gate cheap fix: negative days must be rejected at the input layer."""
    with pytest.raises(ValidationError):
        _trip(days=-1)


# ---------------------------------------------------------------------------
# D7 — travel_months validation (dedupe exact duplicates, reject malformed)
# ---------------------------------------------------------------------------

def test_trip_input_rejects_out_of_range_month():
    with pytest.raises(ValidationError):
        _trip(travel_months=["99"])


def test_trip_input_rejects_empty_month_string():
    with pytest.raises(ValidationError):
        _trip(travel_months=[""])


def test_trip_input_rejects_non_numeric_month():
    with pytest.raises(ValidationError):
        _trip(travel_months=["abc"])


def test_trip_input_rejects_csv_in_one_element():
    """A client sending '03,03' as a single list element (instead of two
    entries) must be rejected, never silently mis-parsed."""
    with pytest.raises(ValidationError):
        _trip(travel_months=["03,03"])


def test_trip_input_rejects_empty_travel_months_list():
    with pytest.raises(ValidationError):
        _trip(travel_months=[])


def test_trip_input_dedupes_exact_duplicate_months():
    """Decided (D7): dedupe EXACT duplicates rather than reject — a client
    accidentally submitting the same month twice must not halve the
    per-diem split (n=1, not n=2)."""
    trip = _trip(travel_months=["03", "03"])
    assert trip.travel_months == ["03"]


# ---------------------------------------------------------------------------
# D9 — Pydantic length/range guards (NVARCHAR / DECIMAL overflow)
# ---------------------------------------------------------------------------

def test_trip_input_rejects_destination_over_200_chars():
    with pytest.raises(ValidationError):
        _trip(destination="x" * 201)


def test_trip_input_rejects_purpose_over_500_chars():
    with pytest.raises(ValidationError):
        _trip(purpose="x" * 501)


def test_trip_input_rejects_cost_center_over_20_chars():
    with pytest.raises(ValidationError):
        _trip(cost_center="x" * 21)


def test_pending_row_input_rejects_remark_over_500_chars():
    with pytest.raises(ValidationError):
        _row(remark="x" * 501)


def test_pending_row_input_rejects_month_amount_at_decimal_max():
    with pytest.raises(ValidationError):
        _row(m01=1e16)


def test_detail_line_input_rejects_line_label_over_300_chars():
    with pytest.raises(ValidationError):
        _detail(line_label="x" * 301)


def test_trip_forbidden_scope_no_db_call():
    conn = MagicMock()
    scope = _scope(fill_cost_centers=[], see_cost_centers=[])
    results = save_trip(conn, [_trip()], "user@chememan.com", scope)
    assert results[0].error == "forbidden"
    conn.cursor.assert_not_called()


def test_traveler_not_found_fails():
    conn = MagicMock()
    cursor = conn.cursor.return_value
    cursor.fetchone.side_effect = [None]  # traveler lookup -> not found
    scope = _scope()
    results = save_trip(conn, [_trip()], "filler@chememan.com", scope)
    assert results[0].error == "traveler_not_found"


def test_missing_per_diem_rate_fails_loud_as_5xx_class_error():
    conn = MagicMock()
    cursor = conn.cursor.return_value
    cursor.fetchone.side_effect = [("Somchai", "N/A"), None]  # traveler found, rate lookup -> none
    scope = _scope()
    with pytest.raises(MissingPerDiemRateError):
        save_trip(conn, [_trip()], "filler@chememan.com", scope)


def test_per_diem_rate_lookup_queries_job_level_column_not_position():
    """D1 SHOWSTOPPER fix: the live `dbo.per_diem_rate` column is `job_level`,
    not `position` (the spec DBML's column name was wrong). Every real
    POST|PUT /budget/trip raised pyodbc 42S22 ("invalid column name
    'position'") before this fix — every single Travelling Expense save was
    dead."""
    conn = MagicMock()
    cursor = conn.cursor.return_value
    cursor.fetchone.return_value = (500, None, None)
    from app.write_model import _lookup_per_diem_rate

    _lookup_per_diem_rate(conn, "Manager")
    sql_text = cursor.execute.call_args.args[0]
    assert "job_level = ?" in sql_text
    assert "position = ?" not in sql_text


def test_save_trip_succeeds_for_a_traveler_whose_rate_is_zero_not_missing():
    """D12 policy (decided): 0.00 IS a valid configured rate (e.g. a
    Department Head / Operator position with no per-diem entitlement) — must
    compute a 0 per-diem, never raise MissingPerDiemRateError. Only a
    traveler whose job_level has NO ROW AT ALL (e.g. 'N/A') fails loud.
    Verified: `_lookup_per_diem_rate` only raises when `row is None` (no
    row), never when a rate column merely equals 0 — this was already
    correct, this test locks it in as a regression guard."""
    conn = MagicMock()
    cursor = conn.cursor.return_value
    cursor.fetchone.side_effect = [
        ("Somchai", "Director"),  # traveler lookup
        (0, None, None),           # per_diem_rate ROW EXISTS, rate_domestic=0.00 (not missing)
        ("deptA", "divA", "clA"),   # cc_dims lookup for department-lock check
        None,                       # department-lock check -> no approval_status row, not locked
        None,                       # deadline check -> no row, open
        None,                       # existing trip-detail lookup -> none, will INSERT
        ("Bank Charge", "Bank Charge Fee"), ("deptA", "divA", "clA"),
        (0.0,) * 12,                 # SUM(...) recompute -> all zero
    ]
    cursor.fetchval.return_value = 55
    scope = _scope()
    results = save_trip(conn, [_trip(days=5, country_group=1)], "filler@chememan.com", scope)
    result = results[0]
    assert result.ok is True, f"expected success for a 0.00-rate traveler, got error={result.error}"
    assert result.trip.per_diem_months["m03"] == 0.0


def test_missing_fx_rate_fails_loud_for_asian_group():
    conn = MagicMock()
    cursor = conn.cursor.return_value
    cursor.fetchone.side_effect = [
        ("Somchai", "Manager"),               # traveler
        (0, 50, 70),                            # per_diem_rate row (domestic, asian, other)
        None,                                    # FX lookup -> missing
    ]
    scope = _scope()
    with pytest.raises(MissingFxRateError):
        save_trip(conn, [_trip(country_group=2)], "filler@chememan.com", scope)


def test_trip_create_succeeds_and_derives_per_diem_matching_the_formula():
    conn = MagicMock()
    cursor = conn.cursor.return_value
    cursor.fetchone.side_effect = [
        ("Somchai", "Manager"),                        # traveler lookup
        (500, None, None),                               # per_diem_rate (domestic=500)
        ("deptA", "divA", "clA"),                         # cc_dims lookup for department-lock check
        None,                                             # department-lock check -> no approval_status row, not locked
        None,                                             # deadline check -> no row, open
        None,                                             # existing trip-detail lookup -> none, will INSERT
        ("Bank Charge", "Bank Charge Fee"), ("deptA", "divA", "clA"),        # dims for the per-diem GL
        (0, 0, 5000.0, 0, 0, 0, 0, 0, 0, 0, 0, 0),        # SUM(...) recompute -> m03=5000
    ]
    cursor.fetchval.return_value = 42  # OUTPUT INSERTED.trip_id
    scope = _scope()
    results = save_trip(conn, [_trip(days=10, country_group=1)], "filler@chememan.com", scope)
    result = results[0]
    assert result.ok is True
    assert result.trip.trip_id == 42
    assert result.trip.traveler_name == "Somchai"
    assert result.trip.position == "Manager"
    # 10 days * 500 THB domestic (no FX) = 5000.00, all in month 03 (single selected month)
    assert result.trip.per_diem_months["m03"] == 5000.0
    conn.commit.assert_called_once()


def test_trip_side_selects_the_matching_perdiem_gl():
    conn = MagicMock()
    cursor = conn.cursor.return_value
    cursor.fetchone.side_effect = [
        ("Somchai", "Manager"), (500, None, None),
        ("deptA", "divA", "clA"),  # cc_dims lookup for department-lock check
        None,  # department-lock check -> no approval_status row, not locked
        None,  # deadline check -> no row, open
        None,  # existing trip-detail lookup -> none, will INSERT
        ("Bank Charge", "Bank Charge Fee"), ("deptA", "divA", "clA"),
        (0,) * 12,
    ]
    cursor.fetchval.return_value = 7
    scope = _scope()
    save_trip(conn, [_trip(side="SGA")], "filler@chememan.com", scope)
    all_sql_and_params = [(c.args[0], c.args[1:]) for c in cursor.execute.call_args_list]
    flat_params = [p for _, params in all_sql_and_params for p in params]
    assert "6210400010" in flat_params  # SGA per-diem GL, never the COST one


def test_trip_update_stale_lock_conflict():
    conn = MagicMock()
    cursor = conn.cursor.return_value
    cursor.fetchone.side_effect = [
        ("Somchai", "Manager"), (500, None, None),
        ("CC1", "COST", 2027),  # old-trip lookup (captures old side before the stale UPDATE fails)
        ("deptA", "divA", "clA"),  # cc_dims lookup for department-lock check
        None,  # department-lock check -> no approval_status row, not locked
        None,  # deadline check -> no row, open
    ]
    cursor.rowcount = 0
    scope = _scope()
    results = save_trip(
        conn, [_trip(trip_id=1, expected_updated_at=STALE)], "filler@chememan.com", scope,
    )
    assert results[0].error == "conflict"
    conn.commit.assert_not_called()


def test_per_diem_detail_line_is_recomputed_fresh_never_reusing_a_stale_stored_amount():
    """Never-cut: per-diem is DERIVED ON READ (ADR-0015) — a Master-FX edit
    must re-price it immediately. Proof here: `_upsert_trip_detail_line` never
    fetches the existing line's stored m01..m12 (only whether a line already
    exists), so an update ALWAYS writes the freshly-derived total — even
    though a stale row (from a since-changed FX) already exists in the DB."""
    conn = MagicMock()
    cursor = conn.cursor.return_value
    cursor.fetchone.side_effect = [
        ("Somchai", "Manager"), (500, None, None),
        ("CC1", "COST", 2027),  # old-trip lookup — side unchanged (COST->COST), no GL flip
        ("deptA", "divA", "clA"),  # cc_dims lookup for department-lock check
        None,  # department-lock check -> no approval_status row, not locked
        None,  # deadline check -> no row, open
        (99,),  # an existing per-diem detail line already exists (detail_id=99) — its OLD amount is never read
        ("Bank Charge", "Bank Charge Fee"), ("deptA", "divA", "clA"),
        (None,),  # echo fix: project not sent -> read back the actually-stored value (none here)
    ]
    cursor.rowcount = 1
    scope = _scope()
    results = save_trip(
        conn, [_trip(trip_id=1, days=14, country_group=1, expected_updated_at=STALE)],
        "filler@chememan.com", scope,
    )
    result = results[0]
    assert result.ok is True
    # 14 days * 500 THB domestic = 7000.00 — the freshly derived total, not whatever "99" held before.
    assert result.trip.per_diem_months["m03"] == 7000.0
    update_detail_sql, update_detail_params = next(
        (c.args[0], c.args[1:]) for c in cursor.execute.call_args_list if "UPDATE budget.pending_budget_detail" in c.args[0]
    )
    assert 7000.0 in update_detail_params
    assert 99 in update_detail_params  # targets the existing line by its detail_id, not a blind insert


def test_per_diem_line_label_is_bound_as_a_parameter_never_a_varchar_sql_literal():
    """Live-DB confirmed corruption (2026-07-16): the Thai label embedded as a
    plain (non-N-prefixed) SQL literal is converted through the DB's default
    code page on INSERT — every Thai char persisted as '?', so every auto-calc
    per-diem line showed '??????????? · Per Diem' in the subform UI (the '·'
    U+00B7 survived, it's in Latin1). The label must reach cursor.execute as a
    BOUND parameter (pyodbc sends NVARCHAR — collation can never touch it) and
    the SQL text itself must stay pure ASCII."""
    conn = MagicMock()
    cursor = conn.cursor.return_value
    cursor.fetchone.return_value = None  # no existing per-diem line -> INSERT path
    from app.write_model import MONTH_COLUMNS, _upsert_trip_detail_line

    months = {m: 0.0 for m in MONTH_COLUMNS} | {"m03": 5000.0}
    _upsert_trip_detail_line(
        conn, 42, "CC1", "5210400010", 2027, months, "filler@chememan.com",
        datetime(2026, 7, 16, tzinfo=timezone.utc),
    )
    insert_sql, insert_params = next(
        (c.args[0], c.args[1:]) for c in cursor.execute.call_args_list
        if "INSERT INTO budget.pending_budget_detail" in c.args[0]
    )
    assert "เบี้ยเลี้ยง · Per Diem" in insert_params, (
        "per-diem line_label must be passed as a bound parameter, codepoint-for-codepoint"
    )
    assert insert_sql.isascii(), (
        "non-ASCII embedded in the SQL string -> varchar literal -> code-page corruption"
    )


def test_trip_side_flip_deletes_old_gl_line_and_recomputes_old_gl_parent_cell():
    """A5 gate MUST-FIX 4 + D8 (NEVER-CUT COST/SGA + parent==SUM): updating a
    trip's side (COST->SGA) changes its per-diem GL AND must re-home the 3
    manual travel lines (transport/accommodation/other) too — before the D8
    fix, only per-diem moved and a manual line could be left stranded under
    the OLD side's GL (one trip spanning both COST and SGA)."""
    conn = MagicMock()
    cursor = conn.cursor.return_value

    # The first 6 fetchone() calls are one-off (traveler/rate/old-trip/
    # department-lock cc_dims+status/deadline/existing-per-diem-line lookups);
    # every call after that is a gl_group-then-cc_dims pair for whichever GL
    # is being recomputed next (D5's atomic recompute never issues a SELECT
    # of its own when the parent row already exists — cursor.rowcount=1
    # below — so only the dims lookups remain to mock).
    one_off = iter([
        ("Somchai", "Manager"),    # 1 traveler lookup
        (500, None, None),          # 2 per_diem_rate (domestic=500)
        ("CC1", "COST", 2027),       # 3 OLD trip lookup -> old side was COST
        ("deptA", "divA", "clA"),     # 4 cc_dims lookup for department-lock check
        None,                         # 5 department-lock check -> no approval_status row, not locked
        None,                         # 6 deadline check -> no row, open
        None,                         # 7 existing per-diem line under NEW (SGA) gl -> none, INSERT
    ])
    dims_cycle = itertools.cycle([("Bank Charge", "Bank Charge Fee"), ("deptA", "divA", "clA")])

    def _fetchone_side_effect():
        try:
            return next(one_off)
        except StopIteration:
            return next(dims_cycle)

    cursor.fetchone.side_effect = _fetchone_side_effect
    cursor.rowcount = 1  # trip UPDATE + every atomic parent-cell recompute matches an existing row directly
    scope = _scope()
    results = save_trip(
        conn, [_trip(trip_id=1, side="SGA", days=10, country_group=1, expected_updated_at=STALE)],
        "filler@chememan.com", scope,
    )
    result = results[0]
    assert result.ok is True

    executed = [(c.args[0], c.args[1:]) for c in cursor.execute.call_args_list]

    delete_calls = [args for sql, args in executed if sql.strip().startswith("DELETE FROM budget.pending_budget_detail")]
    assert delete_calls, "expected a DELETE of the stale per-diem line under the old (COST) GL"
    assert "5210400010" in delete_calls[0]  # COST per-diem GL — the OLD side

    rehome_calls = [
        args for sql, args in executed
        if sql.strip().startswith("UPDATE budget.pending_budget_detail SET gl_account")
    ]
    rehomed_pairs = {(args[0], args[2]) for args in rehome_calls}  # (new_gl, old_gl) per _rehome_trip_detail_lines call
    assert ("6210400020", "5210400020") in rehomed_pairs, "transport line must move COST->SGA"
    assert ("6210400030", "5210400030") in rehomed_pairs, "accommodation line must move COST->SGA"
    assert ("6210400999", "5210400999") in rehomed_pairs, "other-travel line must move COST->SGA"

    def _is_parent_table_write(sql: str) -> bool:
        s = sql.strip()
        is_detail = s.startswith("INSERT INTO budget.pending_budget_detail") or s.startswith("UPDATE budget.pending_budget_detail")
        return (s.startswith("INSERT INTO budget.pending_budget") or s.startswith("UPDATE budget.pending_budget")) and not is_detail

    parent_writes = [args for sql, args in executed if _is_parent_table_write(sql)]
    old_side_gls = {"5210400010", "5210400020", "5210400030", "5210400999"}
    new_side_gls = {"6210400010", "6210400020", "6210400030", "6210400999"}
    recomputed_old = {gl for args in parent_writes for gl in old_side_gls if gl in args}
    recomputed_new = {gl for args in parent_writes for gl in new_side_gls if gl in args}
    assert recomputed_old == old_side_gls, f"expected all 4 OLD-side parent cells recomputed, got {recomputed_old}"
    assert recomputed_new == new_side_gls, f"expected all 4 NEW-side parent cells recomputed, got {recomputed_new}"

    new_gl_inserts = [args for sql, args in executed if sql.strip().startswith("INSERT INTO budget.pending_budget_detail")]
    assert any("6210400010" in args for args in new_gl_inserts)  # SGA per-diem GL — the NEW side


def test_trip_create_rejected_when_deadline_has_passed_no_db_write():
    conn = MagicMock()
    cursor = conn.cursor.return_value
    cursor.fetchone.side_effect = [
        ("Somchai", "Manager"),        # traveler lookup
        (500, None, None),              # per_diem_rate (domestic=500)
        ("deptA", "divA", "clA"),        # cc_dims lookup for department-lock check
        None,                            # department-lock check -> no approval_status row, not locked
        (date(2020, 1, 1),),             # dbo.submission_deadline -> already passed
    ]
    scope = _scope()
    results = save_trip(conn, [_trip(days=10, country_group=1)], "filler@chememan.com", scope)
    assert results[0].ok is False
    assert results[0].error == "past_deadline"
    conn.commit.assert_not_called()
    executed_sql = [c.args[0] for c in cursor.execute.call_args_list]
    assert not any("INSERT INTO budget.budget_trip" in s for s in executed_sql)


def test_trip_update_rejected_when_deadline_has_passed_no_db_write_and_no_side_flip():
    """Covers the update / side-flip path: the deadline gate runs before the
    FIRST write, so a blocked update never reaches the side-flip logic
    either (no old-GL delete/rehome, no parent-cell recompute)."""
    conn = MagicMock()
    cursor = conn.cursor.return_value
    cursor.fetchone.side_effect = [
        ("Somchai", "Manager"),          # traveler lookup
        (500, None, None),                # per_diem_rate (domestic=500)
        ("CC1", "COST", 2027),             # old-trip lookup (side would-be COST)
        ("deptA", "divA", "clA"),           # cc_dims lookup for department-lock check
        None,                               # department-lock check -> no approval_status row, not locked
        (date(2020, 1, 1),),                # dbo.submission_deadline -> already passed
    ]
    scope = _scope()
    results = save_trip(
        conn, [_trip(trip_id=1, side="SGA", days=10, country_group=1, expected_updated_at=STALE)],
        "filler@chememan.com", scope,
    )
    assert results[0].ok is False
    assert results[0].error == "past_deadline"
    conn.commit.assert_not_called()
    executed_sql = [c.args[0] for c in cursor.execute.call_args_list]
    assert not any(s.strip().startswith("UPDATE budget.budget_trip") for s in executed_sql)
    assert not any("DELETE FROM budget.pending_budget_detail" in s for s in executed_sql)


# ---------------------------------------------------------------------------
# A9 backend gap close — delete_detail_line / delete_trip
#
# Authorization is resolved from the row's ACTUAL owner (detail_id/trip_id
# looked up fresh from the DB) — neither delete function accepts
# cost_center/gl_account/fiscal_year in its signature at all, so unlike
# save's IDOR fix (which has to compare a payload-declared CC against the
# real owner) there is no redundant field left to spoof in the first place.
# ---------------------------------------------------------------------------

def test_delete_detail_line_forbidden_when_actual_cc_outside_caller_scope():
    """The caller's OWN Fill scope (CC-MINE) never includes the row's ACTUAL
    owning cost_center (CC-OTHER) — rejected before any write, no spoof
    vector exists since the request never carries a cost_center at all."""
    conn = MagicMock()
    cursor = conn.cursor.return_value
    cursor.fetchone.side_effect = [("CC-OTHER", "5211900030", 2027)]  # owner lookup
    scope = _scope(fill_cost_centers=["CC-MINE"], see_cost_centers=["CC-MINE"])
    result = delete_detail_line(conn, 30, STALE, "attacker@chememan.com", scope)
    assert result.ok is False
    assert result.error == "forbidden"
    executed_sql = [c.args[0] for c in cursor.execute.call_args_list]
    assert not any("DELETE FROM budget.pending_budget_detail" in s for s in executed_sql)


def test_delete_detail_line_stale_token_is_conflict_no_write():
    conn = MagicMock()
    cursor = conn.cursor.return_value
    cursor.fetchone.side_effect = [
        ("CC1", "5211900030", 2027),  # owner lookup
        ("deptA", "divA", "clA"),      # cc_dims lookup for department-lock check
        None,                          # department-lock check -> no approval_status row, not locked
        None,                          # deadline check -> no row, open
    ]
    cursor.rowcount = 0  # DELETE matches nothing -> stale token
    scope = _scope()
    result = delete_detail_line(conn, 5, STALE, "filler@chememan.com", scope)
    assert result.ok is False
    assert result.error == "conflict"
    conn.commit.assert_not_called()


def test_delete_detail_line_rejected_when_deadline_has_passed_no_db_write():
    conn = MagicMock()
    cursor = conn.cursor.return_value
    cursor.fetchone.side_effect = [
        ("CC1", "5211900030", 2027),   # owner lookup
        ("deptA", "divA", "clA"),       # cc_dims lookup for department-lock check
        None,                           # department-lock check -> no approval_status row, not locked
        (date(2020, 1, 1),),            # dbo.submission_deadline -> already passed
    ]
    scope = _scope()
    result = delete_detail_line(conn, 5, STALE, "filler@chememan.com", scope)
    assert result.ok is False
    assert result.error == "past_deadline"
    conn.commit.assert_not_called()
    executed_sql = [c.args[0] for c in cursor.execute.call_args_list]
    assert not any("DELETE FROM budget.pending_budget_detail" in s for s in executed_sql)


def test_delete_detail_line_admin_bypasses_deadline_and_scope():
    conn = MagicMock()
    cursor = conn.cursor.return_value
    cursor.fetchone.side_effect = [
        ("ANY-CC", "5211900030", 2027),                                     # owner lookup
        (1,),                                                                # admin CC-existence check
        ("Entertainment", "Entertainment Expense"), ("deptA", "divA", "clA"),  # dims for recompute
    ]
    cursor.rowcount = 1
    scope = _admin_scope()
    result = delete_detail_line(conn, 5, STALE, "admin@chememan.com", scope)
    assert result.ok is True
    executed_sql = [c.args[0] for c in cursor.execute.call_args_list]
    assert not any("submission_deadline" in s for s in executed_sql)


def test_delete_detail_line_commit_happens_after_delete_and_recompute():
    """Same commit-order rule as every other write in this module: db.py has
    no implicit commit, so a commit placed before the DELETE/recompute would
    silently discard them on connection close."""
    conn = MagicMock()
    cursor = conn.cursor.return_value
    cursor.fetchone.side_effect = [
        ("CC1", "5211900030", 2027),                                          # owner lookup
        ("deptA", "divA", "clA"),                                              # cc_dims for department-lock check
        None,                                                                  # department-lock check -> not locked
        None,                                                                  # deadline check -> open
        ("Entertainment", "Entertainment Expense"), ("deptA", "divA", "clA"),  # dims for recompute
    ]
    cursor.rowcount = 1
    scope = _scope()
    result = delete_detail_line(conn, 5, STALE, "filler@chememan.com", scope)
    assert result.ok is True
    assert conn.commit.call_count == 1

    def _is_detail_delete(sql: str) -> bool:
        return sql.strip().startswith("DELETE FROM budget.pending_budget_detail")

    def _is_parent_write(sql: str) -> bool:
        s = sql.strip()
        return (s.startswith("INSERT INTO budget.pending_budget") or s.startswith("UPDATE budget.pending_budget")) and not (
            s.startswith("INSERT INTO budget.pending_budget_detail") or s.startswith("UPDATE budget.pending_budget_detail")
        )

    commit_idx = delete_idx = parent_write_idx = None
    for i, call in enumerate(conn.mock_calls):
        name, args = call[0], call[1]
        if name == "commit":
            commit_idx = i
        elif name.endswith("execute") and args:
            if _is_detail_delete(args[0]):
                delete_idx = i
            elif _is_parent_write(args[0]):
                parent_write_idx = i

    assert commit_idx is not None
    assert delete_idx is not None, "detail-line DELETE not found"
    assert parent_write_idx is not None, "parent-cell recompute write not found"
    assert delete_idx < commit_idx
    assert parent_write_idx < commit_idx


def test_delete_detail_line_not_found_is_conflict_not_500():
    conn = MagicMock()
    cursor = conn.cursor.return_value
    cursor.fetchone.side_effect = [None]  # owner lookup finds nothing
    scope = _scope()
    result = delete_detail_line(conn, 999, STALE, "filler@chememan.com", scope)
    assert result.ok is False
    assert result.error == "conflict"


def test_delete_detail_line_deleting_last_line_removes_the_empty_parent():
    """Deleting the LAST remaining detail line removes the now-empty parent
    row too (2026-07-21 jakkaritw spot-test residue fix) — but ONLY via the
    guarded DELETE: `remark IS NULL` (a user-authored grid remark keeps the
    row), `total_year = 0`, and `NOT EXISTS` any remaining detail line for
    the cell (other lines — e.g. another trip's — keep it)."""
    conn = MagicMock()
    cursor = conn.cursor.return_value
    cursor.fetchone.side_effect = [
        ("CC1", "5211900030", 2027),
        ("deptA", "divA", "clA"),  # cc_dims for department-lock check
        None,  # department-lock check -> not locked
        None,  # deadline check -> open
        ("Entertainment", "Entertainment Expense"), ("deptA", "divA", "clA"),
    ]
    cursor.rowcount = 1  # parent row already exists -> recompute UPDATE matches it
    scope = _scope()
    result = delete_detail_line(conn, 5, STALE, "filler@chememan.com", scope)
    assert result.ok is True
    executed_sql = [c.args[0] for c in cursor.execute.call_args_list]
    assert any(s.strip().startswith("UPDATE budget.pending_budget") for s in executed_sql)
    parent_deletes = [
        s
        for s in executed_sql
        if s.strip().startswith("DELETE FROM budget.pending_budget")
        and not s.strip().startswith("DELETE FROM budget.pending_budget_detail")
    ]
    assert len(parent_deletes) == 1, "expected exactly one guarded parent DELETE"
    sql = parent_deletes[0]
    assert "remark IS NULL" in sql
    assert "total_year = 0" in sql
    assert "NOT EXISTS" in sql


def test_delete_trip_removes_all_lines_and_recomputes_all_four_side_gls():
    conn = MagicMock()
    cursor = conn.cursor.return_value
    one_off = iter([
        ("CC1", "COST", 2027),      # trip lookup
        ("deptA", "divA", "clA"),    # cc_dims lookup for department-lock check
        None,                         # department-lock check -> not locked
        None,                         # deadline check -> open
    ])
    dims_cycle = itertools.cycle([("Bank Charge", "Bank Charge Fee"), ("deptA", "divA", "clA")])

    def _fetchone_side_effect():
        try:
            return next(one_off)
        except StopIteration:
            return next(dims_cycle)

    cursor.fetchone.side_effect = _fetchone_side_effect
    cursor.rowcount = 1
    scope = _scope()
    result = delete_trip(conn, 7, STALE, "filler@chememan.com", scope)
    assert result.ok is True

    executed = [(c.args[0], c.args[1:]) for c in cursor.execute.call_args_list]

    trip_delete_calls = [args for sql, args in executed if sql.strip().startswith("DELETE FROM budget.budget_trip")]
    assert trip_delete_calls, "trip header row was never deleted"

    line_delete_calls = [
        (sql, args) for sql, args in executed if sql.strip().startswith("DELETE FROM budget.pending_budget_detail")
    ]
    assert line_delete_calls, "expected exactly one DELETE removing every one of the trip's detail lines"
    assert "trip_id" in line_delete_calls[0][0]
    assert 7 in line_delete_calls[0][1]

    def _is_parent_write(sql: str) -> bool:
        s = sql.strip()
        is_detail = s.startswith("INSERT INTO budget.pending_budget_detail") or s.startswith("UPDATE budget.pending_budget_detail")
        return (s.startswith("INSERT INTO budget.pending_budget") or s.startswith("UPDATE budget.pending_budget")) and not is_detail

    parent_writes = [args for sql, args in executed if _is_parent_write(sql)]
    cost_side_gls = {"5210400010", "5210400020", "5210400030", "5210400999"}
    recomputed = {gl for args in parent_writes for gl in cost_side_gls if gl in args}
    assert recomputed == cost_side_gls, f"expected all 4 COST-side parent cells recomputed, got {recomputed}"


def test_delete_trip_removes_orphaned_parents_for_all_four_side_gls():
    """After the trip's lines are gone, each of the 4 travel-GL parent rows
    gets the same guarded orphan DELETE as the detail-line path (2026-07-21
    residue fix) — a parent another trip still uses is kept by the NOT EXISTS
    guard, not by skipping the attempt."""
    conn = MagicMock()
    cursor = conn.cursor.return_value
    one_off = iter([
        ("CC1", "COST", 2027),      # trip lookup
        ("deptA", "divA", "clA"),    # cc_dims lookup for department-lock check
        None,                         # department-lock check -> not locked
        None,                         # deadline check -> open
    ])
    dims_cycle = itertools.cycle([("Bank Charge", "Bank Charge Fee"), ("deptA", "divA", "clA")])

    def _fetchone_side_effect():
        try:
            return next(one_off)
        except StopIteration:
            return next(dims_cycle)

    cursor.fetchone.side_effect = _fetchone_side_effect
    cursor.rowcount = 1
    scope = _scope()
    result = delete_trip(conn, 7, STALE, "filler@chememan.com", scope)
    assert result.ok is True

    executed = [(c.args[0], c.args[1:]) for c in cursor.execute.call_args_list]
    cost_side_gls = {"5210400010", "5210400020", "5210400030", "5210400999"}
    parent_deletes = [
        (sql, args)
        for sql, args in executed
        if sql.strip().startswith("DELETE FROM budget.pending_budget")
        and not sql.strip().startswith("DELETE FROM budget.pending_budget_detail")
    ]
    deleted_gls = {gl for sql, args in parent_deletes for gl in cost_side_gls if gl in args}
    assert deleted_gls == cost_side_gls, f"expected guarded parent DELETE for all 4 GLs, got {deleted_gls}"
    for sql, _args in parent_deletes:
        assert "remark IS NULL" in sql
        assert "NOT EXISTS" in sql


def test_delete_trip_forbidden_when_actual_cc_outside_caller_scope():
    conn = MagicMock()
    cursor = conn.cursor.return_value
    cursor.fetchone.side_effect = [("CC-OTHER", "COST", 2027)]  # trip lookup
    scope = _scope(fill_cost_centers=["CC-MINE"], see_cost_centers=["CC-MINE"])
    result = delete_trip(conn, 7, STALE, "attacker@chememan.com", scope)
    assert result.ok is False
    assert result.error == "forbidden"
    executed_sql = [c.args[0] for c in cursor.execute.call_args_list]
    assert not any("DELETE FROM budget.budget_trip" in s for s in executed_sql)


def test_delete_trip_stale_token_is_conflict_no_lines_removed():
    conn = MagicMock()
    cursor = conn.cursor.return_value
    cursor.fetchone.side_effect = [
        ("CC1", "COST", 2027), ("deptA", "divA", "clA"), None, None,
    ]  # trip lookup, cc_dims for lock, lock check (not locked), deadline open
    cursor.rowcount = 0  # trip DELETE matches nothing -> stale
    scope = _scope()
    result = delete_trip(conn, 7, STALE, "filler@chememan.com", scope)
    assert result.ok is False
    assert result.error == "conflict"
    conn.commit.assert_not_called()
    executed_sql = [c.args[0] for c in cursor.execute.call_args_list]
    assert not any("DELETE FROM budget.pending_budget_detail" in s for s in executed_sql)


def test_delete_trip_rejected_when_deadline_has_passed_no_db_write():
    conn = MagicMock()
    cursor = conn.cursor.return_value
    cursor.fetchone.side_effect = [
        ("CC1", "COST", 2027), ("deptA", "divA", "clA"), None, (date(2020, 1, 1),),
    ]  # trip lookup, cc_dims for lock, lock check (not locked), deadline passed
    scope = _scope()
    result = delete_trip(conn, 7, STALE, "filler@chememan.com", scope)
    assert result.ok is False
    assert result.error == "past_deadline"
    conn.commit.assert_not_called()
    executed_sql = [c.args[0] for c in cursor.execute.call_args_list]
    assert not any("DELETE FROM budget.budget_trip" in s for s in executed_sql)


def test_delete_trip_not_found_is_conflict_not_500():
    conn = MagicMock()
    cursor = conn.cursor.return_value
    cursor.fetchone.side_effect = [None]  # trip lookup finds nothing
    scope = _scope()
    result = delete_trip(conn, 999, STALE, "filler@chememan.com", scope)
    assert result.ok is False
    assert result.error == "conflict"


# ---------------------------------------------------------------------------
# A10 gap close — department-approval lock (ADR-0006/0008/0012/0013)
#
# budget.approval_status is keyed (department, fiscal_year). Non-admin writes
# must be rejected while status is PENDING_APPROVER1/2/3 or APPROVED (only
# Submit/Approve/Reject may move status, ADR-0013). Admin always bypasses
# (ADR-0012). DRAFT/REJECTED/no-row = not locked — already proven implicitly
# by every "happy path" test above (the lock-check fetchone there mocks
# `None` = no approval_status row = not locked).
# ---------------------------------------------------------------------------

LOCKED_STATUSES = [PENDING_APPROVER1, PENDING_APPROVER2, PENDING_APPROVER3, APPROVED]


def test_lookup_department_approval_status_query_shape():
    from app.write_model import _lookup_department_approval_status

    conn = MagicMock()
    cursor = conn.cursor.return_value
    cursor.fetchone.return_value = (PENDING_APPROVER2,)
    status = _lookup_department_approval_status(conn, "deptA", 2027)
    assert status == PENDING_APPROVER2
    sql_text = cursor.execute.call_args.args[0]
    assert "budget.approval_status" in sql_text
    assert "department = ?" in sql_text
    assert "fiscal_year = ?" in sql_text


@pytest.mark.parametrize("locked_status", LOCKED_STATUSES)
def test_pending_row_rejected_when_department_is_locked(locked_status):
    conn = MagicMock()
    cursor = conn.cursor.return_value
    cursor.fetchone.side_effect = [
        ("Bank Charge", "Bank Charge Fee"), ("deptA", "divA", "clA"),  # dims
        (locked_status,),  # approval_status row -> locked
    ]
    scope = _scope()
    results = save_pending_rows(conn, [_row(m01=100, expected_updated_at=None)], "filler@chememan.com", scope)
    assert results[0].ok is False
    assert results[0].error == "department_locked"
    conn.commit.assert_not_called()
    executed_sql = [c.args[0] for c in cursor.execute.call_args_list]
    assert not any(
        "INSERT INTO budget.pending_budget" in s or "UPDATE budget.pending_budget" in s for s in executed_sql
    )


def test_pending_row_allowed_when_department_status_is_rejected():
    conn = MagicMock()
    cursor = conn.cursor.return_value
    cursor.fetchone.side_effect = [
        ("Bank Charge", "Bank Charge Fee"), ("deptA", "divA", "clA"),
        (REJECTED,),  # approval_status row -> REJECTED is edit-like DRAFT, not locked
        None,  # deadline check -> open
    ]
    scope = _scope()
    results = save_pending_rows(conn, [_row(m01=100, expected_updated_at=None)], "filler@chememan.com", scope)
    assert results[0].ok is True


def test_pending_row_admin_bypasses_department_lock_and_never_queries_it():
    conn = MagicMock()
    cursor = conn.cursor.return_value
    cursor.fetchone.side_effect = [(1,), ("Bank Charge", "Bank Charge Fee"), ("deptA", "divA", "clA")]
    scope = _admin_scope()
    results = save_pending_rows(conn, [_row(cost_center="ANY-CC", m01=100)], "admin@chememan.com", scope)
    assert results[0].ok is True
    executed_sql = [c.args[0] for c in cursor.execute.call_args_list]
    assert not any("approval_status" in s for s in executed_sql)


def test_two_pending_rows_one_department_locked_blocks_independently():
    """Batch semantics: one row's department_locked error must never block
    another row targeting a different, open department (never-cut)."""
    conn = MagicMock()
    cursor = conn.cursor.return_value
    cursor.fetchone.side_effect = [
        ("Bank Charge", "Bank Charge Fee"), ("deptA", "divA", "clA"), (APPROVED,),  # row A: locked
        ("Bank Charge", "Bank Charge Fee"), ("deptB", "divB", "clB"), None, None,   # row B: not locked, open
    ]
    scope = _scope(fill_cost_centers=["CC1", "CC2"], see_cost_centers=["CC1", "CC2"])
    row_a = _row(cost_center="CC1", gl_account="GLA", m01=10, expected_updated_at=None)
    row_b = _row(cost_center="CC2", gl_account="GLB", m01=20, expected_updated_at=None)
    results = save_pending_rows(conn, [row_a, row_b], "filler@chememan.com", scope)
    assert results[0].ok is False
    assert results[0].error == "department_locked"
    assert results[1].ok is True


def test_pending_row_unknown_department_mapping_is_not_locked():
    """Unknown CC->department mapping (department resolves to None): treated
    as 'not locked' rather than inventing a new failure mode. Cannot
    currently be reached by a non-admin in practice (their Fill scope is
    itself derived from dbo.cc_filler_map, so any cost_center they may
    address already has a department) — this locks in the chosen fail-open
    behavior for that edge (mirrors is_post_deadline's own missing-row-is-
    OPEN policy elsewhere in this module)."""
    conn = MagicMock()
    cursor = conn.cursor.return_value
    cursor.fetchone.side_effect = [
        ("Bank Charge", "Bank Charge Fee"), None,  # dims: cc_dims lookup -> no row, department unresolved
        None,  # deadline check -> open (department=None short-circuits the lock check with NO extra query)
    ]
    scope = _scope()
    results = save_pending_rows(conn, [_row(m01=100, expected_updated_at=None)], "filler@chememan.com", scope)
    assert results[0].ok is True
    executed_sql = [c.args[0] for c in cursor.execute.call_args_list]
    assert not any("approval_status" in s for s in executed_sql), (
        "department already known to be unresolved (None) — must not re-query dbo.cc_filler_map"
    )


@pytest.mark.parametrize("locked_status", LOCKED_STATUSES)
def test_detail_line_rejected_when_department_is_locked(locked_status):
    conn = MagicMock()
    cursor = conn.cursor.return_value
    cursor.fetchone.side_effect = [
        ("Entertainment", "Entertainment Expense"), ("deptA", "divA", "clA"),  # dims
        (locked_status,),  # approval_status row -> locked
    ]
    scope = _scope()
    results = save_detail_lines(conn, [_detail(m01=1000)], "filler@chememan.com", scope)
    assert results[0].ok is False
    assert results[0].error == "department_locked"
    conn.commit.assert_not_called()


@pytest.mark.parametrize("locked_status", LOCKED_STATUSES)
def test_trip_create_rejected_when_department_is_locked(locked_status):
    conn = MagicMock()
    cursor = conn.cursor.return_value
    cursor.fetchone.side_effect = [
        ("Somchai", "Manager"),        # traveler lookup
        (500, None, None),              # per_diem_rate (domestic=500)
        ("deptA", "divA", "clA"),        # cc_dims lookup for department-lock check
        (locked_status,),                # approval_status row -> locked
    ]
    scope = _scope()
    results = save_trip(conn, [_trip(days=10, country_group=1)], "filler@chememan.com", scope)
    assert results[0].ok is False
    assert results[0].error == "department_locked"
    conn.commit.assert_not_called()
    executed_sql = [c.args[0] for c in cursor.execute.call_args_list]
    assert not any("INSERT INTO budget.budget_trip" in s for s in executed_sql)


@pytest.mark.parametrize("locked_status", LOCKED_STATUSES)
def test_trip_update_rejected_when_department_is_locked(locked_status):
    conn = MagicMock()
    cursor = conn.cursor.return_value
    cursor.fetchone.side_effect = [
        ("Somchai", "Manager"),
        (500, None, None),
        ("CC1", "COST", 2027),            # old-trip lookup
        ("deptA", "divA", "clA"),          # cc_dims lookup for department-lock check
        (locked_status,),                  # approval_status row -> locked
    ]
    scope = _scope()
    results = save_trip(
        conn, [_trip(trip_id=1, side="SGA", days=10, country_group=1, expected_updated_at=STALE)],
        "filler@chememan.com", scope,
    )
    assert results[0].ok is False
    assert results[0].error == "department_locked"
    conn.commit.assert_not_called()
    executed_sql = [c.args[0] for c in cursor.execute.call_args_list]
    assert not any(s.strip().startswith("UPDATE budget.budget_trip") for s in executed_sql)


@pytest.mark.parametrize("locked_status", LOCKED_STATUSES)
def test_delete_detail_line_rejected_when_department_is_locked(locked_status):
    conn = MagicMock()
    cursor = conn.cursor.return_value
    cursor.fetchone.side_effect = [
        ("CC1", "5211900030", 2027),      # owner lookup
        ("deptA", "divA", "clA"),          # cc_dims lookup for department-lock check
        (locked_status,),                  # approval_status row -> locked
    ]
    scope = _scope()
    result = delete_detail_line(conn, 5, STALE, "filler@chememan.com", scope)
    assert result.ok is False
    assert result.error == "department_locked"
    conn.commit.assert_not_called()
    executed_sql = [c.args[0] for c in cursor.execute.call_args_list]
    assert not any("DELETE FROM budget.pending_budget_detail" in s for s in executed_sql)


@pytest.mark.parametrize("locked_status", LOCKED_STATUSES)
def test_delete_trip_rejected_when_department_is_locked(locked_status):
    conn = MagicMock()
    cursor = conn.cursor.return_value
    cursor.fetchone.side_effect = [
        ("CC1", "COST", 2027),            # trip lookup
        ("deptA", "divA", "clA"),          # cc_dims lookup for department-lock check
        (locked_status,),                  # approval_status row -> locked
    ]
    scope = _scope()
    result = delete_trip(conn, 7, STALE, "filler@chememan.com", scope)
    assert result.ok is False
    assert result.error == "department_locked"
    conn.commit.assert_not_called()
    executed_sql = [c.args[0] for c in cursor.execute.call_args_list]
    assert not any("DELETE FROM budget.budget_trip" in s for s in executed_sql)


def test_delete_trip_admin_bypasses_department_lock_and_never_queries_it():
    conn = MagicMock()
    cursor = conn.cursor.return_value
    one_off = iter([
        ("ANY-CC", "COST", 2027),  # trip lookup
        (1,),                       # admin CC-existence check (_ensure_write_scope's admin branch)
    ])
    dims_cycle = itertools.cycle([("Bank Charge", "Bank Charge Fee"), ("deptA", "divA", "clA")])

    def _fetchone_side_effect():
        try:
            return next(one_off)
        except StopIteration:
            return next(dims_cycle)

    cursor.fetchone.side_effect = _fetchone_side_effect
    cursor.rowcount = 1
    scope = _admin_scope()
    result = delete_trip(conn, 7, STALE, "admin@chememan.com", scope)
    assert result.ok is True
    executed_sql = [c.args[0] for c in cursor.execute.call_args_list]
    assert not any("approval_status" in s for s in executed_sql)
    assert not any("submission_deadline" in s for s in executed_sql)


# ---------------------------------------------------------------------------
# client_token idempotency (POST /budget/trip create path only) — a network
# retry / double-click must NEVER create a duplicate trip or double-count its
# per-diem into the parent cell. Dedup key = (client_token, _user) ONLY — a
# hard unique on trip content is wrong (two genuinely-identical trips are
# legitimate business data).
# ---------------------------------------------------------------------------

def _stored_trip_row(**overrides):
    """Build the replay row in whatever order `_TRIP_REPLAY_COLUMNS`
    declares — robust to column additions (e.g. `project`)."""
    from app.write_model import _TRIP_REPLAY_COLUMNS

    base = dict(
        trip_id=42, cost_center="CC1", fiscal_year=2027, traveler_empcode="E1",
        traveler_name="Somchai", position="Manager", destination="Bangkok",
        country_group=1, days=10, travel_months="03", purpose="site visit",
        project=None, side="COST", _updated_at=STALE,
    )
    base.update(overrides)
    return tuple(base[c] for c in _TRIP_REPLAY_COLUMNS)


_STORED_TRIP_ROW = _stored_trip_row()


def test_trip_input_accepts_client_token_defaulting_to_none():
    assert _trip().client_token is None
    assert _trip(client_token="a" * 64).client_token == "a" * 64


def test_trip_input_rejects_client_token_over_64_chars():
    with pytest.raises(ValidationError):
        _trip(client_token="a" * 65)


def test_trip_create_same_token_replays_existing_trip_no_insert_no_per_diem_readd():
    """Retry-after-lost-response: the token already has a row for this user ->
    return THAT trip (200), never a second row, never a per-diem re-add (the
    parent cell keeps the original single amount)."""
    conn = MagicMock()
    cursor = conn.cursor.return_value
    cursor.fetchone.side_effect = [
        _STORED_TRIP_ROW,   # dedup SELECT by (client_token, _user) -> HIT
        (500, None, None),   # per_diem_rate lookup for the replay recompute
    ]
    scope = _scope()
    results = save_trip(conn, [_trip(client_token="tok-1", days=10)], "filler@chememan.com", scope)
    result = results[0]
    assert result.ok is True
    assert result.trip.trip_id == 42  # the ORIGINAL trip, not a new one
    assert result.trip.per_diem_months["m03"] == 5000.0  # 10 days x 500 THB, single month
    executed_sql = [c.args[0] for c in cursor.execute.call_args_list]
    assert not any("INSERT INTO budget.budget_trip" in s for s in executed_sql)
    assert not any("pending_budget" in s for s in executed_sql)  # no per-diem line, no parent recompute
    conn.commit.assert_not_called()  # replay is a pure read


def test_trip_create_replay_returns_the_stored_values_not_the_retry_payload():
    """If the user edited fields between the lost response and the retry, the
    reply must reflect the STORED row — edits go through a normal PUT using
    the lock token this response provides."""
    conn = MagicMock()
    cursor = conn.cursor.return_value
    cursor.fetchone.side_effect = [_STORED_TRIP_ROW, (500, None, None)]
    scope = _scope()
    results = save_trip(
        conn, [_trip(client_token="tok-1", days=7, destination="Chiangmai")], "filler@chememan.com", scope
    )
    trip = results[0].trip
    assert trip.days == 10                 # stored, not the retry's 7
    assert trip.destination == "Bangkok"   # stored, not the retry's edit
    assert trip.updated_at == STALE        # the stored lock token, usable for a follow-up PUT


def test_trip_create_with_token_miss_inserts_with_the_token():
    conn = MagicMock()
    cursor = conn.cursor.return_value
    cursor.fetchone.side_effect = [
        None,                      # dedup SELECT -> no row yet
        ("Somchai", "Manager"),    # traveler lookup
        (500, None, None),          # per_diem_rate
        ("deptA", "divA", "clA"),   # cc_dims for department-lock check
        None,                       # department-lock check -> not locked
        None,                       # deadline check -> open
        None,                       # existing trip-detail lookup -> INSERT
        ("Bank Charge", "Bank Charge Fee"), ("deptA", "divA", "clA"),
        (0, 0, 5000.0, 0, 0, 0, 0, 0, 0, 0, 0, 0),
    ]
    cursor.fetchval.return_value = 43
    scope = _scope()
    results = save_trip(conn, [_trip(client_token="tok-2")], "filler@chememan.com", scope)
    assert results[0].ok is True
    insert_calls = [c for c in cursor.execute.call_args_list if "INSERT INTO budget.budget_trip" in c.args[0]]
    assert len(insert_calls) == 1
    assert "client_token" in insert_calls[0].args[0]
    assert "tok-2" in insert_calls[0].args[1:]


def test_trip_create_without_token_keeps_the_legacy_insert_shape():
    """No token (older client / null) -> byte-identical legacy INSERT: no
    client_token column referenced anywhere, current behavior preserved
    (works against the un-migrated live table)."""
    conn = MagicMock()
    cursor = conn.cursor.return_value
    cursor.fetchone.side_effect = [
        ("Somchai", "Manager"), (500, None, None),
        ("deptA", "divA", "clA"), None, None, None,
        ("Bank Charge", "Bank Charge Fee"), ("deptA", "divA", "clA"),
        (0,) * 12,
    ]
    cursor.fetchval.return_value = 44
    scope = _scope()
    results = save_trip(conn, [_trip()], "filler@chememan.com", scope)
    assert results[0].ok is True
    executed_sql = [c.args[0] for c in cursor.execute.call_args_list]
    assert not any("client_token" in s for s in executed_sql)


def test_trip_create_concurrent_unique_violation_returns_the_existing_trip():
    """True concurrent double-submit: both requests pass the dedup SELECT
    before either inserts; the loser's INSERT hits the filtered UNIQUE index
    -> catch, re-SELECT by token, return the winner's trip (200)."""
    conn = MagicMock()
    cursor = conn.cursor.return_value
    cursor.fetchone.side_effect = [
        None,                      # dedup SELECT -> no row yet (both raced past this)
        ("Somchai", "Manager"),    # traveler lookup
        (500, None, None),          # per_diem_rate
        ("deptA", "divA", "clA"),   # cc_dims for department-lock check
        None,                       # department-lock check -> not locked
        None,                       # deadline check -> open
        _STORED_TRIP_ROW,           # re-SELECT by token after the violation -> winner's row
        (500, None, None),          # per_diem_rate for the replay recompute
    ]

    def _execute_side_effect(sql, *params):
        if "INSERT INTO budget.budget_trip" in sql:
            raise pyodbc.IntegrityError("23000", "unique index ux_trip_client_token_user violation")
        return None

    cursor.execute.side_effect = _execute_side_effect
    scope = _scope()
    results = save_trip(conn, [_trip(client_token="tok-1", days=10)], "filler@chememan.com", scope)
    result = results[0]
    assert result.ok is True
    assert result.trip.trip_id == 42
    conn.rollback.assert_called()   # failed INSERT discarded before the re-SELECT
    conn.commit.assert_not_called()


def test_trip_create_integrity_error_reraised_when_token_lookup_finds_nothing():
    """An IntegrityError that is NOT the token dedup (re-SELECT finds no row)
    must propagate — never silently swallowed as a fake success."""
    conn = MagicMock()
    cursor = conn.cursor.return_value
    cursor.fetchone.side_effect = [
        None, ("Somchai", "Manager"), (500, None, None),
        ("deptA", "divA", "clA"), None, None,
        None,  # re-SELECT by token after the violation -> still nothing
    ]

    def _execute_side_effect(sql, *params):
        if "INSERT INTO budget.budget_trip" in sql:
            raise pyodbc.IntegrityError("23000", "some other constraint")
        return None

    cursor.execute.side_effect = _execute_side_effect
    scope = _scope()
    with pytest.raises(pyodbc.IntegrityError):
        save_trip(conn, [_trip(client_token="tok-1")], "filler@chememan.com", scope)


def test_trip_create_integrity_error_without_token_propagates_uncaught():
    conn = MagicMock()
    cursor = conn.cursor.return_value
    cursor.fetchone.side_effect = [
        ("Somchai", "Manager"), (500, None, None),
        ("deptA", "divA", "clA"), None, None,
    ]

    def _execute_side_effect(sql, *params):
        if "INSERT INTO budget.budget_trip" in sql:
            raise pyodbc.IntegrityError("23000", "PK violation")
        return None

    cursor.execute.side_effect = _execute_side_effect
    scope = _scope()
    with pytest.raises(pyodbc.IntegrityError):
        save_trip(conn, [_trip()], "filler@chememan.com", scope)


def test_trip_token_dedup_select_is_scoped_to_the_calling_user():
    """Cross-user guard: the dedup SELECT must filter on _user as well — one
    user's token can never return (or block on) another user's trip."""
    conn = MagicMock()
    cursor = conn.cursor.return_value
    cursor.fetchone.side_effect = [_STORED_TRIP_ROW, (500, None, None)]
    scope = _scope()
    save_trip(conn, [_trip(client_token="tok-1")], "filler@chememan.com", scope)
    dedup_sql, dedup_params = cursor.execute.call_args_list[0].args[0], cursor.execute.call_args_list[0].args[1:]
    assert "client_token = ?" in dedup_sql
    assert "_user = ?" in dedup_sql
    assert "tok-1" in dedup_params
    assert "filler@chememan.com" in dedup_params


def test_trip_update_ignores_client_token_never_dedups_an_edit():
    """PUT (trip_id set) must never dedup: an edit with a token neither runs
    the dedup SELECT nor writes client_token."""
    conn = MagicMock()
    cursor = conn.cursor.return_value
    cursor.fetchone.side_effect = [
        ("Somchai", "Manager"), (500, None, None),
        ("CC1", "COST", 2027),      # old-trip lookup (side-flip capture)
        ("deptA", "divA", "clA"),   # cc_dims for department-lock check
        None,                        # department-lock check -> not locked
        None,                        # deadline check -> open
        None,                        # existing trip-detail lookup -> INSERT
        ("Bank Charge", "Bank Charge Fee"), ("deptA", "divA", "clA"),
        (None,),                     # echo fix: project not sent -> read back the actually-stored value (none here)
    ]
    cursor.rowcount = 1
    scope = _scope()
    results = save_trip(
        conn, [_trip(trip_id=42, client_token="tok-1", expected_updated_at=STALE)], "filler@chememan.com", scope
    )
    assert results[0].ok is True
    executed_sql = [c.args[0] for c in cursor.execute.call_args_list]
    assert not any("client_token" in s for s in executed_sql)


# ---------------------------------------------------------------------------
# TripInput.project — free-text project name on the trip header (Excel
# template col F). Persisted with the client_token conditional-column trick:
# the column is referenced ONLY when a non-null value is supplied, so a
# project-less request stays byte-identical to the pre-migration SQL
# (deploy-safe before setup/migrate_budget_trip_project.py runs).
# ---------------------------------------------------------------------------

def test_trip_input_accepts_project_defaulting_to_none():
    assert _trip().project is None
    assert _trip(project="ERP rollout").project == "ERP rollout"


def test_trip_input_rejects_project_over_200_chars():
    with pytest.raises(ValidationError):
        _trip(project="a" * 201)


def _trip_create_fetchone_sequence():
    """The legacy (token-less, project-less) create path's mock sequence —
    same shape as test_trip_create_without_token_keeps_the_legacy_insert_shape."""
    return [
        ("Somchai", "Manager"), (500, None, None),
        ("deptA", "divA", "clA"), None, None, None,
        ("Bank Charge", "Bank Charge Fee"), ("deptA", "divA", "clA"),
        (0,) * 12,
    ]


def test_trip_create_with_project_includes_project_column():
    conn = MagicMock()
    cursor = conn.cursor.return_value
    cursor.fetchone.side_effect = _trip_create_fetchone_sequence()
    cursor.fetchval.return_value = 45
    scope = _scope()
    results = save_trip(conn, [_trip(project="ERP rollout")], "filler@chememan.com", scope)
    assert results[0].ok is True
    insert_calls = [c for c in cursor.execute.call_args_list if "INSERT INTO budget.budget_trip" in c.args[0]]
    assert len(insert_calls) == 1
    assert "project" in insert_calls[0].args[0]
    assert "ERP rollout" in insert_calls[0].args[1:]
    assert results[0].trip.project == "ERP rollout"


def test_trip_create_without_project_keeps_the_legacy_insert_shape():
    """No project -> NO 'project' referenced in ANY SQL (works against the
    un-migrated live table)."""
    conn = MagicMock()
    cursor = conn.cursor.return_value
    cursor.fetchone.side_effect = _trip_create_fetchone_sequence()
    cursor.fetchval.return_value = 46
    scope = _scope()
    results = save_trip(conn, [_trip()], "filler@chememan.com", scope)
    assert results[0].ok is True
    assert results[0].trip.project is None
    executed_sql = [c.args[0] for c in cursor.execute.call_args_list]
    assert not any("project" in s for s in executed_sql)


def _trip_update_fetchone_sequence():
    """The update path's mock sequence — same shape as
    test_trip_update_ignores_client_token_never_dedups_an_edit. Ends right
    after the parent-cell recompute (which never issues its own SELECT when
    `cursor.rowcount` mocks a matched row) — callers append one more item
    only if their scenario triggers an extra read after that (e.g. the
    project echo-fix lookup when `project` is None)."""
    return [
        ("Somchai", "Manager"), (500, None, None),
        ("CC1", "COST", 2027),      # old-trip lookup (side-flip capture)
        ("deptA", "divA", "clA"),   # cc_dims for department-lock check
        None,                        # department-lock check -> not locked
        None,                        # deadline check -> open
        None,                        # existing trip-detail lookup -> INSERT
        ("Bank Charge", "Bank Charge Fee"), ("deptA", "divA", "clA"),
    ]


def test_trip_update_with_project_sets_project_column():
    conn = MagicMock()
    cursor = conn.cursor.return_value
    cursor.fetchone.side_effect = _trip_update_fetchone_sequence()
    cursor.rowcount = 1
    scope = _scope()
    results = save_trip(
        conn, [_trip(trip_id=42, project="ERP rollout", expected_updated_at=STALE)], "filler@chememan.com", scope
    )
    assert results[0].ok is True
    update_calls = [c for c in cursor.execute.call_args_list if "UPDATE budget.budget_trip" in c.args[0]]
    assert len(update_calls) == 1
    assert "project = ?" in update_calls[0].args[0]
    assert "ERP rollout" in update_calls[0].args[1:]
    assert results[0].trip.project == "ERP rollout"


def test_trip_update_with_empty_project_clears_the_column():
    """Explicit "" (NOT None) means "clear the field" — distinct from
    omitting the field (None = leave untouched). The frontend now always
    sends a concrete string when the user edits the project input, never
    null (see TripManager.tsx), so this is the normal "user cleared it"
    request shape."""
    conn = MagicMock()
    cursor = conn.cursor.return_value
    cursor.fetchone.side_effect = _trip_update_fetchone_sequence()
    cursor.rowcount = 1
    scope = _scope()
    results = save_trip(
        conn, [_trip(trip_id=42, project="", expected_updated_at=STALE)], "filler@chememan.com", scope
    )
    assert results[0].ok is True
    update_calls = [c for c in cursor.execute.call_args_list if "UPDATE budget.budget_trip" in c.args[0]]
    assert len(update_calls) == 1
    assert "project = ?" in update_calls[0].args[0]
    assert "" in update_calls[0].args[1:]
    assert results[0].trip.project == ""


def test_trip_update_without_project_keeps_the_legacy_update_shape():
    """No project sent (None) -> the WRITE itself stays legacy-shaped (never
    references `project`, pre-migration-safe) — but the echoed TripState
    must still reflect the ACTUAL stored value, not just parrot back the
    request's None (that used to lie: DB kept "Legacy Project", response
    claimed null)."""
    conn = MagicMock()
    cursor = conn.cursor.return_value
    cursor.fetchone.side_effect = _trip_update_fetchone_sequence() + [("Legacy Project",)]
    cursor.rowcount = 1
    scope = _scope()
    results = save_trip(
        conn, [_trip(trip_id=42, expected_updated_at=STALE)], "filler@chememan.com", scope
    )
    assert results[0].ok is True
    update_calls = [c for c in cursor.execute.call_args_list if "UPDATE budget.budget_trip" in c.args[0]]
    assert len(update_calls) == 1
    assert "project" not in update_calls[0].args[0]
    assert results[0].trip.project == "Legacy Project"


def test_trip_create_replay_returns_stored_project():
    """A token replay must return the STORED project (like every other
    stored field), and _TRIP_REPLAY_COLUMNS must therefore carry it."""
    conn = MagicMock()
    cursor = conn.cursor.return_value
    cursor.fetchone.side_effect = [_stored_trip_row(project="ERP rollout"), (500, None, None)]
    scope = _scope()
    results = save_trip(conn, [_trip(client_token="tok-1")], "filler@chememan.com", scope)
    assert results[0].ok is True
    assert results[0].trip.project == "ERP rollout"


# ---------------------------------------------------------------------------
# Grid trailing "ลบ" column — delete_pending_row: a generic delete of one
# manually-added Pending row by its natural key (cost_center, gl_account,
# fiscal_year), cascading any special-GL detail lines it owns. Same guard
# chain/shape as delete_detail_line/delete_trip above, but — unlike those —
# resolves NOTHING from an id first: cost_center/gl_account/fiscal_year come
# straight from the caller, exactly like save_pending_rows already does.
# ---------------------------------------------------------------------------

def test_delete_pending_row_forbidden_when_outside_fill_scope_no_db_call():
    conn = MagicMock()
    scope = _scope(fill_cost_centers=[], see_cost_centers=["CC1"])  # See-only, not Fill
    result = delete_pending_row(conn, "CC1", "GL1", 2027, STALE, "filler@chememan.com", scope)
    assert result.ok is False
    assert result.error == "forbidden"
    conn.cursor.assert_not_called()


def test_delete_pending_row_success_cascades_detail_lines_and_commits_once():
    conn = MagicMock()
    cursor = conn.cursor.return_value
    cursor.fetchone.side_effect = [
        ("deptA", "divA", "clA"),  # cc_dims lookup for department-lock check
        None,                       # department-lock check -> no approval_status row, not locked
        None,                       # deadline check -> no row, open
    ]
    cursor.rowcount = 1
    scope = _scope()
    result = delete_pending_row(conn, "CC1", "5211900030", 2027, STALE, "filler@chememan.com", scope)
    assert result.ok is True
    assert result.cost_center == "CC1"
    assert result.gl_account == "5211900030"
    assert result.fiscal_year == 2027
    assert conn.commit.call_count == 1

    executed_sql = [c.args[0] for c in cursor.execute.call_args_list]
    assert any(s.strip().startswith("DELETE FROM budget.pending_budget_detail") for s in executed_sql)
    assert any(s.strip().startswith("DELETE FROM budget.pending_budget ") for s in executed_sql)

    # commit-order rule: both DELETEs happen before commit (db.py has no
    # implicit commit — a commit placed earlier would silently discard them).
    delete_idx = parent_idx = commit_idx = None
    for i, call in enumerate(conn.mock_calls):
        name, args = call[0], call[1]
        if name == "commit":
            commit_idx = i
        elif name.endswith("execute") and args:
            if args[0].strip().startswith("DELETE FROM budget.pending_budget_detail"):
                delete_idx = i
            elif args[0].strip().startswith("DELETE FROM budget.pending_budget "):
                parent_idx = i
    assert delete_idx is not None, "detail-line cascade DELETE not found"
    assert parent_idx is not None, "parent-row DELETE not found"
    assert commit_idx is not None
    assert delete_idx < commit_idx
    assert parent_idx < commit_idx


def test_delete_pending_row_stale_token_is_conflict_no_commit():
    conn = MagicMock()
    cursor = conn.cursor.return_value
    cursor.fetchone.side_effect = [
        ("deptA", "divA", "clA"),
        None,
        None,
    ]
    cursor.rowcount = 0  # parent DELETE matches nothing -> stale token
    scope = _scope()
    result = delete_pending_row(conn, "CC1", "GL1", 2027, STALE, "filler@chememan.com", scope)
    assert result.ok is False
    assert result.error == "conflict"
    conn.commit.assert_not_called()


def test_delete_pending_row_rejected_when_deadline_has_passed_no_db_write():
    conn = MagicMock()
    cursor = conn.cursor.return_value
    cursor.fetchone.side_effect = [
        ("deptA", "divA", "clA"),
        None,
        (date(2020, 1, 1),),  # dbo.submission_deadline -> already passed
    ]
    scope = _scope()
    result = delete_pending_row(conn, "CC1", "GL1", 2027, STALE, "filler@chememan.com", scope)
    assert result.ok is False
    assert result.error == "past_deadline"
    conn.commit.assert_not_called()
    executed_sql = [c.args[0] for c in cursor.execute.call_args_list]
    assert not any("DELETE FROM budget.pending_budget" in s for s in executed_sql)


@pytest.mark.parametrize("locked_status", LOCKED_STATUSES)
def test_delete_pending_row_rejected_when_department_is_locked(locked_status):
    conn = MagicMock()
    cursor = conn.cursor.return_value
    cursor.fetchone.side_effect = [
        ("deptA", "divA", "clA"),
        (locked_status,),  # approval_status row -> locked
    ]
    scope = _scope()
    result = delete_pending_row(conn, "CC1", "GL1", 2027, STALE, "filler@chememan.com", scope)
    assert result.ok is False
    assert result.error == "department_locked"
    conn.commit.assert_not_called()
    executed_sql = [c.args[0] for c in cursor.execute.call_args_list]
    assert not any("DELETE FROM budget.pending_budget" in s for s in executed_sql)


def test_delete_pending_row_admin_bypasses_deadline_and_department_lock():
    conn = MagicMock()
    cursor = conn.cursor.return_value
    cursor.fetchone.side_effect = [(1,)]  # admin CC-existence check only (_ensure_write_scope)
    cursor.rowcount = 1
    scope = _admin_scope()
    result = delete_pending_row(conn, "ANY-CC", "GL1", 2027, STALE, "admin@chememan.com", scope)
    assert result.ok is True
    executed_sql = [c.args[0] for c in cursor.execute.call_args_list]
    assert not any("approval_status" in s for s in executed_sql)
    assert not any("submission_deadline" in s for s in executed_sql)
