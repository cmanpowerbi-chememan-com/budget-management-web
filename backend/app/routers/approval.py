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

from app import notifications
from app.approval import (
    APPROVED,
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
from app.config import get_settings
from app.db import get_fabric_conn
from app.rls import resolve_scope

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/approval")

_DB_UNAVAILABLE_DETAIL = "Database unavailable, please try again later"
_T = TypeVar("_T")


def _notify_after_transition(conn: pyodbc.Connection, action: str, state: ApprovalStatusState) -> None:
    """A12: fire the relevant email AFTER the transition already committed
    (`submit_department`/`approve_department`/`reject_department` all
    commit internally before returning). Wrapped so a notification failure
    NEVER fails the request (never-cut) — caught, logged loudly, and
    surfaced only as a non-fatal `notification_warning` on the response,
    never a 5xx.

    Placement note: wired HERE (the router) rather than inside
    `app.approval`'s pure state-machine functions — those are unit-tested
    with a single shared mock cursor and finite `side_effect` lists (see
    test_approval.py's own docstring); adding an unconditional extra DB
    lookup inside them would have broken most of that suite. The router
    already receives the fully-resolved `ApprovalStatusState` (department,
    fiscal_year, current_approver_empcode, submitter_email, reject_reason),
    which is everything notify_turn/notify_reject need, so no behavior is
    lost by wiring it here instead.

    No admin-direct-approve branch (ADMIN_SUBMIT/ADMIN_OVERRIDE_*) ever
    reaches the `notify_turn`/`notify_approved` branches below — those
    branches run through `submit_department` (action == "submit"), and both
    branches below are gated on action == "approve" or "reject" specifically
    — flagged decision: no email fires for admin branches (no chain, and the
    spec's email trigger map never describes one).

    `notify_approved` (4th notification, added 2026-07-16) fires only when
    an "approve" action is the one that lands the department on `APPROVED`
    — the LAST step of the normal chain, where there is no next approver
    left to `notify_turn`. Auto-escalate can never land `APPROVED` directly
    (ADR-0006, asserted in `app.approval.auto_escalate_step`), so that path
    never needs this branch either."""
    settings = get_settings()
    try:
        if action == "reject":
            notifications.notify_reject(
                department=state.department, fiscal_year=state.fiscal_year,
                submitter_email=state.submitter_email, reason=state.reject_reason,
                dry_run=settings.notifications_dry_run,
            )
        elif action == "approve" and state.status == APPROVED:
            notifications.notify_approved(
                department=state.department, fiscal_year=state.fiscal_year,
                submitter_email=state.submitter_email, dry_run=settings.notifications_dry_run,
            )
        elif state.current_position is not None:  # submit/approve landed on a PENDING_* step
            notifications.notify_turn(
                conn, department=state.department, fiscal_year=state.fiscal_year,
                approver_empcode=state.current_approver_empcode, submitter_email=state.submitter_email,
                dry_run=settings.notifications_dry_run,
            )
    except Exception as exc:  # noqa: BLE001 -- deliberate: a notify failure must never fail the action
        logger.error("notification failed after %s for %s/%s: %s", action, state.department, state.fiscal_year, exc)
        state.notification_warning = "การแจ้งเตือนอีเมลล้มเหลว แต่การทำรายการสำเร็จแล้ว"


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
            state = submit_department(conn, body.department, body.fiscal_year, email, scope)
            _notify_after_transition(conn, "submit", state)
            return state

    return _run(_action)


@router.post("/approve", response_model=ApprovalStatusState)
def approve(body: ApproveBody, email: str = Depends(get_current_user_email)):
    def _action():
        with get_fabric_conn() as conn:
            state = approve_department(conn, body.department, body.fiscal_year, email, body.comment)
            _notify_after_transition(conn, "approve", state)
            return state

    return _run(_action)


@router.post("/reject", response_model=ApprovalStatusState)
def reject(body: RejectBody, email: str = Depends(get_current_user_email)):
    def _action():
        with get_fabric_conn() as conn:
            state = reject_department(conn, body.department, body.fiscal_year, email, body.reason)
            _notify_after_transition(conn, "reject", state)
            return state

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
