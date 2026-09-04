"""Read-only support for the A9 special-GL/Trip-Manager subforms — a gap
closed in A9, flagged rather than silently invented:

A5 shipped save-ONLY entry points (`PUT /budget/detail`, `POST|PUT
/budget/trip` in `write_model.py`/`routers/budget_write.py`) with no matching
GET. Without a read path a subform can create a detail line/trip but never
list, review, or edit an EXISTING one — and the optimistic-lock token
(`expected_updated_at`) every UPDATE requires can only come from a prior
read. This module is READ-ONLY: it never writes, and it does not modify
`write_model.py`/`approval.py` — it only IMPORTS two already-tested private
lookups (`_lookup_per_diem_rate`, `_lookup_fx`) so the per-diem recompute
below can never drift from the (already bug-fixed once, D1) write path.

Per-diem recompute-on-read (ADR-0015, ADR-0011 "opening the subform
recomputes immediately"): `fetch_trips` re-derives every trip's
`per_diem_months` with the CURRENT fiscal-year FX / per-diem rate on every
read, never the stale amount last persisted to `pending_budget_detail`.
Trip-level failures (missing rate/FX) are caught PER TRIP here — never
raised for the whole list — mirroring `write_model._run_per_item`'s "one
item's failure never blocks the others" philosophy, applied to a read
instead of a write; each trip carries its own `per_diem_error` instead.

No DELETE here (and none in `write_model.py` either) — flagged as a real
backend gap in the A9 final report, not invented inline.
"""
import json

import pyodbc

from app.per_diem import MONTH_COLUMNS, MissingFxRateError, MissingPerDiemRateError, derive_per_diem
from app.write_model import _lookup_fx, _lookup_per_diem_rate

_DETAIL_LINE_COLUMNS: tuple[str, ...] = (
    "detail_id", "cost_center", "gl_account", "fiscal_year", "trip_id", "gl_group", "line_label",
    *MONTH_COLUMNS, "total_year", "meta_json", "_updated_at",
)

# ⚠ `project` was added by setup/migrate_budget_trip_project.py and `remark`
# by setup/migrate_budget_trip_remark.py — this SELECT requires BOTH
# migrations on the live table (same rule as client_token: run the
# migrations before deploying this backend, or every GET /budget/trip 502s).
_TRIP_COLUMNS: tuple[str, ...] = (
    "trip_id", "cost_center", "fiscal_year", "traveler_empcode", "traveler_name", "position",
    "destination", "country_group", "days", "travel_months", "purpose", "project", "remark", "side", "_updated_at",
)


def fetch_detail_lines(conn: pyodbc.Connection, cost_center: str, gl_account: str, fiscal_year: int) -> list[dict]:
    """All `pending_budget_detail` lines for one (cost_center, gl_account,
    fiscal_year) key — the 5 non-travel special groups' subform lists this
    directly; Trip Manager also calls it (per travel type × side GL) to show
    the manually-entered transport/accommodation/other lines already
    attached to a `trip_id`."""
    cursor = conn.cursor()
    try:
        cursor.execute(
            f"""
            SELECT {', '.join(_DETAIL_LINE_COLUMNS)}
            FROM budget.pending_budget_detail
            WHERE cost_center = ? AND gl_account = ? AND fiscal_year = ?
            ORDER BY detail_id
            """,
            cost_center, gl_account, fiscal_year,
        )
        rows = cursor.fetchall()
    finally:
        cursor.close()

    result = []
    for row in rows:
        r = dict(zip(_DETAIL_LINE_COLUMNS, row))
        r["meta_json"] = json.loads(r["meta_json"]) if r["meta_json"] else None
        r["updated_at"] = r.pop("_updated_at")
        result.append(r)
    return result


def fetch_trips(conn: pyodbc.Connection, cost_center: str, fiscal_year: int) -> list[dict]:
    """All `budget_trip` rows for one (cost_center, fiscal_year) — both
    COST and SGA sides together (Trip Manager shows every trip regardless of
    side, each trip carries its own `side`). `per_diem_months` is
    RECOMPUTED here with the current rate/FX (never trusted from the stored
    detail line, ADR-0015); a missing rate/FX becomes `per_diem_error` on
    that ONE trip, never an exception that would 500 the whole list."""
    cursor = conn.cursor()
    try:
        cursor.execute(
            f"""
            SELECT {', '.join(_TRIP_COLUMNS)}
            FROM budget.budget_trip
            WHERE cost_center = ? AND fiscal_year = ?
            ORDER BY trip_id
            """,
            cost_center, fiscal_year,
        )
        rows = cursor.fetchall()
    finally:
        cursor.close()

    result = []
    for row in rows:
        r = dict(zip(_TRIP_COLUMNS, row))
        r["updated_at"] = r.pop("_updated_at")
        travel_months_csv = r.pop("travel_months")
        r["travel_months"] = travel_months_csv.split(",") if travel_months_csv else []

        per_diem_months: dict[str, float] | None = None
        per_diem_error: str | None = None
        try:
            rate_row = _lookup_per_diem_rate(conn, r["position"])
            fx_rate = None
            if r["country_group"] in (2, 3):
                fx_rate = _lookup_fx(conn, r["fiscal_year"])
                if fx_rate is None:
                    raise MissingFxRateError(f"no master_currency_rate for fiscal_year={r['fiscal_year']}")
            per_diem_months = derive_per_diem(
                days=r["days"], country_group=r["country_group"], rate_row=rate_row,
                fx_rate=fx_rate, travel_months=r["travel_months"],
            )
        except (MissingPerDiemRateError, MissingFxRateError, ValueError) as exc:
            per_diem_error = str(exc)

        r["per_diem_months"] = per_diem_months
        r["per_diem_error"] = per_diem_error
        result.append(r)
    return result
