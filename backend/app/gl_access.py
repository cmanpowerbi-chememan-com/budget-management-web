"""GL `edit_by` admin-only lock (design v2, 2026-07-17, flag-gated by
`Settings.gl_edit_by_enabled`) — shared normalize + admin-GL lookups.

13 live GLs on `dbo.gl_group` carry `edit_by='admin'` (Insurance Premium,
Employee benefits severance, Depreciation) and must never be visible to a
non-admin in any API response, and never writable by a non-admin. Extracted
to its own module (same rationale as `app/deadline.py`) so the 4 call sites —
`reference_data.fetch_gl_accounts` (list), `read_model.merge_budget_rows`
(row strip), `write_model.py` (write-time 403), `approval.submit_department`
(normal-chain guard) — can never disagree on what counts as an admin GL.
"""
from typing import Literal

import pyodbc

EditBy = Literal["user", "admin"]


def normalize_edit_by(raw: str | None) -> EditBy:
    """Only a literal 'admin' (case-insensitive, trimmed) locks a GL to
    admin-only; anything else (None, '', unexpected data) normalizes to
    'user' — never fail-closed-lock on unexpected data."""
    if raw is not None and raw.strip().lower() == "admin":
        return "admin"
    return "user"


def fetch_admin_gl_codes(conn: pyodbc.Connection) -> frozenset[str]:
    """The current set of `gl_code` values locked to admin-only. Used by
    `read_model.get_budget_grid` (once per request, to strip rows for a
    non-admin caller)."""
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT gl_code, edit_by FROM dbo.gl_group")
        rows = cursor.fetchall()
    finally:
        cursor.close()
    return frozenset(code for code, edit_by in rows if normalize_edit_by(edit_by) == "admin")


def is_admin_only_gl(conn: pyodbc.Connection, gl_account: str) -> bool:
    """Cheap single-GL check (one row, not the full admin-GL set) — used as
    a defensive guard on the A9 subform read path (`GET /budget/detail`),
    which always addresses exactly one `gl_account` at a time. A GL not
    found in `dbo.gl_group` at all is never treated as admin-only (fail-open,
    matching this module's other "unknown data never locks" defaults)."""
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT edit_by FROM dbo.gl_group WHERE gl_code = ?", gl_account)
        row = cursor.fetchone()
    finally:
        cursor.close()
    return row is not None and normalize_edit_by(row[0]) == "admin"


def department_has_pending_admin_gl_rows(conn: pyodbc.Connection, department: str, fiscal_year: int) -> bool:
    """True when `budget.pending_budget` has any row for `(department,
    fiscal_year)` whose GL is admin-only. Used by
    `approval.submit_department`'s normal-chain guard: admin-GL rows must
    never enter the normal approval chain (the approver can never see them,
    per rule 1 — they would stick forever with no reviewer able to act on
    them); they must go through the admin direct-approve door instead
    (ADR-0012)."""
    cursor = conn.cursor()
    try:
        cursor.execute(
            """
            SELECT TOP 1 1
            FROM budget.pending_budget pb
            JOIN dbo.gl_group g ON pb.gl_account = g.gl_code
            WHERE pb.department = ? AND pb.fiscal_year = ?
                AND LOWER(LTRIM(RTRIM(g.edit_by))) = 'admin'
            """,
            department, fiscal_year,
        )
        row = cursor.fetchone()
    finally:
        cursor.close()
    return row is not None
