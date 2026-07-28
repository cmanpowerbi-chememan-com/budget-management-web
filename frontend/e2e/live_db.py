"""Live-DB helper for the Playwright LIVE e2e spec (`live-backend.spec.ts`).

Playwright is TypeScript, so DB access (test-data discovery + sentinel-year
cleanup) is shelled out to this script via child_process. It reuses the
backend's own connection machinery (`app.db`) and the EXACT discovery queries
of `backend/tests/test_integration_live.py` — never reads or prints
`backend/.env` (credentials stay inside `app.config`'s Settings load).

Subcommands (run with the repo venv python; cwd is irrelevant — this script
inserts `backend/` into sys.path itself):

    python live_db.py discover   -> one JSON line:
        {"cost_center": ..., "filler_email": ..., "department": ..., "gl_account": ...}
    python live_db.py cleanup    -> deletes EVERY fiscal_year=2099 row and
        verifies 0 remain; prints {"remaining": {...}} (all zeros) on success,
        exits non-zero if any row survives.

SAFETY (mirrors test_integration_live.py, never-cut):
- `discover` is READ-ONLY against dbo.* masters.
- `cleanup` only ever touches fiscal_year = 2099 (the sentinel year that can
  never collide with real budget data). Tables cleaned: the 3 transactional
  ones (budget.pending_budget_detail / budget.budget_trip /
  budget.pending_budget) PLUS budget.approval_log / budget.approval_status —
  the live spec's Submit step writes those two (same pattern as the
  2093-sentinel section in test_integration_live.py), and leaving a
  PENDING_APPROVER1 row behind would department-lock every later run.
"""
import json
import sys
from pathlib import Path

# Make `app.*` importable regardless of the caller's cwd (Playwright shells
# out from frontend/). backend/.env is anchored absolutely inside
# app.config already, so Settings resolution is cwd-independent too.
_BACKEND_DIR = Path(__file__).resolve().parents[2] / "backend"
sys.path.insert(0, str(_BACKEND_DIR))

from app.config import get_settings  # noqa: E402
from app.db import get_fabric_conn  # noqa: E402
from app.gl_access import fetch_admin_gl_codes  # noqa: E402
from app.read_model import fetch_cc_dims  # noqa: E402
from app.special_gl import SPECIAL_GL_GROUPS  # noqa: E402
from app.write_model import EXCLUDED_COST_CENTERS  # noqa: E402

FISCAL_YEAR = 2099  # sentinel — never a real planning year


def _discover_cc_filler(conn) -> tuple[str, str]:
    """Same query as test_integration_live._discover_cc_filler: a real
    (cost_center, filler_email) pair whose CC is not structurally excluded."""
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
    if row is None:
        raise RuntimeError("no usable (cost_center, filler_email) pair found in dbo.cc_filler_map")
    return row[0], row[1]


def _discover_grid_renderable_non_special_gl(conn) -> str:
    """A real GL code that the LIVE UI can actually exercise end to end:

    - NOT one of the 6 special-GL groups (ADR-0005) — plain cell edit path.
    - gl_code starts with 5 or 6 — the frontend's `groupAndSortBySide` DROPS
      OTHER-side rows from both grid sections, so a non-5/6 GL would save
      fine but be invisible in the browser (and un-assertable).
    - not admin-only (`edit_by='admin'`) — those are hidden from a non-admin
      caller when `gl_edit_by_enabled` is on (fetched here via Settings, not
      by reading any env file).
    """
    admin_gls = fetch_admin_gl_codes(conn) if get_settings().gl_edit_by_enabled else frozenset()
    placeholders = ", ".join("?" for _ in SPECIAL_GL_GROUPS)
    cursor = conn.cursor()
    try:
        cursor.execute(
            f"""
            SELECT gl_code FROM dbo.gl_group
            WHERE gl_group NOT IN ({placeholders})
              AND (gl_code LIKE '5%' OR gl_code LIKE '6%')
            ORDER BY gl_code
            """,
            *SPECIAL_GL_GROUPS,
        )
        candidates = [r[0] for r in cursor.fetchall()]
    finally:
        cursor.close()
    for gl_code in candidates:
        if gl_code not in admin_gls:
            return gl_code
    raise RuntimeError("no grid-renderable non-special GL code found in dbo.gl_group")


def cmd_discover() -> None:
    with get_fabric_conn() as conn:
        cost_center, filler_email = _discover_cc_filler(conn)
        department = fetch_cc_dims(conn, [cost_center]).get(cost_center, {}).get("department")
        if not department:
            raise RuntimeError(f"{cost_center} has no resolvable department in dbo.cc_filler_map")
        gl_account = _discover_grid_renderable_non_special_gl(conn)
    print(json.dumps({
        "cost_center": cost_center,
        "filler_email": filler_email,
        "department": department,
        "gl_account": gl_account,
    }))


def cmd_cleanup() -> None:
    tables = [
        "budget.pending_budget_detail",
        "budget.budget_trip",
        "budget.pending_budget",
        "budget.approval_log",
        "budget.approval_status",
    ]
    with get_fabric_conn() as conn:
        cursor = conn.cursor()
        try:
            for table in tables:
                cursor.execute(f"DELETE FROM {table} WHERE fiscal_year = ?", FISCAL_YEAR)
            conn.commit()
        finally:
            cursor.close()

        remaining: dict[str, int] = {}
        cursor = conn.cursor()
        try:
            for table in tables:
                cursor.execute(f"SELECT COUNT(*) FROM {table} WHERE fiscal_year = ?", FISCAL_YEAR)
                remaining[table] = cursor.fetchone()[0]
        finally:
            cursor.close()

    print(json.dumps({"fiscal_year": FISCAL_YEAR, "remaining": remaining}))
    leftover = {t: n for t, n in remaining.items() if n != 0}
    if leftover:
        print(f"cleanup FAILED — rows left at fiscal_year={FISCAL_YEAR}: {leftover}", file=sys.stderr)
        sys.exit(1)


def main() -> None:
    if len(sys.argv) != 2 or sys.argv[1] not in ("discover", "cleanup"):
        print("usage: live_db.py discover|cleanup", file=sys.stderr)
        sys.exit(2)
    if sys.argv[1] == "discover":
        cmd_discover()
    else:
        cmd_cleanup()


if __name__ == "__main__":
    main()
