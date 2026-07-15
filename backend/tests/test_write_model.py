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
- total_year stays in sync with SUM(months); parent cell == SUM(detail)
"""
from datetime import datetime, timezone
from unittest.mock import MagicMock

import pyodbc
import pytest
from pydantic import ValidationError

from app.per_diem import MissingFxRateError, MissingPerDiemRateError
from app.rls import Scope
from app.write_model import (
    DetailLineInput,
    ExcludedCostCenterError,
    ForbiddenScopeError,
    NegativeMonthError,
    NotSpecialGlError,
    PendingRowInput,
    PerDiemDirectEditError,
    RowConflictError,
    SpecialGlDirectEditError,
    TravelerNotFoundError,
    TripInput,
    TripNotFoundError,
    TripSideMismatchError,
    UnknownGlAccountError,
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
        ("Bank Charge",), ("deptA", "divA", "clA"),
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


def test_special_gl_cell_cannot_be_edited_directly():
    conn = MagicMock()
    cursor = conn.cursor.return_value
    cursor.fetchone.side_effect = [("Entertainment",), ("deptA", "divA", "clA")]
    scope = _scope()
    results = save_pending_rows(conn, [_row(gl_account="5211900030")], "filler@chememan.com", scope)
    assert results[0].error == "special_gl_direct_edit"


def test_new_row_insert_succeeds_and_total_year_is_sum_of_months():
    conn = MagicMock()
    cursor = conn.cursor.return_value
    cursor.fetchone.side_effect = [("Bank Charge",), ("deptA", "divA", "clA")]
    scope = _scope()
    row = _row(m01=100, m02=200, expected_updated_at=None)
    results = save_pending_rows(conn, [row], "filler@chememan.com", scope)
    result = results[0]
    assert result.ok is True
    assert result.row.total_year == 300
    assert result.row.gl_group == "Bank Charge"
    assert result.row.gl_name is None  # known gap — never invented
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
    cursor.fetchone.side_effect = [("Bank Charge",), ("deptA", "divA", "clA")]
    cursor.execute.side_effect = [None, None, pyodbc.IntegrityError("23000", "PK violation")]
    scope = _scope()
    results = save_pending_rows(conn, [_row(expected_updated_at=None)], "filler@chememan.com", scope)
    assert results[0].error == "conflict"
    conn.commit.assert_not_called()


def test_stale_optimistic_lock_returns_conflict_and_does_not_write():
    conn = MagicMock()
    cursor = conn.cursor.return_value
    cursor.fetchone.side_effect = [("Bank Charge",), ("deptA", "divA", "clA")]
    cursor.rowcount = 0  # WHERE _updated_at = ? matched nothing -> stale
    scope = _scope()
    results = save_pending_rows(conn, [_row(expected_updated_at=STALE)], "filler@chememan.com", scope)
    assert results[0].error == "conflict"
    conn.commit.assert_not_called()


def test_update_succeeds_when_lock_matches():
    conn = MagicMock()
    cursor = conn.cursor.return_value
    cursor.fetchone.side_effect = [("Bank Charge",), ("deptA", "divA", "clA")]
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
        ("Bank Charge",), ("deptA", "divA", "clA"),  # row A dims
        ("Bank Charge",), ("deptB", "divB", "clB"),  # row B dims
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
    cursor.fetchone.side_effect = [("Bank Charge",), ("deptA", "divA", "clA")]
    cursor.rowcount = 0
    scope = _scope()
    results = save_pending_rows(conn, [_row(expected_updated_at=STALE)], "filler@chememan.com", scope)
    assert results[0].error == "conflict"
    conn.rollback.assert_called_once()


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
    cursor.fetchone.side_effect = [("Bank Charge",), ("deptA", "divA", "clA")]
    scope = _scope()
    results = save_detail_lines(conn, [_detail(gl_account="NORMALGL")], "filler@chememan.com", scope)
    assert results[0].error == "not_special_gl"


def test_entertainment_detail_line_insert_succeeds():
    conn = MagicMock()
    cursor = conn.cursor.return_value
    cursor.fetchone.side_effect = [
        ("Entertainment",), ("deptA", "divA", "clA"),  # dims
        (1000.0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0),        # SUM(...) recompute
    ]
    scope = _scope()
    results = save_detail_lines(conn, [_detail(m01=1000)], "filler@chememan.com", scope)
    assert results[0].ok is True
    conn.commit.assert_called_once()


def test_entertainment_detail_line_invalid_meta_rejected():
    conn = MagicMock()
    cursor = conn.cursor.return_value
    cursor.fetchone.side_effect = [("Entertainment",), ("deptA", "divA", "clA")]
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
    cursor.fetchone.side_effect = [("Travelling Expense",), ("deptA", "divA", "clA")]
    scope = _scope()
    results = save_detail_lines(
        conn, [_detail(gl_account="5210400010", trip_id=1, meta_json=None)], "filler@chememan.com", scope,
    )
    assert results[0].error == "per_diem_direct_edit"


def test_trip_not_found_for_a_referenced_trip_id():
    conn = MagicMock()
    cursor = conn.cursor.return_value
    cursor.fetchone.side_effect = [("Travelling Expense",), ("deptA", "divA", "clA"), None]
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
        ("Travelling Expense",), ("deptA", "divA", "clA"),
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
        ("Travelling Expense",), ("deptA", "divA", "clA"),  # dims
        ("CC1", "COST", 2027),                                 # trip row: cost_center, side, fiscal_year
        (500.0, *([0.0] * 11)),                                # SUM(...) recompute
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
    cursor.fetchone.side_effect = [("Entertainment",), ("deptA", "divA", "clA")]
    cursor.rowcount = 0
    scope = _scope()
    results = save_detail_lines(
        conn, [_detail(detail_id=5, expected_updated_at=STALE)], "filler@chememan.com", scope,
    )
    assert results[0].error == "conflict"
    conn.commit.assert_not_called()


def test_detail_line_commit_happens_after_parent_cell_recompute_not_before():
    """A5 gate MUST-FIX 1 (silent data loss): conn.commit() must fire AFTER
    _recompute_parent_cell, not right after the detail-line write. db.py
    closes the connection without an implicit commit, so a commit placed
    before the recompute silently rolled back the parent-cell UPDATE/INSERT
    every time — asserts ORDER, not just call count."""
    conn = MagicMock()
    cursor = conn.cursor.return_value
    cursor.fetchone.side_effect = [
        ("Entertainment",), ("deptA", "divA", "clA"),  # dims
        (1000.0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0),        # SUM(...) recompute
    ]
    scope = _scope()
    results = save_detail_lines(conn, [_detail(m01=1000)], "filler@chememan.com", scope)
    assert results[0].ok is True
    assert conn.commit.call_count == 1

    commit_idx = detail_write_idx = parent_write_idx = None
    for i, call in enumerate(conn.mock_calls):
        name, args = call[0], call[1]
        if name == "commit":
            commit_idx = i
        elif name.endswith("execute") and args:
            sql = args[0]
            if "pending_budget_detail" in sql and ("INSERT INTO" in sql or "UPDATE" in sql):
                detail_write_idx = i
            elif "pending_budget_detail" not in sql and ("INSERT INTO budget.pending_budget" in sql or "UPDATE budget.pending_budget" in sql):
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
        ("Entertainment",), ("deptA", "divA", "clA"),  # dims
        (1000.0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0),        # SUM(...) recompute
    ]
    cursor.fetchval.return_value = 999  # OUTPUT INSERTED.detail_id
    cursor.rowcount = 0  # parent row does not exist yet -> UPDATE matches nothing
    cursor.execute.side_effect = [
        None, None,          # gl_group + cc_dims lookups
        None,                 # detail line INSERT
        None,                 # SUM(...) recompute select
        None,                 # parent UPDATE (rowcount==0 -> falls to INSERT)
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
        ("Entertainment",), ("deptA", "divA", "clA"),  # dims
        (1000.0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0),        # SUM(...) recompute
    ]
    cursor.fetchval.return_value = 999  # OUTPUT INSERTED.detail_id

    call_count = {"n": 0}

    def _execute_side_effect(sql, *params):
        call_count["n"] += 1
        if call_count["n"] == 5:
            cursor.rowcount = 0  # parent UPDATE matches nothing -> falls to INSERT
        elif call_count["n"] == 6:
            raise pyodbc.IntegrityError("23000", "PK violation")  # concurrent INSERT collision
        elif call_count["n"] == 7:
            cursor.rowcount = 1  # retry UPDATE now matches the winner's row -> succeeds
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
    cursor.fetchone.side_effect = [("Travelling Expense",), ("deptA", "divA", "clA")]
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
    cursor.fetchone.side_effect = [("Entertainment",), ("deptA", "divA", "clA")]
    scope = _scope()
    results = save_detail_lines(
        conn, [_detail(gl_account="5211900030", trip_id=1)], "filler@chememan.com", scope,
    )
    assert results[0].error == "invalid_request"
    executed_sql = [c.args[0] for c in cursor.execute.call_args_list]
    assert not any("budget_trip" in s for s in executed_sql), "must not look up an unrelated trip_id"


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
        None,                                             # existing trip-detail lookup -> none, will INSERT
        ("Bank Charge",), ("deptA", "divA", "clA"),        # dims for the per-diem GL
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
        ("Somchai", "Manager"), (500, None, None), None,
        ("Bank Charge",), ("deptA", "divA", "clA"),
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
        (99,),  # an existing per-diem detail line already exists (detail_id=99) — its OLD amount is never read
        ("Bank Charge",), ("deptA", "divA", "clA"),
        (0, 0, 7000.0, 0, 0, 0, 0, 0, 0, 0, 0, 0),  # recompute SUM reflects the freshly-written amount
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


def test_trip_side_flip_deletes_old_gl_line_and_recomputes_old_gl_parent_cell():
    """A5 gate MUST-FIX 4 (NEVER-CUT COST/SGA + parent==SUM): updating a
    trip's side (COST->SGA) changes its per-diem GL. Before this fix the OLD
    GL's line + parent cell were never touched, leaving a ghost amount under
    the old GL forever."""
    conn = MagicMock()
    cursor = conn.cursor.return_value
    cursor.fetchone.side_effect = [
        ("Somchai", "Manager"),                        # 1 traveler lookup
        (500, None, None),                               # 2 per_diem_rate (domestic=500)
        ("CC1", "COST", 2027),                            # 3 OLD trip lookup -> old side was COST
        None,                                              # 4 existing per-diem line under NEW (SGA) gl -> none, INSERT
        ("Bank Charge",), ("deptA", "divA", "clA"),         # 5,6 dims for NEW gl
        (0, 0, 5000.0, 0, 0, 0, 0, 0, 0, 0, 0, 0),         # 7 SUM recompute -> NEW gl m03=5000
        ("Bank Charge",), ("deptA", "divA", "clA"),         # 8,9 dims for OLD gl
        (0,) * 12,                                          # 10 SUM recompute -> OLD gl now zero (line deleted)
    ]
    cursor.rowcount = 1  # trip UPDATE + both parent-cell recomputes all match an existing row
    scope = _scope()
    results = save_trip(
        conn, [_trip(trip_id=1, side="SGA", days=10, country_group=1, expected_updated_at=STALE)],
        "filler@chememan.com", scope,
    )
    result = results[0]
    assert result.ok is True

    executed = [(c.args[0], c.args[1:]) for c in cursor.execute.call_args_list]

    delete_calls = [args for sql, args in executed if "DELETE FROM budget.pending_budget_detail" in sql]
    assert delete_calls, "expected a DELETE of the stale per-diem line under the old (COST) GL"
    assert "5210400010" in delete_calls[0]  # COST per-diem GL — the OLD side

    parent_updates = [
        args for sql, args in executed
        if "UPDATE budget.pending_budget" in sql and "pending_budget_detail" not in sql
    ]
    old_gl_updates = [args for args in parent_updates if "5210400010" in args]
    assert old_gl_updates, "old GL's parent cell was never recomputed — ghost amount would remain"
    assert all(v == 0 for v in old_gl_updates[0][:13]), "old GL's parent cell must be zeroed, not left stale"

    new_gl_inserts = [args for sql, args in executed if "INSERT INTO budget.pending_budget_detail" in sql]
    assert any("6210400010" in args for args in new_gl_inserts)  # SGA per-diem GL — the NEW side
