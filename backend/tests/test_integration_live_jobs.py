"""Live-DB integration tests for the A11 scheduled jobs (`jobs.auto_submit`,
`jobs.auto_escalate`) against the REAL, consolidated Fabric SQL Database
(ADR-0023).

Kept in its OWN file — `test_integration_live.py` is being edited by a
parallel A8 agent (per this task's instructions); this file never touches
it, `frontend/`, `read_model.py`, `reference_data.py`,
`routers/reference.py`, or `main.py`.

SAFETY (never-cut):
- Every row this file writes uses `fiscal_year = 2096` — a sentinel year
  distinct from every other suite's sentinel (2097 = A5 deadline lock,
  2099 = A4/A5/A6) and from any real planning year.
- `department = "ZZ_TEST_DEPT_A11_NEVER_REAL"` (same naming convention as
  A6's `FAKE_DEPARTMENT`) — cannot collide with a real ฝ่าย name.
- Cleanup runs in a `finally` for every test, deletes every
  `fiscal_year = 2096` row across all 5 `budget.*` tables AND
  `dbo.submission_deadline`, then verifies 0 rows remain.
- `dbo.cc_filler_map` / `dbo.v_employee_budget_01` are READ-ONLY here (one
  real filler_email is discovered, never written).
- No real email is ever sent: every job call passes `notifications_dry_run=True`.

Skipped by default (`pytest.ini`: `addopts = -m "not integration"`). Run:
    pytest -m integration tests/test_integration_live_jobs.py -v
"""
from datetime import date, datetime, timedelta, timezone

import pyodbc
import pytest

from app.approval import PENDING_APPROVER1, PENDING_APPROVER2, PENDING_APPROVER3
from app.db import get_fabric_conn
from jobs.auto_escalate import run as run_auto_escalate
from jobs.auto_submit import run as run_auto_submit

FISCAL_YEAR = 2096  # sentinel — distinct from 2097 (A5 deadline) / 2099 (A4/A5/A6)
FAKE_DEPARTMENT = "ZZ_TEST_DEPT_A11_NEVER_REAL"
SENTINEL_CC = "ZZ_TEST_CC_A11"
SENTINEL_GL = "ZZ_TEST_GL_A11"

_BUDGET_TABLES_BY_FISCAL_YEAR = (
    "budget.pending_budget_detail",
    "budget.budget_trip",
    "budget.pending_budget",
    "budget.approval_log",
    "budget.approval_status",
)


def _discover_real_filler_email(conn: pyodbc.Connection) -> str:
    """A real, live `filler_email` from `dbo.cc_filler_map` — confirmed
    (project memory) to be 100% covered by `dbo.v_employee_budget_01`, so
    `resolve_chain` always resolves a genuine manager chain for it, never
    the "not found" fallback path (that path is already covered by mocked
    unit tests)."""
    cursor = conn.cursor()
    try:
        cursor.execute(
            "SELECT TOP 1 filler_email FROM dbo.cc_filler_map "
            "WHERE filler_email IS NOT NULL AND LTRIM(RTRIM(filler_email)) <> '' ORDER BY filler_email"
        )
        row = cursor.fetchone()
    finally:
        cursor.close()
    assert row is not None, "no usable filler_email found in dbo.cc_filler_map"
    return row[0]


def _insert_sentinel_pending_row(conn: pyodbc.Connection, editor_email: str, updated_at: datetime) -> None:
    """One zero-amount `budget.pending_budget` row under the sentinel CC/GL,
    department pre-set to FAKE_DEPARTMENT (mirrors the raw-INSERT pattern
    `test_integration_live.py`'s own A6 Template-2 test already uses — the
    discovery query only reads department/_user/_updated_at, so a synthetic
    cost_center/gl_account is safe here)."""
    cursor = conn.cursor()
    try:
        cursor.execute(
            """
            INSERT INTO budget.pending_budget
                (cost_center, gl_account, fiscal_year,
                 m01, m02, m03, m04, m05, m06, m07, m08, m09, m10, m11, m12,
                 total_year, template, department, _user, _updated_at)
            VALUES (?, ?, ?, 0,0,0,0,0,0,0,0,0,0,0,0, 0, 'USER', ?, ?, ?)
            """,
            SENTINEL_CC, SENTINEL_GL, FISCAL_YEAR, FAKE_DEPARTMENT, editor_email, updated_at,
        )
        conn.commit()
    finally:
        cursor.close()


def _insert_sentinel_approval_status_row(
    conn: pyodbc.Connection, status: str, submitted_at: datetime, approver1_empcode: str,
) -> None:
    """A raw INSERT (not via `submit_department`, which always stamps
    `submitted_at = now()`) — the only way to create a row whose current
    step is already >=30 days old without waiting 30 real days."""
    cursor = conn.cursor()
    try:
        cursor.execute(
            """
            INSERT INTO budget.approval_status
                (department, fiscal_year, status, submitter_empcode, submitter_email, submitted_at,
                 approver1_empcode, _updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            FAKE_DEPARTMENT, FISCAL_YEAR, status, "999999", "sentinel-submitter@chememan.com", submitted_at,
            approver1_empcode, submitted_at,
        )
        conn.commit()
    finally:
        cursor.close()


def _insert_deadline_row(conn: pyodbc.Connection, deadline_date_value: date, reminder_date_value: date) -> None:
    """Mirrors `test_integration_live.py`'s A5-lock sentinel pattern
    (`_insert_past_deadline_row`) — all 9 live columns are NOT NULL
    (verified via INFORMATION_SCHEMA.COLUMNS there); only
    fiscal_year/deadline_date matter to `is_post_deadline`."""
    cursor = conn.cursor()
    try:
        cursor.execute(
            """
            INSERT INTO dbo.submission_deadline
                (fiscal_year, closing_date, closing_month, closing_year, reminder_day,
                 deadline_date, reminder_date, _load_dt, _load_dttm)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            FISCAL_YEAR, deadline_date_value.day, deadline_date_value.month, deadline_date_value.year, 15,
            deadline_date_value, reminder_date_value, deadline_date_value,
            datetime.combine(deadline_date_value, datetime.min.time()),
        )
        conn.commit()
    finally:
        cursor.close()


def _cleanup_sentinel(conn: pyodbc.Connection) -> None:
    """Deletes every `fiscal_year = 2096` row across all 5 `budget.*` tables
    and `dbo.submission_deadline`, then verifies 0 rows remain in each."""
    cursor = conn.cursor()
    try:
        for table in _BUDGET_TABLES_BY_FISCAL_YEAR:
            cursor.execute(f"DELETE FROM {table} WHERE fiscal_year = ?", FISCAL_YEAR)
        cursor.execute("DELETE FROM dbo.submission_deadline WHERE fiscal_year = ?", FISCAL_YEAR)
        conn.commit()
    finally:
        cursor.close()

    cursor = conn.cursor()
    try:
        leftover: dict[str, int] = {}
        for table in _BUDGET_TABLES_BY_FISCAL_YEAR:
            cursor.execute(f"SELECT COUNT(*) FROM {table} WHERE fiscal_year = ?", FISCAL_YEAR)
            count = cursor.fetchone()[0]
            if count:
                leftover[table] = count
        cursor.execute("SELECT COUNT(*) FROM dbo.submission_deadline WHERE fiscal_year = ?", FISCAL_YEAR)
        count = cursor.fetchone()[0]
        if count:
            leftover["dbo.submission_deadline"] = count
    finally:
        cursor.close()
    assert not leftover, f"cleanup left rows at fiscal_year={FISCAL_YEAR}: {leftover}"


@pytest.mark.integration
def test_auto_submit_dry_run_then_execute_then_idempotent_live() -> None:
    """End-to-end against the real DB: dry-run lists the sentinel
    department without writing, --execute submits it into the real chain
    (resolved from a REAL filler's REAL manager), and a 2nd real run is a
    no-op (idempotent — the department now has an approval_status row)."""
    with get_fabric_conn() as conn:
        editor_email = _discover_real_filler_email(conn)

    try:
        with get_fabric_conn() as conn:
            _insert_deadline_row(conn, date(2020, 1, 1), date(2019, 12, 17))
            _insert_sentinel_pending_row(conn, editor_email, datetime.now(timezone.utc))

        dry_count = run_auto_submit(FISCAL_YEAR, dry_run=True, notifications_dry_run=True)
        assert dry_count == 1, "dry-run should have listed exactly the 1 sentinel department"

        with get_fabric_conn() as verify_conn:
            cursor = verify_conn.cursor()
            try:
                cursor.execute(
                    "SELECT COUNT(*) FROM budget.approval_status WHERE department = ? AND fiscal_year = ?",
                    FAKE_DEPARTMENT, FISCAL_YEAR,
                )
                assert cursor.fetchone()[0] == 0, "dry-run must not have written an approval_status row"
            finally:
                cursor.close()

        executed_count = run_auto_submit(FISCAL_YEAR, dry_run=False, notifications_dry_run=True)
        assert executed_count == 1, "expected exactly 1 department to be auto-submitted"

        with get_fabric_conn() as verify_conn:
            cursor = verify_conn.cursor()
            try:
                cursor.execute(
                    "SELECT status FROM budget.approval_status WHERE department = ? AND fiscal_year = ?",
                    FAKE_DEPARTMENT, FISCAL_YEAR,
                )
                row = cursor.fetchone()
            finally:
                cursor.close()
        assert row is not None, "auto_submit_department should have created a real approval_status row"
        assert row[0] in {PENDING_APPROVER1, PENDING_APPROVER2, PENDING_APPROVER3}, (
            f"expected a PENDING_* status (never straight to APPROVED), got {row[0]}"
        )

        second_run_count = run_auto_submit(FISCAL_YEAR, dry_run=False, notifications_dry_run=True)
        assert second_run_count == 0, "idempotent: a 2nd real run must not double-submit the same department"
    finally:
        with get_fabric_conn() as cleanup_conn:
            _cleanup_sentinel(cleanup_conn)


@pytest.mark.integration
def test_auto_escalate_advances_a_stale_sentinel_row_live() -> None:
    """A `budget.approval_status` row whose PENDING_APPROVER1 step has sat
    unactioned for 31 days (raw-inserted -- `submit_department` always
    stamps `submitted_at = now()`, so a real 30-day-old row can only be
    built this way in a test) advances to PENDING_APPROVER2 via the real
    job, against the real database."""
    stale_submitted_at = datetime.now(timezone.utc) - timedelta(days=31)

    try:
        with get_fabric_conn() as conn:
            _insert_sentinel_approval_status_row(
                conn, status=PENDING_APPROVER1, submitted_at=stale_submitted_at, approver1_empcode="999999-unknown",
            )

        escalated_count = run_auto_escalate(FISCAL_YEAR, dry_run=False, notifications_dry_run=True)
        assert escalated_count == 1, "expected exactly 1 stale row to be escalated"

        with get_fabric_conn() as verify_conn:
            cursor = verify_conn.cursor()
            try:
                cursor.execute(
                    "SELECT status, approver1_actioned_at FROM budget.approval_status "
                    "WHERE department = ? AND fiscal_year = ?",
                    FAKE_DEPARTMENT, FISCAL_YEAR,
                )
                row = cursor.fetchone()
            finally:
                cursor.close()
        assert row is not None
        assert row[0] == PENDING_APPROVER2, f"expected PENDING_APPROVER2 after escalation, got {row[0]}"
        assert row[1] is not None, "approver1_actioned_at should be stamped by the escalation"

        # Idempotent per 30-day window: the just-escalated row's new step
        # started "now" (0 days old) -- a 2nd run right after must not
        # escalate it again.
        second_run_count = run_auto_escalate(FISCAL_YEAR, dry_run=False, notifications_dry_run=True)
        assert second_run_count == 0, "the freshly-escalated row must not be re-escalated immediately"
    finally:
        with get_fabric_conn() as cleanup_conn:
            _cleanup_sentinel(cleanup_conn)
