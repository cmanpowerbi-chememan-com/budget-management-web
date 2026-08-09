"""Unit tests for app.rls — RLS scope resolution (ADR-0019, A3).

Fully mocked cursor/connection — no live DB. Any live-DB verification needs
the env re-point to `fabric_sql_database` (ADR-0023), not done yet.
"""
from datetime import datetime, timezone
from unittest.mock import MagicMock

from app.approval import NIPAPORN_EMPCODE, PENDING_APPROVER1
from app.config import Settings
from app.rls import resolve_scope

NO_ADMINS = Settings(_env_file=None)
ONE_ADMIN = Settings(_env_file=None, admin_emails="jakkaritw@chememan.com")


def _pending_status_row(department: str, approver1_empcode: str) -> tuple:
    """Raw `budget.approval_status` row tuple, in `app.approval._STATUS_COLUMNS`
    order, for a department PENDING at position 1 (this module never needs to
    exercise positions 2/3 — that logic is unit-tested directly in
    test_approval.py; here we only need ONE pending row to prove the overlay
    wiring)."""
    now = datetime(2027, 1, 1, tzinfo=timezone.utc)
    return (
        department, 2027, PENDING_APPROVER1, "999", "submitter@chememan.com", now,
        approver1_empcode, None, None, None, None, None, now,
    )


def _make_conn(
    fill_rows: list[tuple],
    manager_add_rows: list[tuple],
    employee_row: tuple | None = None,
    pending_rows: list[tuple] | None = None,
    overlay_cc_rows: list[tuple] | None = None,
) -> MagicMock:
    """Mock connection whose cursor answers, IN ORDER: the Fill query, the
    See-add query, then — for the ADR-0029 approver see-overlay —
    `resolve_submitter`'s `fetchone()` (`employee_row`) and (only if an
    empcode resolved and it has pending departments) the pending-departments
    query and the overlay cost-center query.

    Default `employee_row=None` ("caller not in the employee view") makes
    `_pending_approval_overlay` short-circuit with NO further `fetchall()`
    calls at all — every pre-existing test below (written before ADR-0029)
    keeps working unmodified. `pending_rows`/`overlay_cc_rows` are harmless
    to leave at their `[]` default even when unused: `cursor.fetchall`'s
    `side_effect` list only advances as far as calls actually made, so
    unused trailing entries are simply never consumed.
    """
    cursor = MagicMock()
    cursor.fetchall.side_effect = [fill_rows, manager_add_rows, pending_rows or [], overlay_cc_rows or []]
    cursor.fetchone.return_value = employee_row
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


# ---------------------------------------------------------------------------
# ADR-0029 — approver see-overlay: a department PENDING on the caller as its
# current approver is always visible, even with zero personal Fill/See.
# ---------------------------------------------------------------------------

def test_pending_department_overlay_adds_its_ccs_to_see_only_never_fill():
    """The measured D-04 defect: Nipaporn/Waraporn (fixed step-2/3 approvers,
    ADR-0006) are outside every submitter's manager chain, so without the
    overlay a department PENDING on them never appears in their own scope at
    all."""
    conn = _make_conn(
        fill_rows=[], manager_add_rows=[],
        employee_row=(NIPAPORN_EMPCODE, None),
        pending_rows=[_pending_status_row("Solution Delivery", approver1_empcode=NIPAPORN_EMPCODE)],
        overlay_cc_rows=[("10IT011300",), ("10IT0130000",)],
    )
    scope = resolve_scope("nipapornt@chememan.com", conn, settings=NO_ADMINS)

    assert scope.see_cost_centers == ["10IT011300", "10IT0130000"]
    assert scope.fill_cost_centers == []


def test_pending_department_not_at_callers_step_grants_nothing():
    """Position 1 is frozen to a DIFFERENT empcode — this caller is not the
    department's CURRENT approver, so the overlay must not add it."""
    conn = _make_conn(
        fill_rows=[], manager_add_rows=[],
        employee_row=("500", None),
        pending_rows=[_pending_status_row("Solution Delivery", approver1_empcode="999999")],
    )
    scope = resolve_scope("someone@chememan.com", conn, settings=NO_ADMINS)

    assert scope.see_cost_centers == []
    cursor = conn.cursor.return_value
    # fill + manager_add + the pending-departments query itself (which finds
    # nothing for THIS caller) — but the batch cost-center lookup for the
    # overlay never fires, since there is nothing to look up.
    assert cursor.fetchall.call_count == 3


def test_overlay_only_scope_role_is_see_only_not_none():
    """A caller with zero personal Fill, zero personal See-add, but one
    department pending on them must come out `see_only`, not `none` — a
    `none` role would block the very page they need to reach the Approve
    button on."""
    conn = _make_conn(
        fill_rows=[], manager_add_rows=[],
        employee_row=(NIPAPORN_EMPCODE, None),
        pending_rows=[_pending_status_row("Solution Delivery", approver1_empcode=NIPAPORN_EMPCODE)],
        overlay_cc_rows=[("10IT011300",)],
    )
    scope = resolve_scope("nipapornt@chememan.com", conn, settings=NO_ADMINS)

    assert scope.role == "see_only"
    assert scope.fill_cost_centers == []
    assert scope.see_cost_centers == ["10IT011300"]


def test_position1_manager_who_already_sees_the_department_gets_no_duplicate():
    """A plain position-1 approver (the submitter's own manager) already sees
    the department's CCs via `_MANAGER_SEE_ADD_SQL` — the overlay resolving
    the SAME CC must be a no-op union, not a duplicate-row bug."""
    conn = _make_conn(
        fill_rows=[], manager_add_rows=[("CC1",)],
        employee_row=("200", None),
        pending_rows=[_pending_status_row("Solution Delivery", approver1_empcode="200")],
        overlay_cc_rows=[("CC1",)],  # same CC the manager-add query already returned
    )
    scope = resolve_scope("manager@chememan.com", conn, settings=NO_ADMINS)

    assert scope.see_cost_centers == ["CC1"]  # not ["CC1", "CC1"] / no duplication
    assert scope.role == "see_only"


def test_admin_with_no_employee_row_gets_an_empty_overlay_gracefully():
    """A pure admin (e.g. jakkaritw) has no `dbo.v_employee_budget_01` row at
    all -> `resolve_submitter` returns `(None, None)` -> the overlay
    short-circuits with no `budget.approval_status` query, no crash."""
    conn = _make_conn(
        fill_rows=[], manager_add_rows=[],
        employee_row=None,  # not found in the employee view
    )
    scope = resolve_scope("jakkaritw@chememan.com", conn, settings=ONE_ADMIN)

    assert scope.is_admin is True
    assert scope.see_cost_centers == []
    cursor = conn.cursor.return_value
    assert cursor.fetchall.call_count == 2  # overlay never queried past resolve_submitter
