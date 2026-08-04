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
- `fetch_travelers` — Trip Manager's traveler picker, scoped by the
  COST CENTER BEING EDITED (2026-08-04) — the ฝ่าย/CC the grid has open,
  never the caller's own department (an admin has none). Resolves
  `cost_center` -> its Filler email(s) in `dbo.cc_filler_map` -> the UNION of
  `dbo.v_traveler_picker` rows for those Fillers (same department + direct
  manager + manager's manager + direct reports — see
  db/ddl/traveler_picker_views.sql), a SUBSET of `dbo.v_employee_primary`
  which `write_model._lookup_traveler` validates against, so every pickable
  traveler stays save-able. Falls back to the CALLER's own picker rows when
  the cost center has no Filler mapping, then to the full roster when the
  caller isn't in the employee roster either (admin/test accounts) — a
  filler must never lose the ability to pick (never an empty list where the
  old code returned rows).
- `fetch_countries` — Trip Manager's destination-country picker from
  `dbo.country_group` (group NAME → per-diem group int).

gl_group/cc_filler_map columns were already exercised by A4/A5's live
integration tests; v_employee_primary/country_group columns were freshly
introspected via INFORMATION_SCHEMA 2026-07-17 (the spec DBML's
country_group columns were WRONG — live stores group NAMES).
"""
import logging

import pyodbc

from app.gl_access import normalize_edit_by
from app.special_gl import classify_special_gl

logger = logging.getLogger(__name__)

# Live dbo.country_group stores NAMES (introspected 2026-07-17: 'domestic' 1
# row, 'asian' 12 rows); the API/per-diem contract is ints (TripInput
# .country_group). Group 3 ("other") is deliberately NOT here — it is a
# frontend-added choice covering every country outside this master list.
_COUNTRY_GROUP_BY_NAME: dict[str, int] = {"domestic": 1, "asian": 2}


def fetch_gl_accounts(conn: pyodbc.Connection, *, include_edit_by: bool = False, is_admin: bool = False) -> list[dict]:
    """Full GL master, one row per GL account. No RLS — GL codes are a
    shared reference list, not scoped per user (EXCEPT the 13 admin-only
    GLs, design v2 — SECRET from a non-admin caller: they never appear in
    this list at all, not just their amounts).

    `include_edit_by=False` (the flag-OFF default): identical query/shape to
    before this feature — never selects `edit_by`, zero behavior change.
    `include_edit_by=True`: also selects `edit_by`; a row normalizing to
    'admin' is DROPPED entirely for a non-admin caller (`is_admin=False`) —
    not just its `edit_by` field, the whole row — and every remaining row
    carries a normalized `edit_by` ('user'/'admin')."""
    cursor = conn.cursor()
    try:
        if include_edit_by:
            cursor.execute("SELECT gl_code, gl_group, gl_name, edit_by FROM dbo.gl_group ORDER BY gl_group, gl_code")
        else:
            cursor.execute("SELECT gl_code, gl_group, gl_name FROM dbo.gl_group ORDER BY gl_group, gl_code")
        rows = cursor.fetchall()
    finally:
        cursor.close()

    result: list[dict] = []
    for r in rows:
        item = {
            "gl_code": r[0],
            "gl_group": r[1],
            "gl_name": r[2],
            "is_special": classify_special_gl(r[1]) is not None,
        }
        if include_edit_by:
            edit_by = normalize_edit_by(r[3])
            if edit_by == "admin" and not is_admin:
                continue  # SECRET GL — non-admin never sees this row exists
            item["edit_by"] = edit_by
        result.append(item)
    return result


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


# v_traveler_picker's own dedup (view 2 of traveler_picker_views.sql) only
# collapses ONE filler's rows. Unioning several fillers of the same cost
# center can reintroduce the same traveler via more than one leg — this
# keeps the single strongest reason, same priority order as the view.
_PICK_REASON_RANK = {"manager": 0, "skip_manager": 1, "direct_report": 2, "same_department": 3}


def _query_picker_rows(cursor: pyodbc.Cursor, filler_emails: list[str]) -> list[tuple]:
    """One `dbo.v_traveler_picker` read for however many Filler emails are
    reaching for the same cost center (1 for the caller-fallback path, N for
    a multi-Filler CC)."""
    placeholders = ", ".join(["?"] * len(filler_emails))
    cursor.execute(
        "SELECT traveler_empcode, traveler_name, traveler_position, traveler_email, pick_reason "
        f"FROM dbo.v_traveler_picker WHERE filler_email IN ({placeholders}) "
        # Deterministic input to the dedupe below — without it a tie between
        # two Fillers' rows for the same traveler is resolved by whatever
        # order the engine happened to return.
        "ORDER BY traveler_empcode",
        *[e.strip().lower() for e in filler_emails],
    )
    return cursor.fetchall()


def _dedupe_picker_rows(rows: list[tuple]) -> list[dict]:
    """Collapse (filler x traveler) pairs to one row per `traveler_empcode`,
    keeping the strongest `pick_reason`, sorted by name. NULL HR fields
    coerce to '' (API contract is plain strings); email is lower-cased."""
    best: dict[str, tuple[int, str, str, str]] = {}
    for empcode, name, position, email, pick_reason in rows:
        rank = _PICK_REASON_RANK.get(pick_reason, 99)
        if empcode not in best or rank < best[empcode][0]:
            best[empcode] = (rank, name or "", position or "", (email or "").lower())
    result = [
        {"empcode": empcode, "name": name, "position": position, "email": email}
        for empcode, (_rank, name, position, email) in best.items()
    ]
    result.sort(key=lambda r: r["name"])
    return result


def fetch_travelers(conn: pyodbc.Connection, cost_center: str, caller_email: str) -> list[dict]:
    """Traveler list for the cost_center being edited, sorted by Thai name.

    Scoping order (each fallback logged at WARNING — a filler must never
    lose the ability to pick, so this never returns an empty list where the
    old caller-only lookup returned rows):
    1. `dbo.cc_filler_map` -> every Filler email mapped to `cost_center` ->
       the UNION of their `dbo.v_traveler_picker` rows (dept + manager chain
       + direct reports, deduped by empcode — see `_dedupe_picker_rows`).
    2. No Filler mapped to `cost_center` (or the mapped Fillers matched 0
       picker rows) -> the CALLER's own picker rows (today's pre-scoping
       behavior) — e.g. an admin browsing a CC they don't fill.
    3. Caller absent from the picker too (admin/test account, not an
       employee at all) -> the FULL roster from `dbo.v_employee_primary`.
    """
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT DISTINCT filler_email FROM dbo.cc_filler_map WHERE cost_center = ?", cost_center)
        # `.strip()` guards a whitespace-only mapping row: SQL Server compares
        # strings trailing-blank-insensitively, so a lone ' ' would match the
        # picker view's empty filler_email bucket (235 travelers) and hand one
        # cost center the wrong department.
        filler_emails = [r[0] for r in cursor.fetchall() if r[0] and r[0].strip()]

        if filler_emails:
            rows = _dedupe_picker_rows(_query_picker_rows(cursor, filler_emails))
            if rows:
                return rows
            logger.warning(
                "fetch_travelers: cost_center=%r's %d filler(s) matched 0 v_traveler_picker rows — "
                "falling back to caller %r",
                cost_center, len(filler_emails), caller_email,
            )
        else:
            logger.warning(
                "fetch_travelers: cost_center=%r has no dbo.cc_filler_map row — falling back to caller %r",
                cost_center, caller_email,
            )

        rows = _dedupe_picker_rows(_query_picker_rows(cursor, [caller_email]))
        if rows:
            return rows

        logger.warning(
            "fetch_travelers: caller %r not in dbo.v_traveler_picker either — full-roster fallback",
            caller_email,
        )
        cursor.execute(
            "SELECT employee_code, full_name_th, job_level_name_en, email "
            "FROM dbo.v_employee_primary ORDER BY full_name_th"
        )
        rows = [
            {"empcode": r[0], "name": r[1] or "", "position": r[2] or "", "email": (r[3] or "").lower()}
            for r in cursor.fetchall()
        ]
    finally:
        cursor.close()
    return rows


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
