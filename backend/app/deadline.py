"""Shared submission-deadline / fiscal-year-state gate (ADR-0012, extended
2026-08-08).

Extracted from `app.approval` (A6, the original owner of this check) so the
approval engine's Submit gate and the write path's edit gate (A5) can never
silently drift on timezone, inclusive/exclusive semantics, or the
missing-deadline-row policy. `app.approval.submit_department`,
`app.write_model`'s per-item write guards, and `app.read_model`'s
`merge_budget_rows`/`get_budget_grid` (editable computation) all consult
`fiscal_year_state` — ONE implementation, every call site.

Three-state model (2026-08-08 product decision, jakkaritw — replaces the old
two-state "open"/"past-deadline" view): a fiscal_year with NO
`dbo.submission_deadline` row at all is now **NOT_OPEN**, not silently
"open". Live measurement 2026-08-07: the table holds exactly one row
(fiscal_year 2027) — every other year (2020-2026) was open for anyone to
type into, with no reminder emails either. Reason for the change: data for a
year nobody configured a cutoff for does not come from users typing it in —
the admin imports it (backend script or a future per-year SharePoint
workbook, same shape as the existing approved-budget import; that import is
a separate, not-yet-built feature). Admin may still write in every state.

    | state         | condition                                    | non-admin write |
    |---------------|-----------------------------------------------|-----------------|
    | NOT_OPEN      | no `dbo.submission_deadline` row for the year  | refused          |
    | OPEN          | row exists, today <= `deadline_date` (Bangkok) | allowed          |
    | PAST_DEADLINE | row exists, today > `deadline_date`            | refused          |

NOT_OPEN and PAST_DEADLINE are deliberately DIFFERENT machine codes/messages
(`year_not_open` vs `past_deadline`) — a year that was simply never
configured is not "past its deadline", so they must never collapse into one
error for the caller.
"""
from datetime import date, datetime
from typing import Literal
from zoneinfo import ZoneInfo

import pyodbc

_BANGKOK_TZ = ZoneInfo("Asia/Bangkok")

YEAR_NOT_OPEN: Literal["not_open"] = "not_open"
YEAR_OPEN: Literal["open"] = "open"
YEAR_PAST_DEADLINE: Literal["past_deadline"] = "past_deadline"
FiscalYearState = Literal["not_open", "open", "past_deadline"]


class PastDeadlineError(PermissionError):
    """A normal (non-admin) user tried to submit or edit a fiscal_year whose
    `dbo.submission_deadline` row exists but is already past — the cycle is
    closed to users (ADR-0012: "after the deadline the admin handles
    everything"); only admin may act past this point. Distinct from
    `YearNotOpenError` below (no deadline row configured at all)."""


class YearNotOpenError(PermissionError):
    """A normal (non-admin) user tried to submit or edit a fiscal_year with
    NO `dbo.submission_deadline` row configured at all (2026-08-08 product
    decision, jakkaritw) — see the module docstring's 3-state table. Distinct
    from `PastDeadlineError` (a row exists and its date has passed): this
    year was simply never opened for web entry, so the message must not read
    as "you missed the deadline". Only admin may write to such a year; the
    Thai message is deliberately final (no client-side translation needed,
    same convention as `app.approval.DepartmentEmptyError`)."""


def bangkok_today() -> date:
    """Anchor "today" to Asia/Bangkok explicitly instead of the server-local
    `date.today()` — a server running in a different timezone (e.g. UTC)
    would flip the post-deadline boundary by hours."""
    return datetime.now(_BANGKOK_TZ).date()


def fiscal_year_state(conn: pyodbc.Connection, fiscal_year: int) -> FiscalYearState:
    """ONE query, ONE source of truth for where `fiscal_year` sits relative
    to `dbo.submission_deadline` (see the module docstring's 3-state table).
    Every consumer that needs to know "is this year open for a non-admin to
    write" calls this — never a second, independently-written query — so the
    write gate, A6's submit gate, and the read-side editable lock can never
    drift apart on the answer.

    Inclusive of the deadline day itself — only the day AFTER `deadline_date`
    counts as PAST_DEADLINE (unchanged S1 gate semantics, still Bangkok-
    anchored via `bangkok_today()`)."""
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT deadline_date FROM dbo.submission_deadline WHERE fiscal_year = ?", fiscal_year)
        row = cursor.fetchone()
    finally:
        cursor.close()
    if row is None:
        return YEAR_NOT_OPEN
    return YEAR_PAST_DEADLINE if bangkok_today() > row[0] else YEAR_OPEN


def is_post_deadline(conn: pyodbc.Connection, fiscal_year: int) -> bool:
    """True only for PAST_DEADLINE (row exists, today > deadline_date) — a
    thin, semantics-preserving projection of `fiscal_year_state` kept for
    every existing caller that only ever cared about that one question
    (`jobs/auto_submit.py`, `app.approval`'s admin post-deadline-override
    branch). A missing row is NOT_OPEN, not PAST_DEADLINE, so this still
    returns `False` for it — exactly the same answer as before the 2026-08-08
    3-state extension; nothing that calls this function changes behavior."""
    return fiscal_year_state(conn, fiscal_year) == YEAR_PAST_DEADLINE
