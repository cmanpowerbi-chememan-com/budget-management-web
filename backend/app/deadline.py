"""Shared submission-deadline gate (ADR-0012).

Extracted from `app.approval` (A6, the original owner of this check) so the
approval engine's Submit gate and the write path's edit gate (A5) can never
silently drift on timezone, inclusive/exclusive semantics, or the
missing-deadline-row policy. Both `app.approval.submit_department` and
`app.write_model`'s per-item write guards call `is_post_deadline` — one
implementation, two call sites.
"""
from datetime import date, datetime
from zoneinfo import ZoneInfo

import pyodbc

_BANGKOK_TZ = ZoneInfo("Asia/Bangkok")


class PastDeadlineError(PermissionError):
    """A normal (non-admin) user tried to submit or edit past
    `dbo.submission_deadline` for this fiscal_year — the cycle is closed to
    users (ADR-0012: "after the deadline the admin handles everything");
    only admin may act past this point."""


def bangkok_today() -> date:
    """Anchor "today" to Asia/Bangkok explicitly instead of the server-local
    `date.today()` — a server running in a different timezone (e.g. UTC)
    would flip the post-deadline boundary by hours."""
    return datetime.now(_BANGKOK_TZ).date()


def is_post_deadline(conn: pyodbc.Connection, fiscal_year: int) -> bool:
    """No `dbo.submission_deadline` row for this fiscal_year -> treat as OPEN
    (never silently lock a year nobody configured a cutoff for). Inclusive of
    the deadline day itself — only the day AFTER `deadline_date` counts as
    post-deadline."""
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT deadline_date FROM dbo.submission_deadline WHERE fiscal_year = ?", fiscal_year)
        row = cursor.fetchone()
    finally:
        cursor.close()
    if row is None:
        return False
    return bangkok_today() > row[0]
