"""Reference-data endpoints for the frontend pickers:

- `GET /budget/gl-accounts` — full GL master, flagged `is_special` so the
  "+ เพิ่ม transaction" picker can offer only normal (non-special) GLs.
- `GET /scope/departments` — the caller's (cost_center, department,
  division, c_level) rows, scoped like `GET /budget` (See-scope, or
  admin-wide when `admin_view_enabled=True` AND the caller is admin) — feeds
  the ฝ่าย picker's สายงาน›ฝ่าย›CC hierarchy (ADR-0019).
- `GET /reference/travelers` — Trip Manager's traveler picker, scoped by the
  cost_center being edited (its Filler(s) + manager chain via
  `dbo.v_traveler_picker`, `fetch_travelers`'s fallback ladder); See-scope
  gated on the requested cost_center, admin bypass.
- `GET /reference/countries` — Trip Manager's destination-country picker
  (identity-only auth, like /budget/gl-accounts).

All are read-only, no write path, no approval concern (A5/A6 untouched).
"""
import logging

import pyodbc
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from app.auth import get_current_user_email
from app.config import get_settings
from app.db import get_fabric_conn
from app.reference_data import fetch_countries, fetch_departments, fetch_gl_accounts, fetch_travelers
from app.rls import Scope, resolve_scope

logger = logging.getLogger(__name__)
router = APIRouter()

_DB_UNAVAILABLE_DETAIL = "Database unavailable, please try again later"


class GlAccount(BaseModel):
    gl_code: str
    gl_group: str | None = None
    gl_name: str | None = None
    is_special: bool = False
    # Design v2 (2026-07-17), flag-gated: only present when
    # `Settings.gl_edit_by_enabled` is True. A non-admin caller never
    # receives a row where this would be 'admin' — see fetch_gl_accounts.
    edit_by: str | None = None


class DepartmentRow(BaseModel):
    cost_center: str
    department: str | None = None
    division: str | None = None
    c_level: str | None = None


class TravelerRow(BaseModel):
    empcode: str
    name: str
    position: str
    # Added 2026-08-04 so the frontend combobox can search by email, not
    # just name (common Thai names collide) — always populated, lower-cased.
    email: str


class CountryRow(BaseModel):
    country: str
    # 1 = domestic, 2 = asian, 3 = other (mapped from dbo.country_group's
    # stored NAMES — see app.reference_data._COUNTRY_GROUP_BY_NAME). All 3
    # tiers live in the master since 2026-08-22; before that, group 3 was a
    # FRONTEND-ADDED synthetic choice and never appeared in this response.
    country_group: int


def _ensure_see_scope(cost_center: str, scope: Scope) -> None:
    """Same read-RLS rule as routers/subform.py: the caller must See the
    cost_center, admin bypasses (ADR-0019)."""
    if scope.is_admin:
        return
    if cost_center not in scope.see_cost_centers:
        raise HTTPException(status_code=403, detail=f"{cost_center} is not in your See scope")


@router.get("/budget/gl-accounts", response_model=list[GlAccount])
def gl_accounts(email: str = Depends(get_current_user_email)) -> list[GlAccount]:
    settings = get_settings()
    try:
        # Connection-open inside the try: an open-time failure (driver
        # pyodbc.Error, or msal token failure — DbConnectionError, a
        # pyodbc.Error subclass) → 502, same as a query-time failure.
        with get_fabric_conn() as conn:
            # Flag OFF (default): identity stays unresolved, `edit_by` is
            # never selected — zero behavior change from before this
            # feature. Flag ON: resolve_scope only to learn `is_admin`
            # (needed to decide which rows to drop), not for CC scoping —
            # this list has never been RLS-scoped by cost center.
            is_admin = False
            if settings.gl_edit_by_enabled:
                scope = resolve_scope(email, conn)
                is_admin = scope.is_admin
            rows = fetch_gl_accounts(conn, include_edit_by=settings.gl_edit_by_enabled, is_admin=is_admin)
    except pyodbc.Error as exc:
        logger.exception("fetch_gl_accounts failed for %s", email)
        raise HTTPException(status_code=502, detail=_DB_UNAVAILABLE_DETAIL) from exc
    return [GlAccount(**r) for r in rows]


@router.get("/scope/departments", response_model=list[DepartmentRow])
def departments(
    admin_view_enabled: bool = Query(default=False),
    email: str = Depends(get_current_user_email),
) -> list[DepartmentRow]:
    try:
        # Connection-open AND resolve_scope inside the try: a DB blip at open
        # time or during scope resolution is a 502, never an uncaught 500.
        # Admin-bypass logic unchanged.
        with get_fabric_conn() as conn:
            scope = resolve_scope(email, conn, admin_view_enabled=admin_view_enabled)
            admin_wide = scope.is_admin and admin_view_enabled
            cost_centers = None if admin_wide else scope.see_cost_centers
            rows = fetch_departments(conn, cost_centers)
    except pyodbc.Error as exc:
        logger.exception("fetch_departments failed for %s", email)
        raise HTTPException(status_code=502, detail=_DB_UNAVAILABLE_DETAIL) from exc
    return [DepartmentRow(**r) for r in rows]


@router.get("/reference/travelers", response_model=list[TravelerRow])
def travelers(
    cost_center: str = Query(...),
    email: str = Depends(get_current_user_email),
) -> list[TravelerRow]:
    try:
        # Connection-open AND resolve_scope inside the try: a DB blip at open
        # time or during scope resolution is a 502, never an uncaught 500.
        # The 403 HTTPException from _ensure_see_scope passes through.
        with get_fabric_conn() as conn:
            scope = resolve_scope(email, conn)
            _ensure_see_scope(cost_center, scope)
            rows = fetch_travelers(conn, cost_center, email)
    except pyodbc.Error as exc:
        logger.exception("fetch_travelers failed for %s (cost_center=%s)", email, cost_center)
        raise HTTPException(status_code=502, detail=_DB_UNAVAILABLE_DETAIL) from exc
    return [TravelerRow(**r) for r in rows]


@router.get("/reference/countries", response_model=list[CountryRow])
def countries(email: str = Depends(get_current_user_email)) -> list[CountryRow]:
    try:
        # Identity-only auth (like /budget/gl-accounts) — a shared reference
        # list, never RLS-scoped.
        with get_fabric_conn() as conn:
            rows = fetch_countries(conn)
    except pyodbc.Error as exc:
        logger.exception("fetch_countries failed for %s", email)
        raise HTTPException(status_code=502, detail=_DB_UNAVAILABLE_DETAIL) from exc
    return [CountryRow(**r) for r in rows]
