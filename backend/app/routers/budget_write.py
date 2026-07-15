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

import pyodbc
from fastapi import APIRouter, Depends, HTTPException

from app.auth import get_current_user_email
from app.db import get_fabric_conn
from app.per_diem import MissingFxRateError, MissingPerDiemRateError
from app.rls import resolve_scope
from app.write_model import (
    ERROR_HTTP_STATUS,
    DetailLineInput,
    PendingRowInput,
    TripInput,
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
    with get_fabric_conn() as conn:
        scope = resolve_scope(email, conn)
        try:
            result = save_pending_rows(conn, [body], email, scope)[0]
        except pyodbc.Error as exc:
            logger.exception("save_pending_rows failed for %s/%s", body.cost_center, body.gl_account)
            raise HTTPException(status_code=502, detail=_DB_UNAVAILABLE_DETAIL) from exc
    _raise_for_result(result)
    return result.row


@router.put("/detail")
def put_detail_line(body: DetailLineInput, email: str = Depends(get_current_user_email)):
    with get_fabric_conn() as conn:
        scope = resolve_scope(email, conn)
        try:
            result = save_detail_lines(conn, [body], email, scope)[0]
        except pyodbc.Error as exc:
            logger.exception("save_detail_lines failed for %s/%s", body.cost_center, body.gl_account)
            raise HTTPException(status_code=502, detail=_DB_UNAVAILABLE_DETAIL) from exc
    _raise_for_result(result)
    return result.line


def _save_one_trip(body: TripInput, email: str):
    with get_fabric_conn() as conn:
        scope = resolve_scope(email, conn)
        try:
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
