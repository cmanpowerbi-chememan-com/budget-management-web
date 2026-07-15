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

    scope = _scope(fill_cost_centers=["CC1"], see_cost_centers=["CC1", "CC2"])
    get_budget_grid(MagicMock(), MagicMock(), planning_year=2027, scope=scope, admin_view_enabled=False)

    assert sorted(captured["cost_centers"]) == ["CC1", "CC2"]


def test_get_budget_grid_admin_without_toggle_still_passes_see_cost_centers_filter(monkeypatch):
    """An admin who has NOT enabled the admin-wide toggle is treated like a
    normal user for the SQL-side filter too."""
    captured = {}

    def fake_fetch_board_pending_rows(conn, board_year, pending_year, cost_centers=None):
        captured["cost_centers"] = cost_centers
        return []

    monkeypatch.setattr("app.read_model.fetch_board_pending_rows", fake_fetch_board_pending_rows)
    monkeypatch.setattr("app.read_model.fetch_sap_actuals", lambda conn, fiscal_year: {})

    scope = _scope(email="admin@chememan.com", is_admin=True, role="admin", fill_cost_centers=["CC1"], see_cost_centers=["CC1"])
    get_budget_grid(MagicMock(), MagicMock(), planning_year=2027, scope=scope, admin_view_enabled=False)

    assert captured["cost_centers"] == ["CC1"]
