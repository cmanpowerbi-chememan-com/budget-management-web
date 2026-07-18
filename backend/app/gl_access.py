"""GL `dbo.gl_group` master-membership + `edit_by` admin-only lock — shared
GL-master lookups.

Two independent rules live here, both keyed off `dbo.gl_group`:

- **Master-membership** (`fetch_master_gl_codes`, 2026-07-18 product
  decision by jakkaritw): a GL account that appears in SAP actuals (or
  anywhere) but is NOT a row in `dbo.gl_group` must be HIDDEN from the
  budget grid entirely — never shown, not even as a read-only reference row
  (reverses the earlier "add-later reference" behavior). Role-independent:
  applies to every caller, admin and non-admin alike.
- **`edit_by` admin-only lock** (design v2, 2026-07-17, flag-gated by
  `Settings.gl_edit_by_enabled`): 13 live GLs on `dbo.gl_group` carry
  `edit_by='admin'` (Insurance Premium, Employee benefits severance,
  Depreciation) and must never be visible to a non-admin in any API
  response, and never writable by a non-admin.

Extracted to its own module (same rationale as `app/deadline.py`) so every
call site — `reference_data.fetch_gl_accounts` (list), `read_model.py`
(master filter + admin-GL row strip), `write_model.py` (write-time 403) —
can never disagree on what counts as a master GL or an admin GL. Admin-GL
rows are approved-on-save (ADR-0024) and never enter
`budget.approval_status` at all, so `approval.py` has no call site here.
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


def fetch_master_gl_codes(conn: pyodbc.Connection) -> frozenset[str]:
    """The full set of `gl_code` values that exist in the GL master
    (`dbo.gl_group`). Used by `read_model.get_budget_grid` to drop any row
    whose `gl_account` is not in this set, for EVERY caller — this rule is
    not role-based (unlike the admin-GL strip below)."""
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT gl_code FROM dbo.gl_group")
        rows = cursor.fetchall()
    finally:
        cursor.close()
    return frozenset(code for (code,) in rows)


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
