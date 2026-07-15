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

import pyodbc
import pytest
from fastapi.testclient import TestClient

import app.sap as sap_module
from app.auth import get_current_user_email
from app.db import get_fabric_conn, get_gold_conn
from app.main import app as fastapi_app
from app.read_model import fetch_board_pending_rows, fetch_cc_dims, get_budget_grid
from app.rls import resolve_scope
from app.sap import MONTH_COLUMNS, SapActualsFetchError, fetch_sap_actuals
from app.special_gl import SPECIAL_GL_GROUPS
from app.write_model import (
    EXCLUDED_COST_CENTERS,
    DetailLineInput,
    PendingRowInput,
    save_detail_lines,
    save_pending_rows,
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
