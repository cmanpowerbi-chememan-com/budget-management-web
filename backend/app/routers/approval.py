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
    admin_override_step,
    approve_department,
    authorize_status_view,
    evaluate_submit_eligibility,
    get_approval_status,
    list_departments_pending_my_approval,
    lookup_employee_name,
    reject_department,
    resolve_submitter,
    submit_department,
)
from app.auth import get_current_user_email
from app.config import get_settings
from app.db import get_fabric_conn
from app.deadline import YEAR_NOT_OPEN, fiscal_year_state, is_post_deadline
from app.read_model import fetch_locked_departments
from app.reference_data import fetch_departments
from app.rls import Scope, resolve_scope

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/approval")

_DB_UNAVAILABLE_DETAIL = "Database unavailable, please try again later"
_T = TypeVar("_T")


def _notify_after_transition(
    conn: pyodbc.Connection, action: str, state: ApprovalStatusState, admin_email: str | None = None
) -> None:
    """A12: fire the relevant email AFTER the transition already committed
    (`submit_department`/`approve_department`/`reject_department`/
    `admin_override_step` all commit internally before returning). Wrapped
    so a notification failure NEVER fails the request (never-cut) — caught,
    logged loudly, and surfaced only as a non-fatal `notification_warning`
    on the response, never a 5xx.

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
    left to `notify_turn`. The admin step-override (ADR-0027) can never land
    `APPROVED` either (refused by `app.approval.admin_override_step`), so
    that path never needs this branch.

    `notify_step_overridden` (6th notification, ADR-0027) fires on action ==
    "override_step": To the submitter, cc the skipped position-1 approver
    (`state.approver1_empcode` — unchanged by the override, so it still
    names who was skipped). The NEXT approver also still gets their normal
    `notify_turn` mail — an override sends exactly two mails, to two
    DIFFERENT recipients, so each send is wrapped in its OWN try/except
    (review fix): a failure in one must never suppress the other, or the
    department the override just unblocked goes silent again until the
    7-day reminder — exactly the stuck window ADR-0027 exists to clear.
    `admin_email` is the acting admin's real email (the route's
    authenticated caller)."""
    settings = get_settings()
    try:
        if action == "reject":
            notifications.notify_reject(
                conn, department=state.department, fiscal_year=state.fiscal_year,
                submitter_email=state.submitter_email, reason=state.reject_reason,
                approver1_empcode=state.approver1_empcode,  # 2026-07-31 revamp: cc the frozen approver1
                dry_run=settings.notifications_dry_run,
            )
        elif action == "approve" and state.status == APPROVED:
            notifications.notify_approved(
                conn, department=state.department, fiscal_year=state.fiscal_year,
                submitter_email=state.submitter_email,
                approver1_empcode=state.approver1_empcode,  # 2026-07-31 revamp: cc the frozen approver1
                dry_run=settings.notifications_dry_run,
            )
        elif action == "override_step":
            override_send_failed = False
            try:
                notifications.notify_step_overridden(
                    conn, department=state.department, fiscal_year=state.fiscal_year,
                    submitter_email=state.submitter_email,
                    skipped_approver_empcode=state.approver1_empcode,
                    admin_email=admin_email or "",
                    dry_run=settings.notifications_dry_run,
                    new_current_approver_empcode=state.current_approver_empcode,
                )
            except Exception as exc:  # noqa: BLE001 -- must never block the next approver's turn mail below
                logger.error(
                    "notification failed after override_step (notify_step_overridden) for %s/%s: %s",
                    state.department, state.fiscal_year, exc,
                )
                override_send_failed = True
            if state.current_position is not None:  # the next approver's normal "ถึงตาคุณ" mail
                try:
                    notifications.notify_turn(
                        conn, department=state.department, fiscal_year=state.fiscal_year,
                        approver_empcode=state.current_approver_empcode, submitter_email=state.submitter_email,
                        dry_run=settings.notifications_dry_run,
                    )
                except Exception as exc:  # noqa: BLE001 -- must never undo the override notice sent above
                    logger.error(
                        "notification failed after override_step (notify_turn) for %s/%s: %s",
                        state.department, state.fiscal_year, exc,
                    )
                    override_send_failed = True
            if override_send_failed:
                state.notification_warning = "The email notification failed, but your action was saved."
        elif state.current_position is not None:  # submit/approve landed on a PENDING_* step
            notifications.notify_turn(
                conn, department=state.department, fiscal_year=state.fiscal_year,
                approver_empcode=state.current_approver_empcode, submitter_email=state.submitter_email,
                dry_run=settings.notifications_dry_run,
            )
    except Exception as exc:  # noqa: BLE001 -- deliberate: a notify failure must never fail the action
        logger.error("notification failed after %s for %s/%s: %s", action, state.department, state.fiscal_year, exc)
        state.notification_warning = "The email notification failed, but your action was saved."


class DepartmentYearBody(BaseModel):
    department: str
    fiscal_year: int


class ApproveBody(DepartmentYearBody):
    comment: str | None = None


class RejectBody(DepartmentYearBody):
    reason: str


class PendingForMeResponse(BaseModel):
    """A10 รออนุมัติ badge data source — department NAMES only (the caller is
    by definition the frozen approver of each one, so no extra field leaks
    anything they should not already know)."""

    departments: list[str]


class LockedDepartmentsResponse(BaseModel):
    """"+ เพิ่ม Transaction" lock-awareness (2026-08-08 bug fix): every
    department, among the CALLER's OWN Fill-scope departments, whose
    approval status is locked for `fiscal_year`. Built from the exact same
    `read_model.fetch_locked_departments` (`LOCKED_APPROVAL_STATUSES`)
    `merge_budget_rows` already uses to compute `row.editable` — this
    endpoint can never grow a second, drifting definition of "locked".
    Scoped to `scope.fill_cost_centers` only (never all-company): a caller
    only ever learns about departments they could already see via
    `GET /scope/departments`, so this adds no new leakage.

    `year_not_open` (2026-08-08 3-state extension): `True` when `fiscal_year`
    has no `dbo.submission_deadline` row at all (see `app.deadline`'s module
    docstring) AND the caller is not admin — a year-wide signal, not
    per-department, from the SAME `app.deadline.fiscal_year_state` the write
    path and A6's submit gate consult, so this control can never offer to
    add a row into a year the server would then 403. Always `False` for an
    admin caller (admin may always add)."""

    departments: list[str]
    year_not_open: bool = False


def _set_is_post_deadline(conn: pyodbc.Connection, state: ApprovalStatusState) -> None:
    """Populates `state.is_post_deadline` — wired HERE (the router), not
    inside `app.approval`'s pure state-machine functions, for the same
    reason `current_approver_name` is (see GET /status below): an
    unconditional extra DB lookup inside those functions would break most of
    test_approval.py's finite mocked `side_effect` sequences. Called
    identically at every endpoint that returns `ApprovalStatusState` (SIT
    defect fix, 2026-08-14) so the frontend's `canSubmit` never sees a
    stale/absent value after any action, not just after GET /status.

    KEPT despite `canSubmit` no longer reading it (2026-08-16 gate review:
    verified zero frontend production reads remain — `types.ts`'s doc comment
    for `is_post_deadline` was corrected to say so). Deliberately NOT folded
    into `_set_can_submit`/`evaluate_submit_eligibility`: this is a
    year-wide flag computed identically for every caller/branch, whereas
    `SubmitEligibility.is_post_deadline` is only ever `true` inside ONE
    narrow admin branch — reusing that value here would silently change this
    field's meaning (e.g. a FILLER blocked by `past_deadline` would show
    `is_post_deadline=False`, which is wrong) and break the router tests that
    pin its value independently of `evaluate_submit_eligibility` (see
    `test_status_is_post_deadline_true/false_when_not_past_deadline` in
    test_approval_router.py). The extra query stays a real, once-per-request
    cost, not a redundant one.

    Never-cut (review fix, gate MED finding): wrapped in try/except so a
    broken or half-configured `dbo.submission_deadline` row (`deadline_date`
    is nullable, `db/schema.sql:105` — `fiscal_year_state`'s `bangkok_today()
    > row[0]` raises `TypeError` on a NULL) can never turn an
    ALREADY-COMMITTED action into a 500/502 for the caller. Callers on the 4
    action paths (submit/approve/reject/override-step) run this AFTER
    `_notify_after_transition` for the same reason — a raise here must never
    block the next approver's "ถึงตาคุณ" mail, or the department goes silent
    until the 7-day reminder (exactly what that function's own docstring
    says must never happen). On failure `state.is_post_deadline` simply
    stays at its fail-safe `False` default (hides the submit button) and a
    WARNING is logged so a broken row is visible in the container logs."""
    try:
        state.is_post_deadline = is_post_deadline(conn, state.fiscal_year)
    except Exception:  # noqa: BLE001 -- must never fail an already-committed action or block the notify that follows
        logger.warning(
            "is_post_deadline lookup failed for fiscal_year=%s — defaulting to False (submit button stays hidden)",
            state.fiscal_year, exc_info=True,
        )


def _set_can_submit(
    conn: pyodbc.Connection, state: ApprovalStatusState, email: str, scope: Scope | None = None,
) -> None:
    """Populates `state.can_submit`/`state.submit_blocked_reason` — the SIT
    "doomed submit button" fix #2 (2026-08-16, sibling of the 2026-08-14
    `is_post_deadline` fix directly above). The admin hat used to decide
    button visibility client-side from `status`/`is_post_deadline` alone,
    which cannot tell the 3 admin doors (Template-2/orphan/post-deadline
    override) apart from the 4th, refused shape (not a filler, department
    not orphan, no Template-2 rows, cycle still open) — that shape always
    showed a Submit button that then 403'd (`AdminCannotSubmitInCycleError`).
    `evaluate_submit_eligibility` is the EXACT same read-only decision
    `submit_department` itself now delegates to (`app.approval`, single
    source of truth) — this only surfaces its verdict here so the frontend's
    `canSubmit` (`model.ts`) never re-derives admin authorization
    client-side again.

    Perf fix (2026-08-16 gate review): `scope` is OPTIONAL — pass the one the
    caller already resolved this request (`submit`/`override-step`/`status`
    all call `resolve_scope` earlier in the SAME request) instead of paying a
    SECOND full `resolve_scope` (up to 5 round-trips: `_FILL_SQL`,
    `_MANAGER_SEE_ADD_SQL`, `resolve_submitter`,
    `departments_pending_for_empcode`, `cost_centers_for_departments`) on top
    of `evaluate_submit_eligibility`'s own 4-5 queries. `GET /approval/status`
    is the hottest endpoint in the app (fires on every ฝ่าย switch and after
    every action — the SAME endpoint the 2026-08-02 first-load fix targeted,
    `c2bd552`), so doubling its round-trips was a real regression, not a
    theoretical one. Only `approve`/`reject` have no scope in hand (their
    write path never needed one) — those two genuinely resolve fresh here.

    Never-cut / fail-closed (same reasoning as `_set_is_post_deadline`
    directly above): ANY failure — a broken scope lookup, an unexpected DB
    error — leaves `can_submit` at its pydantic default `False` (hides the
    button) and only logs a warning, never raises. A failure here must never
    turn an already-committed action into a 500, or block the notify that
    ran just before it."""
    try:
        resolved_scope = scope if scope is not None else resolve_scope(email, conn)
        eligibility = evaluate_submit_eligibility(conn, state.department, state.fiscal_year, email, resolved_scope)
        state.can_submit = eligibility.can_submit
        state.submit_blocked_reason = eligibility.reason
    except Exception:  # noqa: BLE001 -- must never fail an already-committed action
        logger.warning(
            "evaluate_submit_eligibility failed for %s/%s — defaulting can_submit=False",
            state.department, state.fiscal_year, exc_info=True,
        )


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
            _set_is_post_deadline(conn, state)
            _set_can_submit(conn, state, email, scope)
            return state

    return _run(_action)


@router.post("/approve", response_model=ApprovalStatusState)
def approve(body: ApproveBody, email: str = Depends(get_current_user_email)):
    def _action():
        with get_fabric_conn() as conn:
            state = approve_department(conn, body.department, body.fiscal_year, email, body.comment)
            _notify_after_transition(conn, "approve", state)
            _set_is_post_deadline(conn, state)
            _set_can_submit(conn, state, email)
            return state

    return _run(_action)


@router.post("/reject", response_model=ApprovalStatusState)
def reject(body: RejectBody, email: str = Depends(get_current_user_email)):
    def _action():
        with get_fabric_conn() as conn:
            state = reject_department(conn, body.department, body.fiscal_year, email, body.reason)
            _notify_after_transition(conn, "reject", state)
            _set_is_post_deadline(conn, state)
            _set_can_submit(conn, state, email)
            return state

    return _run(_action)


@router.post("/override-step", response_model=ApprovalStatusState)
def override_step(body: DepartmentYearBody, email: str = Depends(get_current_user_email)):
    """ADR-0027 manual admin step-override: advance a stuck POSITION-1 step
    by exactly one step (never APPROVED, never positions 2/3 — those map to
    a 409 with a Thai detail the UI shows as-is). The ONLY gate is
    `scope.is_admin` (D3: no waiting period, no reason field) — the frontend
    reuses the normal อนุมัติ button for this; the approve/override split is
    server-side only, with its own endpoint and its own
    `ADMIN_STEP_OVERRIDE` log action so the audit trail can always tell a
    real review from an override."""
    def _action():
        with get_fabric_conn() as conn:
            scope = resolve_scope(email, conn)
            if not scope.is_admin:
                raise HTTPException(
                    status_code=403, detail="Only an administrator can approve on behalf of an approver."
                )
            state = admin_override_step(conn, body.department, body.fiscal_year, email)
            _notify_after_transition(conn, "override_step", state, admin_email=email)
            _set_is_post_deadline(conn, state)
            _set_can_submit(conn, state, email, scope)
            return state

    return _run(_action)


@router.get("/pending-for-me", response_model=PendingForMeResponse)
def pending_for_me(fiscal_year: int = Query(...), email: str = Depends(get_current_user_email)):
    """A10 ฝ่าย-picker รออนุมัติ badge: every department whose current
    PENDING_* step, for `fiscal_year`, is frozen to the caller. No
    authorization check beyond identity — a caller only ever gets back
    departments where THEY are the frozen approver, never another
    department's data."""

    def _action():
        with get_fabric_conn() as conn:
            departments = list_departments_pending_my_approval(conn, fiscal_year, email)
            return PendingForMeResponse(departments=departments)

    return _run(_action)


@router.get("/locked-departments", response_model=LockedDepartmentsResponse)
def locked_departments(fiscal_year: int = Query(...), email: str = Depends(get_current_user_email)):
    """Feeds "+ เพิ่ม Transaction"'s per-Cost-Center lock check
    (`BudgetGrid.tsx`): the caller already knows which department each of
    their own Fill cost centers belongs to (`GET /scope/departments`) — this
    only adds whether that department is currently locked, so the Add form
    can reject a locked pick with a reason before ever calling
    `PUT /budget/rows` (the late-403 UX ADR-0013 exists to eliminate).

    `year_not_open` (2026-08-08 3-state extension, revised 2026-08-10):
    a year-wide sibling of the per-department `locked` set — `fiscal_year`
    has no `dbo.submission_deadline` row at all, so EVERY department (not
    just the ones already mid-approval) is closed to adds. Applies to admin
    too since 2026-08-10 (jakkaritw): a NOT_OPEN year is file-import-only,
    matching the write path's revised guard."""

    def _action():
        with get_fabric_conn() as conn:
            scope = resolve_scope(email, conn)
            year_not_open = fiscal_year_state(conn, fiscal_year) == YEAR_NOT_OPEN
            if not scope.fill_cost_centers:
                return LockedDepartmentsResponse(departments=[], year_not_open=year_not_open)
            dept_rows = fetch_departments(conn, scope.fill_cost_centers)
            own_departments = {row["department"] for row in dept_rows if row["department"]}
            locked = fetch_locked_departments(conn, fiscal_year)
            return LockedDepartmentsResponse(departments=sorted(own_departments & locked), year_not_open=year_not_open)

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
            state = get_approval_status(conn, department, fiscal_year, caller_empcode=caller_empcode)
            # ADR-0027: the override confirm dialog must NAME the approver
            # being skipped — resolved here from the same source as the mail
            # cc lookup, so the UI needs no second fetch.
            state.current_approver_name = lookup_employee_name(conn, state.current_approver_empcode)
            _set_is_post_deadline(conn, state)
            _set_can_submit(conn, state, email, scope)
            return state

    return _run(_action)
