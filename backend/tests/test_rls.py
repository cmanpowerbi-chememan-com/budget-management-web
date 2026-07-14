"""Unit tests for app.rls — RLS scope resolution (ADR-0019, A3).

Fully mocked cursor/connection — no live DB. Any live-DB verification needs
the env re-point to `fabric_sql_database` (ADR-0023), not done yet.
"""
from unittest.mock import MagicMock

from app.config import Settings
from app.rls import resolve_scope

NO_ADMINS = Settings(_env_file=None)
ONE_ADMIN = Settings(_env_file=None, admin_emails="jakkaritw@chememan.com")


def _make_conn(fill_rows: list[tuple], manager_add_rows: list[tuple]) -> MagicMock:
    """Mock connection whose cursor answers the Fill query then the See-add query,
    in that call order (matches resolve_scope's two sequential execute/fetchall calls).
    """
    cursor = MagicMock()
    cursor.fetchall.side_effect = [fill_rows, manager_add_rows]
    conn = MagicMock()
    conn.cursor.return_value = cursor
    return conn


def test_fill_only_user_sees_only_their_own_ccs():
    conn = _make_conn(fill_rows=[("10CA013000",)], manager_add_rows=[])
    scope = resolve_scope("filler@chememan.com", conn, settings=NO_ADMINS)
    assert scope.fill_cost_centers == ["10CA013000"]
    assert scope.see_cost_centers == ["10CA013000"]
    assert scope.role == "filler"
    assert scope.is_admin is False


def test_manager_sees_reports_ccs_in_addition_to_their_own_fill():
    conn = _make_conn(
        fill_rows=[("CC1",)],
        manager_add_rows=[("CC2",), ("CC3",)],
    )
    scope = resolve_scope("manager@chememan.com", conn, settings=NO_ADMINS)
    assert scope.fill_cost_centers == ["CC1"]
    assert scope.see_cost_centers == ["CC1", "CC2", "CC3"]
    assert scope.role == "filler"


def test_pure_approver_has_see_but_no_fill_is_see_only_role():
    conn = _make_conn(fill_rows=[], manager_add_rows=[("CC2",), ("CC3",)])
    scope = resolve_scope("approver@chememan.com", conn, settings=NO_ADMINS)
    assert scope.fill_cost_centers == []
    assert scope.see_cost_centers == ["CC2", "CC3"]
    assert scope.role == "see_only"


def test_filler_not_in_employee_view_still_fills_with_no_see_add_and_no_crash():
    """Real edge case (warapornkh@ typo, ADR-0019): the Filler-manager JOIN simply
    returns 0 rows for this person — Fill still resolves straight from cc_filler_map.
    """
    conn = _make_conn(fill_rows=[("10OS013000",)], manager_add_rows=[])
    scope = resolve_scope("warapornkh@chememan.com", conn, settings=NO_ADMINS)
    assert scope.fill_cost_centers == ["10OS013000"]
    assert scope.see_cost_centers == ["10OS013000"]
    assert scope.role == "filler"


def test_admin_email_is_admin_and_role_admin_even_with_no_personal_scope():
    conn = _make_conn(fill_rows=[], manager_add_rows=[])
    scope = resolve_scope("jakkaritw@chememan.com", conn, settings=ONE_ADMIN)
    assert scope.is_admin is True
    assert scope.role == "admin"
    assert scope.fill_cost_centers == []
    assert scope.see_cost_centers == []


def test_admin_email_match_is_case_insensitive():
    conn = _make_conn(fill_rows=[], manager_add_rows=[])
    scope = resolve_scope("Jakkaritw@Chememan.com", conn, settings=ONE_ADMIN)
    assert scope.is_admin is True
    assert scope.role == "admin"


def test_admin_still_gets_their_own_personal_fill_and_see_not_all_ccs():
    """Dual-role admin (e.g. Nipaporn/Waraporn): admin overlay does not expand
    scope to every CC here — that expansion is an A4 query-layer concern."""
    conn = _make_conn(fill_rows=[("CC1",)], manager_add_rows=[("CC2",)])
    scope = resolve_scope("nipapornt@chememan.com", conn, settings=Settings(_env_file=None, admin_emails="nipapornt@chememan.com"))
    assert scope.is_admin is True
    assert scope.role == "admin"
    assert scope.fill_cost_centers == ["CC1"]
    assert scope.see_cost_centers == ["CC1", "CC2"]


def test_duplicate_cost_center_rows_across_department_are_deduped():
    """cc_filler_map is exploded per (cost_center, filler_email, department) — a
    45% real-world case of a Filler spanning >1 ฝ่าย can surface the same CC twice.
    SQL already has DISTINCT; this proves the Python side dedupes too as a backstop.
    """
    conn = _make_conn(
        fill_rows=[("CC1",), ("CC1",), ("CC2",)],
        manager_add_rows=[("CC2",), ("CC3",)],
    )
    scope = resolve_scope("multidept@chememan.com", conn, settings=NO_ADMINS)
    assert scope.fill_cost_centers == ["CC1", "CC2"]
    assert scope.see_cost_centers == ["CC1", "CC2", "CC3"]


def test_no_scope_user_role_none_with_empty_lists():
    conn = _make_conn(fill_rows=[], manager_add_rows=[])
    scope = resolve_scope("nobody@chememan.com", conn, settings=NO_ADMINS)
    assert scope.role == "none"
    assert scope.is_admin is False
    assert scope.fill_cost_centers == []
    assert scope.see_cost_centers == []


def test_fill_query_uses_lower_case_insensitive_email_match():
    conn = _make_conn(fill_rows=[], manager_add_rows=[])
    resolve_scope("Someone@Chememan.com", conn, settings=NO_ADMINS)
    cursor = conn.cursor.return_value
    fill_call = cursor.execute.call_args_list[0]
    sql_text = fill_call.args[0]
    assert "cc_filler_map" in sql_text
    assert "LOWER(" in sql_text.upper() or "LOWER(" in sql_text
    assert fill_call.args[1] == "Someone@Chememan.com"


def test_admin_view_enabled_does_not_self_elevate_a_non_admin_user():
    """`admin_view_enabled` is a forward-looking hook for A4's read path
    (ADR-0014), not a self-elevation switch. A non-admin caller passing
    admin_view_enabled=True must not gain is_admin, and their scope must not
    widen beyond exactly what the Fill/See queries returned.
    """
    conn = _make_conn(fill_rows=[("CC1",)], manager_add_rows=[("CC2",)])
    settings = Settings(_env_file=None, admin_emails="someoneelse@chememan.com")
    scope = resolve_scope(
        "regular@chememan.com",
        conn,
        admin_view_enabled=True,
        settings=settings,
    )
    assert scope.is_admin is False
    assert scope.fill_cost_centers == ["CC1"]
    assert scope.see_cost_centers == ["CC1", "CC2"]


def test_manager_see_query_joins_employee_view_on_manager_email():
    conn = _make_conn(fill_rows=[], manager_add_rows=[])
    resolve_scope("mgr@chememan.com", conn, settings=NO_ADMINS)
    cursor = conn.cursor.return_value
    see_call = cursor.execute.call_args_list[1]
    sql_text = see_call.args[0]
    assert "v_employee_budget_01" in sql_text
    assert "manager_email" in sql_text
    assert see_call.args[1] == "mgr@chememan.com"
