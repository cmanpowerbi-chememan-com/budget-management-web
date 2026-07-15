"""Approval endpoints (A6) — submit / approve / reject / status.

No batch shape here (unlike budget_write.py): approval acts on exactly ONE
`(department, fiscal_year)` unit per call, so business-rule exceptions from
`app.approval` propagate directly and are mapped to an HTTP status via
`ERROR_HTTP_STATUS` / `ERROR_CODE_BY_EXCEPTION` — the same dict-based mapping
idiom as `write_model.py`, just applied per-call instead of per-result.
"""
import logging
from typing import Callable, TypeVar

import pyodbc
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from app.approval import (
    ERROR_CODE_BY_EXCEPTION,
    ERROR_HTTP_STATUS,
    ApprovalStatusState,
    approve_department,
    authorize_status_view,
    get_approval_status,
    reject_department,
    resolve_submitter,
    submit_department,
)
from app.auth import get_current_user_email
from app.db import get_fabric_conn
from app.rls import resolve_scope

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/approval")

_DB_UNAVAILABLE_DETAIL = "Database unavailable, please try again later"
_T = TypeVar("_T")


class DepartmentYearBody(BaseModel):
    department: str
    fiscal_year: int


class ApproveBody(DepartmentYearBody):
    comment: str | None = None


class RejectBody(DepartmentYearBody):
    reason: str


def _run(action: Callable[[], _T]) -> _T:
    try:
        return action()
    except pyodbc.Error as exc:
        logger.exception("approval action failed")
        raise HTTPException(status_code=502, detail=_DB_UNAVAILABLE_DETAIL) from exc
    except tuple(ERROR_CODE_BY_EXCEPTION) as exc:
        code = ERROR_CODE_BY_EXCEPTION[type(exc)]
        raise HTTPException(status_code=ERROR_HTTP_STATUS[code], detail=str(exc)) from exc


@router.post("/submit", response_model=ApprovalStatusState)
def submit(body: DepartmentYearBody, email: str = Depends(get_current_user_email)):
    def _action():
        with get_fabric_conn() as conn:
            scope = resolve_scope(email, conn)
            return submit_department(conn, body.department, body.fiscal_year, email, scope)

    return _run(_action)


@router.post("/approve", response_model=ApprovalStatusState)
def approve(body: ApproveBody, email: str = Depends(get_current_user_email)):
    def _action():
        with get_fabric_conn() as conn:
            return approve_department(conn, body.department, body.fiscal_year, email, body.comment)

    return _run(_action)


@router.post("/reject", response_model=ApprovalStatusState)
def reject(body: RejectBody, email: str = Depends(get_current_user_email)):
    def _action():
        with get_fabric_conn() as conn:
            return reject_department(conn, body.department, body.fiscal_year, email, body.reason)

    return _run(_action)


@router.get("/status", response_model=ApprovalStatusState)
def status(
    department: str = Query(...),
    fiscal_year: int = Query(...),
    email: str = Depends(get_current_user_email),
):
    def _action():
        with get_fabric_conn() as conn:
            scope = resolve_scope(email, conn)
            authorize_status_view(conn, department, scope)  # B1 gate fix — was unauthorized-by-department
            caller_empcode, _ = resolve_submitter(conn, email)
            return get_approval_status(conn, department, fiscal_year, caller_empcode=caller_empcode)

    return _run(_action)
