"""Reference-data reads for the frontend pickers — no RLS write path, no
approval concern. Independent lookups grouped here because all exist for
the same purpose (feed a picker) and are each a single trivial `dbo.*`
master read:

- `fetch_gl_accounts` — the full GL master (`dbo.gl_group`), flagged with
  `is_special` (ADR-0005) so the frontend's "+ เพิ่ม transaction" GL picker
  can exclude the 6 special groups (those route through their own subform,
  A9 — not a plain main-page cell).
- `fetch_departments` — the caller's (cost_center, department, division,
  c_level) rows from `dbo.cc_filler_map`, scoped exactly like `GET /budget`
  (See-scope list, or `None` for the admin-wide bypass). Feeds the ฝ่าย
  picker's สายงาน›ฝ่าย›CC hierarchy (ADR-0019).
- `fetch_travelers` — Trip Manager's traveler picker: the full roster from
  `dbo.v_employee_primary` (the SAME view `write_model._lookup_traveler`
  validates against, so every pickable traveler is save-able).
- `fetch_countries` — Trip Manager's destination-country picker from
  `dbo.country_group` (group NAME → per-diem group int).

gl_group/cc_filler_map columns were already exercised by A4/A5's live
integration tests; v_employee_primary/country_group columns were freshly
introspected via INFORMATION_SCHEMA 2026-07-17 (the spec DBML's
country_group columns were WRONG — live stores group NAMES).
"""
import logging

import pyodbc

from app.special_gl import classify_special_gl

logger = logging.getLogger(__name__)

# Live dbo.country_group stores NAMES (introspected 2026-07-17: 'domestic' 1
# row, 'asian' 12 rows); the API/per-diem contract is ints (TripInput
# .country_group). Group 3 ("other") is deliberately NOT here — it is a
# frontend-added choice covering every country outside this master list.
_COUNTRY_GROUP_BY_NAME: dict[str, int] = {"domestic": 1, "asian": 2}


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


def fetch_travelers(conn: pyodbc.Connection) -> list[dict]:
    """Full roster traveler list, sorted by Thai name.

    FULL ROSTER, not dept-filtered: cc_filler_map.department matches the HR
    org names (`org_name_en`) for only 35/114 ฝ่าย (0/114 on Thai names —
    live-verified 2026-07-17), so filtering the picker by the CC's
    department would return an EMPTY list for ~70% of departments. The
    task-approved fallback is the full active roster; the caller's
    See-scope on the cost_center is still enforced at the router. NULL HR
    fields coerce to '' (API contract is plain strings)."""
    cursor = conn.cursor()
    try:
        cursor.execute(
            "SELECT employee_code, full_name_th, job_level_name_en "
            "FROM dbo.v_employee_primary ORDER BY full_name_th"
        )
        rows = cursor.fetchall()
    finally:
        cursor.close()
    return [{"empcode": r[0], "name": r[1] or "", "position": r[2] or ""} for r in rows]


def fetch_countries(conn: pyodbc.Connection) -> list[dict]:
    """Country → per-diem group list, ints per the API contract (1=domestic,
    2=asian; group 3 "other" is frontend-added, never stored). A row whose
    group name is not recognised is SKIPPED with a warning — a typo'd master
    row must surface as a visible picker gap, never silently mis-map to a
    per-diem bucket (and never 500 the whole list)."""
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT country, country_group FROM dbo.country_group")
        rows = cursor.fetchall()
    finally:
        cursor.close()

    result: list[dict] = []
    for country, group_name in rows:
        group = _COUNTRY_GROUP_BY_NAME.get(group_name)
        if group is None:
            logger.warning("dbo.country_group: unrecognised country_group %r for %r — row skipped", group_name, country)
            continue
        result.append({"country": country, "country_group": group})
    result.sort(key=lambda r: (r["country_group"], r["country"]))
    return result
