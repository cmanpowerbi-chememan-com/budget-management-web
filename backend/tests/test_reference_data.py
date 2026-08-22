"""Unit tests for app.reference_data — GL-account list (A8 "+ เพิ่ม
transaction" picker), the caller's department/CC hierarchy (A8 ฝ่าย
picker), and the Trip-Manager pickers (travelers, countries). DB always
mocked, no live connection."""
import logging
from unittest.mock import MagicMock

from app.reference_data import fetch_countries, fetch_departments, fetch_gl_accounts, fetch_travelers


# ---------------------------------------------------------------------------
# fetch_gl_accounts
# ---------------------------------------------------------------------------

def test_fetch_gl_accounts_maps_rows_and_flags_special_groups():
    conn = MagicMock()
    conn.cursor.return_value.fetchall.return_value = [
        ("6211800030", "Office expenses", "อุปกรณ์และเครื่องใช้สำนักงาน"),
        ("5211900030", "Entertainment", "ค่าเลี้ยงรับรองภายนอก"),
    ]

    rows = fetch_gl_accounts(conn)

    assert rows[0] == {
        "gl_code": "6211800030",
        "gl_group": "Office expenses",
        "gl_name": "อุปกรณ์และเครื่องใช้สำนักงาน",
        "is_special": False,
    }
    assert rows[1]["is_special"] is True


def test_fetch_gl_accounts_queries_dbo_gl_group():
    conn = MagicMock()
    conn.cursor.return_value.fetchall.return_value = []
    fetch_gl_accounts(conn)
    sql_text = conn.cursor.return_value.execute.call_args.args[0]
    assert "dbo.gl_group" in sql_text
    assert "gl_code" in sql_text and "gl_group" in sql_text and "gl_name" in sql_text


def test_fetch_gl_accounts_closes_cursor():
    conn = MagicMock()
    conn.cursor.return_value.fetchall.return_value = []
    fetch_gl_accounts(conn)
    conn.cursor.return_value.close.assert_called_once()


# ---------------------------------------------------------------------------
# fetch_gl_accounts — GL edit_by admin-only lock (design v2, flag-gated)
# ---------------------------------------------------------------------------

def test_fetch_gl_accounts_default_never_selects_edit_by():
    """Flag OFF (default param) — identical SQL to before this feature."""
    conn = MagicMock()
    conn.cursor.return_value.fetchall.return_value = []
    fetch_gl_accounts(conn)
    sql_text = conn.cursor.return_value.execute.call_args.args[0]
    assert "edit_by" not in sql_text


def test_fetch_gl_accounts_include_edit_by_selects_the_column():
    conn = MagicMock()
    conn.cursor.return_value.fetchall.return_value = []
    fetch_gl_accounts(conn, include_edit_by=True, is_admin=True)
    sql_text = conn.cursor.return_value.execute.call_args.args[0]
    assert "edit_by" in sql_text


def test_fetch_gl_accounts_admin_caller_sees_admin_gl_with_normalized_field():
    conn = MagicMock()
    conn.cursor.return_value.fetchall.return_value = [
        ("6211800030", "Office expenses", "อุปกรณ์และเครื่องใช้สำนักงาน", "user"),
        ("5210100010", "Insurance Premium", "ค่าเบี้ยประกันภัย", "Admin"),
    ]
    rows = fetch_gl_accounts(conn, include_edit_by=True, is_admin=True)
    assert len(rows) == 2
    by_code = {r["gl_code"]: r for r in rows}
    assert by_code["6211800030"]["edit_by"] == "user"
    assert by_code["5210100010"]["edit_by"] == "admin"


def test_fetch_gl_accounts_non_admin_caller_never_sees_admin_gl_row_at_all():
    """SECRET (design v2): the admin GL is dropped entirely, not just its
    edit_by field — a non-admin must never learn the row even exists."""
    conn = MagicMock()
    conn.cursor.return_value.fetchall.return_value = [
        ("6211800030", "Office expenses", "อุปกรณ์และเครื่องใช้สำนักงาน", "user"),
        ("5210100010", "Insurance Premium", "ค่าเบี้ยประกันภัย", "admin"),
    ]
    rows = fetch_gl_accounts(conn, include_edit_by=True, is_admin=False)
    assert [r["gl_code"] for r in rows] == ["6211800030"]
    assert rows[0]["edit_by"] == "user"


def test_fetch_gl_accounts_garbage_edit_by_normalizes_to_user_and_is_visible():
    conn = MagicMock()
    conn.cursor.return_value.fetchall.return_value = [("GL1", "Office expenses", "x", None)]
    rows = fetch_gl_accounts(conn, include_edit_by=True, is_admin=False)
    assert rows == [{"gl_code": "GL1", "gl_group": "Office expenses", "gl_name": "x", "is_special": False, "edit_by": "user"}]


# ---------------------------------------------------------------------------
# fetch_departments
# ---------------------------------------------------------------------------

def test_fetch_departments_empty_scope_short_circuits_no_query():
    conn = MagicMock()
    rows = fetch_departments(conn, [])
    assert rows == []
    conn.cursor.assert_not_called()


def test_fetch_departments_none_means_admin_wide_no_restriction():
    conn = MagicMock()
    conn.cursor.return_value.fetchall.return_value = []
    fetch_departments(conn, None)
    sql_text = conn.cursor.return_value.execute.call_args.args[0]
    assert "cost_center IN" not in sql_text


def test_fetch_departments_restricts_to_given_cost_centers():
    conn = MagicMock()
    conn.cursor.return_value.fetchall.return_value = []
    fetch_departments(conn, ["CC1", "CC2"])
    call = conn.cursor.return_value.execute.call_args
    sql_text = call.args[0]
    assert "cost_center IN (?, ?)" in sql_text
    assert call.args[1] == "CC1"
    assert call.args[2] == "CC2"


def test_fetch_departments_maps_rows_and_dedupes_deterministically():
    conn = MagicMock()
    conn.cursor.return_value.fetchall.return_value = [
        ("CC1", "Solution Delivery", "Digital Technology Division", "CTO"),
    ]
    rows = fetch_departments(conn, ["CC1"])
    assert rows == [
        {
            "cost_center": "CC1",
            "department": "Solution Delivery",
            "division": "Digital Technology Division",
            "c_level": "CTO",
        }
    ]
    sql_text = conn.cursor.return_value.execute.call_args.args[0]
    assert "ORDER BY filler_email" in sql_text  # same D11 tie-break as fetch_cc_dims


def test_fetch_departments_closes_cursor():
    conn = MagicMock()
    conn.cursor.return_value.fetchall.return_value = []
    fetch_departments(conn, ["CC1"])
    conn.cursor.return_value.close.assert_called_once()


# ---------------------------------------------------------------------------
# fetch_countries — Trip Manager destination-country picker
# ---------------------------------------------------------------------------

def test_fetch_countries_maps_group_names_to_ints_and_sorts_domestic_first():
    """Live dbo.country_group stores group NAMES ('domestic'/'asian' —
    introspected 2026-07-17, NOT the spec DBML's ints); the API contract is
    ints: 1=domestic, 2=asian. Sorted (group, country)."""
    conn = MagicMock()
    conn.cursor.return_value.fetchall.return_value = [
        ("China", "asian"),
        ("Thailand", "domestic"),
        ("Cambodia", "asian"),
    ]
    rows = fetch_countries(conn)
    assert rows == [
        {"country": "Thailand", "country_group": 1},
        {"country": "Cambodia", "country_group": 2},
        {"country": "China", "country_group": 2},
    ]


def test_fetch_countries_maps_other_group_name_to_group_3():
    """2026-08-22: setup/add_country_master_other_group.py added 16 rows to
    the live SharePoint master under the Excel label 'ต่างประเทศ-อื่นๆ', which
    the DW sync notebook's else-branch (map_country_group) stores as the
    STRING 'other'. A live-shaped row must map to country_group 3, not be
    dropped by the unrecognised-label guard."""
    conn = MagicMock()
    conn.cursor.return_value.fetchall.return_value = [("United States", "other")]
    rows = fetch_countries(conn)
    assert rows == [{"country": "United States", "country_group": 3}]


def test_fetch_countries_sorts_all_three_tiers_by_group_then_country():
    """All three tiers together, out of order and out of alphabetical order
    within a tier — sort must be (country_group, country), never insertion
    order or a partial sort of only the tiers seen before 2026-08-22."""
    conn = MagicMock()
    conn.cursor.return_value.fetchall.return_value = [
        ("United Kingdom", "other"),
        ("China", "asian"),
        ("Thailand", "domestic"),
        ("United States", "other"),
        ("Cambodia", "asian"),
    ]
    rows = fetch_countries(conn)
    assert rows == [
        {"country": "Thailand", "country_group": 1},
        {"country": "Cambodia", "country_group": 2},
        {"country": "China", "country_group": 2},
        {"country": "United Kingdom", "country_group": 3},
        {"country": "United States", "country_group": 3},
    ]


def test_fetch_countries_skips_unrecognised_thai_label_not_yet_mapped(caplog):
    """Defensive floor for `_COUNTRY_GROUP_BY_NAME`: the DW notebook's
    else-branch already collapses every Excel label except 'ในประเทศ'/
    'ต่างประเทศ-อาเซียน' into the STRING 'other' before this code ever reads
    `dbo.country_group`, so a stored value like 'ต่างประเทศ-ยุโรป' should not
    arise via that pipeline today — but this function must not TRUST that
    invariant (a stale row from before the notebook existed, a manual edit,
    or a future notebook change could still land one). Any value outside the
    3 known strings stays SKIPPED + WARNED, never guessed."""
    conn = MagicMock()
    conn.cursor.return_value.fetchall.return_value = [
        ("France", "ต่างประเทศ-ยุโรป"),
        ("Thailand", "domestic"),
    ]
    with caplog.at_level(logging.WARNING):
        rows = fetch_countries(conn)
    assert rows == [{"country": "Thailand", "country_group": 1}]
    assert "ต่างประเทศ-ยุโรป" in caplog.text


def test_fetch_countries_queries_dbo_country_group():
    conn = MagicMock()
    conn.cursor.return_value.fetchall.return_value = []
    fetch_countries(conn)
    sql_text = conn.cursor.return_value.execute.call_args.args[0]
    assert "dbo.country_group" in sql_text
    assert "country" in sql_text and "country_group" in sql_text


def test_fetch_countries_skips_unknown_group_name_with_warning(caplog):
    """A typo'd/new group name in the master must never silently mis-map to
    a per-diem bucket — skip the row (visible gap in the picker) + WARN."""
    conn = MagicMock()
    conn.cursor.return_value.fetchall.return_value = [
        ("Mars", "lunar"),
        ("Thailand", "domestic"),
    ]
    with caplog.at_level(logging.WARNING):
        rows = fetch_countries(conn)
    assert rows == [{"country": "Thailand", "country_group": 1}]
    assert "lunar" in caplog.text


def test_fetch_countries_closes_cursor():
    conn = MagicMock()
    conn.cursor.return_value.fetchall.return_value = []
    fetch_countries(conn)
    conn.cursor.return_value.close.assert_called_once()


# ---------------------------------------------------------------------------
# fetch_travelers — Trip Manager traveler picker, scoped by the COST CENTER
# being edited (2026-08-04): dbo.cc_filler_map -> Filler email(s) -> UNION of
# dbo.v_traveler_picker rows, deduped by empcode. Falls back to the caller's
# own picker rows (no Filler mapping), then the full roster (caller absent
# too) — never an empty list where the old caller-only lookup returned rows.
# ---------------------------------------------------------------------------

def _picker_row(empcode, name, position, email, pick_reason):
    return (empcode, name, position, email, pick_reason)


def test_fetch_travelers_cost_center_scoped_returns_dept_and_manager_rows():
    """One Filler mapped to the cost_center -> its dbo.v_traveler_picker
    rows (dept + manager chain + direct reports), sorted by name, email
    carried through and lower-cased."""
    conn = MagicMock()
    conn.cursor.return_value.fetchall.side_effect = [
        [("suchanyay@chememan.com",)],  # cc_filler_map: 1 filler for the CC
        [
            _picker_row("100002", "สมหญิง สายลม", "Officer", "SomyingS@chememan.com", "same_department"),
            _picker_row("100001", "สมชาย ใจดี", "Manager", "somchai@chememan.com", "manager"),
        ],
    ]
    rows = fetch_travelers(conn, "CC1", "suchanyay@chememan.com")
    assert rows == [
        {"empcode": "100001", "name": "สมชาย ใจดี", "position": "Manager", "email": "somchai@chememan.com"},
        {"empcode": "100002", "name": "สมหญิง สายลม", "position": "Officer", "email": "somyings@chememan.com"},
    ]
    cc_sql = conn.cursor.return_value.execute.call_args_list[0].args
    assert "dbo.cc_filler_map" in cc_sql[0] and "WHERE cost_center = ?" in cc_sql[0]
    assert cc_sql[1] == "CC1"
    picker_sql = conn.cursor.return_value.execute.call_args_list[1].args
    assert "dbo.v_traveler_picker" in picker_sql[0]
    assert "WHERE filler_email IN (?)" in picker_sql[0]
    assert picker_sql[1] == "suchanyay@chememan.com"  # parameterized, lower-cased


def test_fetch_travelers_multi_filler_cc_dedupes_by_empcode_keeping_strongest_reason():
    """2 Fillers mapped to the same cost_center both reach the same
    traveler via different legs — one row survives, the stronger
    pick_reason (manager beats same_department)."""
    conn = MagicMock()
    conn.cursor.return_value.fetchall.side_effect = [
        [("fillera@chememan.com",), ("fillerb@chememan.com",)],
        [
            _picker_row("999", "กลาง คนกลาง", "Officer", "old@chememan.com", "same_department"),
            _picker_row("999", "กลาง คนกลาง", "Officer", "new@chememan.com", "manager"),
        ],
    ]
    rows = fetch_travelers(conn, "CC-MULTI", "fillera@chememan.com")
    assert rows == [{"empcode": "999", "name": "กลาง คนกลาง", "position": "Officer", "email": "new@chememan.com"}]
    picker_sql = conn.cursor.return_value.execute.call_args_list[1].args
    assert "WHERE filler_email IN (?, ?)" in picker_sql[0]
    assert picker_sql[1:] == ("fillera@chememan.com", "fillerb@chememan.com")


def test_fetch_travelers_no_filler_mapping_falls_back_to_caller_picker_rows(caplog):
    """cost_center has no dbo.cc_filler_map row (e.g. an admin browsing a CC
    they don't fill) -> fall back to the CALLER's own picker rows, warned."""
    conn = MagicMock()
    conn.cursor.return_value.fetchall.side_effect = [
        [],  # cc_filler_map: no filler mapped to this CC
        [_picker_row("100001", "สมชาย ใจดี", "Manager", "somchai@chememan.com", "same_department")],
    ]
    with caplog.at_level(logging.WARNING):
        rows = fetch_travelers(conn, "CC-ORPHAN", "admin@chememan.com")
    assert rows == [{"empcode": "100001", "name": "สมชาย ใจดี", "position": "Manager", "email": "somchai@chememan.com"}]
    assert "no dbo.cc_filler_map row" in caplog.text
    caller_picker_sql = conn.cursor.return_value.execute.call_args_list[1].args
    assert caller_picker_sql[1] == "admin@chememan.com"


def test_fetch_travelers_caller_absent_falls_back_to_full_roster(caplog):
    """Neither the CC's Fillers nor the caller are in dbo.v_traveler_picker
    (admin/test account, not an employee at all) -> FULL roster from
    dbo.v_employee_primary + a warning, exactly like before the CC-scoping."""
    conn = MagicMock()
    conn.cursor.return_value.fetchall.side_effect = [
        [],  # cc_filler_map: no filler mapped
        [],  # picker view for the caller: no rows either
        [("100001", "สมชาย ใจดี", "Manager", "somchai@chememan.com")],  # fallback roster
    ]
    with caplog.at_level(logging.WARNING):
        rows = fetch_travelers(conn, "CC-ORPHAN", "admin@example.com")
    assert rows == [{"empcode": "100001", "name": "สมชาย ใจดี", "position": "Manager", "email": "somchai@chememan.com"}]
    assert "full-roster fallback" in caplog.text
    fallback_sql = conn.cursor.return_value.execute.call_args_list[2].args[0]
    assert "dbo.v_employee_primary" in fallback_sql and "email" in fallback_sql


def test_fetch_travelers_filler_mapped_but_zero_picker_rows_falls_back_to_caller():
    """A mapped Filler that matches 0 v_traveler_picker rows (edge case —
    e.g. a stale email) still falls back to the caller, never an empty list."""
    conn = MagicMock()
    conn.cursor.return_value.fetchall.side_effect = [
        [("stale@chememan.com",)],
        [],  # picker rows for the stale filler: none
        [_picker_row("100001", "สมชาย ใจดี", "Manager", "somchai@chememan.com", "manager")],
    ]
    rows = fetch_travelers(conn, "CC1", "caller@chememan.com")
    assert rows == [{"empcode": "100001", "name": "สมชาย ใจดี", "position": "Manager", "email": "somchai@chememan.com"}]
    caller_picker_sql = conn.cursor.return_value.execute.call_args_list[2].args
    assert caller_picker_sql[1] == "caller@chememan.com"


def test_fetch_travelers_coerces_null_name_or_position_to_empty_string():
    """API contract is plain strings — a NULL HR field renders as '' in the
    picker, never null/None."""
    conn = MagicMock()
    conn.cursor.return_value.fetchall.side_effect = [
        [("filler@chememan.com",)],
        [_picker_row("100003", None, None, None, "same_department")],
    ]
    rows = fetch_travelers(conn, "CC1", "filler@chememan.com")
    assert rows == [{"empcode": "100003", "name": "", "position": "", "email": ""}]


def test_fetch_travelers_closes_cursor():
    conn = MagicMock()
    conn.cursor.return_value.fetchall.return_value = []
    fetch_travelers(conn, "CC1", "a@b.com")
    conn.cursor.return_value.close.assert_called_once()
