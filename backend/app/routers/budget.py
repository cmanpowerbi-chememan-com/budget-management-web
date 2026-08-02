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
from app.sap import SapActualsFetchError, SapCoverage, resolve_sap_coverage_cached

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
    try:
        # BOTH connection opens are inside the try: a failure at open time
        # (driver pyodbc.Error, or msal token failure — DbConnectionError,
        # a pyodbc.Error subclass raised by app.db) is the same "DB blip"
        # contract as a query-time failure → 502, never an uncaught 500.
        with get_fabric_conn() as fabric_conn:
            scope = resolve_scope(email, fabric_conn, admin_view_enabled=admin_view_enabled)
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


@router.get("/budget/sap-coverage", response_model=SapCoverage)
def sap_coverage(
    year: int = Query(..., description="Planning fiscal year, same as GET /budget — the SAP layer is year-1"),
    email: str = Depends(get_current_user_email),
) -> SapCoverage:
    """How fresh the SAP · ใช้จริง layer is and which of its months are shown
    (ADR-0026) — the grid labels its own coverage from this ("ครบถึงเดือน
    3/2026 · ข้อมูลคีย์ถึง 29 เม.ย. 69").

    Deliberately its OWN endpoint rather than an envelope around
    `GET /budget`: coverage depends on the year alone, so switching ฝ่าย /
    cost center / admin mode re-reads the grid without re-reading this, and no
    existing response shape changes. Carries no financial figures and no
    per-user data, so it needs auth but no RLS."""
    try:
        with get_gold_conn() as gold_conn:
            # TTL-cached (perf fix — Settings.sap_cache_ttl_seconds): the
            # entry-day watermark only changes when new SAP data lands.
            return resolve_sap_coverage_cached(gold_conn, fiscal_year=year - 1)
    except (SapActualsFetchError, pyodbc.Error) as exc:
        logger.exception("SAP coverage resolution failed for year=%s, email=%s", year, email)
        raise HTTPException(status_code=502, detail=_SAP_UNAVAILABLE_DETAIL) from exc
