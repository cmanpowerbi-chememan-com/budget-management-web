"""Reference-data endpoints for the A8 frontend pickers:

- `GET /budget/gl-accounts` — full GL master, flagged `is_special` so the
  "+ เพิ่ม transaction" picker can offer only normal (non-special) GLs.
- `GET /scope/departments` — the caller's (cost_center, department,
  division, c_level) rows, scoped like `GET /budget` (See-scope, or
  admin-wide when `admin_view_enabled=True` AND the caller is admin) — feeds
  the ฝ่าย picker's สายงาน›ฝ่าย›CC hierarchy (ADR-0019).

Both are read-only, no write path, no approval concern (A5/A6 untouched).
"""
import logging

import pyodbc
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from app.auth import get_current_user_email
from app.db import get_fabric_conn
from app.reference_data import fetch_departments, fetch_gl_accounts
from app.rls import resolve_scope

logger = logging.getLogger(__name__)
router = APIRouter()

_DB_UNAVAILABLE_DETAIL = "Database unavailable, please try again later"


class GlAccount(BaseModel):
    gl_code: str
    gl_group: str | None = None
    gl_name: str | None = None
    is_special: bool = False


class DepartmentRow(BaseModel):
    cost_center: str
    department: str | None = None
    division: str | None = None
    c_level: str | None = None


@router.get("/budget/gl-accounts", response_model=list[GlAccount])
def gl_accounts(email: str = Depends(get_current_user_email)) -> list[GlAccount]:
    with get_fabric_conn() as conn:
        try:
            rows = fetch_gl_accounts(conn)
        except pyodbc.Error as exc:
            logger.exception("fetch_gl_accounts failed for %s", email)
            raise HTTPException(status_code=502, detail=_DB_UNAVAILABLE_DETAIL) from exc
    return [GlAccount(**r) for r in rows]


@router.get("/scope/departments", response_model=list[DepartmentRow])
def departments(
    admin_view_enabled: bool = Query(default=False),
    email: str = Depends(get_current_user_email),
) -> list[DepartmentRow]:
    with get_fabric_conn() as conn:
        scope = resolve_scope(email, conn, admin_view_enabled=admin_view_enabled)
        admin_wide = scope.is_admin and admin_view_enabled
        cost_centers = None if admin_wide else scope.see_cost_centers
        try:
            rows = fetch_departments(conn, cost_centers)
        except pyodbc.Error as exc:
            logger.exception("fetch_departments failed for %s", email)
            raise HTTPException(status_code=502, detail=_DB_UNAVAILABLE_DETAIL) from exc
    return [DepartmentRow(**r) for r in rows]
