"""GET /budget — the merged 3-layer (SAP/Approved/Pending) main budget grid,
RLS-filtered (A4). Read-only: no write, no approval (A5/A6).

GET /budget/export — issue #35's "ดาวน์โหลด Excel" button: the SAME grid
read path (scope + `get_budget_grid`, same params), turned into the
approved 1-sheet workbook via `app.budget_export`.
"""
import logging
from datetime import datetime
from zoneinfo import ZoneInfo

import pyodbc
from fastapi import APIRouter, Depends, HTTPException, Query, Response

from app.auth import get_current_user_email
from app.budget_export import build_export_summary_rows, build_export_workbook, content_disposition, filter_rows_by_department, XLSX_MEDIA_TYPE
from app.db import get_fabric_conn, get_gold_conn
from app.read_model import BudgetRow, get_budget_grid
from app.rls import resolve_scope
from app.sap import SapActualsFetchError, SapCoverage, resolve_sap_coverage_cached

logger = logging.getLogger(__name__)
router = APIRouter()

BANGKOK_TZ = ZoneInfo("Asia/Bangkok")

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


@router.get("/budget/export")
def budget_export(
    year: int = Query(..., description="Planning fiscal year, same as GET /budget"),
    department: str = Query(..., description="ฝ่าย to export — required, one ฝ่าย per download (no 'all departments')"),
    cost_center: str | None = Query(default=None, alias="cost_center"),
    admin_view_enabled: bool = Query(default=False),
    email: str = Depends(get_current_user_email),
) -> Response:
    """"ดาวน์โหลด Excel" (issue #35): the EXACT `GET /budget` read path — same
    scope resolver, same `get_budget_grid` call with the same params — turned
    into the approved 1-sheet workbook (`app.budget_export`). Inherits every
    grid rule unchanged (RLS, GL master-membership hide, admin-only GL strip,
    SAP+Approved=prior-year, the department filter, SIT impersonation's
    effective identity) since it is literally the same orchestrator call.
    Same failure contract as `GET /budget`: an SAP/DB failure is a generic
    502, never a leaked driver error."""
    try:
        with get_fabric_conn() as fabric_conn:
            scope = resolve_scope(email, fabric_conn, admin_view_enabled=admin_view_enabled)
            with get_gold_conn() as gold_conn:
                budget_rows = get_budget_grid(
                    fabric_conn,
                    gold_conn,
                    planning_year=year,
                    scope=scope,
                    admin_view_enabled=admin_view_enabled,
                    cost_center_filter=cost_center,
                    department_filter=department,
                )
                admitted_rows = filter_rows_by_department(budget_rows, department)
                summary_rows = build_export_summary_rows(
                    fabric_conn, admitted_rows, planning_year=year, department=department,
                )
                sap_watermark = resolve_sap_coverage_cached(gold_conn, fiscal_year=year - 1).watermark_date
        filename, xlsx_bytes = build_export_workbook(
            summary_rows,
            planning_year=year,
            department=department,
            as_of=datetime.now(BANGKOK_TZ),
            sap_watermark=sap_watermark,
        )
    except (SapActualsFetchError, pyodbc.Error) as exc:
        logger.exception("Budget export failed for year=%s, department=%s, email=%s", year, department, email)
        raise HTTPException(status_code=502, detail=_SAP_UNAVAILABLE_DETAIL) from exc

    return Response(
        content=xlsx_bytes,
        media_type=XLSX_MEDIA_TYPE,
        headers={"Content-Disposition": content_disposition(filename)},
    )


@router.get("/budget/sap-coverage", response_model=SapCoverage)
def sap_coverage(
    year: int = Query(..., description="Planning fiscal year, same as GET /budget — the SAP layer is year-1"),
    email: str = Depends(get_current_user_email),
) -> SapCoverage:
    """Freshness of the SAP · ใช้จริง layer (ADR-0030, supersedes ADR-0026's
    "which months are shown" coverage — no month is ever withheld now) — the
    grid's legend chip labels itself from this ("ข้อมูลอัปเดตล่าสุด 11 ก.ย. 2026",
    or a ⚠ stale variant when 3+ days behind).

    Deliberately its OWN endpoint rather than an envelope around
    `GET /budget`: coverage depends on the year alone, so switching ฝ่าย /
    cost center / admin mode re-reads the grid without re-reading this, and no
    existing response shape changes. Carries no financial figures and no
    per-user data, so it needs auth but no RLS.

    Freshness is surfaced to the user ONLY via this response (the grid's
    legend chip) — there is no admin alert mail (ADR-0030 amendment
    2026-09-14: the stale-feed mail was withdrawn after arriving 3x on the
    same day from prd's multiple worker processes)."""
    try:
        with get_gold_conn() as gold_conn:
            # TTL-cached (perf fix — Settings.sap_cache_ttl_seconds): the
            # entry-day watermark only changes when new SAP data lands.
            coverage = resolve_sap_coverage_cached(gold_conn, fiscal_year=year - 1)
    except (SapActualsFetchError, pyodbc.Error) as exc:
        logger.exception("SAP coverage resolution failed for year=%s, email=%s", year, email)
        raise HTTPException(status_code=502, detail=_SAP_UNAVAILABLE_DETAIL) from exc

    return coverage
