"""Unit tests for app.reference_data — GL-account list (A8 "+ เพิ่ม
transaction" picker) and the caller's department/CC hierarchy (A8 ฝ่าย
picker). DB always mocked, no live connection."""
from unittest.mock import MagicMock

from app.reference_data import fetch_departments, fetch_gl_accounts


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
