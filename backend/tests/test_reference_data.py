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
# fetch_travelers — Trip Manager traveler picker (full roster fallback)
# ---------------------------------------------------------------------------

def test_fetch_travelers_maps_full_roster_from_v_employee_primary():
    """Full roster from dbo.v_employee_primary — the SAME view
    write_model._lookup_traveler validates against, so every pickable
    traveler is guaranteed save-able. (dept→employee filtering proven
    unreliable live 2026-07-17: cc_filler_map.department matches
    employee org_name_en for only 35/114 ฝ่าย.)"""
    conn = MagicMock()
    conn.cursor.return_value.fetchall.return_value = [
        ("100001", "สมชาย ใจดี", "Manager"),
        ("100002", "สมหญิง สายลม", "Officer"),
    ]
    rows = fetch_travelers(conn)
    assert rows == [
        {"empcode": "100001", "name": "สมชาย ใจดี", "position": "Manager"},
        {"empcode": "100002", "name": "สมหญิง สายลม", "position": "Officer"},
    ]
    sql_text = conn.cursor.return_value.execute.call_args.args[0]
    assert "dbo.v_employee_primary" in sql_text
    assert "employee_code" in sql_text
    assert "full_name_th" in sql_text
    assert "job_level_name_en" in sql_text
    assert "ORDER BY full_name_th" in sql_text


def test_fetch_travelers_coerces_null_name_or_position_to_empty_string():
    """API contract is plain strings — a NULL HR field renders as '' in the
    picker, never null/None."""
    conn = MagicMock()
    conn.cursor.return_value.fetchall.return_value = [("100003", None, None)]
    rows = fetch_travelers(conn)
    assert rows == [{"empcode": "100003", "name": "", "position": ""}]


def test_fetch_travelers_closes_cursor():
    conn = MagicMock()
    conn.cursor.return_value.fetchall.return_value = []
    fetch_travelers(conn)
    conn.cursor.return_value.close.assert_called_once()
