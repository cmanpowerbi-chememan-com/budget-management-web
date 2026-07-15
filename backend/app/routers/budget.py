"""GET /budget — the merged 3-layer (SAP/Approved/Pending) main budget grid,
RLS-filtered (A4). Read-only: no write, no approval (A5/A6).
"""
import logging

import pyodbc
from fastapi import APIRouter, Depends, HTTPException, Query

from app.auth import get_current_user_email
from app.db import get_fabric_conn, get_gold_conn
from app.read_model import BudgetRow, get_budget_grid
from app.rls import resolve_scope
from app.sap import SapActualsFetchError

logger = logging.getLogger(__name__)
router = APIRouter()

# Generic client-facing detail for any SAP/DB failure — never the raw driver
# or DW error text (that goes to the server log only), matching health.py's
# "never leaks connection details, only a status word" pattern.
_SAP_UNAVAILABLE_DETAIL = "SAP actuals unavailable, please try again later"


@router.get("/budget", response_model=list[BudgetRow])
def budget(
    year: int = Query(..., description="Planning fiscal year (Pending layer), e.g. 2027"),
    cost_center: str | None = Query(default=None, alias="cost_center"),
    department: str | None = Query(default=None, alias="department"),
    admin_view_enabled: bool = Query(default=False),
    email: str = Depends(get_current_user_email),
) -> list[BudgetRow]:
    with get_fabric_conn() as fabric_conn:
        scope = resolve_scope(email, fabric_conn, admin_view_enabled=admin_view_enabled)
        try:
            with get_gold_conn() as gold_conn:
                return get_budget_grid(
                    fabric_conn,
                    gold_conn,
                    planning_year=year,
                    scope=scope,
                    admin_view_enabled=admin_view_enabled,
                    cost_center_filter=cost_center,
                    department_filter=department,
                )
        except (SapActualsFetchError, pyodbc.Error) as exc:
            logger.exception("Budget grid fetch failed for year=%s, email=%s", year, email)
            raise HTTPException(status_code=502, detail=_SAP_UNAVAILABLE_DETAIL) from exc
