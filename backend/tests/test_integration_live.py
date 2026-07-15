"""Live-DB integration tests — the FIRST tests that run against the real,
consolidated Fabric SQL Database (ADR-0023: `budget.*` transactional +
`dbo.*` masters, same DB).

Why this file exists: the A5 gate found that `conn.commit()` ran BEFORE
`_recompute_parent_cell`, so a special-GL parent cell's total was silently
rolled back on connection close while the API still returned 200. That bug
was fixed and mock-verified only. This file proves it on the REAL database:
save Entertainment 1,000 -> the API says ok AND the parent cell is really
1,000 when read back on a FRESH connection.

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
import pyodbc
import pytest

from app.db import get_fabric_conn
from app.rls import resolve_scope
from app.write_model import EXCLUDED_COST_CENTERS, DetailLineInput, save_detail_lines

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
