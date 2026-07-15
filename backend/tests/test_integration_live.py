"""Live-DB integration tests — the FIRST tests that run against the real,
consolidated Fabric SQL Database (ADR-0023: `budget.*` transactional +
`dbo.*` masters, same DB).

Why this file exists: the A5 gate found that `conn.commit()` ran BEFORE
`_recompute_parent_cell`, so a special-GL parent cell's total was silently
rolled back on connection close while the API still returned 200. That bug
was fixed and mock-verified only. This file proves it on the REAL database:
save Entertainment 1,000 -> the API says ok AND the parent cell is really
1,000 when read back on a FRESH connection.

Extended 2026-07-16 to cover the A4 read path (`app.read_model`) and the SAP
read-through (`app.sap`) — both had NEVER executed against a real database
before this pass. Introspecting `INFORMATION_SCHEMA.COLUMNS` live found the
A4 read path's column assumptions already matched the real `dbo.board_budget`
/ `budget.pending_budget` tables (the earlier A5 live fix had already
corrected the shared `status`-column bug). It DID find one new bug in
`app.sap.fetch_sap_actuals`: `conn.cursor()` was called OUTSIDE the
try/except, so a connection-level failure (closed connection, dropped
session) raised a raw `pyodbc.Error` instead of `SapActualsFetchError` —
fixed by moving `cursor = conn.cursor()` inside the try, mock-regression-
tested in `test_sap.py`, and proven live in
`test_sap_failure_is_loud_not_silent` below.

Skipped by default (`pytest.ini`: `addopts = -m "not integration"`). Run
explicitly:
    pytest -m integration -v

SAFETY (never-cut):
- Every row this file writes uses `fiscal_year = 2099` — a sentinel year
  that can never collide with real budget data (planning years are the
  current year +/- a handful, never 2099).
- Cleanup runs in a `finally` for every test that writes, deletes every
  `fiscal_year = 2099` row across the 3 transactional tables, and verifies
  afterwards that 0 rows remain at that year.
- `dbo.*` (masters, employee views) is READ-ONLY in this file — no insert,
  update, or delete ever targets a `dbo.*` table here.
- Nothing outside `fiscal_year = 2099` is ever touched.

Real cc/filler pair and Entertainment GL code are DISCOVERED from the live
DB at fixture setup, never hardcoded — the SharePoint-synced masters can
change on their own sync cadence.
"""
import threading
from datetime import date, datetime, timezone

import pyodbc
import pytest
from fastapi.testclient import TestClient

import app.sap as sap_module
from app.approval import (
    APPROVED,
    NIPAPORN_EMPCODE,
    PENDING_APPROVER1,
    PENDING_APPROVER2,
    PENDING_APPROVER3,
    REJECTED,
    WARAPORN_EMPCODE,
    ConcurrentApprovalError,
    NotCurrentApproverError,
    approve_department,
    reject_department,
    resolve_chain,
    submit_department,
)
from app.auth import get_current_user_email
from app.db import get_fabric_conn, get_gold_conn
from app.main import app as fastapi_app
from app.read_model import fetch_board_pending_rows, fetch_cc_dims, get_budget_grid
from app.rls import resolve_scope
from app.sap import MONTH_COLUMNS, SapActualsFetchError, fetch_sap_actuals
from app.special_gl import SPECIAL_GL_GROUPS
from app.write_model import (
    EXCLUDED_COST_CENTERS,
    TRAVEL_GL_BY_TYPE_SIDE,
    DetailLineInput,
    PendingRowInput,
    TripInput,
    delete_detail_line,
    delete_trip,
    save_detail_lines,
    save_pending_rows,
    save_trip,
)

FISCAL_YEAR = 2099  # sentinel — never a real planning year


def _discover_cc_filler(conn: pyodbc.Connection) -> tuple[str, str]:
    """Return a real (cost_center, filler_email) pair from `dbo.cc_filler_map`
    whose cost_center is NOT on the structural exclusion list."""
    placeholders = ", ".join("?" for _ in EXCLUDED_COST_CENTERS)
    cursor = conn.cursor()
    try:
        cursor.execute(
            f"""
            SELECT TOP 1 cost_center, filler_email
            FROM dbo.cc_filler_map
            WHERE filler_email IS NOT NULL AND LTRIM(RTRIM(filler_email)) <> ''
              AND cost_center NOT IN ({placeholders})
            ORDER BY cost_center
            """,
            *EXCLUDED_COST_CENTERS,
        )
        row = cursor.fetchone()
    finally:
        cursor.close()
    assert row is not None, "no usable (cost_center, filler_email) pair found in dbo.cc_filler_map"
    return row[0], row[1]


def _discover_entertainment_gl(conn: pyodbc.Connection) -> str:
    """Return a real Entertainment GL code from `dbo.gl_group`.

    Uses the column names verified live 2026-07-15: `gl_code` + `gl_group`
    (NOT `group_name` — see the fix + docstring note in `write_model.py`).
    """
    cursor = conn.cursor()
    try:
        cursor.execute(
            "SELECT TOP 1 gl_code FROM dbo.gl_group WHERE gl_group = 'Entertainment' ORDER BY gl_code"
        )
        row = cursor.fetchone()
    finally:
        cursor.close()
    assert row is not None, "no Entertainment GL code found in dbo.gl_group"
    return row[0]


def _discover_non_special_gl(conn: pyodbc.Connection) -> str:
    """Return a real GL code whose `gl_group` is NOT one of the 6 special-GL
    groups (ADR-0005) — i.e. one `save_pending_rows` (plain cell edit)
    accepts without raising `SpecialGlDirectEditError`."""
    placeholders = ", ".join("?" for _ in SPECIAL_GL_GROUPS)
    cursor = conn.cursor()
    try:
        cursor.execute(
            f"SELECT TOP 1 gl_code FROM dbo.gl_group WHERE gl_group NOT IN ({placeholders}) ORDER BY gl_code",
            *SPECIAL_GL_GROUPS,
        )
        row = cursor.fetchone()
    finally:
        cursor.close()
    assert row is not None, "no non-special GL code found in dbo.gl_group"
    return row[0]


def _discover_board_year(conn: pyodbc.Connection) -> int:
    """Return the most recent `fiscal_year` present in `dbo.board_budget` —
    never hardcoded, `board_budget` is a yearly SharePoint-drop master that
    rolls forward every year (ADR-0021)."""
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT DISTINCT fiscal_year FROM dbo.board_budget ORDER BY fiscal_year DESC")
        row = cursor.fetchone()
    finally:
        cursor.close()
    assert row is not None, "dbo.board_budget has no rows — cannot discover a board year"
    return row[0]


def _discover_grid_filler(conn: pyodbc.Connection, board_ccs: set[str]) -> str:
    """Return a filler email for the live `get_budget_grid` test.

    Prefers a manager-filler whose See-only cost centers (See minus Fill)
    overlap real `board_budget` rows, so the RLS "See-only rows are
    non-editable" assertion is exercised on real rows instead of holding
    vacuously; falls back to any filler with a non-empty Fill scope if
    today's master data has no such manager-filler."""
    cursor = conn.cursor()
    try:
        cursor.execute(
            "SELECT DISTINCT filler_email FROM dbo.cc_filler_map "
            "WHERE filler_email IS NOT NULL AND LTRIM(RTRIM(filler_email)) <> ''"
        )
        emails = [r[0] for r in cursor.fetchall()]
    finally:
        cursor.close()

    fallback: str | None = None
    for email in emails:
        scope = resolve_scope(email, conn)
        if not scope.fill_cost_centers:
            continue
        if fallback is None:
            fallback = email
        see_only = set(scope.see_cost_centers) - set(scope.fill_cost_centers)
        if see_only & board_ccs:
            return email
    assert fallback is not None, "no filler with a non-empty Fill scope found in dbo.cc_filler_map"
    return fallback


def _discover_traveler_with_a_configured_rate(conn: pyodbc.Connection) -> str:
    """Return a real employee_code whose job_level_name_en HAS a matching row
    in dbo.per_diem_rate (i.e. not e.g. 'N/A') — used to exercise a real
    per-diem calculation end to end (D1)."""
    cursor = conn.cursor()
    try:
        cursor.execute(
            "SELECT TOP 1 e.employee_code FROM dbo.v_employee_primary e "
            "JOIN dbo.per_diem_rate r ON r.job_level = e.job_level_name_en "
            "ORDER BY e.employee_code"
        )
        row = cursor.fetchone()
    finally:
        cursor.close()
    assert row is not None, "no traveler found whose job_level has a matching dbo.per_diem_rate row"
    return row[0]


def _discover_two_disjoint_fillers(conn: pyodbc.Connection) -> tuple[str, str, str, str]:
    """Return (victim_cc, victim_email, attacker_cc, attacker_email) — two
    fillers whose Fill scopes are DISJOINT, used to prove the D3/D4 IDOR fix:
    the attacker declares THEIR OWN in-scope cost_center but targets a
    detail_id that actually belongs to the victim's cost_center."""
    cursor = conn.cursor()
    try:
        cursor.execute(
            "SELECT DISTINCT filler_email FROM dbo.cc_filler_map "
            "WHERE filler_email IS NOT NULL AND LTRIM(RTRIM(filler_email)) <> '' ORDER BY filler_email"
        )
        emails = [r[0] for r in cursor.fetchall()]
    finally:
        cursor.close()

    scopes: dict[str, set[str]] = {}
    for email in emails:
        scope = resolve_scope(email, conn)
        fill = {cc for cc in scope.fill_cost_centers if cc not in EXCLUDED_COST_CENTERS}
        if fill:
            scopes[email] = fill

    items = list(scopes.items())
    for i, (email_a, fill_a) in enumerate(items):
        for email_b, fill_b in items[i + 1:]:
            if fill_a.isdisjoint(fill_b):
                return next(iter(fill_a)), email_a, next(iter(fill_b)), email_b
    pytest.skip("no two fillers with disjoint Fill scopes found in dbo.cc_filler_map")


def _discover_department_with_sap_led_row(
    fabric_conn: pyodbc.Connection, gold_conn: pyodbc.Connection, scope, planning_year: int
) -> tuple[str, str, str]:
    """Return (department, cost_center, gl_account) for a REAL SAP-led
    (cc,gl) row (no board, no pending) whose cost_center's department (via
    dbo.cc_filler_map) is resolvable — used to prove D10 (department filter
    must not drop SAP-led rows) on real data."""
    rows = get_budget_grid(fabric_conn, gold_conn, planning_year=planning_year, scope=scope)
    sap_led = [r for r in rows if r.sap.total_year != 0 and r.board.gl_name is None and r.pending.gl_name is None]
    ccs = list({r.cost_center for r in sap_led})
    cc_dims = fetch_cc_dims(fabric_conn, ccs)
    for r in sap_led:
        dept = cc_dims.get(r.cost_center, {}).get("department")
        if dept:
            return dept, r.cost_center, r.gl_account
    pytest.skip("no SAP-led row with a resolvable department found for this filler/board_year — cannot prove D10 live")


def _cleanup_sentinel_year(conn: pyodbc.Connection) -> None:
    """Delete every row at FISCAL_YEAR across the 3 transactional tables,
    then verify 0 remain. Never touches any other fiscal_year."""
    cursor = conn.cursor()
    try:
        cursor.execute("DELETE FROM budget.pending_budget_detail WHERE fiscal_year = ?", FISCAL_YEAR)
        cursor.execute("DELETE FROM budget.budget_trip WHERE fiscal_year = ?", FISCAL_YEAR)
        cursor.execute("DELETE FROM budget.pending_budget WHERE fiscal_year = ?", FISCAL_YEAR)
        conn.commit()
    finally:
        cursor.close()

    cursor = conn.cursor()
    try:
        cursor.execute("SELECT COUNT(*) FROM budget.pending_budget_detail WHERE fiscal_year = ?", FISCAL_YEAR)
        detail_left = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM budget.budget_trip WHERE fiscal_year = ?", FISCAL_YEAR)
        trip_left = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM budget.pending_budget WHERE fiscal_year = ?", FISCAL_YEAR)
        pending_left = cursor.fetchone()[0]
    finally:
        cursor.close()

    assert detail_left == 0, f"cleanup left {detail_left} budget.pending_budget_detail rows at fiscal_year={FISCAL_YEAR}"
    assert trip_left == 0, f"cleanup left {trip_left} budget.budget_trip rows at fiscal_year={FISCAL_YEAR}"
    assert pending_left == 0, f"cleanup left {pending_left} budget.pending_budget rows at fiscal_year={FISCAL_YEAR}"


@pytest.fixture(scope="module")
def discovered() -> tuple[str, str, str]:
    """(cost_center, filler_email, entertainment_gl) — discovered once per
    module run from the live DB, never hardcoded."""
    with get_fabric_conn() as conn:
        cost_center, filler_email = _discover_cc_filler(conn)
        gl_account = _discover_entertainment_gl(conn)
    return cost_center, filler_email, gl_account


@pytest.mark.integration
def test_scope_resolution_against_live_data(discovered: tuple[str, str, str]) -> None:
    """A3 RLS against the real DB: the discovered filler's Fill scope is
    non-empty and See is a superset of Fill."""
    cost_center, filler_email, _ = discovered

    with get_fabric_conn() as conn:
        scope = resolve_scope(filler_email, conn)

    assert scope.fill_cost_centers, f"{filler_email} resolved to an empty Fill scope"
    assert set(scope.fill_cost_centers) <= set(scope.see_cost_centers), "See must be a superset of Fill"
    assert cost_center in scope.fill_cost_centers


@pytest.mark.integration
def test_entertainment_1000_parent_cell_is_really_1000(discovered: tuple[str, str, str]) -> None:
    """The exact scenario the A5 gate flagged: user enters Entertainment
    1,000 -> API reports 1,000 AND the parent cell total is really 1,000 in
    the DB, verified on a FRESH connection (this is what caught the bug —
    the original connection's uncommitted work would otherwise vanish)."""
    cost_center, filler_email, gl_account = discovered

    try:
        with get_fabric_conn() as conn:
            scope = resolve_scope(filler_email, conn)
            assert cost_center in scope.fill_cost_centers, (
                f"{cost_center} should be in {filler_email}'s Fill scope (A3 RLS)"
            )

            results = save_detail_lines(
                conn,
                [DetailLineInput(cost_center=cost_center, gl_account=gl_account, fiscal_year=FISCAL_YEAR, m01=1000)],
                user_email=filler_email,
                scope=scope,
            )

        assert len(results) == 1
        result = results[0]
        assert result.ok, f"expected ok=True, got error={result.error} detail={result.detail}"
        assert result.line is not None
        assert result.line.m01 == 1000
        assert result.line.total_year == 1000

        # Fresh connection: proves the write really committed, not just that
        # the in-process result object claims success.
        with get_fabric_conn() as verify_conn:
            cursor = verify_conn.cursor()
            try:
                cursor.execute(
                    "SELECT m01, total_year, gl_name FROM budget.pending_budget "
                    "WHERE cost_center = ? AND gl_account = ? AND fiscal_year = ?",
                    cost_center, gl_account, FISCAL_YEAR,
                )
                parent_row = cursor.fetchone()
                cursor.execute(
                    "SELECT m01 FROM budget.pending_budget_detail "
                    "WHERE cost_center = ? AND gl_account = ? AND fiscal_year = ?",
                    cost_center, gl_account, FISCAL_YEAR,
                )
                detail_row = cursor.fetchone()
                cursor.execute("SELECT gl_name FROM dbo.gl_group WHERE gl_code = ?", gl_account)
                expected_gl_name_row = cursor.fetchone()
            finally:
                cursor.close()

        assert parent_row is not None, "parent cell row was not created — the write silently did nothing"
        assert float(parent_row[0]) == 1000, f"parent m01 = {parent_row[0]}, expected 1000"
        assert float(parent_row[1]) == 1000, f"parent total_year = {parent_row[1]}, expected 1000"
        assert detail_row is not None, "detail line was not persisted"
        assert float(detail_row[0]) == 1000, f"detail m01 = {detail_row[0]}, expected 1000"

        # GL-name GAP resolved 2026-07-15: the snapshot must now be resolved
        # from dbo.gl_group, never left NULL, and must match the live master.
        assert expected_gl_name_row is not None, f"no gl_name found in dbo.gl_group for gl_code={gl_account}"
        assert parent_row[2] is not None, "gl_name snapshot was left NULL — expected resolution from dbo.gl_group"
        assert parent_row[2] == expected_gl_name_row[0], (
            f"pending_budget.gl_name={parent_row[2]!r} does not match dbo.gl_group.gl_name={expected_gl_name_row[0]!r}"
        )
    finally:
        with get_fabric_conn() as cleanup_conn:
            _cleanup_sentinel_year(cleanup_conn)


@pytest.mark.integration
def test_add_second_detail_line_parent_cell_sums_both(discovered: tuple[str, str, str]) -> None:
    """Add a 2nd Entertainment detail line (500) alongside a 1st (1000) ->
    the parent cell must be 1,500 — proves parent == SUM(detail) on the real
    DB, not just against a mocked cursor."""
    cost_center, filler_email, gl_account = discovered

    try:
        with get_fabric_conn() as conn:
            scope = resolve_scope(filler_email, conn)

            results = save_detail_lines(
                conn,
                [
                    DetailLineInput(cost_center=cost_center, gl_account=gl_account, fiscal_year=FISCAL_YEAR, m01=1000),
                    DetailLineInput(cost_center=cost_center, gl_account=gl_account, fiscal_year=FISCAL_YEAR, m01=500),
                ],
                user_email=filler_email,
                scope=scope,
            )

        assert all(r.ok for r in results), [r.error for r in results if not r.ok]

        with get_fabric_conn() as verify_conn:
            cursor = verify_conn.cursor()
            try:
                cursor.execute(
                    "SELECT m01, total_year FROM budget.pending_budget "
                    "WHERE cost_center = ? AND gl_account = ? AND fiscal_year = ?",
                    cost_center, gl_account, FISCAL_YEAR,
                )
                parent_row = cursor.fetchone()
                cursor.execute(
                    "SELECT COUNT(*), SUM(m01) FROM budget.pending_budget_detail "
                    "WHERE cost_center = ? AND gl_account = ? AND fiscal_year = ?",
                    cost_center, gl_account, FISCAL_YEAR,
                )
                detail_count, detail_sum = cursor.fetchone()
            finally:
                cursor.close()

        assert parent_row is not None
        assert float(parent_row[0]) == 1500, f"parent m01 = {parent_row[0]}, expected 1500 (1000 + 500)"
        assert float(parent_row[1]) == 1500, f"parent total_year = {parent_row[1]}, expected 1500"
        assert detail_count == 2, f"expected 2 detail rows, found {detail_count}"
        assert float(detail_sum) == 1500
    finally:
        with get_fabric_conn() as cleanup_conn:
            _cleanup_sentinel_year(cleanup_conn)


# ---------------------------------------------------------------------------
# A5 gap close — deadline lock on the write path (final A6 gate flag,
# 2026-07-16): A6's submit already enforces dbo.submission_deadline, but
# PUT /budget/rows|detail|trip did not — a non-admin could edit a closed
# fiscal_year forever. Proves the fix against the REAL database: a non-admin
# write is rejected once the deadline has passed, admin is exempt (ADR-0012).
#
# Uses its OWN sentinel fiscal_year (2097, distinct from the 2099 sentinel
# used throughout the rest of this file) because this is the ONLY test in
# the whole suite allowed to write to dbo.submission_deadline — strictly
# keyed to fiscal_year=2097, deleted in the cleanup below. No other dbo.*
# row is ever touched.
# ---------------------------------------------------------------------------

DEADLINE_SENTINEL_YEAR = 2097


def _insert_past_deadline_row(conn: pyodbc.Connection) -> None:
    """INSERT one dbo.submission_deadline row for DEADLINE_SENTINEL_YEAR with
    deadline_date safely in the past (2020-01-01). All 9 live columns are
    NOT NULL (verified via INFORMATION_SCHEMA.COLUMNS) so every one needs a
    value; only fiscal_year/deadline_date matter to `is_post_deadline`, the
    rest are filled with coherent placeholder values."""
    cursor = conn.cursor()
    try:
        cursor.execute(
            """
            INSERT INTO dbo.submission_deadline
                (fiscal_year, closing_date, closing_month, closing_year, reminder_day,
                 deadline_date, reminder_date, _load_dt, _load_dttm)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            DEADLINE_SENTINEL_YEAR, 1, 1, 2020, 15,
            date(2020, 1, 1), date(2019, 12, 17), date(2020, 1, 1), datetime(2020, 1, 1),
        )
        conn.commit()
    finally:
        cursor.close()


def _cleanup_deadline_sentinel(conn: pyodbc.Connection) -> None:
    """Delete DEADLINE_SENTINEL_YEAR from budget.pending_budget (the write
    target) and dbo.submission_deadline (the one sentinel row this file is
    allowed to write), then verify 0 rows remain at that year in either."""
    cursor = conn.cursor()
    try:
        cursor.execute("DELETE FROM budget.pending_budget WHERE fiscal_year = ?", DEADLINE_SENTINEL_YEAR)
        cursor.execute("DELETE FROM dbo.submission_deadline WHERE fiscal_year = ?", DEADLINE_SENTINEL_YEAR)
        conn.commit()
    finally:
        cursor.close()

    cursor = conn.cursor()
    try:
        cursor.execute("SELECT COUNT(*) FROM budget.pending_budget WHERE fiscal_year = ?", DEADLINE_SENTINEL_YEAR)
        pending_left = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM dbo.submission_deadline WHERE fiscal_year = ?", DEADLINE_SENTINEL_YEAR)
        deadline_left = cursor.fetchone()[0]
    finally:
        cursor.close()

    assert pending_left == 0, (
        f"cleanup left {pending_left} budget.pending_budget rows at fiscal_year={DEADLINE_SENTINEL_YEAR}"
    )
    assert deadline_left == 0, (
        f"cleanup left {deadline_left} dbo.submission_deadline rows at fiscal_year={DEADLINE_SENTINEL_YEAR}"
    )


@pytest.mark.integration
def test_write_path_rejects_non_admin_past_deadline_write_live(discovered: tuple[str, str, str]) -> None:
    """A5 gap close: a normal Filler's write to a fiscal_year whose deadline
    already passed must be rejected (past_deadline, 403 at the router) with
    NO row written — proven against the real database, not a mock."""
    cost_center, filler_email, _ = discovered

    try:
        with get_fabric_conn() as conn:
            _insert_past_deadline_row(conn)

        with get_fabric_conn() as conn:
            gl_account = _discover_non_special_gl(conn)
            scope = resolve_scope(filler_email, conn)
            assert cost_center in scope.fill_cost_centers, (
                f"{cost_center} should be in {filler_email}'s Fill scope (A3 RLS)"
            )

            results = save_pending_rows(
                conn,
                [PendingRowInput(
                    cost_center=cost_center, gl_account=gl_account,
                    fiscal_year=DEADLINE_SENTINEL_YEAR, m01=100,
                )],
                user_email=filler_email,
                scope=scope,
            )

        assert len(results) == 1
        result = results[0]
        assert result.ok is False, "expected the write to be rejected past the deadline"
        assert result.error == "past_deadline"

        with get_fabric_conn() as verify_conn:
            cursor = verify_conn.cursor()
            try:
                cursor.execute(
                    "SELECT COUNT(*) FROM budget.pending_budget "
                    "WHERE cost_center = ? AND gl_account = ? AND fiscal_year = ?",
                    cost_center, gl_account, DEADLINE_SENTINEL_YEAR,
                )
                row_count = cursor.fetchone()[0]
            finally:
                cursor.close()
        assert row_count == 0, "the blocked write must not have created a budget.pending_budget row"
    finally:
        with get_fabric_conn() as cleanup_conn:
            _cleanup_deadline_sentinel(cleanup_conn)


@pytest.mark.integration
def test_write_path_admin_bypasses_past_deadline_write_live() -> None:
    """ADR-0012: after the deadline the admin handles everything — admin's
    write to the SAME closed fiscal_year must still succeed."""
    admin_email = "jakkaritw@chememan.com"

    try:
        with get_fabric_conn() as conn:
            _insert_past_deadline_row(conn)

        with get_fabric_conn() as conn:
            cost_center, _ = _discover_cc_filler(conn)
            gl_account = _discover_non_special_gl(conn)
            scope = resolve_scope(admin_email, conn)
            assert scope.is_admin, f"{admin_email} expected to be admin (ADMIN_EMAILS)"

            results = save_pending_rows(
                conn,
                [PendingRowInput(
                    cost_center=cost_center, gl_account=gl_account,
                    fiscal_year=DEADLINE_SENTINEL_YEAR, m01=250,
                )],
                user_email=admin_email,
                scope=scope,
            )

        assert len(results) == 1
        result = results[0]
        assert result.ok, f"admin write should succeed past the deadline, got error={result.error} detail={result.detail}"
        assert result.row is not None
        assert result.row.m01 == 250
    finally:
        with get_fabric_conn() as cleanup_conn:
            _cleanup_deadline_sentinel(cleanup_conn)


# ---------------------------------------------------------------------------
# A4 read path + SAP read-through — added 2026-07-16, first-ever live run.
# ---------------------------------------------------------------------------

@pytest.mark.integration
def test_sap_actuals_query_runs_live_and_matches_an_independent_sum() -> None:
    """The never-cut financial contract (ADR-0020, corrected 2026-07-16 by
    D2), proven live: `fetch_sap_actuals`' total SUM must equal the SAME
    aggregate hand-written independently (`company_code='1000'`,
    `doc_type<>'CO'`, the 8 excluded CCs WITHOUT `10SC012000`, the D2
    NULL-safe `(assignment_number IS NULL OR assignment_number<>'TFRS16')`,
    `SUM(company_curr_amount)`, no sign flip, no `doc_status` filter) —
    exact match. Also proves the pivot: one (cc, gl) key's m01..m12 sums
    back to that key's own total_year.

    NOTE: this test's own "independent" SQL previously used the bare
    (non-NULL-safe) filter, which matched `fetch_sap_actuals` only because
    both sides shared the SAME NULL-dropping bug (self-consistency, not
    correctness — see the D2 finding). Updated here in lockstep with the D2
    fix so this test keeps proving the CORRECT contract, not the old one."""
    with get_gold_conn() as conn:
        cursor = conn.cursor()
        try:
            cursor.execute(
                "SELECT DISTINCT fiscal_year FROM gold.fact_gl_trans WHERE company_code = '1000' ORDER BY fiscal_year DESC"
            )
            years_with_data = [r[0] for r in cursor.fetchall()]
        finally:
            cursor.close()
        assert years_with_data, "gold.fact_gl_trans has no company_code='1000' rows at all — nothing to test against"

        year = int(years_with_data[0])  # most recent year with data — discovered, not hardcoded

        result = fetch_sap_actuals(conn, year)
        assert result, (
            f"fetch_sap_actuals returned empty for fiscal_year={year}; "
            f"years that DO have company_code='1000' data: {years_with_data}"
        )

        code_total = round(sum(v["total_year"] for v in result.values()), 2)

        cursor = conn.cursor()
        try:
            cursor.execute(
                """
                SELECT SUM(company_curr_amount)
                FROM gold.fact_gl_trans
                WHERE company_code='1000' AND doc_type<>'CO'
                  AND cost_center NOT IN ('CMRY01','CMKK01','CMPB01','MNLB00','MNLB01','MNLB02','MNLB03','MNLB04')
                  AND (assignment_number IS NULL OR assignment_number<>'TFRS16') AND fiscal_year=?
                """,
                year,
            )
            independent_total = cursor.fetchone()[0]
        finally:
            cursor.close()

        assert independent_total is not None
        assert code_total == round(float(independent_total), 2), (
            f"fetch_sap_actuals total {code_total} != independent hand-written SUM {independent_total} "
            f"for fiscal_year={year} — the shipped query no longer matches its own contract"
        )

        sample_key = next(iter(result))
        months = result[sample_key]
        pivot_sum = round(sum(months[col] for col in MONTH_COLUMNS), 2)
        assert pivot_sum == months["total_year"], (
            f"{sample_key}: sum(m01..m12)={pivot_sum} != total_year={months['total_year']}"
        )


@pytest.mark.integration
def test_cost_center_is_not_null_hardening_is_behavior_identical() -> None:
    """2026-07-16 D2 follow-up (ADR-0020 + `app.sap` docstring): the new
    explicit `AND cost_center IS NOT NULL` predicate must be **behavior-
    identical** to the OLD form, which excluded NULL-cost_center rows only
    as a side effect of `cost_center NOT IN (...)` evaluating to SQL UNKNOWN
    for NULL. Proves this directly on the live warehouse: the OLD-form query
    (no explicit predicate) and the NEW-form query (with it) must return the
    exact same (cost_center, gl_account) keys and per-key totals, and the
    shipped `fetch_sap_actuals` (now carrying the new predicate) must match
    both. Does not compare against the stale pre-D2-assignment-fix constant
    (1722 keys / 309,049,478.15 THB) since that total legitimately changed
    when D2 stopped dropping NULL-assignment rows — self-consistency against
    a fresh independent query is the correct proof here, not that constant."""
    with get_gold_conn() as conn:
        cursor = conn.cursor()
        try:
            cursor.execute(
                "SELECT DISTINCT fiscal_year FROM gold.fact_gl_trans WHERE company_code = '1000' ORDER BY fiscal_year DESC"
            )
            years_with_data = [r[0] for r in cursor.fetchall()]
        finally:
            cursor.close()
        assert years_with_data, "gold.fact_gl_trans has no company_code='1000' rows at all"
        year = int(years_with_data[0])

        old_form_sql = """
            SELECT cost_center, gl_account_number, SUM(company_curr_amount) AS actual_thb
            FROM gold.fact_gl_trans
            WHERE company_code='1000' AND doc_type<>'CO'
              AND cost_center NOT IN ('CMRY01','CMKK01','CMPB01','MNLB00','MNLB01','MNLB02','MNLB03','MNLB04')
              AND (assignment_number IS NULL OR assignment_number<>'TFRS16') AND fiscal_year=?
            GROUP BY cost_center, gl_account_number
        """
        new_form_sql = """
            SELECT cost_center, gl_account_number, SUM(company_curr_amount) AS actual_thb
            FROM gold.fact_gl_trans
            WHERE company_code='1000' AND doc_type<>'CO'
              AND cost_center NOT IN ('CMRY01','CMKK01','CMPB01','MNLB00','MNLB01','MNLB02','MNLB03','MNLB04')
              AND cost_center IS NOT NULL
              AND (assignment_number IS NULL OR assignment_number<>'TFRS16') AND fiscal_year=?
            GROUP BY cost_center, gl_account_number
        """

        cursor = conn.cursor()
        try:
            cursor.execute(old_form_sql, year)
            old_rows = {(r[0], r[1]): round(float(r[2]), 2) for r in cursor.fetchall()}
            cursor.execute(new_form_sql, year)
            new_rows = {(r[0], r[1]): round(float(r[2]), 2) for r in cursor.fetchall()}
        finally:
            cursor.close()

        assert len(old_rows) == len(new_rows), (
            f"key count changed: old={len(old_rows)} new={len(new_rows)} -- the hardening is NOT behavior-identical"
        )
        assert old_rows == new_rows, "row values changed after adding the explicit cost_center IS NOT NULL predicate"

        new_total = round(sum(new_rows.values()), 2)

        result = fetch_sap_actuals(conn, year)
        code_total = round(sum(v["total_year"] for v in result.values()), 2)
        assert len(result) == len(new_rows), (
            f"fetch_sap_actuals key count {len(result)} != independent explicit-form key count {len(new_rows)}"
        )
        assert code_total == new_total, (
            f"fetch_sap_actuals total {code_total} != independent explicit-form total {new_total}"
        )

        print(  # noqa: T201 -- observed live figure requested for the task report, run with `-s` to see it
            f"[D2 cost_center IS NOT NULL hardening] fiscal_year={year} "
            f"keys={len(new_rows)} total_thb={new_total} (old form == new form, behavior-identical)"
        )


@pytest.mark.integration
def test_sap_failure_is_loud_not_silent(monkeypatch: pytest.MonkeyPatch) -> None:
    """A revoked grant / dropped table must raise `SapActualsFetchError` —
    never resolve to a silently-empty actuals layer (ADR-0020 Consequences).
    Read-only: the bogus query fails before touching any real data."""
    monkeypatch.setattr(
        sap_module,
        "SAP_ACTUALS_SQL",
        "SELECT cost_center, gl_account_number, fiscal_year, period_month, SUM(company_curr_amount) AS actual_thb "
        "FROM gold.__table_does_not_exist__ WHERE fiscal_year=? "
        "GROUP BY cost_center, gl_account_number, fiscal_year, period_month",
    )
    with get_gold_conn() as conn:
        with pytest.raises(SapActualsFetchError):
            fetch_sap_actuals(conn, 2026)


@pytest.mark.integration
def test_board_pending_join_runs_live() -> None:
    """The real board x pending FULL OUTER JOIN (`read_model.fetch_board_pending_rows`)
    executes against the live DB and returns board rows. `budget.pending_budget`
    is empty today, so every board row must survive the join as a board-only
    row — that is exactly ADR-0010's FULL OUTER guarantee (not a board-only
    LEFT join)."""
    with get_fabric_conn() as conn:
        board_year = _discover_board_year(conn)
        cursor = conn.cursor()
        try:
            cursor.execute("SELECT COUNT(*) FROM dbo.board_budget WHERE fiscal_year = ?", board_year)
            expected_board_rows = cursor.fetchone()[0]
        finally:
            cursor.close()

        join_rows = fetch_board_pending_rows(conn, board_year=board_year, pending_year=board_year + 1, cost_centers=None)

    assert join_rows, f"fetch_board_pending_rows returned nothing for board_year={board_year}"
    assert len(join_rows) == expected_board_rows, (
        f"expected {expected_board_rows} board rows to survive the FULL OUTER join, got {len(join_rows)}"
    )
    board_only = [r for r in join_rows if r["pending_cost_center"] is None]
    assert len(board_only) == len(join_rows), (
        "budget.pending_budget is expected to be empty right now — every joined row should be board-only; "
        "if this fails, pending_budget is no longer empty (re-check test isolation before trusting this failure)"
    )


@pytest.mark.integration
def test_get_budget_grid_live_for_a_real_filler() -> None:
    """Full `get_budget_grid` (board + pending + SAP merged, RLS-filtered)
    for a real filler at planning_year = board_year + 1. Proves RLS holds
    on real data: every returned cost_center is inside the filler's See
    scope; See-only rows are non-editable; Fill rows are editable; and a
    SAP-led (cc, gl) with no pending appears with a blank editable pending
    row."""
    with get_fabric_conn() as conn:
        board_year = _discover_board_year(conn)
        cursor = conn.cursor()
        try:
            cursor.execute("SELECT DISTINCT cost_center FROM dbo.board_budget WHERE fiscal_year = ?", board_year)
            board_ccs = {r[0] for r in cursor.fetchall()}
        finally:
            cursor.close()
        filler_email = _discover_grid_filler(conn, board_ccs)
        scope = resolve_scope(filler_email, conn)

    assert scope.fill_cost_centers, f"{filler_email} resolved to an empty Fill scope"

    planning_year = board_year + 1
    with get_fabric_conn() as fabric_conn, get_gold_conn() as gold_conn:
        rows = get_budget_grid(fabric_conn, gold_conn, planning_year=planning_year, scope=scope)

    assert rows, f"get_budget_grid returned no rows for {filler_email} at planning_year={planning_year}"

    see_set = set(scope.see_cost_centers)
    out_of_scope = {r.cost_center for r in rows} - see_set
    assert not out_of_scope, f"RLS violation: rows outside {filler_email}'s See scope: {out_of_scope}"

    fill_set = set(scope.fill_cost_centers)
    see_only_rows = [r for r in rows if r.cost_center not in fill_set]
    assert all(not r.editable for r in see_only_rows), "See-only row(s) incorrectly marked editable"

    fill_rows = [r for r in rows if r.cost_center in fill_set]
    assert fill_rows, "expected at least one Fill-scope row"
    assert all(r.editable for r in fill_rows), "Fill-scope row(s) not editable"

    sap_led_blank_pending = [
        r for r in fill_rows
        if r.sap.total_year != 0 and r.pending.total_year == 0 and r.pending.gl_name is None
    ]
    assert sap_led_blank_pending, "expected >=1 SAP-led (cc,gl) with a blank editable pending row"


@pytest.mark.integration
def test_pending_layer_appears_in_get_budget_grid_after_a_sentinel_write() -> None:
    """Writes ONE sentinel `pending_budget` row (fiscal_year=2099, a plain
    non-special GL) via the real write path, re-reads it through the real
    read path (`get_budget_grid`), and asserts the Pending layer is
    populated — proving the 3-layer merge round-trips end to end on a live
    write, not just a mocked one. Cleaned up in `finally`."""
    with get_fabric_conn() as conn:
        cost_center, filler_email = _discover_cc_filler(conn)
        gl_account = _discover_non_special_gl(conn)
        scope = resolve_scope(filler_email, conn)
    assert cost_center in scope.fill_cost_centers

    try:
        with get_fabric_conn() as conn:
            results = save_pending_rows(
                conn,
                [PendingRowInput(cost_center=cost_center, gl_account=gl_account, fiscal_year=FISCAL_YEAR, m01=777)],
                user_email=filler_email,
                scope=scope,
            )
        assert results[0].ok, f"sentinel write failed: error={results[0].error} detail={results[0].detail}"

        with get_fabric_conn() as fabric_conn, get_gold_conn() as gold_conn:
            rows = get_budget_grid(fabric_conn, gold_conn, planning_year=FISCAL_YEAR, scope=scope)

        row = next((r for r in rows if r.cost_center == cost_center and r.gl_account == gl_account), None)
        assert row is not None, f"({cost_center}, {gl_account}) not found in the re-read grid"
        assert row.pending.m01 == 777, f"pending.m01 = {row.pending.m01}, expected 777"
        assert row.pending.total_year == 777, f"pending.total_year = {row.pending.total_year}, expected 777"
        assert row.editable, "the filler's own Fill-scope row must be editable"
    finally:
        with get_fabric_conn() as cleanup_conn:
            _cleanup_sentinel_year(cleanup_conn)


# ---------------------------------------------------------------------------
# A4+A5 exhaustive-verify defect fixes — live proofs (2026-07-16, see
# docs/a4-a5-verify-findings.md). Sentinel fiscal_year=2099 throughout.
# ---------------------------------------------------------------------------

@pytest.mark.integration
def test_post_trip_endpoint_succeeds_end_to_end_after_the_job_level_column_fix(
    discovered: tuple[str, str, str],
) -> None:
    """D1 SHOWSTOPPER, live, through the REAL HTTP endpoint: before the fix,
    `_lookup_per_diem_rate`'s `WHERE position = ?` raised pyodbc 42S22 ("no
    such column") on EVERY real trip save -> `POST /budget/trip` always 502.
    Proves the fix through the full stack (real router, real auth override,
    real Fabric SQL DB): 200 + a persisted `budget.budget_trip` row."""
    cost_center, filler_email, _ = discovered

    with get_fabric_conn() as conn:
        traveler_empcode = _discover_traveler_with_a_configured_rate(conn)

    fastapi_app.dependency_overrides[get_current_user_email] = lambda: filler_email
    try:
        with TestClient(fastapi_app) as client:
            response = client.post(
                "/budget/trip",
                json={
                    "cost_center": cost_center,
                    "fiscal_year": FISCAL_YEAR,
                    "traveler_empcode": traveler_empcode,
                    "country_group": 1,
                    "days": 3,
                    "travel_months": ["05"],
                    "side": "COST",
                },
            )
        assert response.status_code == 200, response.text
        trip_id = response.json()["trip_id"]
        assert trip_id is not None

        with get_fabric_conn() as verify_conn:
            cursor = verify_conn.cursor()
            try:
                cursor.execute("SELECT trip_id FROM budget.budget_trip WHERE trip_id = ?", trip_id)
                row = cursor.fetchone()
            finally:
                cursor.close()
        assert row is not None, "trip row was not persisted despite a 200 response"
    finally:
        fastapi_app.dependency_overrides.pop(get_current_user_email, None)
        with get_fabric_conn() as cleanup_conn:
            _cleanup_sentinel_year(cleanup_conn)


@pytest.mark.integration
def test_sap_null_assignment_fix_nets_a_balanced_clearing_account_to_zero() -> None:
    """D2 policy fix (confirmed): NULL-assignment rows are KEPT, not
    silently dropped by a bare `assignment_number<>'TFRS16'` (`NULL <>
    'TFRS16'` is SQL UNKNOWN). Before the fix, GL 9110100020 on cost center
    10QC011000 (a balanced clearing account, FY2026) showed a multi-million
    THB phantom because the +NULL legs were dropped while the -PO legs were
    kept. After the fix the per-cell total must net to ~0.00. Read-only —
    no writes, no cleanup needed."""
    gl_account = "9110100020"
    cost_center = "10QC011000"
    fiscal_year = 2026
    with get_gold_conn() as conn:
        result = fetch_sap_actuals(conn, fiscal_year)
    key = (cost_center, gl_account)
    assert key in result, f"{key} not found in fiscal_year={fiscal_year} SAP actuals — re-check the discovery values"
    total = result[key]["total_year"]
    assert abs(total) < 1.0, f"expected a near-zero balanced clearing total, got {total}"


@pytest.mark.integration
def test_idor_cannot_rewrite_a_detail_line_outside_fill_scope() -> None:
    """D3/D4 IDOR fix, live: a filler cannot rewrite an existing detail_id
    that belongs to a DIFFERENT cost_center, even by declaring their OWN
    in-scope cost_center in the payload — the fix reads the row's ACTUAL
    owner from the DB and authorizes/compares against that, never the
    payload. The victim row must remain unchanged."""
    with get_fabric_conn() as conn:
        victim_cc, victim_email, attacker_cc, attacker_email = _discover_two_disjoint_fillers(conn)
        gl_account = _discover_entertainment_gl(conn)
        victim_scope = resolve_scope(victim_email, conn)
        attacker_scope = resolve_scope(attacker_email, conn)

    try:
        with get_fabric_conn() as conn:
            create_results = save_detail_lines(
                conn,
                [DetailLineInput(cost_center=victim_cc, gl_account=gl_account, fiscal_year=FISCAL_YEAR, m01=42)],
                user_email=victim_email, scope=victim_scope,
            )
        assert create_results[0].ok, create_results[0].detail
        victim_detail_id = create_results[0].line.detail_id
        victim_updated_at = create_results[0].line.updated_at

        with get_fabric_conn() as conn:
            attack_results = save_detail_lines(
                conn,
                [DetailLineInput(
                    detail_id=victim_detail_id, cost_center=attacker_cc, gl_account=gl_account,
                    fiscal_year=FISCAL_YEAR, m01=999999, expected_updated_at=victim_updated_at,
                )],
                user_email=attacker_email, scope=attacker_scope,
            )
        assert attack_results[0].ok is False, "attacker's rewrite must be rejected"
        assert attack_results[0].error in ("forbidden", "conflict"), attack_results[0].error

        with get_fabric_conn() as verify_conn:
            cursor = verify_conn.cursor()
            try:
                cursor.execute(
                    "SELECT m01, cost_center FROM budget.pending_budget_detail WHERE detail_id = ?",
                    victim_detail_id,
                )
                row = cursor.fetchone()
            finally:
                cursor.close()
        assert row is not None
        assert float(row[0]) == 42, f"victim row was modified: m01={row[0]}"
        assert row[1] == victim_cc
    finally:
        with get_fabric_conn() as cleanup_conn:
            _cleanup_sentinel_year(cleanup_conn)


@pytest.mark.integration
def test_concurrent_detail_saves_never_lose_a_line_in_the_parent_sum(
    discovered: tuple[str, str, str],
) -> None:
    """D5 (never-cut): two REAL connections each save a detail line to the
    SAME parent cell within the same window (via a Barrier to maximize
    overlap) — the atomic recompute (D5 fix) must make the parent cell equal
    SUM(detail), never lose either writer's line to a race (the old bug:
    SELECT sum, then a separate UPDATE — a concurrent commit landing in
    between was silently overwritten)."""
    cost_center, filler_email, gl_account = discovered
    barrier = threading.Barrier(2)
    errors: list[BaseException] = []

    def _write(amount: float) -> None:
        try:
            with get_fabric_conn() as conn:
                scope = resolve_scope(filler_email, conn)
                barrier.wait(timeout=10)
                save_detail_lines(
                    conn,
                    [DetailLineInput(cost_center=cost_center, gl_account=gl_account, fiscal_year=FISCAL_YEAR, m01=amount)],
                    user_email=filler_email, scope=scope,
                )
        except BaseException as exc:  # noqa: BLE001 — surfaced via `errors`, never swallowed
            errors.append(exc)

    try:
        t1 = threading.Thread(target=_write, args=(150.0,))
        t2 = threading.Thread(target=_write, args=(150.0,))
        t1.start()
        t2.start()
        t1.join(timeout=30)
        t2.join(timeout=30)
        assert not errors, f"writer thread(s) raised: {errors}"

        with get_fabric_conn() as verify_conn:
            cursor = verify_conn.cursor()
            try:
                cursor.execute(
                    "SELECT m01 FROM budget.pending_budget WHERE cost_center = ? AND gl_account = ? AND fiscal_year = ?",
                    cost_center, gl_account, FISCAL_YEAR,
                )
                parent_row = cursor.fetchone()
                cursor.execute(
                    "SELECT COUNT(*), SUM(m01) FROM budget.pending_budget_detail "
                    "WHERE cost_center = ? AND gl_account = ? AND fiscal_year = ?",
                    cost_center, gl_account, FISCAL_YEAR,
                )
                detail_count, detail_sum = cursor.fetchone()
            finally:
                cursor.close()

        assert detail_count == 2, f"expected both concurrent writes to persist, found {detail_count} detail rows"
        assert parent_row is not None
        assert float(parent_row[0]) == float(detail_sum) == 300.0, (
            f"parent m01={parent_row[0]} != SUM(detail)={detail_sum} — a concurrent write was lost (D5 race)"
        )
    finally:
        with get_fabric_conn() as cleanup_conn:
            _cleanup_sentinel_year(cleanup_conn)


@pytest.mark.integration
def test_decimal_quantization_two_lines_of_100_005_sum_to_200_00(
    discovered: tuple[str, str, str],
) -> None:
    """D6 (never-cut): two detail lines each entered as 100.005 must each
    persist as 100.00 (DECIMAL(18,2), ROUND_HALF_UP on the exact double) and
    the parent cell must be exactly 200.00 — proving total_year ==
    SUM(m01..m12) holds at a real cent-rounding boundary, on the real DB."""
    cost_center, filler_email, gl_account = discovered

    try:
        with get_fabric_conn() as conn:
            scope = resolve_scope(filler_email, conn)
            results = save_detail_lines(
                conn,
                [
                    DetailLineInput(cost_center=cost_center, gl_account=gl_account, fiscal_year=FISCAL_YEAR, m01=100.005),
                    DetailLineInput(cost_center=cost_center, gl_account=gl_account, fiscal_year=FISCAL_YEAR, m01=100.005),
                ],
                user_email=filler_email, scope=scope,
            )
        assert all(r.ok for r in results), [r.error for r in results if not r.ok]
        assert results[0].line.m01 == 100.00
        assert results[1].line.m01 == 100.00

        with get_fabric_conn() as verify_conn:
            cursor = verify_conn.cursor()
            try:
                cursor.execute(
                    "SELECT m01, total_year FROM budget.pending_budget "
                    "WHERE cost_center = ? AND gl_account = ? AND fiscal_year = ?",
                    cost_center, gl_account, FISCAL_YEAR,
                )
                parent_row = cursor.fetchone()
            finally:
                cursor.close()
        assert parent_row is not None
        assert float(parent_row[0]) == 200.00, f"parent m01={parent_row[0]}, expected 200.00"
        assert float(parent_row[1]) == 200.00, f"parent total_year={parent_row[1]}, expected 200.00"
    finally:
        with get_fabric_conn() as cleanup_conn:
            _cleanup_sentinel_year(cleanup_conn)


@pytest.mark.integration
def test_department_filter_keeps_sap_led_rows_live() -> None:
    """D10 fix, live: a department filter must not silently drop SAP-led
    (cc,gl) rows that have no board/pending snapshot yet — the department
    for those rows is now derived from dbo.cc_filler_map via fetch_cc_dims."""
    with get_fabric_conn() as conn:
        board_year = _discover_board_year(conn)
        cursor = conn.cursor()
        try:
            cursor.execute("SELECT DISTINCT cost_center FROM dbo.board_budget WHERE fiscal_year = ?", board_year)
            board_ccs = {r[0] for r in cursor.fetchall()}
        finally:
            cursor.close()
        filler_email = _discover_grid_filler(conn, board_ccs)
        scope = resolve_scope(filler_email, conn)

    planning_year = board_year + 1
    with get_fabric_conn() as fabric_conn, get_gold_conn() as gold_conn:
        department, cost_center, gl_account = _discover_department_with_sap_led_row(
            fabric_conn, gold_conn, scope, planning_year
        )

    with get_fabric_conn() as fabric_conn, get_gold_conn() as gold_conn:
        filtered_rows = get_budget_grid(
            fabric_conn, gold_conn, planning_year=planning_year, scope=scope, department_filter=department
        )

    assert any(r.cost_center == cost_center and r.gl_account == gl_account for r in filtered_rows), (
        f"SAP-led row ({cost_center}, {gl_account}) for department={department!r} was dropped by the department filter"
    )


@pytest.mark.integration
def test_cc_dims_lookup_is_deterministic_for_a_multi_division_cc() -> None:
    """D11 fix: `dbo.cc_filler_map` can have >1 row (>1 filler_email) for the
    same cost_center with DIFFERENT divisions — `_lookup_cc_dims` must return
    the SAME row every time (`ORDER BY filler_email`), not flip by scan
    order. CC 10OS011400 is a real 2-division CC per the exhaustive verify
    finding; skips gracefully if that's no longer true today."""
    from app.write_model import _lookup_cc_dims

    cost_center = "10OS011400"
    with get_fabric_conn() as conn:
        cursor = conn.cursor()
        try:
            cursor.execute(
                "SELECT COUNT(DISTINCT division) FROM dbo.cc_filler_map WHERE cost_center = ?", cost_center
            )
            distinct_divisions = cursor.fetchone()[0]
        finally:
            cursor.close()
        if distinct_divisions < 2:
            pytest.skip(f"{cost_center} no longer has >1 division in dbo.cc_filler_map (today: {distinct_divisions})")

        results = [_lookup_cc_dims(conn, cost_center) for _ in range(5)]
    assert all(r == results[0] for r in results), f"non-deterministic pick across repeated calls: {results}"


# ---------------------------------------------------------------------------
# A6 approval engine — live proofs (added 2026-07-16). Only 2 NEW tables are
# touched here (`budget.approval_status` / `budget.approval_log`) -- no
# collision with the A4/A5 sentinel usage above (different tables entirely).
# Real department names + real employee relationships (Nipaporn/Waraporn's
# own manager chain, a discovered normal filler's chain) are used to prove
# chain resolution against LIVE data; all writes are scoped to sentinel
# fiscal_year=2099 in the 2 A6-owned tables, cleaned up in `finally`. The
# admin orphan/Template-2 branches use a synthetic department name that can
# never collide with a real one.
# ---------------------------------------------------------------------------

FAKE_DEPARTMENT = "ZZ_TEST_DEPT_A6_NEVER_REAL"


def _cleanup_approval(conn: pyodbc.Connection, department: str, fiscal_year: int = FISCAL_YEAR) -> None:
    cursor = conn.cursor()
    try:
        cursor.execute("DELETE FROM budget.approval_log WHERE department = ? AND fiscal_year = ?", department, fiscal_year)
        cursor.execute("DELETE FROM budget.approval_status WHERE department = ? AND fiscal_year = ?", department, fiscal_year)
        conn.commit()
    finally:
        cursor.close()

    cursor = conn.cursor()
    try:
        cursor.execute(
            "SELECT COUNT(*) FROM budget.approval_log WHERE department = ? AND fiscal_year = ?", department, fiscal_year
        )
        log_left = cursor.fetchone()[0]
        cursor.execute(
            "SELECT COUNT(*) FROM budget.approval_status WHERE department = ? AND fiscal_year = ?", department, fiscal_year
        )
        status_left = cursor.fetchone()[0]
    finally:
        cursor.close()
    assert log_left == 0, f"cleanup left {log_left} budget.approval_log rows for {department}/{fiscal_year}"
    assert status_left == 0, f"cleanup left {status_left} budget.approval_status rows for {department}/{fiscal_year}"


def _discover_nipaporn_waraporn_shared_department(conn: pyodbc.Connection) -> str:
    """A department both Nipaporn and Waraporn personally Fill (real, verified
    2026-07-16: 5 such departments exist) -- used to exercise the self-skip
    single-step chain (ADR-0006's own worked example) end to end."""
    cursor = conn.cursor()
    try:
        cursor.execute(
            "SELECT DISTINCT department FROM dbo.cc_filler_map WHERE LOWER(filler_email) = LOWER(?) "
            "INTERSECT "
            "SELECT DISTINCT department FROM dbo.cc_filler_map WHERE LOWER(filler_email) = LOWER(?) "
            "ORDER BY department",
            "nipapornt@chememan.com", "warapornt@chememan.com",
        )
        row = cursor.fetchone()
    finally:
        cursor.close()
    assert row is not None, "no department shared by nipapornt and warapornt found in dbo.cc_filler_map"
    return row[0]


def _discover_full_chain_filler(conn: pyodbc.Connection) -> tuple[str, str, str]:
    """Returns (department, filler_email, manager_email) for a filler whose
    Primary-row manager is neither Nipaporn nor Waraporn -- exercises the
    untouched full 3-step chain (no self-skip/dedup)."""
    cursor = conn.cursor()
    try:
        cursor.execute(
            """
            SELECT TOP 1 f.department, f.filler_email, e.manager_email
            FROM dbo.cc_filler_map f
            JOIN dbo.v_employee_budget_01 e ON LOWER(e.email) = LOWER(f.filler_email)
            WHERE f.filler_email NOT IN (?, ?)
              AND e.manager_employee_code IS NOT NULL
              AND e.manager_employee_code NOT IN (?, ?)
            ORDER BY f.department, f.filler_email
            """,
            "nipapornt@chememan.com", "warapornt@chememan.com", NIPAPORN_EMPCODE, WARAPORN_EMPCODE,
        )
        row = cursor.fetchone()
    finally:
        cursor.close()
    assert row is not None, "no filler with a full 3-distinct-step chain found in the live data"
    return row[0], row[1], row[2]


def _log_actions(conn: pyodbc.Connection, department: str, fiscal_year: int = FISCAL_YEAR) -> list[str]:
    cursor = conn.cursor()
    try:
        cursor.execute(
            "SELECT action FROM budget.approval_log WHERE department = ? AND fiscal_year = ? ORDER BY log_id",
            department, fiscal_year,
        )
        rows = cursor.fetchall()
    finally:
        cursor.close()
    return [r[0] for r in rows]


@pytest.mark.integration
def test_resolve_chain_self_skip_nipaporn_live() -> None:
    """ADR-0006 worked example, live: Nipaporn's own Primary-row manager is
    Waraporn -> chain collapses to ONE active step."""
    with get_fabric_conn() as conn:
        submitter_empcode, approver1_empcode, active = resolve_chain(conn, "nipapornt@chememan.com")
    assert submitter_empcode == NIPAPORN_EMPCODE
    assert approver1_empcode == WARAPORN_EMPCODE
    assert active == [1]


@pytest.mark.integration
def test_resolve_chain_dedup_waraporn_live() -> None:
    """ADR-0006 worked example, live: Waraporn's own manager is Piyada ->
    chain keeps 2 steps (Piyada, then Nipaporn), her own step deduped away."""
    with get_fabric_conn() as conn:
        submitter_empcode, approver1_empcode, active = resolve_chain(conn, "warapornt@chememan.com")
    assert submitter_empcode == WARAPORN_EMPCODE
    assert approver1_empcode == "101218"  # Piyada -- verified live 2026-07-16
    assert active == [1, 2]


@pytest.mark.integration
def test_resolve_chain_full_chain_live() -> None:
    with get_fabric_conn() as conn:
        _department, filler_email, _manager_email = _discover_full_chain_filler(conn)
        submitter_empcode, approver1_empcode, active = resolve_chain(conn, filler_email)
    assert active == [1, 2, 3]
    assert approver1_empcode not in (NIPAPORN_EMPCODE, WARAPORN_EMPCODE)


@pytest.mark.integration
def test_submit_then_approve_self_skip_chain_end_to_end_live() -> None:
    """Nipaporn submits one of her own departments -- the chain collapses to
    ONE step (Waraporn); approving it goes straight to APPROVED."""
    with get_fabric_conn() as conn:
        department = _discover_nipaporn_waraporn_shared_department(conn)

    try:
        with get_fabric_conn() as conn:
            scope = resolve_scope("nipapornt@chememan.com", conn)
            state = submit_department(conn, department, FISCAL_YEAR, "nipapornt@chememan.com", scope)
        assert state.status == PENDING_APPROVER1
        assert state.approver1_empcode == WARAPORN_EMPCODE

        with get_fabric_conn() as conn:
            approved = approve_department(conn, department, FISCAL_YEAR, "warapornt@chememan.com")
        assert approved.status == APPROVED

        with get_fabric_conn() as verify_conn:
            actions = _log_actions(verify_conn, department)
        assert actions == ["SUBMIT", "APPROVE"]
    finally:
        with get_fabric_conn() as cleanup_conn:
            _cleanup_approval(cleanup_conn, department)


@pytest.mark.integration
def test_submit_then_approve_full_three_step_chain_end_to_end_live() -> None:
    with get_fabric_conn() as conn:
        department, filler_email, manager_email = _discover_full_chain_filler(conn)

    try:
        with get_fabric_conn() as conn:
            scope = resolve_scope(filler_email, conn)
            state = submit_department(conn, department, FISCAL_YEAR, filler_email, scope)
        assert state.status == PENDING_APPROVER1

        with get_fabric_conn() as conn:
            state = approve_department(conn, department, FISCAL_YEAR, manager_email)
        assert state.status == PENDING_APPROVER2

        with get_fabric_conn() as conn:
            state = approve_department(conn, department, FISCAL_YEAR, "nipapornt@chememan.com")
        assert state.status == PENDING_APPROVER3

        with get_fabric_conn() as conn:
            state = approve_department(conn, department, FISCAL_YEAR, "warapornt@chememan.com")
        assert state.status == APPROVED

        with get_fabric_conn() as verify_conn:
            actions = _log_actions(verify_conn, department)
        assert actions == ["SUBMIT", "APPROVE", "APPROVE", "APPROVE"]
    finally:
        with get_fabric_conn() as cleanup_conn:
            _cleanup_approval(cleanup_conn, department)


@pytest.mark.integration
def test_approve_by_wrong_person_is_rejected_live() -> None:
    with get_fabric_conn() as conn:
        department, filler_email, _manager_email = _discover_full_chain_filler(conn)

    try:
        with get_fabric_conn() as conn:
            scope = resolve_scope(filler_email, conn)
            submit_department(conn, department, FISCAL_YEAR, filler_email, scope)

        with get_fabric_conn() as conn:
            with pytest.raises(NotCurrentApproverError):
                approve_department(conn, department, FISCAL_YEAR, filler_email)  # the submitter, not the manager
    finally:
        with get_fabric_conn() as cleanup_conn:
            _cleanup_approval(cleanup_conn, department)


@pytest.mark.integration
def test_reject_then_resubmit_restarts_whole_chain_live() -> None:
    with get_fabric_conn() as conn:
        department, filler_email, manager_email = _discover_full_chain_filler(conn)

    try:
        with get_fabric_conn() as conn:
            scope = resolve_scope(filler_email, conn)
            submit_department(conn, department, FISCAL_YEAR, filler_email, scope)

        with get_fabric_conn() as conn:
            rejected = reject_department(conn, department, FISCAL_YEAR, manager_email, "numbers look wrong")
        assert rejected.status == REJECTED
        assert rejected.reject_reason == "numbers look wrong"

        with get_fabric_conn() as conn:
            scope = resolve_scope(filler_email, conn)
            resubmitted = submit_department(conn, department, FISCAL_YEAR, filler_email, scope)
        assert resubmitted.status == PENDING_APPROVER1, "resubmit must restart at step 1, never resume mid-chain"
        assert resubmitted.reject_reason is None, "re-freeze from scratch -- reject_reason must be cleared"
        assert resubmitted.approver1_actioned_at is None, "re-freeze from scratch -- prior actioned_at must be cleared"

        with get_fabric_conn() as verify_conn:
            actions = _log_actions(verify_conn, department)
        assert actions == ["SUBMIT", "REJECT", "RESUBMIT"]
    finally:
        with get_fabric_conn() as cleanup_conn:
            _cleanup_approval(cleanup_conn, department)


@pytest.mark.integration
def test_admin_direct_approve_orphan_department_live() -> None:
    """A department name with ZERO rows in dbo.cc_filler_map (nobody can Fill
    or submit it normally) -- admin direct-approve, logged
    ADMIN_OVERRIDE_ORPHAN (S4 gate fix: distinct from the post-deadline
    branch's ADMIN_OVERRIDE_DEADLINE), no approver chain ever created."""
    admin_email = "jakkaritw@chememan.com"
    try:
        with get_fabric_conn() as conn:
            scope = resolve_scope(admin_email, conn)
            assert scope.is_admin, f"{admin_email} expected to be admin (ADMIN_EMAILS)"
            state = submit_department(conn, FAKE_DEPARTMENT, FISCAL_YEAR, admin_email, scope)
        assert state.status == APPROVED
        assert state.approver1_empcode is None

        with get_fabric_conn() as verify_conn:
            actions = _log_actions(verify_conn, FAKE_DEPARTMENT)
        assert actions == ["ADMIN_OVERRIDE_ORPHAN"]
    finally:
        with get_fabric_conn() as cleanup_conn:
            _cleanup_approval(cleanup_conn, FAKE_DEPARTMENT)


@pytest.mark.integration
def test_admin_direct_approve_template_2_door_live() -> None:
    """A department with a real `template='ADMIN'` pending_budget row (the
    Budget-dept Template-2 door, spec §1d) -- admin direct-approve, logged
    ADMIN_SUBMIT (distinct from the orphan case's ADMIN_OVERRIDE_ORPHAN)."""
    admin_email = "jakkaritw@chememan.com"
    now = datetime.now(timezone.utc)
    cost_center, gl_account = "ZZ_TEST_CC_A6", "ZZ_TEST_GL_A6"

    try:
        with get_fabric_conn() as conn:
            cursor = conn.cursor()
            try:
                cursor.execute(
                    """
                    INSERT INTO budget.pending_budget
                        (cost_center, gl_account, fiscal_year,
                         m01, m02, m03, m04, m05, m06, m07, m08, m09, m10, m11, m12,
                         total_year, template, department, _user, _updated_at)
                    VALUES (?, ?, ?, 0,0,0,0,0,0,0,0,0,0,0,0, 0, 'ADMIN', ?, ?, ?)
                    """,
                    cost_center, gl_account, FISCAL_YEAR, FAKE_DEPARTMENT, admin_email, now,
                )
                conn.commit()
            finally:
                cursor.close()

        with get_fabric_conn() as conn:
            scope = resolve_scope(admin_email, conn)
            state = submit_department(conn, FAKE_DEPARTMENT, FISCAL_YEAR, admin_email, scope)
        assert state.status == APPROVED

        with get_fabric_conn() as verify_conn:
            actions = _log_actions(verify_conn, FAKE_DEPARTMENT)
        assert actions == ["ADMIN_SUBMIT"]
    finally:
        with get_fabric_conn() as cleanup_conn:
            _cleanup_approval(cleanup_conn, FAKE_DEPARTMENT)
            cursor = cleanup_conn.cursor()
            try:
                cursor.execute(
                    "DELETE FROM budget.pending_budget WHERE cost_center = ? AND gl_account = ? AND fiscal_year = ?",
                    cost_center, gl_account, FISCAL_YEAR,
                )
                cleanup_conn.commit()
            finally:
                cursor.close()


@pytest.mark.integration
def test_concurrent_double_approve_does_not_double_advance_live() -> None:
    """D5-style race (never-cut), applied to A6: two connections race to
    approve the SAME single-step chain (the self-skip scenario -- only
    Waraporn's step exists) -- exactly one must succeed (-> APPROVED), the
    other must get ConcurrentApprovalError, and only ONE APPROVE log row may
    ever be written (no double-advance)."""
    with get_fabric_conn() as conn:
        department = _discover_nipaporn_waraporn_shared_department(conn)

    barrier = threading.Barrier(2)
    results: list[tuple[str, str | None]] = []
    errors: list[BaseException] = []

    def _approve() -> None:
        try:
            with get_fabric_conn() as conn:
                barrier.wait(timeout=10)
                try:
                    state = approve_department(conn, department, FISCAL_YEAR, "warapornt@chememan.com")
                    results.append(("ok", state.status))
                except ConcurrentApprovalError:
                    results.append(("conflict", None))
        except BaseException as exc:  # noqa: BLE001 -- surfaced via `errors`, never swallowed
            errors.append(exc)

    try:
        with get_fabric_conn() as conn:
            scope = resolve_scope("nipapornt@chememan.com", conn)
            submit_department(conn, department, FISCAL_YEAR, "nipapornt@chememan.com", scope)

        t1 = threading.Thread(target=_approve)
        t2 = threading.Thread(target=_approve)
        t1.start()
        t2.start()
        t1.join(timeout=30)
        t2.join(timeout=30)

        assert not errors, f"thread(s) raised unexpectedly: {errors}"
        assert len(results) == 2
        ok_results = [r for r in results if r[0] == "ok"]
        conflict_results = [r for r in results if r[0] == "conflict"]
        assert len(ok_results) == 1, f"expected exactly one successful approve, got {results}"
        assert len(conflict_results) == 1, f"expected exactly one conflict, got {results}"
        assert ok_results[0][1] == APPROVED

        with get_fabric_conn() as verify_conn:
            cursor = verify_conn.cursor()
            try:
                cursor.execute(
                    "SELECT status FROM budget.approval_status WHERE department = ? AND fiscal_year = ?",
                    department, FISCAL_YEAR,
                )
                final_status = cursor.fetchone()[0]
                cursor.execute(
                    "SELECT COUNT(*) FROM budget.approval_log WHERE department = ? AND fiscal_year = ? AND action = 'APPROVE'",
                    department, FISCAL_YEAR,
                )
                approve_log_count = cursor.fetchone()[0]
            finally:
                cursor.close()
        assert final_status == APPROVED
        assert approve_log_count == 1, "exactly one APPROVE log row expected -- no double-advance"
    finally:
        with get_fabric_conn() as cleanup_conn:
            _cleanup_approval(cleanup_conn, department)


# ---------------------------------------------------------------------------
# B1 gate fix — GET /approval/status had no authorization at all. Read-only:
# a 403 is raised before any DB write, so no cleanup is needed here.
# ---------------------------------------------------------------------------

def _discover_department_outside_filler_scope(conn: pyodbc.Connection, filler_email: str) -> str:
    """Return a real department name whose cost centers (per
    dbo.cc_filler_map) are entirely OUTSIDE `filler_email`'s own See scope --
    used to prove B1 (a filler must not be able to view another
    department's approval status)."""
    scope = resolve_scope(filler_email, conn)
    see_cost_centers = scope.see_cost_centers or ["__NONE__"]
    placeholders = ", ".join("?" for _ in see_cost_centers)
    cursor = conn.cursor()
    try:
        cursor.execute(
            f"""
            SELECT TOP 1 department FROM dbo.cc_filler_map
            WHERE department NOT IN (
                SELECT DISTINCT department FROM dbo.cc_filler_map WHERE cost_center IN ({placeholders})
            )
            ORDER BY department
            """,
            *see_cost_centers,
        )
        row = cursor.fetchone()
    finally:
        cursor.close()
    assert row is not None, f"no department found outside {filler_email}'s See scope"
    return row[0]


@pytest.mark.integration
def test_status_forbidden_for_department_outside_callers_scope_live() -> None:
    """B1 gate fix, live: GET /approval/status must 403 when the caller
    queries a real department outside their own See scope -- proves the RLS
    check runs against the real dbo.cc_filler_map, not just a mocked scope."""
    with get_fabric_conn() as conn:
        _department, filler_email, _manager_email = _discover_full_chain_filler(conn)
        other_department = _discover_department_outside_filler_scope(conn, filler_email)

    fastapi_app.dependency_overrides[get_current_user_email] = lambda: filler_email
    try:
        with TestClient(fastapi_app) as client:
            response = client.get(
                "/approval/status", params={"department": other_department, "fiscal_year": FISCAL_YEAR}
            )
        assert response.status_code == 403, response.text
    finally:
        fastapi_app.dependency_overrides.pop(get_current_user_email, None)


# ---------------------------------------------------------------------------
# A8 reference-data pickers — live proofs (added 2026-07-16). Read-only
# (dbo.gl_group / dbo.cc_filler_map, both already read elsewhere in this
# file) -- no writes, no sentinel year needed.
# ---------------------------------------------------------------------------

@pytest.mark.integration
def test_fetch_gl_accounts_runs_live_and_flags_a_known_special_group() -> None:
    """Proves `dbo.gl_group`'s real columns (gl_code/gl_group/gl_name) work
    end-to-end through `fetch_gl_accounts`, and that a real Entertainment GL
    is correctly flagged `is_special` (ADR-0005)."""
    from app.reference_data import fetch_gl_accounts

    with get_fabric_conn() as conn:
        rows = fetch_gl_accounts(conn)

    assert rows, "dbo.gl_group returned zero rows live"
    assert all({"gl_code", "gl_group", "gl_name", "is_special"} <= row.keys() for row in rows)
    entertainment_rows = [r for r in rows if r["gl_group"] == "Entertainment"]
    assert entertainment_rows, "no live Entertainment GL found to prove is_special=True"
    assert all(r["is_special"] is True for r in entertainment_rows)
    normal_rows = [r for r in rows if r["gl_group"] not in SPECIAL_GL_GROUPS]
    assert normal_rows, "no live normal (non-special) GL found"
    assert all(r["is_special"] is False for r in normal_rows)


@pytest.mark.integration
def test_fetch_departments_runs_live_scoped_to_a_real_fillers_see_scope() -> None:
    """Proves `dbo.cc_filler_map` read + the D11 dedup tie-break work live,
    scoped exactly like GET /budget for a real filler (never wider)."""
    from app.reference_data import fetch_departments

    with get_fabric_conn() as conn:
        cost_center, filler_email = _discover_cc_filler(conn)
        scope = resolve_scope(filler_email, conn)
        assert scope.see_cost_centers, f"{filler_email} unexpectedly has an empty See scope"

        rows = fetch_departments(conn, scope.see_cost_centers)

    assert rows, "fetch_departments returned zero rows for a real filler's See scope"
    returned_ccs = {r["cost_center"] for r in rows}
    assert returned_ccs <= set(scope.see_cost_centers), "fetch_departments returned a CC outside the requested scope"
    assert cost_center in returned_ccs
    assert all({"cost_center", "department", "division", "c_level"} <= row.keys() for row in rows)


# ---------------------------------------------------------------------------
# A9 backend gap close — delete_detail_line / delete_trip, live (2026-07-16).
# Own sentinel year: 2096/2097/2099 are already used elsewhere in this file.
# ---------------------------------------------------------------------------

DELETE_FISCAL_YEAR = 2095  # sentinel — never a real planning year, distinct from 2096/2097/2099 above


def _cleanup_delete_sentinel_year(conn: pyodbc.Connection) -> None:
    """Same shape as `_cleanup_sentinel_year` above, parametrized to
    DELETE_FISCAL_YEAR instead of the module-wide FISCAL_YEAR — kept as its
    own small helper rather than generalizing the existing one, so this
    section never risks touching the other tests' sentinel year."""
    cursor = conn.cursor()
    try:
        cursor.execute("DELETE FROM budget.pending_budget_detail WHERE fiscal_year = ?", DELETE_FISCAL_YEAR)
        cursor.execute("DELETE FROM budget.budget_trip WHERE fiscal_year = ?", DELETE_FISCAL_YEAR)
        cursor.execute("DELETE FROM budget.pending_budget WHERE fiscal_year = ?", DELETE_FISCAL_YEAR)
        conn.commit()
    finally:
        cursor.close()

    cursor = conn.cursor()
    try:
        cursor.execute("SELECT COUNT(*) FROM budget.pending_budget_detail WHERE fiscal_year = ?", DELETE_FISCAL_YEAR)
        detail_left = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM budget.budget_trip WHERE fiscal_year = ?", DELETE_FISCAL_YEAR)
        trip_left = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM budget.pending_budget WHERE fiscal_year = ?", DELETE_FISCAL_YEAR)
        pending_left = cursor.fetchone()[0]
    finally:
        cursor.close()

    assert detail_left == 0, f"cleanup left {detail_left} budget.pending_budget_detail rows at fiscal_year={DELETE_FISCAL_YEAR}"
    assert trip_left == 0, f"cleanup left {trip_left} budget.budget_trip rows at fiscal_year={DELETE_FISCAL_YEAR}"
    assert pending_left == 0, f"cleanup left {pending_left} budget.pending_budget rows at fiscal_year={DELETE_FISCAL_YEAR}"


@pytest.mark.integration
def test_delete_detail_line_zeroes_parent_cell_live(discovered: tuple[str, str, str]) -> None:
    """Create an Entertainment detail line (1000) -> parent cell is really
    1000 -> delete it -> parent cell is really 0 (row kept, zeroed, never
    removed) and the detail row itself is gone."""
    cost_center, filler_email, gl_account = discovered

    try:
        with get_fabric_conn() as conn:
            scope = resolve_scope(filler_email, conn)
            create_results = save_detail_lines(
                conn,
                [DetailLineInput(cost_center=cost_center, gl_account=gl_account, fiscal_year=DELETE_FISCAL_YEAR, m01=1000)],
                user_email=filler_email, scope=scope,
            )
        assert create_results[0].ok, create_results[0].detail
        detail_id = create_results[0].line.detail_id
        updated_at = create_results[0].line.updated_at

        with get_fabric_conn() as conn:
            scope = resolve_scope(filler_email, conn)
            delete_result = delete_detail_line(conn, detail_id, updated_at, filler_email, scope)
        assert delete_result.ok, delete_result.detail

        with get_fabric_conn() as verify_conn:
            cursor = verify_conn.cursor()
            try:
                cursor.execute(
                    "SELECT m01, total_year FROM budget.pending_budget "
                    "WHERE cost_center = ? AND gl_account = ? AND fiscal_year = ?",
                    cost_center, gl_account, DELETE_FISCAL_YEAR,
                )
                parent_row = cursor.fetchone()
                cursor.execute("SELECT COUNT(*) FROM budget.pending_budget_detail WHERE detail_id = ?", detail_id)
                detail_left = cursor.fetchone()[0]
            finally:
                cursor.close()

        assert parent_row is not None, "parent row must be KEPT (zeroed), not removed"
        assert float(parent_row[0]) == 0, f"parent m01 = {parent_row[0]}, expected 0 after deleting the only line"
        assert float(parent_row[1]) == 0, f"parent total_year = {parent_row[1]}, expected 0"
        assert detail_left == 0, "the detail row itself must be gone after delete"
    finally:
        with get_fabric_conn() as cleanup_conn:
            _cleanup_delete_sentinel_year(cleanup_conn)


@pytest.mark.integration
def test_delete_detail_line_stale_token_is_409_and_row_still_there_live(discovered: tuple[str, str, str]) -> None:
    """A stale `expected_updated_at` (deliberately not the real lock token
    just returned by the create) must be rejected with a conflict and must
    NOT delete the row."""
    cost_center, filler_email, gl_account = discovered

    try:
        with get_fabric_conn() as conn:
            scope = resolve_scope(filler_email, conn)
            create_results = save_detail_lines(
                conn,
                [DetailLineInput(cost_center=cost_center, gl_account=gl_account, fiscal_year=DELETE_FISCAL_YEAR, m01=250)],
                user_email=filler_email, scope=scope,
            )
        assert create_results[0].ok, create_results[0].detail
        detail_id = create_results[0].line.detail_id
        stale_token = datetime(2020, 1, 1, tzinfo=timezone.utc)  # deliberately not the real lock token

        with get_fabric_conn() as conn:
            scope = resolve_scope(filler_email, conn)
            delete_result = delete_detail_line(conn, detail_id, stale_token, filler_email, scope)
        assert delete_result.ok is False
        assert delete_result.error == "conflict"

        with get_fabric_conn() as verify_conn:
            cursor = verify_conn.cursor()
            try:
                cursor.execute("SELECT m01 FROM budget.pending_budget_detail WHERE detail_id = ?", detail_id)
                row = cursor.fetchone()
            finally:
                cursor.close()
        assert row is not None, "the row must still exist after a rejected stale-token delete"
        assert float(row[0]) == 250
    finally:
        with get_fabric_conn() as cleanup_conn:
            _cleanup_delete_sentinel_year(cleanup_conn)


@pytest.mark.integration
def test_delete_trip_removes_all_lines_and_recomputes_all_parents_live(discovered: tuple[str, str, str]) -> None:
    """Create a trip (auto-derived per-diem) + its 3 manual expense lines
    (transport/accommodation/other) -> delete the trip -> the trip row is
    gone, every one of its detail lines (all 4 types) is gone, and all 4
    of that side's travel-GL parent cells are really 0."""
    cost_center, filler_email, _ = discovered

    with get_fabric_conn() as conn:
        traveler_empcode = _discover_traveler_with_a_configured_rate(conn)

    try:
        with get_fabric_conn() as conn:
            scope = resolve_scope(filler_email, conn)
            trip_results = save_trip(
                conn,
                [TripInput(
                    cost_center=cost_center, fiscal_year=DELETE_FISCAL_YEAR, traveler_empcode=traveler_empcode,
                    country_group=1, days=3, travel_months=["01"], side="COST",
                )],
                user_email=filler_email, scope=scope,
            )
        assert trip_results[0].ok, trip_results[0].detail
        trip_id = trip_results[0].trip.trip_id
        trip_updated_at = trip_results[0].trip.updated_at

        with get_fabric_conn() as conn:
            scope = resolve_scope(filler_email, conn)
            manual_results = save_detail_lines(
                conn,
                [
                    DetailLineInput(
                        cost_center=cost_center, gl_account=TRAVEL_GL_BY_TYPE_SIDE["transport"]["COST"],
                        fiscal_year=DELETE_FISCAL_YEAR, trip_id=trip_id, m01=100,
                    ),
                    DetailLineInput(
                        cost_center=cost_center, gl_account=TRAVEL_GL_BY_TYPE_SIDE["accommodation"]["COST"],
                        fiscal_year=DELETE_FISCAL_YEAR, trip_id=trip_id, m01=200,
                    ),
                    DetailLineInput(
                        cost_center=cost_center, gl_account=TRAVEL_GL_BY_TYPE_SIDE["other"]["COST"],
                        fiscal_year=DELETE_FISCAL_YEAR, trip_id=trip_id, m01=50,
                    ),
                ],
                user_email=filler_email, scope=scope,
            )
        assert all(r.ok for r in manual_results), [r.detail for r in manual_results if not r.ok]

        with get_fabric_conn() as conn:
            scope = resolve_scope(filler_email, conn)
            delete_result = delete_trip(conn, trip_id, trip_updated_at, filler_email, scope)
        assert delete_result.ok, delete_result.detail

        with get_fabric_conn() as verify_conn:
            cursor = verify_conn.cursor()
            try:
                cursor.execute("SELECT COUNT(*) FROM budget.budget_trip WHERE trip_id = ?", trip_id)
                trip_left = cursor.fetchone()[0]
                cursor.execute("SELECT COUNT(*) FROM budget.pending_budget_detail WHERE trip_id = ?", trip_id)
                lines_left = cursor.fetchone()[0]
                cost_side_gls = [sides["COST"] for sides in TRAVEL_GL_BY_TYPE_SIDE.values()]
                parent_totals = {}
                for gl in cost_side_gls:
                    cursor.execute(
                        "SELECT total_year FROM budget.pending_budget "
                        "WHERE cost_center = ? AND gl_account = ? AND fiscal_year = ?",
                        cost_center, gl, DELETE_FISCAL_YEAR,
                    )
                    r = cursor.fetchone()
                    parent_totals[gl] = float(r[0]) if r else None
            finally:
                cursor.close()

        assert trip_left == 0, "trip header row must be gone after delete"
        assert lines_left == 0, "every one of the trip's detail lines must be gone after delete"
        assert all(total == 0 for total in parent_totals.values()), (
            f"expected all 4 COST-side parent cells to be 0 (row kept, zeroed), got {parent_totals}"
        )
    finally:
        with get_fabric_conn() as cleanup_conn:
            _cleanup_delete_sentinel_year(cleanup_conn)
