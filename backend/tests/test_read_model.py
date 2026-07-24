"""Unit tests for app.read_model — board+pending local join, SAP merge, and
RLS filtering for the main budget grid (A4, ADR-0010/0020/0023).

Two layers of tests:
- `fetch_board_pending_rows` — SQL shape (mocked cursor, no live DB).
- `merge_budget_rows` — pure function, no DB at all; this is where the
  never-cut visibility/RLS/editable rules are proven.
"""
from unittest.mock import MagicMock

import pytest

from app.read_model import (
    JOIN_ROW_COLUMNS,
    fetch_board_pending_rows,
    fetch_cc_dims,
    get_budget_grid,
    merge_budget_rows,
)
from app.rls import Scope
from app.sap import SapActualsFetchError


def _blank_join_row(cost_center: str, gl_account: str, **overrides) -> dict:
    """A join row with everything blank except cost/gl identity + presence
    markers, so tests only need to override what they care about."""
    row = {col: None for col in JOIN_ROW_COLUMNS}
    row["cost_center"] = cost_center
    row["gl_account"] = gl_account
    row.update(overrides)
    return row


def _scope(**overrides) -> Scope:
    defaults = dict(
        email="user@chememan.com",
        is_admin=False,
        role="filler",
        fill_cost_centers=[],
        see_cost_centers=[],
    )
    defaults.update(overrides)
    return Scope(**defaults)


# ---------------------------------------------------------------------------
# fetch_board_pending_rows — SQL shape
# ---------------------------------------------------------------------------

def test_join_sql_is_full_outer_join_on_cost_center_and_gl_account():
    conn = MagicMock()
    conn.cursor.return_value.fetchall.return_value = []
    fetch_board_pending_rows(conn, board_year=2026, pending_year=2027)
    sql_text = conn.cursor.return_value.execute.call_args.args[0]
    assert "FULL OUTER JOIN" in sql_text
    assert "dbo.board_budget" in sql_text
    assert "budget.pending_budget" in sql_text
    assert "b.cost_center = p.cost_center" in sql_text
    assert "b.gl_account = p.gl_account" in sql_text


def test_join_sql_passes_board_year_then_pending_year_as_params():
    conn = MagicMock()
    conn.cursor.return_value.fetchall.return_value = []
    fetch_board_pending_rows(conn, board_year=2026, pending_year=2027)
    call = conn.cursor.return_value.execute.call_args
    assert call.args[1] == 2026
    assert call.args[2] == 2027


def test_fetch_board_pending_rows_maps_positional_tuple_to_named_dict():
    conn = MagicMock()
    raw_row = tuple(range(len(JOIN_ROW_COLUMNS)))
    conn.cursor.return_value.fetchall.return_value = [raw_row]
    rows = fetch_board_pending_rows(conn, board_year=2026, pending_year=2027)
    assert rows[0]["cost_center"] == 0  # positional smoke test
    assert set(rows[0].keys()) == set(JOIN_ROW_COLUMNS)


def test_fetch_board_pending_rows_closes_cursor():
    conn = MagicMock()
    conn.cursor.return_value.fetchall.return_value = []
    fetch_board_pending_rows(conn, board_year=2026, pending_year=2027)
    conn.cursor.return_value.close.assert_called_once()


# ---------------------------------------------------------------------------
# fetch_board_pending_rows — SQL-side RLS filter (gate finding #1)
# ---------------------------------------------------------------------------

def test_fetch_board_pending_rows_applies_cost_center_filter_to_both_join_sides():
    """A non-admin's See-scope CC list must be pushed into the SQL as a
    parameterized IN-restriction on BOTH sides of the FULL OUTER JOIN (never
    string-interpolated) — defense-in-depth + avoids over-fetching."""
    conn = MagicMock()
    conn.cursor.return_value.fetchall.return_value = []
    fetch_board_pending_rows(conn, board_year=2026, pending_year=2027, cost_centers=["CC1", "CC2"])
    call = conn.cursor.return_value.execute.call_args
    sql_text = call.args[0]
    assert sql_text.count("cost_center IN (?, ?)") == 2  # one per subquery side
    # board_year, [board CC params], pending_year, [pending CC params]
    assert call.args[1] == 2026
    assert call.args[2] == "CC1"
    assert call.args[3] == "CC2"
    assert call.args[4] == 2027
    assert call.args[5] == "CC1"
    assert call.args[6] == "CC2"


def test_fetch_board_pending_rows_none_cost_centers_omits_in_filter():
    """Admin-wide bypass: `cost_centers=None` must not restrict either side."""
    conn = MagicMock()
    conn.cursor.return_value.fetchall.return_value = []
    fetch_board_pending_rows(conn, board_year=2026, pending_year=2027, cost_centers=None)
    sql_text = conn.cursor.return_value.execute.call_args.args[0]
    assert "cost_center IN" not in sql_text


def test_fetch_board_pending_rows_empty_cost_centers_short_circuits_no_query():
    """Never-cut: an empty See scope must return zero rows WITHOUT executing
    any query — an empty SQL `IN ()` is invalid syntax, so this must
    short-circuit before touching the connection at all."""
    conn = MagicMock()
    rows = fetch_board_pending_rows(conn, board_year=2026, pending_year=2027, cost_centers=[])
    assert rows == []
    conn.cursor.assert_not_called()


# ---------------------------------------------------------------------------
# fetch_cc_dims — batch dims lookup for the D10 department-filter fallback
# ---------------------------------------------------------------------------

def test_fetch_cc_dims_empty_list_short_circuits_no_query():
    conn = MagicMock()
    result = fetch_cc_dims(conn, [])
    assert result == {}
    conn.cursor.assert_not_called()


def test_fetch_cc_dims_returns_one_deterministic_row_per_cc():
    conn = MagicMock()
    conn.cursor.return_value.fetchall.return_value = [("CC1", "deptA", "divA", "clA")]
    result = fetch_cc_dims(conn, ["CC1"])
    assert result == {"CC1": {"department": "deptA", "division": "divA", "c_level": "clA"}}
    sql_text = conn.cursor.return_value.execute.call_args.args[0]
    assert "ORDER BY filler_email" in sql_text  # D11: deterministic tie-break


# ---------------------------------------------------------------------------
# merge_budget_rows — pure merge / visibility / RLS / editable
# ---------------------------------------------------------------------------

def test_row_present_in_all_three_layers():
    join_rows = [
        _blank_join_row(
            "CC1", "GL1",
            board_cost_center="CC1", board_m01=100.0, board_total_year=100.0,
            pending_cost_center="CC1", pending_m01=50.0, pending_total_year=50.0,
        )
    ]
    sap_actuals = {("CC1", "GL1"): {**{c: 0.0 for c in [f"m{m:02d}" for m in range(1, 13)]}, "m01": 200.0, "total_year": 200.0}}
    scope = _scope(fill_cost_centers=["CC1"], see_cost_centers=["CC1"])

    rows = merge_budget_rows(join_rows, sap_actuals, scope)

    assert len(rows) == 1
    row = rows[0]
    assert row.cost_center == "CC1" and row.gl_account == "GL1"
    assert row.sap.m01 == 200.0
    assert row.board.m01 == 100.0
    assert row.pending.m01 == 50.0
    assert row.editable is True


def test_pending_layer_carries_updated_at_optimistic_lock_token():
    """A8 needs the pending row's `_updated_at` token to send back as
    `expected_updated_at` on `PUT /budget/rows` — without it the frontend can
    never edit an EXISTING pending row (only ever create new ones)."""
    from datetime import datetime, timezone

    stamp = datetime(2026, 7, 16, 10, 30, tzinfo=timezone.utc)
    join_rows = [
        _blank_join_row(
            "CC1", "GL1",
            pending_cost_center="CC1", pending_m01=50.0, pending_total_year=50.0,
            pending_updated_at=stamp,
        )
    ]
    scope = _scope(fill_cost_centers=["CC1"], see_cost_centers=["CC1"])

    rows = merge_budget_rows(join_rows, {}, scope)

    assert rows[0].pending.updated_at == stamp


def test_pending_layer_updated_at_is_none_when_no_pending_row_exists():
    join_rows: list[dict] = []
    # Non-zero m01 (not net-zero) keeps this SAP-only row visible under the
    # 2026-07-24 net-zero-hide rule (see below) — an all-zero SAP total here
    # would now be hidden, which is orthogonal to what this test checks.
    sap_actuals = {("CC1", "GL1"): {c: 0.0 for c in [f"m{m:02d}" for m in range(1, 13)]} | {"m01": 100.0, "total_year": 100.0}}
    scope = _scope(fill_cost_centers=["CC1"], see_cost_centers=["CC1"])

    rows = merge_budget_rows(join_rows, sap_actuals, scope)

    assert rows[0].pending.updated_at is None


def test_pending_budget_query_selects_updated_at_column():
    """SQL shape: the pending-side subquery must select `_updated_at` so the
    optimistic-lock token is available to alias as `pending_updated_at`."""
    conn = MagicMock()
    conn.cursor.return_value.fetchall.return_value = []
    fetch_board_pending_rows(conn, board_year=2026, pending_year=2027)
    sql_text = conn.cursor.return_value.execute.call_args.args[0]
    assert "p._updated_at AS pending_updated_at" in sql_text


def test_sap_led_row_with_no_board_or_pending_shows_blank_editable_pending():
    """Never-cut: SAP-only (cc,gl) must still render, with a blank (all-zero)
    Pending layer that IS editable if the CC is in Fill scope — persistence
    per ADR-0010, "no SAP actual" is not the only reason a row exists."""
    join_rows: list[dict] = []
    months = {c: 0.0 for c in [f"m{m:02d}" for m in range(1, 13)]}
    months["m03"] = 999.0
    months["total_year"] = 999.0
    sap_actuals = {("CC1", "GL1"): months}
    scope = _scope(fill_cost_centers=["CC1"], see_cost_centers=["CC1"])

    rows = merge_budget_rows(join_rows, sap_actuals, scope)

    assert len(rows) == 1
    row = rows[0]
    assert row.sap.m03 == 999.0
    assert row.pending.total_year == 0.0
    assert row.editable is True


def test_board_only_row_with_no_sap_no_pending_persists():
    """ADR-0010: an Approved-import new GL/CC with no actual yet must still
    surface (Approved filled, SAP empty, Pending waiting)."""
    join_rows = [
        _blank_join_row("CC1", "GL1", board_cost_center="CC1", board_m06=300.0, board_total_year=300.0)
    ]
    scope = _scope(fill_cost_centers=["CC1"], see_cost_centers=["CC1"])

    rows = merge_budget_rows(join_rows, {}, scope)

    assert len(rows) == 1
    assert rows[0].board.m06 == 300.0
    assert rows[0].sap.total_year == 0.0
    assert rows[0].pending.total_year == 0.0


def test_pending_only_row_manually_added_persists():
    """ADR-0010: a GL/CC added by hand via "+ เพิ่ม transaction" (no SAP, no
    board) must still appear on later opens, not vanish."""
    join_rows = [
        _blank_join_row("CC1", "GL9", pending_cost_center="CC1", pending_m01=10.0, pending_total_year=10.0)
    ]
    scope = _scope(fill_cost_centers=["CC1"], see_cost_centers=["CC1"])

    rows = merge_budget_rows(join_rows, {}, scope)

    assert len(rows) == 1
    assert rows[0].pending.m01 == 10.0


def test_rls_filters_out_cost_center_outside_see_scope():
    join_rows = [
        _blank_join_row("CC1", "GL1", pending_cost_center="CC1"),
        _blank_join_row("CC2", "GL1", pending_cost_center="CC2"),
    ]
    scope = _scope(fill_cost_centers=["CC1"], see_cost_centers=["CC1"])

    rows = merge_budget_rows(join_rows, {}, scope)

    assert [r.cost_center for r in rows] == ["CC1"]


def test_see_only_cost_center_is_visible_but_not_editable():
    join_rows = [_blank_join_row("CC2", "GL1", pending_cost_center="CC2")]
    scope = _scope(fill_cost_centers=["CC1"], see_cost_centers=["CC1", "CC2"])

    rows = merge_budget_rows(join_rows, {}, scope)

    assert len(rows) == 1
    assert rows[0].editable is False


def test_fill_cost_center_is_editable():
    join_rows = [_blank_join_row("CC1", "GL1", pending_cost_center="CC1")]
    scope = _scope(fill_cost_centers=["CC1"], see_cost_centers=["CC1"])

    rows = merge_budget_rows(join_rows, {}, scope)

    assert rows[0].editable is True


def test_admin_view_enabled_bypasses_cc_restriction_and_is_editable_for_admin():
    join_rows = [
        _blank_join_row("CC1", "GL1", pending_cost_center="CC1"),
        _blank_join_row("CC9", "GL1", pending_cost_center="CC9"),
    ]
    scope = _scope(email="admin@chememan.com", is_admin=True, role="admin", fill_cost_centers=[], see_cost_centers=[])

    rows = merge_budget_rows(join_rows, {}, scope, admin_view_enabled=True)

    assert {r.cost_center for r in rows} == {"CC1", "CC9"}
    assert all(r.editable for r in rows)


def test_admin_without_toggle_only_sees_personal_scope_like_a_normal_user():
    join_rows = [
        _blank_join_row("CC1", "GL1", pending_cost_center="CC1"),
        _blank_join_row("CC9", "GL1", pending_cost_center="CC9"),
    ]
    scope = _scope(email="admin@chememan.com", is_admin=True, role="admin", fill_cost_centers=["CC1"], see_cost_centers=["CC1"])

    rows = merge_budget_rows(join_rows, {}, scope, admin_view_enabled=False)

    assert [r.cost_center for r in rows] == ["CC1"]


def test_non_admin_admin_view_enabled_true_does_not_widen_scope():
    """Never-cut: a non-admin passing admin_view_enabled=True must not see
    CCs outside their own See scope."""
    join_rows = [
        _blank_join_row("CC1", "GL1", pending_cost_center="CC1"),
        _blank_join_row("CC9", "GL1", pending_cost_center="CC9"),
    ]
    scope = _scope(is_admin=False, fill_cost_centers=["CC1"], see_cost_centers=["CC1"])

    rows = merge_budget_rows(join_rows, {}, scope, admin_view_enabled=True)

    assert [r.cost_center for r in rows] == ["CC1"]
    assert rows[0].editable is True


def test_cost_and_sga_gl_rows_for_same_cc_never_combined():
    join_rows = [
        _blank_join_row("CC1", "5211900030", pending_cost_center="CC1", pending_m01=100.0, pending_total_year=100.0),
        _blank_join_row("CC1", "6211900030", pending_cost_center="CC1", pending_m01=50.0, pending_total_year=50.0),
    ]
    scope = _scope(fill_cost_centers=["CC1"], see_cost_centers=["CC1"])

    rows = merge_budget_rows(join_rows, {}, scope)

    by_gl = {r.gl_account: r for r in rows}
    assert by_gl["5211900030"].pending.m01 == 100.0
    assert by_gl["6211900030"].pending.m01 == 50.0


def test_optional_cost_center_filter_narrows_result():
    join_rows = [
        _blank_join_row("CC1", "GL1", pending_cost_center="CC1"),
        _blank_join_row("CC2", "GL1", pending_cost_center="CC2"),
    ]
    scope = _scope(fill_cost_centers=["CC1", "CC2"], see_cost_centers=["CC1", "CC2"])

    rows = merge_budget_rows(join_rows, {}, scope, cost_center_filter="CC1")

    assert [r.cost_center for r in rows] == ["CC1"]


def test_optional_department_filter_narrows_result():
    join_rows = [
        _blank_join_row("CC1", "GL1", pending_cost_center="CC1", pending_department="ฝ่ายบัญชี"),
        _blank_join_row("CC2", "GL1", pending_cost_center="CC2", pending_department="ฝ่ายขาย"),
    ]
    scope = _scope(fill_cost_centers=["CC1", "CC2"], see_cost_centers=["CC1", "CC2"])

    rows = merge_budget_rows(join_rows, {}, scope, department_filter="ฝ่ายบัญชี")

    assert [r.cost_center for r in rows] == ["CC1"]


def test_department_filter_falls_back_to_cc_dims_for_sap_led_rows():
    """D10 fix: a SAP-led (cc,gl) with no board/pending row has no department
    on either layer -> the department filter used to silently drop it.
    Falls back to the caller-supplied cc_dims (from dbo.cc_filler_map)."""
    join_rows: list[dict] = []
    months = {c: 0.0 for c in [f"m{m:02d}" for m in range(1, 13)]}
    months["m01"] = 500.0
    months["total_year"] = 500.0
    sap_actuals = {("CC1", "GL1"): months}
    scope = _scope(fill_cost_centers=["CC1"], see_cost_centers=["CC1"])
    cc_dims = {"CC1": {"department": "ฝ่ายบัญชี", "division": "divA", "c_level": "clA"}}

    rows = merge_budget_rows(join_rows, sap_actuals, scope, department_filter="ฝ่ายบัญชี", cc_dims=cc_dims)

    assert [r.cost_center for r in rows] == ["CC1"]


def test_department_filter_without_cc_dims_still_drops_sap_led_row():
    """Backward-compatible default: cc_dims=None (no fallback data supplied)
    preserves the pre-fix behavior for callers that don't pass it."""
    join_rows: list[dict] = []
    months = {c: 0.0 for c in [f"m{m:02d}" for m in range(1, 13)]}
    months["total_year"] = 500.0
    sap_actuals = {("CC1", "GL1"): months}
    scope = _scope(fill_cost_centers=["CC1"], see_cost_centers=["CC1"])

    rows = merge_budget_rows(join_rows, sap_actuals, scope, department_filter="ฝ่ายบัญชี", cc_dims=None)

    assert rows == []


# ---------------------------------------------------------------------------
# merge_budget_rows — GL edit_by admin-only lock (design v2, flag-gated)
# ---------------------------------------------------------------------------

def test_admin_gl_codes_none_default_strips_nothing():
    """Backward-compatible default: admin_gl_codes=None (the caller never
    passed it, e.g. flag OFF) never strips anything."""
    join_rows = [_blank_join_row("CC1", "GL-ADMIN", pending_cost_center="CC1")]
    scope = _scope(fill_cost_centers=["CC1"], see_cost_centers=["CC1"])

    rows = merge_budget_rows(join_rows, {}, scope)

    assert [r.gl_account for r in rows] == ["GL-ADMIN"]


def test_admin_gl_row_stripped_entirely_for_non_admin():
    join_rows = [
        _blank_join_row("CC1", "GL-ADMIN", pending_cost_center="CC1"),
        _blank_join_row("CC1", "GL-NORMAL", pending_cost_center="CC1"),
    ]
    scope = _scope(fill_cost_centers=["CC1"], see_cost_centers=["CC1"])

    rows = merge_budget_rows(join_rows, {}, scope, admin_gl_codes=frozenset({"GL-ADMIN"}))

    assert [r.gl_account for r in rows] == ["GL-NORMAL"]


def test_admin_gl_row_visible_for_admin_caller():
    join_rows = [_blank_join_row("CC1", "GL-ADMIN", pending_cost_center="CC1")]
    scope = _scope(email="admin@chememan.com", is_admin=True, role="admin", fill_cost_centers=[], see_cost_centers=[])

    rows = merge_budget_rows(join_rows, {}, scope, admin_view_enabled=True, admin_gl_codes=frozenset({"GL-ADMIN"}))

    assert [r.gl_account for r in rows] == ["GL-ADMIN"]


def test_admin_gl_row_stripped_for_approver_context_too():
    """Rule 1: a See-only caller (e.g. an approver reviewing a department
    via the manager-add See rule) must not receive admin-GL data either —
    the strip is keyed on scope.is_admin, not Fill/editable."""
    join_rows = [_blank_join_row("CC2", "GL-ADMIN", pending_cost_center="CC2")]
    scope = _scope(fill_cost_centers=["CC1"], see_cost_centers=["CC1", "CC2"])

    rows = merge_budget_rows(join_rows, {}, scope, admin_gl_codes=frozenset({"GL-ADMIN"}))

    assert rows == []


def test_rows_sorted_by_cost_center_then_gl_account():
    join_rows = [
        _blank_join_row("CC2", "GL1", pending_cost_center="CC2"),
        _blank_join_row("CC1", "GL2", pending_cost_center="CC1"),
        _blank_join_row("CC1", "GL1", pending_cost_center="CC1"),
    ]
    scope = _scope(fill_cost_centers=["CC1", "CC2"], see_cost_centers=["CC1", "CC2"])

    rows = merge_budget_rows(join_rows, {}, scope)

    assert [(r.cost_center, r.gl_account) for r in rows] == [("CC1", "GL1"), ("CC1", "GL2"), ("CC2", "GL1")]


# ---------------------------------------------------------------------------
# merge_budget_rows — GL master-membership rule (2026-07-18 product decision
# by jakkaritw: a GL not in dbo.gl_group is HIDDEN entirely, not shown as a
# read-only reference — reverses the earlier add-later-reference behavior).
# Composes with (but is independent of) the admin_gl_codes strip above: a row
# is visible only if (gl in master) AND (gl not admin-locked OR caller admin).
# ---------------------------------------------------------------------------

def test_master_filter_none_default_strips_nothing():
    """Backward-compatible default: master_gl_codes=None (caller never
    passed it) never strips anything — existing callers unaffected."""
    join_rows = [_blank_join_row("CC1", "GL-UNKNOWN", pending_cost_center="CC1")]
    scope = _scope(fill_cost_centers=["CC1"], see_cost_centers=["CC1"])

    rows = merge_budget_rows(join_rows, {}, scope)

    assert [r.gl_account for r in rows] == ["GL-UNKNOWN"]


def test_non_master_gl_row_dropped_for_non_admin():
    join_rows = [
        _blank_join_row("CC1", "GL-MASTER", pending_cost_center="CC1"),
        _blank_join_row("CC1", "GL-NOT-IN-MASTER", pending_cost_center="CC1"),
    ]
    scope = _scope(fill_cost_centers=["CC1"], see_cost_centers=["CC1"])

    rows = merge_budget_rows(join_rows, {}, scope, master_gl_codes=frozenset({"GL-MASTER"}))

    assert [r.gl_account for r in rows] == ["GL-MASTER"]


def test_non_master_gl_row_dropped_for_admin_too():
    """Master-membership is NOT role-based — an admin never sees a
    non-master GL row either (unlike the admin-GL strip, which only hides
    FROM non-admins)."""
    join_rows = [
        _blank_join_row("CC1", "GL-MASTER", pending_cost_center="CC1"),
        _blank_join_row("CC1", "GL-NOT-IN-MASTER", pending_cost_center="CC1"),
    ]
    scope = _scope(email="admin@chememan.com", is_admin=True, role="admin", fill_cost_centers=[], see_cost_centers=[])

    rows = merge_budget_rows(
        join_rows, {}, scope, admin_view_enabled=True, master_gl_codes=frozenset({"GL-MASTER"})
    )

    assert [r.gl_account for r in rows] == ["GL-MASTER"]


def test_master_gl_from_sap_only_row_kept():
    """A SAP-only row (no board/pending yet) whose GL IS in the master must
    still render — the master filter must not accidentally require a
    board/pending presence."""
    months = {c: 0.0 for c in [f"m{m:02d}" for m in range(1, 13)]}
    months["total_year"] = 300.0
    sap_actuals = {("CC1", "GL-MASTER"): months}
    scope = _scope(fill_cost_centers=["CC1"], see_cost_centers=["CC1"])

    rows = merge_budget_rows([], sap_actuals, scope, master_gl_codes=frozenset({"GL-MASTER"}))

    assert [r.gl_account for r in rows] == ["GL-MASTER"]


def test_sap_only_row_not_in_master_dropped():
    months = {c: 0.0 for c in [f"m{m:02d}" for m in range(1, 13)]}
    months["total_year"] = 999.0
    sap_actuals = {("CC1", "GL-NOT-IN-MASTER"): months}
    scope = _scope(fill_cost_centers=["CC1"], see_cost_centers=["CC1"])

    rows = merge_budget_rows([], sap_actuals, scope, master_gl_codes=frozenset({"GL-MASTER"}))

    assert rows == []


def test_master_filter_composes_with_admin_gl_strip():
    """A GL that IS in the master but IS admin-locked: still stripped for a
    non-admin, still visible to an admin — the two rules compose, neither
    shortcuts the other."""
    join_rows = [_blank_join_row("CC1", "GL-ADMIN", pending_cost_center="CC1")]
    non_admin_scope = _scope(fill_cost_centers=["CC1"], see_cost_centers=["CC1"])
    admin_scope = _scope(email="admin@chememan.com", is_admin=True, role="admin", fill_cost_centers=[], see_cost_centers=[])

    non_admin_rows = merge_budget_rows(
        join_rows, {}, non_admin_scope,
        master_gl_codes=frozenset({"GL-ADMIN"}), admin_gl_codes=frozenset({"GL-ADMIN"}),
    )
    admin_rows = merge_budget_rows(
        join_rows, {}, admin_scope, admin_view_enabled=True,
        master_gl_codes=frozenset({"GL-ADMIN"}), admin_gl_codes=frozenset({"GL-ADMIN"}),
    )

    assert non_admin_rows == []
    assert [r.gl_account for r in admin_rows] == ["GL-ADMIN"]


def test_master_filter_subtotal_excludes_dropped_row_no_double_count():
    """Financial-correctness guard: a subtotal computed over the rows the
    merge RETURNS must equal the sum of only the master-GL rows — the
    hidden (non-master) row's amount must never sneak into any downstream
    total, and the master row's own total must not be affected either way."""
    join_rows = [
        _blank_join_row(
            "CC1", "GL-MASTER", pending_cost_center="CC1",
            pending_m01=1_000.0, pending_total_year=1_000.0,
        ),
        _blank_join_row(
            "CC1", "GL-NOT-IN-MASTER", pending_cost_center="CC1",
            pending_m01=500.0, pending_total_year=500.0,
        ),
    ]
    scope = _scope(fill_cost_centers=["CC1"], see_cost_centers=["CC1"])

    unfiltered = merge_budget_rows(join_rows, {}, scope)
    filtered = merge_budget_rows(join_rows, {}, scope, master_gl_codes=frozenset({"GL-MASTER"}))

    unfiltered_subtotal = sum(r.pending.total_year for r in unfiltered)
    filtered_subtotal = sum(r.pending.total_year for r in filtered)

    assert unfiltered_subtotal == 1_500.0  # before: both rows counted
    assert filtered_subtotal == 1_000.0    # after: only the master row counted
    assert len(filtered) == 1 and filtered[0].gl_account == "GL-MASTER"


# ---------------------------------------------------------------------------
# merge_budget_rows — hide net-zero GL rows (plan/hide-netzero-gl-rows.md,
# 2026-07-24 decision by jakkaritw). A (cc,gl) row whose SAP months net to
# zero (e.g. a posting + its reversal, or simply no SAP row) is hidden ONLY
# when NEITHER a board NOR a pending row exists for it. Presence, not value:
# an all-zero board/pending row must still show (WIP safeguard) — see
# `_ALL_ZERO_MONTHS` fixture rows below.
# ---------------------------------------------------------------------------

_ALL_MONTHS = [f"m{m:02d}" for m in range(1, 13)]


def _net_zero_sap_months() -> dict[str, float]:
    """+1,648.13 in m01 / -1,648.13 in m02 -> total_year == 0.0 — the
    reversal-style case from the trigger finding (10GE000000/6210500010)."""
    months = {c: 0.0 for c in _ALL_MONTHS}
    months["m01"] = 1648.13
    months["m02"] = -1648.13
    months["total_year"] = 0.0
    return months


def test_net_zero_sap_key_no_board_no_pending_is_excluded():
    join_rows: list[dict] = []
    sap_actuals = {("CC1", "GL1"): _net_zero_sap_months()}
    scope = _scope(fill_cost_centers=["CC1"], see_cost_centers=["CC1"])

    rows = merge_budget_rows(join_rows, sap_actuals, scope)

    assert rows == []


def test_net_zero_sap_key_with_pending_row_is_included_safeguard():
    """Safeguard: even an all-zero pending row (blank "+ เพิ่ม Transaction"
    row, or a deliberately-zeroed one) must never vanish."""
    join_rows = [_blank_join_row("CC1", "GL1", pending_cost_center="CC1")]  # all pending amounts 0/None
    sap_actuals = {("CC1", "GL1"): _net_zero_sap_months()}
    scope = _scope(fill_cost_centers=["CC1"], see_cost_centers=["CC1"])

    rows = merge_budget_rows(join_rows, sap_actuals, scope)

    assert [r.gl_account for r in rows] == ["GL1"]
    assert rows[0].sap.total_year == 0.0
    assert rows[0].pending.total_year == 0.0


def test_net_zero_sap_key_with_board_row_is_included():
    """Presence, not value: an all-zero Approved (board) row must still
    show — same safeguard as pending, on the board side."""
    join_rows = [_blank_join_row("CC1", "GL1", board_cost_center="CC1")]  # all board amounts 0/None
    sap_actuals = {("CC1", "GL1"): _net_zero_sap_months()}
    scope = _scope(fill_cost_centers=["CC1"], see_cost_centers=["CC1"])

    rows = merge_budget_rows(join_rows, sap_actuals, scope)

    assert [r.gl_account for r in rows] == ["GL1"]
    assert rows[0].board.total_year == 0.0


def test_sap_key_with_non_zero_net_no_board_no_pending_is_included():
    """Existing behavior unchanged: any SAP month != 0 (net total != 0) keeps
    the row visible even with no board/pending, as before this rule."""
    join_rows: list[dict] = []
    months = {c: 0.0 for c in _ALL_MONTHS}
    months["m03"] = 999.0
    months["total_year"] = 999.0
    sap_actuals = {("CC1", "GL1"): months}
    scope = _scope(fill_cost_centers=["CC1"], see_cost_centers=["CC1"])

    rows = merge_budget_rows(join_rows, sap_actuals, scope)

    assert [r.gl_account for r in rows] == ["GL1"]


def test_net_zero_join_row_with_both_presence_markers_null_is_excluded():
    """Presence must come from `board_cost_center`/`pending_cost_center`
    being non-null on the join row — NOT from mere membership in
    `join_rows` — a degenerate join row with both markers null (should not
    occur from the real FULL OUTER JOIN, but guards the presence-detection
    logic itself) is treated the same as a pure-SAP key: hidden if net-zero."""
    join_rows = [_blank_join_row("CC1", "GL1")]  # board_cost_center=None, pending_cost_center=None
    sap_actuals = {("CC1", "GL1"): _net_zero_sap_months()}
    scope = _scope(fill_cost_centers=["CC1"], see_cost_centers=["CC1"])

    rows = merge_budget_rows(join_rows, sap_actuals, scope)

    assert rows == []


def test_net_zero_hidden_row_contributes_nothing_to_grid_totals():
    """TOTALS PARITY: the hidden net-zero row's layers are all exactly
    zero (sap net-zero by construction, board/pending absent -> default
    zero) -- so the grid-wide total is identical whether or not the row
    is (would be) included."""
    join_rows = [
        _blank_join_row(
            "CC1", "GL-VISIBLE", pending_cost_center="CC1",
            pending_m01=500.0, pending_total_year=500.0,
        ),
    ]
    netzero_months = _net_zero_sap_months()
    sap_actuals = {
        ("CC1", "GL-VISIBLE"): {c: 0.0 for c in _ALL_MONTHS} | {"total_year": 0.0},
        ("CC1", "GL-NETZERO"): netzero_months,
    }
    scope = _scope(fill_cost_centers=["CC1"], see_cost_centers=["CC1"])

    rows = merge_budget_rows(join_rows, sap_actuals, scope)

    assert [r.gl_account for r in rows] == ["GL-VISIBLE"]  # GL-NETZERO hidden

    def _layer_total(r):
        return r.sap.total_year + r.board.total_year + r.pending.total_year

    total_returned = sum(_layer_total(r) for r in rows)
    # The hidden row's own total (all 3 layers) — proven zero by
    # construction (net-zero SAP, no board, no pending row for it).
    hidden_row_total = netzero_months["total_year"]  # board/pending default to 0.0
    assert hidden_row_total == 0.0
    assert total_returned == 500.0
    assert total_returned + hidden_row_total == 500.0  # including it changes nothing


# ---------------------------------------------------------------------------
# get_budget_grid — orchestrator
# ---------------------------------------------------------------------------

def test_get_budget_grid_uses_planning_year_minus_1_for_board_and_sap(monkeypatch):
    captured = {}

    def fake_fetch_board_pending_rows(conn, board_year, pending_year, cost_centers=None):
        captured["board_year"] = board_year
        captured["pending_year"] = pending_year
        return []

    def fake_fetch_sap_actuals(conn, fiscal_year):
        captured["sap_year"] = fiscal_year
        return {}

    monkeypatch.setattr("app.read_model.fetch_board_pending_rows", fake_fetch_board_pending_rows)
    monkeypatch.setattr("app.read_model.fetch_sap_actuals", fake_fetch_sap_actuals)
    monkeypatch.setattr("app.read_model.fetch_master_gl_codes", lambda conn: frozenset())

    scope = _scope()
    get_budget_grid(MagicMock(), MagicMock(), planning_year=2027, scope=scope)

    assert captured["board_year"] == 2026
    assert captured["pending_year"] == 2027
    assert captured["sap_year"] == 2026


def test_get_budget_grid_propagates_sap_failure_not_silent_empty(monkeypatch):
    monkeypatch.setattr(
        "app.read_model.fetch_board_pending_rows",
        lambda conn, board_year, pending_year, cost_centers=None: [],
    )

    def raise_sap_error(conn, fiscal_year):
        raise SapActualsFetchError("DW unreachable")

    monkeypatch.setattr("app.read_model.fetch_sap_actuals", raise_sap_error)

    with pytest.raises(SapActualsFetchError):
        get_budget_grid(MagicMock(), MagicMock(), planning_year=2027, scope=_scope())


def test_get_budget_grid_admin_wide_passes_no_cost_center_filter(monkeypatch):
    """Admin-wide (is_admin AND admin_view_enabled): the SQL-side filter must
    be skipped entirely (cost_centers=None) so the join sees all CCs."""
    captured = {}

    def fake_fetch_board_pending_rows(conn, board_year, pending_year, cost_centers=None):
        captured["cost_centers"] = cost_centers
        return []

    monkeypatch.setattr("app.read_model.fetch_board_pending_rows", fake_fetch_board_pending_rows)
    monkeypatch.setattr("app.read_model.fetch_sap_actuals", lambda conn, fiscal_year: {})
    monkeypatch.setattr("app.read_model.fetch_master_gl_codes", lambda conn: frozenset())

    scope = _scope(email="admin@chememan.com", is_admin=True, role="admin", fill_cost_centers=[], see_cost_centers=[])
    get_budget_grid(MagicMock(), MagicMock(), planning_year=2027, scope=scope, admin_view_enabled=True)

    assert captured["cost_centers"] is None


def test_get_budget_grid_non_admin_passes_see_cost_centers_as_filter(monkeypatch):
    """A non-admin (or admin without the toggle) must NEVER skip the
    SQL-side restriction — never-cut, a non-admin cannot self-widen."""
    captured = {}

    def fake_fetch_board_pending_rows(conn, board_year, pending_year, cost_centers=None):
        captured["cost_centers"] = cost_centers
        return []

    monkeypatch.setattr("app.read_model.fetch_board_pending_rows", fake_fetch_board_pending_rows)
    monkeypatch.setattr("app.read_model.fetch_sap_actuals", lambda conn, fiscal_year: {})
    monkeypatch.setattr("app.read_model.fetch_master_gl_codes", lambda conn: frozenset())

    scope = _scope(fill_cost_centers=["CC1"], see_cost_centers=["CC1", "CC2"])
    get_budget_grid(MagicMock(), MagicMock(), planning_year=2027, scope=scope, admin_view_enabled=False)

    assert sorted(captured["cost_centers"]) == ["CC1", "CC2"]


def test_get_budget_grid_fetches_cc_dims_only_when_department_filter_given(monkeypatch):
    """D10: fetch_cc_dims (an extra DB round-trip) must only run when the
    caller actually applies a department filter — never on a plain load."""
    calls = {"n": 0}

    def fake_fetch_cc_dims(conn, cost_centers):
        calls["n"] += 1
        return {}

    monkeypatch.setattr("app.read_model.fetch_board_pending_rows", lambda conn, board_year, pending_year, cost_centers=None: [])
    monkeypatch.setattr("app.read_model.fetch_sap_actuals", lambda conn, fiscal_year: {})
    monkeypatch.setattr("app.read_model.fetch_cc_dims", fake_fetch_cc_dims)
    monkeypatch.setattr("app.read_model.fetch_master_gl_codes", lambda conn: frozenset())

    scope = _scope()
    get_budget_grid(MagicMock(), MagicMock(), planning_year=2027, scope=scope)
    assert calls["n"] == 0

    get_budget_grid(MagicMock(), MagicMock(), planning_year=2027, scope=scope, department_filter="ฝ่ายบัญชี")
    assert calls["n"] == 1


def test_get_budget_grid_admin_without_toggle_still_passes_see_cost_centers_filter(monkeypatch):
    """An admin who has NOT enabled the admin-wide toggle is treated like a
    normal user for the SQL-side filter too."""
    captured = {}

    def fake_fetch_board_pending_rows(conn, board_year, pending_year, cost_centers=None):
        captured["cost_centers"] = cost_centers
        return []

    monkeypatch.setattr("app.read_model.fetch_board_pending_rows", fake_fetch_board_pending_rows)
    monkeypatch.setattr("app.read_model.fetch_sap_actuals", lambda conn, fiscal_year: {})
    monkeypatch.setattr("app.read_model.fetch_master_gl_codes", lambda conn: frozenset())

    scope = _scope(email="admin@chememan.com", is_admin=True, role="admin", fill_cost_centers=["CC1"], see_cost_centers=["CC1"])
    get_budget_grid(MagicMock(), MagicMock(), planning_year=2027, scope=scope, admin_view_enabled=False)

    assert captured["cost_centers"] == ["CC1"]


# ---------------------------------------------------------------------------
# get_budget_grid — GL master-membership rule (2026-07-18, NOT flag-gated,
# NOT role-based: always fetched, for every caller).
# ---------------------------------------------------------------------------

def test_get_budget_grid_always_fetches_master_gl_codes_non_admin(monkeypatch):
    calls = {"n": 0}

    def fake_fetch_master_gl_codes(conn):
        calls["n"] += 1
        return frozenset({"GL1"})

    monkeypatch.setattr("app.read_model.fetch_board_pending_rows", lambda conn, board_year, pending_year, cost_centers=None: [])
    monkeypatch.setattr("app.read_model.fetch_sap_actuals", lambda conn, fiscal_year: {})
    monkeypatch.setattr("app.read_model.fetch_master_gl_codes", fake_fetch_master_gl_codes)

    get_budget_grid(MagicMock(), MagicMock(), planning_year=2027, scope=_scope())
    assert calls["n"] == 1


def test_get_budget_grid_always_fetches_master_gl_codes_admin(monkeypatch):
    """Unlike the flag-gated admin-GL strip, the master filter is NOT
    role-based — an admin caller still gets it fetched and applied."""
    calls = {"n": 0}

    def fake_fetch_master_gl_codes(conn):
        calls["n"] += 1
        return frozenset({"GL1"})

    monkeypatch.setattr("app.read_model.fetch_board_pending_rows", lambda conn, board_year, pending_year, cost_centers=None: [])
    monkeypatch.setattr("app.read_model.fetch_sap_actuals", lambda conn, fiscal_year: {})
    monkeypatch.setattr("app.read_model.fetch_master_gl_codes", fake_fetch_master_gl_codes)

    admin_scope = _scope(email="admin@chememan.com", is_admin=True, role="admin", fill_cost_centers=[], see_cost_centers=[])
    get_budget_grid(MagicMock(), MagicMock(), planning_year=2027, scope=admin_scope, admin_view_enabled=True)
    assert calls["n"] == 1


def test_get_budget_grid_master_filter_drops_non_master_row_end_to_end(monkeypatch):
    """End-to-end: get_budget_grid actually applies the fetched master set,
    not just calls the fetch function."""
    join_rows = [
        _blank_join_row("CC1", "GL-MASTER", pending_cost_center="CC1"),
        _blank_join_row("CC1", "GL-NOT-IN-MASTER", pending_cost_center="CC1"),
    ]
    monkeypatch.setattr("app.read_model.fetch_board_pending_rows", lambda conn, board_year, pending_year, cost_centers=None: join_rows)
    monkeypatch.setattr("app.read_model.fetch_sap_actuals", lambda conn, fiscal_year: {})
    monkeypatch.setattr("app.read_model.fetch_master_gl_codes", lambda conn: frozenset({"GL-MASTER"}))

    scope = _scope(fill_cost_centers=["CC1"], see_cost_centers=["CC1"])
    rows = get_budget_grid(MagicMock(), MagicMock(), planning_year=2027, scope=scope)

    assert [r.gl_account for r in rows] == ["GL-MASTER"]


# ---------------------------------------------------------------------------
# get_budget_grid — GL edit_by admin-only lock (design v2, flag-gated)
# ---------------------------------------------------------------------------

def test_get_budget_grid_flag_off_never_fetches_admin_gl_codes(monkeypatch):
    """Flag OFF (default Settings) — zero behavior change: the extra query
    must never run."""
    calls = {"n": 0}

    def fake_fetch_admin_gl_codes(conn):
        calls["n"] += 1
        return frozenset()

    monkeypatch.setattr("app.read_model.fetch_board_pending_rows", lambda conn, board_year, pending_year, cost_centers=None: [])
    monkeypatch.setattr("app.read_model.fetch_sap_actuals", lambda conn, fiscal_year: {})
    monkeypatch.setattr("app.read_model.fetch_admin_gl_codes", fake_fetch_admin_gl_codes)
    monkeypatch.setattr("app.read_model.fetch_master_gl_codes", lambda conn: frozenset())

    get_budget_grid(MagicMock(), MagicMock(), planning_year=2027, scope=_scope())
    assert calls["n"] == 0


def test_get_budget_grid_flag_on_non_admin_fetches_admin_gl_codes(monkeypatch):
    from app.config import Settings

    calls = {"n": 0}

    def fake_fetch_admin_gl_codes(conn):
        calls["n"] += 1
        return frozenset({"GL-ADMIN"})

    monkeypatch.setattr("app.read_model.fetch_board_pending_rows", lambda conn, board_year, pending_year, cost_centers=None: [])
    monkeypatch.setattr("app.read_model.fetch_sap_actuals", lambda conn, fiscal_year: {})
    monkeypatch.setattr("app.read_model.fetch_admin_gl_codes", fake_fetch_admin_gl_codes)
    monkeypatch.setattr("app.read_model.fetch_master_gl_codes", lambda conn: frozenset())

    settings = Settings(_env_file=None, gl_edit_by_enabled=True)
    get_budget_grid(MagicMock(), MagicMock(), planning_year=2027, scope=_scope(), settings=settings)
    assert calls["n"] == 1


def test_get_budget_grid_flag_on_admin_caller_never_fetches_admin_gl_codes(monkeypatch):
    """An admin caller never needs the admin-GL set (nothing gets stripped
    for them) — skip the extra query even with the flag on."""
    from app.config import Settings

    calls = {"n": 0}

    def fake_fetch_admin_gl_codes(conn):
        calls["n"] += 1
        return frozenset()

    monkeypatch.setattr("app.read_model.fetch_board_pending_rows", lambda conn, board_year, pending_year, cost_centers=None: [])
    monkeypatch.setattr("app.read_model.fetch_sap_actuals", lambda conn, fiscal_year: {})
    monkeypatch.setattr("app.read_model.fetch_admin_gl_codes", fake_fetch_admin_gl_codes)
    monkeypatch.setattr("app.read_model.fetch_master_gl_codes", lambda conn: frozenset())

    settings = Settings(_env_file=None, gl_edit_by_enabled=True)
    admin_scope = _scope(email="admin@chememan.com", is_admin=True, role="admin", fill_cost_centers=[], see_cost_centers=[])
    get_budget_grid(MagicMock(), MagicMock(), planning_year=2027, scope=admin_scope, settings=settings)
    assert calls["n"] == 0


# =========================================================================
# A13 board Replace-by-Year resilience (ADR-0021 + BUILD_PLAN)
# =========================================================================

def test_board_year_empty_returns_zero_filled_pending_and_sap_layers():
    """When dbo.board_budget has ZERO rows for the board year (mid-sync or
    post-deletion), the grid still renders SAP+Pending layers with board
    zero-filled — never crashes, never silent-empty grid."""
    join_rows = [
        _blank_join_row(
            "CC1", "GL1",
            # No board fields (all None) — board year was empty for this cc/gl
            pending_cost_center="CC1", pending_m01=100.0, pending_total_year=100.0
        ),
    ]
    # SAP data passed separately (ADR-0020: cross-store merge)
    # total_year included (not net-zero) — matches the real SAP query, which
    # always carries its own pre-computed total_year column; a fixture
    # without it would look net-zero under the 2026-07-24 hide rule.
    sap_actuals = {
        ("CC1", "GL2"): {"m01": 50.0, "m02": 0.0, "m03": 0.0, "m04": 0.0,
                        "m05": 0.0, "m06": 0.0, "m07": 0.0, "m08": 0.0,
                        "m09": 0.0, "m10": 0.0, "m11": 0.0, "m12": 0.0,
                        "total_year": 50.0}
    }
    scope = _scope(fill_cost_centers=["CC1"], see_cost_centers=["CC1"])

    rows = merge_budget_rows(join_rows, sap_actuals, scope)

    assert len(rows) == 2
    # Row 1: board=0, pending=100, sap=None (GL1 not in SAP)
    assert rows[0].board.total_year == 0
    assert rows[0].pending.m01 == 100.0
    assert rows[0].sap.total_year == 0
    # Row 2: board=0, pending=None, sap=50 (GL2 SAP-only row)
    assert rows[1].cost_center == "CC1" and rows[1].gl_account == "GL2"
    assert rows[1].board.total_year == 0
    assert rows[1].pending.total_year == 0
    assert rows[1].sap.m01 == 50.0


def test_board_year_partial_missing_cost_center_still_renders():
    """When dbo.board_budget is present but missing a specific cost center
    (sync in progress, mid-DROP+re-INSERT), rows from SAP/Pending for that
    CC still appear with zero-filled board layer — never lost."""
    join_rows = []  # No join row yet (board empty for CC_NEW)
    # But SAP has a row for CC_NEW
    # total_year included (not net-zero) — see same note above.
    sap_actuals = {
        ("CC_NEW", "GL1"): {"m01": 200.0, "m02": 0.0, "m03": 0.0, "m04": 0.0,
                           "m05": 0.0, "m06": 0.0, "m07": 0.0, "m08": 0.0,
                           "m09": 0.0, "m10": 0.0, "m11": 0.0, "m12": 0.0,
                           "total_year": 200.0}
    }
    scope = _scope(fill_cost_centers=["CC_NEW"], see_cost_centers=["CC_NEW"])

    rows = merge_budget_rows(join_rows, sap_actuals, scope)

    assert len(rows) == 1
    assert rows[0].cost_center == "CC_NEW"
    assert rows[0].board.total_year == 0  # zero-filled, not skipped
    assert rows[0].sap.m01 == 200.0


def test_fetch_board_pending_rows_empty_board_year_no_crash():
    """A FULL OUTER JOIN returning 0 board rows (mid-sync) must not crash,
    just return an empty list — grid render happens downstream in merge_budget_rows."""
    conn = MagicMock()
    conn.cursor.return_value.fetchall.return_value = []  # Empty board/pending join
    conn.cursor.return_value.close.return_value = None

    rows = fetch_board_pending_rows(conn, board_year=2026, pending_year=2027)

    assert rows == []
    conn.cursor.return_value.execute.assert_called_once()
    conn.cursor.return_value.close.assert_called_once()
