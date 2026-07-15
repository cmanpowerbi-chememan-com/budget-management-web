"""Read-only GET endpoints backing the A9 special-GL detail subforms + Trip
Manager: `GET /budget/detail`, `GET /budget/trip`. A9 gap-fill (flagged, not
invented as a write-path change) — see `app/subform_read.py`'s module
docstring for why these did not already exist. No write, no approval
concern; never touches `write_model.py`/`approval.py`.

Scope check mirrors the write path's `ForbiddenScopeError` (403) but for
READ access: the caller must See the cost_center (or be admin) — matches
`GET /budget`'s RLS model (ADR-0019), just applied to one cost_center at a
time since these two endpoints always take a specific `cost_center` query
param rather than a scoped list.
"""
import logging
from datetime import datetime

import pyodbc
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from app.auth import get_current_user_email
from app.db import get_fabric_conn
from app.rls import Scope, resolve_scope
from app.subform_read import fetch_detail_lines, fetch_trips

logger = logging.getLogger(__name__)
router = APIRouter()

_DB_UNAVAILABLE_DETAIL = "Database unavailable, please try again later"


def _ensure_read_scope(cost_center: str, scope: Scope) -> None:
    if scope.is_admin:
        return
    if cost_center not in scope.see_cost_centers:
        raise HTTPException(status_code=403, detail=f"{cost_center} is not in your See scope")


class DetailLineRow(BaseModel):
    detail_id: int
    cost_center: str
    gl_account: str
    fiscal_year: int
    trip_id: int | None
    gl_group: str
    line_label: str | None
    m01: float
    m02: float
    m03: float
    m04: float
    m05: float
    m06: float
    m07: float
    m08: float
    m09: float
    m10: float
    m11: float
    m12: float
    total_year: float
    meta_json: dict | None
    updated_at: datetime


class TripRow(BaseModel):
    trip_id: int
    cost_center: str
    fiscal_year: int
    traveler_empcode: str
    traveler_name: str
    position: str
    destination: str | None
    country_group: int
    days: int
    travel_months: list[str]
    purpose: str | None
    side: str
    updated_at: datetime
    # Recomputed on every read (ADR-0015) — `None` + `per_diem_error` set
    # when the current rate/FX config can't derive it (never a fallback
    # number, never a 500 for the whole list — see subform_read.fetch_trips).
    per_diem_months: dict[str, float] | None
    per_diem_error: str | None


@router.get("/budget/detail", response_model=list[DetailLineRow])
def get_detail_lines(
    cost_center: str = Query(...),
    gl_account: str = Query(...),
    fiscal_year: int = Query(...),
    email: str = Depends(get_current_user_email),
) -> list[DetailLineRow]:
    with get_fabric_conn() as conn:
        scope = resolve_scope(email, conn)
        _ensure_read_scope(cost_center, scope)
        try:
            rows = fetch_detail_lines(conn, cost_center, gl_account, fiscal_year)
        except pyodbc.Error as exc:
            logger.exception("fetch_detail_lines failed for %s/%s", cost_center, gl_account)
            raise HTTPException(status_code=502, detail=_DB_UNAVAILABLE_DETAIL) from exc
    return [DetailLineRow(**r) for r in rows]


@router.get("/budget/trip", response_model=list[TripRow])
def get_trips(
    cost_center: str = Query(...),
    fiscal_year: int = Query(...),
    email: str = Depends(get_current_user_email),
) -> list[TripRow]:
    with get_fabric_conn() as conn:
        scope = resolve_scope(email, conn)
        _ensure_read_scope(cost_center, scope)
        try:
            rows = fetch_trips(conn, cost_center, fiscal_year)
        except pyodbc.Error as exc:
            logger.exception("fetch_trips failed for %s", cost_center)
            raise HTTPException(status_code=502, detail=_DB_UNAVAILABLE_DETAIL) from exc
    return [TripRow(**r) for r in rows]
