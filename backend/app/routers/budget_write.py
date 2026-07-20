"""Budget WRITE endpoints (A5) — PUT /budget/rows, PUT /budget/detail,
POST|PUT /budget/trip. No approval engine here (A6): status is never touched.

Each endpoint accepts ONE item per request (row / detail line / trip) — the
underlying `write_model` functions are batch-shaped (`list[...] -> list[...]`)
so a future bulk-save endpoint can reuse them unchanged; today's UI has no
batch save workflow yet (frontend is A7+), so the simplest matching surface
is one call per edited cell/line/trip, consistent with this codebase's other
single-purpose endpoints (`GET /budget`, `GET /scope`).

Error handling: `write_model.ERROR_HTTP_STATUS` is the single source of truth
mapping a per-item business error code to its HTTP status (403/400/409).
`per_diem`'s fail-loud errors (`MissingFxRateError`/`MissingPerDiemRateError`)
are never caught by write_model's per-item loop — they propagate here and are
turned into a 500 with a clear, actionable (non-leaky) message, matching the
"missing FX/rate -> fail loud, 5xx, never silent" never-cut rule.
"""
import logging
from datetime import datetime

import pyodbc
from fastapi import APIRouter, Depends, HTTPException, Query

from app.auth import get_current_user_email
from app.db import get_fabric_conn
from app.per_diem import MissingFxRateError, MissingPerDiemRateError
from app.rls import resolve_scope
from app.write_model import (
    ERROR_HTTP_STATUS,
    DetailLineInput,
    PendingRowInput,
    TripInput,
    delete_detail_line,
    delete_pending_row,
    delete_trip,
    save_detail_lines,
    save_pending_rows,
    save_trip,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/budget")

_DB_UNAVAILABLE_DETAIL = "Database unavailable, please try again later"


def _raise_for_result(result) -> None:
    if result.ok:
        return
    raise HTTPException(status_code=ERROR_HTTP_STATUS[result.error], detail=result.detail)


@router.put("/rows")
def put_row(body: PendingRowInput, email: str = Depends(get_current_user_email)):
    try:
        # Connection-open AND resolve_scope inside the try: a DB failure at
        # open time (driver pyodbc.Error, or msal token failure —
        # DbConnectionError, a pyodbc.Error subclass) or during scope
        # resolution is a 502, never an uncaught 500.
        with get_fabric_conn() as conn:
            scope = resolve_scope(email, conn)
            result = save_pending_rows(conn, [body], email, scope)[0]
    except pyodbc.Error as exc:
        logger.exception("save_pending_rows failed for %s/%s", body.cost_center, body.gl_account)
        raise HTTPException(status_code=502, detail=_DB_UNAVAILABLE_DETAIL) from exc
    _raise_for_result(result)
    return result.row


@router.put("/detail")
def put_detail_line(body: DetailLineInput, email: str = Depends(get_current_user_email)):
    try:
        # Same connection-open/resolve_scope contract as put_row above.
        with get_fabric_conn() as conn:
            scope = resolve_scope(email, conn)
            result = save_detail_lines(conn, [body], email, scope)[0]
    except pyodbc.Error as exc:
        logger.exception("save_detail_lines failed for %s/%s", body.cost_center, body.gl_account)
        raise HTTPException(status_code=502, detail=_DB_UNAVAILABLE_DETAIL) from exc
    _raise_for_result(result)
    return result.line


def _save_one_trip(body: TripInput, email: str):
    try:
        # Same connection-open/resolve_scope contract as put_row above. The
        # fail-loud missing-FX/rate errors stay a 500 — they are RuntimeError
        # subclasses, NOT pyodbc.Error, so the 502 branch never catches them.
        with get_fabric_conn() as conn:
            scope = resolve_scope(email, conn)
            result = save_trip(conn, [body], email, scope)[0]
    except pyodbc.Error as exc:
        logger.exception("save_trip failed for %s/%s", body.cost_center, body.traveler_empcode)
        raise HTTPException(status_code=502, detail=_DB_UNAVAILABLE_DETAIL) from exc
    except (MissingFxRateError, MissingPerDiemRateError) as exc:
        logger.exception("save_trip fail-loud: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    _raise_for_result(result)
    return result.trip


@router.post("/trip")
def create_trip(body: TripInput, email: str = Depends(get_current_user_email)):
    body = body.model_copy(update={"trip_id": None, "expected_updated_at": None})
    return _save_one_trip(body, email)


@router.put("/trip")
def update_trip(body: TripInput, email: str = Depends(get_current_user_email)):
    if body.trip_id is None:
        raise HTTPException(status_code=422, detail="trip_id is required to update an existing trip")
    return _save_one_trip(body, email)


@router.delete("/rows")
def delete_row(
    cost_center: str = Query(...),
    gl_account: str = Query(...),
    fiscal_year: int = Query(...),
    expected_updated_at: datetime = Query(...),
    email: str = Depends(get_current_user_email),
):
    """Grid trailing "ลบ" column: delete one manually-added Pending row (and
    cascade any special-GL detail lines it owns). Frontend only offers this
    button for a row with no SAP/Approved value in any month and never for
    Travelling Expense — this endpoint itself is generic and does not
    re-check either condition."""
    try:
        # Same connection-open/resolve_scope contract as put_row above.
        with get_fabric_conn() as conn:
            scope = resolve_scope(email, conn)
            result = delete_pending_row(conn, cost_center, gl_account, fiscal_year, expected_updated_at, email, scope)
    except pyodbc.Error as exc:
        logger.exception("delete_pending_row failed for %s/%s", cost_center, gl_account)
        raise HTTPException(status_code=502, detail=_DB_UNAVAILABLE_DETAIL) from exc
    _raise_for_result(result)
    return {"ok": True, "cost_center": cost_center, "gl_account": gl_account, "fiscal_year": fiscal_year}


@router.delete("/detail")
def delete_detail(
    detail_id: int = Query(...),
    expected_updated_at: datetime = Query(...),
    email: str = Depends(get_current_user_email),
):
    try:
        # Same connection-open/resolve_scope contract as put_row above.
        with get_fabric_conn() as conn:
            scope = resolve_scope(email, conn)
            result = delete_detail_line(conn, detail_id, expected_updated_at, email, scope)
    except pyodbc.Error as exc:
        logger.exception("delete_detail_line failed for detail_id=%s", detail_id)
        raise HTTPException(status_code=502, detail=_DB_UNAVAILABLE_DETAIL) from exc
    _raise_for_result(result)
    return {"ok": True, "detail_id": detail_id}


@router.delete("/trip")
def delete_trip_endpoint(
    trip_id: int = Query(...),
    expected_updated_at: datetime = Query(...),
    email: str = Depends(get_current_user_email),
):
    try:
        # Same connection-open/resolve_scope contract as put_row above.
        with get_fabric_conn() as conn:
            scope = resolve_scope(email, conn)
            result = delete_trip(conn, trip_id, expected_updated_at, email, scope)
    except pyodbc.Error as exc:
        logger.exception("delete_trip failed for trip_id=%s", trip_id)
        raise HTTPException(status_code=502, detail=_DB_UNAVAILABLE_DETAIL) from exc
    _raise_for_result(result)
    return {"ok": True, "trip_id": trip_id}
