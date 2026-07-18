"""Unit tests for app.gl_access — the GL `edit_by` admin-only lock (design
v2, flag-gated). Shared by reference_data.py (list), read_model.py (row
strip), and write_model.py (write-time 403) so all 3 call sites can never
disagree on what counts as an admin GL (same extraction rationale as
app/deadline.py). Admin-GL rows never enter `budget.approval_status`
(ADR-0024) — approval.py has no call site here. DB always mocked, no live
connection."""
from unittest.mock import MagicMock

from app.gl_access import fetch_admin_gl_codes, fetch_master_gl_codes, is_admin_only_gl, normalize_edit_by


# ---------------------------------------------------------------------------
# normalize_edit_by — only a literal 'admin' (case-insensitive, trimmed) locks
# ---------------------------------------------------------------------------

def test_normalize_edit_by_none_is_user():
    assert normalize_edit_by(None) == "user"


def test_normalize_edit_by_empty_string_is_user():
    assert normalize_edit_by("") == "user"


def test_normalize_edit_by_plain_admin_is_admin():
    assert normalize_edit_by("admin") == "admin"


def test_normalize_edit_by_is_case_insensitive():
    assert normalize_edit_by("Admin") == "admin"
    assert normalize_edit_by("ADMIN") == "admin"


def test_normalize_edit_by_trims_whitespace():
    assert normalize_edit_by("  admin  ") == "admin"


def test_normalize_edit_by_plain_user_is_user():
    assert normalize_edit_by("user") == "user"


def test_normalize_edit_by_garbage_falls_back_to_user():
    """Never fail-closed-lock on unexpected/garbage data — anything that is
    not exactly 'admin' after normalizing is 'user'."""
    assert normalize_edit_by("administrator") == "user"
    assert normalize_edit_by("ADMINX") == "user"
    assert normalize_edit_by("xyz") == "user"


# ---------------------------------------------------------------------------
# fetch_admin_gl_codes
# ---------------------------------------------------------------------------

def test_fetch_admin_gl_codes_returns_only_normalized_admin_rows():
    conn = MagicMock()
    conn.cursor.return_value.fetchall.return_value = [
        ("GL1", "admin"),
        ("GL2", "user"),
        ("GL3", "Admin"),
        ("GL4", None),
        ("GL5", "  ADMIN  "),
    ]
    codes = fetch_admin_gl_codes(conn)
    assert codes == frozenset({"GL1", "GL3", "GL5"})


def test_fetch_admin_gl_codes_queries_dbo_gl_group():
    conn = MagicMock()
    conn.cursor.return_value.fetchall.return_value = []
    fetch_admin_gl_codes(conn)
    sql_text = conn.cursor.return_value.execute.call_args.args[0]
    assert "dbo.gl_group" in sql_text
    assert "gl_code" in sql_text and "edit_by" in sql_text


def test_fetch_admin_gl_codes_closes_cursor():
    conn = MagicMock()
    conn.cursor.return_value.fetchall.return_value = []
    fetch_admin_gl_codes(conn)
    conn.cursor.return_value.close.assert_called_once()


# ---------------------------------------------------------------------------
# fetch_master_gl_codes — GL master-membership rule (2026-07-18 product
# decision by jakkaritw: a GL not in dbo.gl_group is HIDDEN entirely, not
# shown as a read-only reference row — reverses the earlier add-later-
# reference behavior). Role-independent: applies to admin AND non-admin.
# ---------------------------------------------------------------------------

def test_fetch_master_gl_codes_returns_all_gl_codes():
    conn = MagicMock()
    conn.cursor.return_value.fetchall.return_value = [("GL1",), ("GL2",), ("GL3",)]
    codes = fetch_master_gl_codes(conn)
    assert codes == frozenset({"GL1", "GL2", "GL3"})


def test_fetch_master_gl_codes_queries_dbo_gl_group():
    conn = MagicMock()
    conn.cursor.return_value.fetchall.return_value = []
    fetch_master_gl_codes(conn)
    sql_text = conn.cursor.return_value.execute.call_args.args[0]
    assert "dbo.gl_group" in sql_text
    assert "gl_code" in sql_text


def test_fetch_master_gl_codes_closes_cursor():
    conn = MagicMock()
    conn.cursor.return_value.fetchall.return_value = []
    fetch_master_gl_codes(conn)
    conn.cursor.return_value.close.assert_called_once()


def test_fetch_master_gl_codes_empty_master_returns_empty_set():
    conn = MagicMock()
    conn.cursor.return_value.fetchall.return_value = []
    assert fetch_master_gl_codes(conn) == frozenset()


# ---------------------------------------------------------------------------
# is_admin_only_gl — cheap single-GL lookup (subform read-path defensive guard)
# ---------------------------------------------------------------------------

def test_is_admin_only_gl_true_for_admin_row():
    conn = MagicMock()
    conn.cursor.return_value.fetchone.return_value = ("admin",)
    assert is_admin_only_gl(conn, "GL1") is True


def test_is_admin_only_gl_false_for_user_row():
    conn = MagicMock()
    conn.cursor.return_value.fetchone.return_value = ("user",)
    assert is_admin_only_gl(conn, "GL1") is False


def test_is_admin_only_gl_false_when_gl_not_found():
    conn = MagicMock()
    conn.cursor.return_value.fetchone.return_value = None
    assert is_admin_only_gl(conn, "NOPE") is False


def test_is_admin_only_gl_closes_cursor():
    conn = MagicMock()
    conn.cursor.return_value.fetchone.return_value = None
    is_admin_only_gl(conn, "GL1")
    conn.cursor.return_value.close.assert_called_once()
