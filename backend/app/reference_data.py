"""Reference-data reads for A8's frontend pickers — no RLS write path, no
approval concern. Two independent lookups grouped here because both exist
for the same purpose (feed a picker on the main budget grid) and are each a
single trivial `dbo.*` master read:

- `fetch_gl_accounts` — the full GL master (`dbo.gl_group`), flagged with
  `is_special` (ADR-0005) so the frontend's "+ เพิ่ม transaction" GL picker
  can exclude the 6 special groups (those route through their own subform,
  A9 — not a plain main-page cell).
- `fetch_departments` — the caller's (cost_center, department, division,
  c_level) rows from `dbo.cc_filler_map`, scoped exactly like `GET /budget`
  (See-scope list, or `None` for the admin-wide bypass). Feeds the ฝ่าย
  picker's สายงาน›ฝ่าย›CC hierarchy (ADR-0019).

Both tables/columns were already exercised successfully by A4/A5's live
integration tests (`dbo.gl_group.{gl_code,gl_group,gl_name}`,
`dbo.cc_filler_map.{cost_center,department,division,c_level,filler_email}`)
— no fresh INFORMATION_SCHEMA probe needed, the column names are proven.
"""
import pyodbc

from app.special_gl import classify_special_gl


def fetch_gl_accounts(conn: pyodbc.Connection) -> list[dict]:
    """Full GL master, one row per GL account. No RLS — GL codes are a
    shared reference list, not scoped per user."""
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT gl_code, gl_group, gl_name FROM dbo.gl_group ORDER BY gl_group, gl_code")
        rows = cursor.fetchall()
    finally:
        cursor.close()
    return [
        {
            "gl_code": r[0],
            "gl_group": r[1],
            "gl_name": r[2],
            "is_special": classify_special_gl(r[1]) is not None,
        }
        for r in rows
    ]


def fetch_departments(conn: pyodbc.Connection, cost_centers: list[str] | None) -> list[dict]:
    """One deterministic row per cost_center (same D11 tie-break as
    `read_model.fetch_cc_dims`: `ROW_NUMBER() ... ORDER BY filler_email`,
    since a CC can have more than one Filler row with the same dims).

    `cost_centers=None` = admin-wide, no restriction (caller decides when
    that is allowed, mirroring `get_budget_grid`'s admin-wide gate).
    `cost_centers=[]` short-circuits to no rows, no query — an empty SQL
    `IN ()` is invalid syntax and there is nothing to fetch anyway."""
    if cost_centers is not None and len(cost_centers) == 0:
        return []

    where_clause = ""
    params: list[str] = []
    if cost_centers is not None:
        placeholders = ", ".join(["?"] * len(cost_centers))
        where_clause = f"WHERE cost_center IN ({placeholders})"
        params = list(cost_centers)

    cursor = conn.cursor()
    try:
        cursor.execute(
            f"""
            SELECT cost_center, department, division, c_level FROM (
                SELECT cost_center, department, division, c_level,
                       ROW_NUMBER() OVER (PARTITION BY cost_center ORDER BY filler_email) AS rn
                FROM dbo.cc_filler_map
                {where_clause}
            ) ranked
            WHERE rn = 1
            ORDER BY division, department, cost_center
            """,
            *params,
        )
        rows = cursor.fetchall()
    finally:
        cursor.close()
    return [
        {"cost_center": r[0], "department": r[1], "division": r[2], "c_level": r[3]}
        for r in rows
    ]
