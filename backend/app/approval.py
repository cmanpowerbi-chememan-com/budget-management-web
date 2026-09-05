"""Approval engine (A6) — `budget.approval_status` + `budget.approval_log`.

Unit of approval = `(department, fiscal_year)` — ALL cost centers of a ฝ่าย
move as one record (ADR-0008). This module owns the state machine
(DRAFT/PENDING_APPROVER1/2/3/APPROVED/REJECTED), chain resolution, and the
append-only audit log. It never touches `budget.pending_budget` amounts
(ADR-0013: editing never changes approval status, and approving never
mutates money) — A5 (`write_model.py`) owns writes, this module only reads
`dbo.cc_filler_map` / `dbo.v_employee_budget_01` / `budget.pending_budget`
(for the `template='ADMIN'` check) / `dbo.submission_deadline`.

Chain model (ADR-0006/0008, confirmed against live data 2026-07-16):
the schema has exactly 3 FIXED positions — position 1 (`approver1_empcode`,
resolved per-submission from the submitter's manager), position 2 (always
Nipaporn, `NIPAPORN_EMPCODE` — a compile-time constant, no stored empcode
column needed), position 3 (always Waraporn, `WARAPORN_EMPCODE`). Self-skip
+ dedup (ADR-0006) never renumbers positions — they just mark some of the 3
fixed positions "inactive" for this submission; `status` walks the ACTIVE
positions in order 1→2→3 and the LAST active position's approval goes
straight to APPROVED (never touching a skipped position's `_actioned_at`
column, which stays NULL for that submission). Both the invalid-approver1
fallback (ADR-0006: no manager found -> approver1 becomes Nipaporn) and the
self-skip (e.g. Nipaporn submitting her own ฝ่าย, whose manager is
Waraporn) are handled by ONE mechanism: whenever `approver1_empcode`
resolves to the SAME empcode as position 2 (Nipaporn) or the submitter
themselves, dedup/self-skip drops the redundant position automatically —
no special-cased branches needed for "invalid approver1" vs "self-submit".
"""
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import TYPE_CHECKING

import pyodbc
from pydantic import BaseModel

from app.deadline import (
    YEAR_NOT_OPEN,
    YEAR_PAST_DEADLINE,
    PastDeadlineError,
    YearNotOpenError,
    bangkok_today as _bangkok_today,
    fiscal_year_state as _fiscal_year_state,
    is_post_deadline as _is_post_deadline,
)

if TYPE_CHECKING:
    # Type-only: `app.rls` now imports FROM this module (the See-overlay,
    # ADR-0029) so a runtime import here would be a circular import. `Scope`
    # is only ever used as a parameter annotation below (duck-typed at
    # runtime, never instantiated or isinstance-checked in this module), so
    # deferring it to type-checking time only is safe.
    from app.rls import Scope

logger = logging.getLogger(__name__)

# Fixed chain constants (ADR-0006) — position 2/3 are compile-time, never
# stored as their own empcode column (only their *_actioned_at timestamps are).
NIPAPORN_EMPCODE = "101032"
WARAPORN_EMPCODE = "100427"

DRAFT = "DRAFT"
PENDING_APPROVER1 = "PENDING_APPROVER1"
PENDING_APPROVER2 = "PENDING_APPROVER2"
PENDING_APPROVER3 = "PENDING_APPROVER3"
APPROVED = "APPROVED"
REJECTED = "REJECTED"

_POSITION_TO_STATUS: dict[int, str] = {1: PENDING_APPROVER1, 2: PENDING_APPROVER2, 3: PENDING_APPROVER3}
_STATUS_TO_POSITION: dict[str, int] = {v: k for k, v in _POSITION_TO_STATUS.items()}
PENDING_STATUSES: frozenset[str] = frozenset(_STATUS_TO_POSITION)

# A department is "locked" (read-only for a non-admin) once its approval
# record has left DRAFT/REJECTED for a fiscal_year — mid-chain
# (PENDING_APPROVER1/2/3) or fully signed off (APPROVED). DRAFT/REJECTED and
# "no row yet" (never submitted) are NOT locked — matches ADR-0013's
# edit-rights-by-status table exactly. ONE definition of the STATUS SET shared
# by the write-side gate (`write_model._ensure_department_not_locked`) and the
# read-side grid lock (`read_model.merge_budget_rows`'s `row.editable`,
# ADR-0013 read-only lock UI parity, 2026-08-05).
#
# WHICH DEPARTMENT a cost_center resolves to is now ALSO shared in priority
# (gate finding 2026-08-05 D2, fixed 2026-08-07 per jakkaritw's decision —
# option A, fix both consumers): the write path always resolves it live from
# `dbo.cc_filler_map` (`_lookup_cc_dims`); the read path's
# `read_model.merge_budget_rows` now resolves it the SAME way, live-first,
# via `read_model._resolve_live_department` — the SNAPSHOT stored on the row
# (`pending.department`/`board.department`, written at save time) is only a
# fallback for a cost_center the live master has nothing to say about
# (absent from `dbo.cc_filler_map` entirely, or `cc_dims` not fetched at
# all). Before this fix the read path preferred the snapshot and only fell
# back to a live lookup when it was absent, so a CC->ฝ่าย remap could make
# the two paths disagree in either direction until the row was re-saved
# (proven live against production 2026-08-07, CC 10IT012000) — jakkaritw
# explicitly accepted the visible consequence that a remapped row now moves
# to the new department's grid entirely ("ย้ายฝ่ายแล้วก็ควรย้ายทั้งตัว ไม่ใช่
# ครึ่งตัว"). One theoretical edge remains, unchanged from the write path's
# own accepted policy: a cost_center removed ENTIRELY from `dbo.cc_filler_map`
# (not merely remapped) still fails open on write (`department=None`), but the
# read path would still fall back to a stale snapshot for that same row if
# one exists — `write_model._ensure_department_not_locked`'s own docstring
# already notes this cannot currently be reached by a non-admin, since their
# Fill scope is itself derived from `dbo.cc_filler_map`.
LOCKED_APPROVAL_STATUSES: frozenset[str] = PENDING_STATUSES | {APPROVED}

# Append-only action log values this module writes.
ACTION_SUBMIT = "SUBMIT"
ACTION_RESUBMIT = "RESUBMIT"
ACTION_APPROVE = "APPROVE"
ACTION_REJECT = "REJECT"
ACTION_ADMIN_SUBMIT = "ADMIN_SUBMIT"
# A11 scheduled job (jobs/auto_submit.py) — written by auto_submit_department
# below, never by a human action.
ACTION_AUTO_SUBMIT = "AUTO_SUBMIT"

# S4 gate fix: split the old single ACTION_ADMIN_OVERRIDE value into two, so
# the audit log can tell apart "department is structurally orphan" from "the
# submission deadline has passed" — both used to log the same indistinguishable
# code. Verified live 2026-07-16: budget.approval_log.action is NVARCHAR(40),
# both values fit with room to spare.
ACTION_ADMIN_OVERRIDE_ORPHAN = "ADMIN_OVERRIDE_ORPHAN"
ACTION_ADMIN_OVERRIDE_DEADLINE = "ADMIN_OVERRIDE_DEADLINE"
# ADR-0027: a human ADMIN advancing a stuck position-1 step by exactly one
# step (admin_override_step below). Deliberately distinct from APPROVE (the
# frozen occupant acting) and from the submit-side ADMIN_* actions above —
# the audit trail must always be able to answer "was this step actually
# reviewed by its owner?".
ACTION_ADMIN_STEP_OVERRIDE = "ADMIN_STEP_OVERRIDE"

_STATUS_COLUMNS: tuple[str, ...] = (
    "department", "fiscal_year", "status", "submitter_empcode", "submitter_email",
    "submitted_at", "approver1_empcode", "approver1_actioned_at", "approver2_actioned_at",
    "approver3_actioned_at", "reject_reason", "rejected_by_empcode", "_updated_at",
)


# ---------------------------------------------------------------------------
# Errors — one class per business rule, mapped to an HTTP status by the router.
# ---------------------------------------------------------------------------

class NotFillerOfDepartmentError(PermissionError):
    """Caller holds no Fill scope on any cost center of this department and
    is not admin — never-cut: only a real filler (or admin, via the direct-
    approve branch) may submit a department."""


class AdminCannotSubmitInCycleError(PermissionError):
    """Admin is not a filler of this department, it is not orphan, it has no
    Template-2 (ADMIN) rows, and the cycle is still open — ADR-0012: an admin
    may only edit a normal in-cycle department, not submit it on the
    submitter's behalf."""


class MidChainAdminOverwriteError(PermissionError):
    """B2 gate fix — fail-closed guard (default policy until jakkaritw
    confirms otherwise, see final report): the ADMIN_SUBMIT (Template-2
    door) and orphan-department branches must not silently overwrite a
    record that already has a real approval in progress or completed
    (PENDING_APPROVER1/2/3 or APPROVED) while the cycle is still open — only
    the confirmed post-deadline override (ADR-0012) may replace ANY existing
    status. Kept as its own error/guard so flipping the policy later (if
    jakkaritw wants admin to always override mid-chain) is a small change,
    not a rewrite."""


class DepartmentEmptyError(ValueError):
    """Submit refused — bug 3 of the 2026-08-07 confirmed-defect wave,
    reproduced live (Solution Delivery/FY2026, 0 rows): submit was ACCEPTED,
    locking the department and landing a real request on a real approver who
    then opened an empty grid. `department`/`fiscal_year` has ZERO
    `budget.pending_budget` rows across every cost center currently mapped
    to it — there is nothing to approve.

    A data-VALIDITY gate, not a permission gate (jakkaritw, 2026-08-08,
    option ก): it runs for EVERY caller identically, admin included, and
    BEFORE any admin-door branch (`submit_department`'s very first check,
    ahead of even the filler/admin branch split) — the orphan/Template-2/
    post-deadline admin doors exist to submit ON BEHALF OF a department that
    HAS data but nobody to submit it, never to submit emptiness itself.
    Template-2 can never trip this guard in practice (a department only
    reaches that door because it already has `template='ADMIN'` pending
    rows). The orphan door CAN still succeed — orphan means zero cost
    centers are currently mapped to the department, not zero data:
    `_department_has_pending_rows` falls back to the department SNAPSHOT
    column for that case (see its own docstring), the only remaining way to
    see an orphan department's real, pre-existing rows.

    The message is Thai on purpose, same convention as
    `StepNotOverridableError` above: the router maps this to a 400 whose
    detail the UI shows directly, no client-side translation needed."""


class InvalidApprovalStateError(ValueError):
    """Submit called while the record is locked (PENDING_* — no recall, ADR-0006)
    or already APPROVED (editing an APPROVED department never needs
    re-submission, ADR-0013); or approve/reject called on a record that is
    not currently in a PENDING_* state."""


class ApprovalRecordNotFoundError(ValueError):
    """approve/reject called for a `(department, fiscal_year)` with no
    approval_status row at all — nothing has ever been submitted."""


class NotCurrentApproverError(PermissionError):
    """Only the CURRENT step's frozen approver may approve/reject
    (ADR-0006/0016) — anyone else, 403. No admin bypass here (ADR-0012 only
    describes admin EDIT/SUBMIT overrides, never an approve/reject bypass;
    the ADR-0009 "reassign a stuck approver" admin view is a separate,
    not-yet-built feature — see the final report)."""


class NotAuthorizedToViewDepartmentError(PermissionError):
    """B1 gate fix — `GET /approval/status` had no authorization at all: any
    authenticated caller could read another department's submitter
    email/empcode, rejecter, and reject_reason. Raised when the caller is
    not admin AND the requested department shares no cost center with the
    caller's See scope (ADR-0007) — deliberately the SAME error for "you are
    out of scope" and "this department does not exist", so an unauthorized
    caller cannot use this endpoint to probe which department names are
    real."""


class MissingReasonError(ValueError):
    """Reject called with a blank reason."""


class ConcurrentApprovalError(RuntimeError):
    """The record's status changed between read and write (two approvers
    racing the same step, or a reject landing mid-approve) — the conditional
    UPDATE matched zero rows, so nothing double-advanced (never-cut)."""


class StepNotOverridableError(ValueError):
    """Admin step-override refused (ADR-0027): either the record is sitting
    on position 2/3 — the budget-dept review itself (Nipaporn/Waraporn),
    never overridable by anyone (D4) — or position 1 is the ONLY active
    position, so the override would land APPROVED, which an override may
    never do. The message is Thai on purpose: the router maps this error to
    a 409 whose detail the UI shows directly."""


ERROR_HTTP_STATUS: dict[str, int] = {
    "not_filler_of_department": 403,
    "admin_cannot_submit_in_cycle": 403,
    "mid_chain_admin_overwrite": 409,
    "past_deadline": 403,
    "year_not_open": 403,
    "department_empty": 400,
    "invalid_approval_state": 409,
    "approval_record_not_found": 404,
    "not_current_approver": 403,
    "not_authorized_to_view_department": 403,
    "missing_reject_reason": 400,
    "concurrent_approval": 409,
    "step_not_overridable": 409,
}

ERROR_CODE_BY_EXCEPTION: dict[type[Exception], str] = {
    NotFillerOfDepartmentError: "not_filler_of_department",
    AdminCannotSubmitInCycleError: "admin_cannot_submit_in_cycle",
    MidChainAdminOverwriteError: "mid_chain_admin_overwrite",
    PastDeadlineError: "past_deadline",
    YearNotOpenError: "year_not_open",
    DepartmentEmptyError: "department_empty",
    InvalidApprovalStateError: "invalid_approval_state",
    ApprovalRecordNotFoundError: "approval_record_not_found",
    NotCurrentApproverError: "not_current_approver",
    NotAuthorizedToViewDepartmentError: "not_authorized_to_view_department",
    MissingReasonError: "missing_reject_reason",
    ConcurrentApprovalError: "concurrent_approval",
    StepNotOverridableError: "step_not_overridable",
}


def _now() -> datetime:
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# Response model
# ---------------------------------------------------------------------------

class ApprovalStatusState(BaseModel):
    """One `(department, fiscal_year)` approval record. `status=DRAFT` with
    every other field `None` represents "never submitted" (no DB row yet) —
    GET /approval/status returns this shape instead of a 404 for the common
    not-yet-submitted case."""

    department: str
    fiscal_year: int
    status: str
    submitter_empcode: str | None = None
    submitter_email: str | None = None
    submitted_at: datetime | None = None
    approver1_empcode: str | None = None
    approver1_actioned_at: datetime | None = None
    approver2_actioned_at: datetime | None = None
    approver3_actioned_at: datetime | None = None
    reject_reason: str | None = None
    rejected_by_empcode: str | None = None
    updated_at: datetime | None = None
    current_position: int | None = None  # 1/2/3 while PENDING_*, else None
    current_approver_empcode: str | None = None  # who may act right now, if PENDING_*
    # Thai display name of the current approver, resolved server-side from
    # dbo.v_employee_budget_01 (the same source the mail cc lookup reads) —
    # the admin step-override confirm dialog must NAME who is being skipped
    # (ADR-0027) without a second client fetch. Populated by the router's
    # GET /approval/status only (never by this module's state builders).
    current_approver_name: str | None = None
    can_act: bool = False  # True when the caller's own empcode IS current_approver_empcode
    # A12: set by the router (never by this module) ONLY when the post-commit
    # notify attempt raised — a non-fatal warning, never a reason to fail the
    # request (the transition above already committed successfully).
    notification_warning: str | None = None
    # SIT defect fix (2026-08-14): set by the router (never by this module,
    # same placement reasoning as `current_approver_name` — an unconditional
    # extra DB lookup inside this module's pure state-machine functions would
    # break test_approval.py's finite mocked side_effect sequences). True
    # only when `app.deadline.is_post_deadline` — the frontend's `canSubmit`
    # uses it to show the admin submit button on a locked status (PENDING_*/
    # APPROVED) ONLY when it will actually reach `submit_department`'s
    # post-deadline override branch (the one door NOT gated by
    # `_ensure_admin_overwrite_allowed`, ADR-0012). Defaults False so any
    # path that never sets it hides the button rather than showing a doomed
    # one.
    is_post_deadline: bool = False
    # SIT defect fix (2026-08-16, doomed-submit-button case #2): set by the
    # router (never by this module, same placement reasoning as
    # `is_post_deadline` just above) from `evaluate_submit_eligibility` --
    # the exact read-only decision `submit_department` itself now delegates
    # to. Replaces `is_post_deadline` as the frontend's `canSubmit` input:
    # `is_post_deadline` alone could not tell apart the post-deadline
    # override door from the OTHER refused admin shape (not a filler, not
    # orphan, no Template-2 rows, cycle still open) -- that shape always
    # showed a Submit button that then 403'd. Defaults False (fail-closed):
    # any path that never sets it hides the button.
    can_submit: bool = False
    # Machine-readable reason when `can_submit` is False -- one of
    # `ERROR_CODE_BY_EXCEPTION`'s submit-related values (`department_empty`,
    # `not_filler_of_department`, `year_not_open`, `past_deadline`,
    # `invalid_approval_state`, `admin_cannot_submit_in_cycle`,
    # `mid_chain_admin_overwrite`). `None` when `can_submit` is True or
    # unknown (fail-closed default).
    submit_blocked_reason: str | None = None


def _occupant_for_position(position: int, approver1_empcode: str | None) -> str:
    if position == 1:
        return approver1_empcode
    return NIPAPORN_EMPCODE if position == 2 else WARAPORN_EMPCODE


def _to_state(row: dict, department: str, fiscal_year: int, caller_empcode: str | None) -> ApprovalStatusState:
    current_position = _STATUS_TO_POSITION.get(row["status"])
    current_approver = _occupant_for_position(current_position, row["approver1_empcode"]) if current_position else None
    return ApprovalStatusState(
        department=row.get("department", department),
        fiscal_year=row.get("fiscal_year", fiscal_year),
        status=row["status"],
        submitter_empcode=row.get("submitter_empcode"),
        submitter_email=row.get("submitter_email"),
        submitted_at=row.get("submitted_at"),
        approver1_empcode=row.get("approver1_empcode"),
        approver1_actioned_at=row.get("approver1_actioned_at"),
        approver2_actioned_at=row.get("approver2_actioned_at"),
        approver3_actioned_at=row.get("approver3_actioned_at"),
        reject_reason=row.get("reject_reason"),
        rejected_by_empcode=row.get("rejected_by_empcode"),
        updated_at=row.get("_updated_at"),
        current_position=current_position,
        current_approver_empcode=current_approver,
        can_act=bool(caller_empcode is not None and current_approver is not None and caller_empcode == current_approver),
    )


# ---------------------------------------------------------------------------
# Lookups
# ---------------------------------------------------------------------------

def resolve_submitter(conn: pyodbc.Connection, email: str) -> tuple[str | None, str | None]:
    """Returns (employee_code, manager_employee_code) for `email`, matched
    case-insensitively against `dbo.v_employee_budget_01` (the confirmed sole
    source for RLS + approver1, spec §1b). `(None, None)` when the email is
    not found — the "Filler not in the employee view" case (ADR-0019): they
    can still submit, there is simply no manager to resolve."""
    cursor = conn.cursor()
    try:
        cursor.execute(
            "SELECT employee_code, manager_employee_code FROM dbo.v_employee_budget_01 WHERE LOWER(email) = LOWER(?)",
            email,
        )
        row = cursor.fetchone()
    finally:
        cursor.close()
    return (row[0], row[1]) if row else (None, None)


def lookup_employee_name(conn: pyodbc.Connection, empcode: str | None) -> str | None:
    """Thai display name for an empcode, from the same
    `dbo.v_employee_budget_01` the mail cc resolution
    (`app.notifications.lookup_email_by_empcode`) reads — lets the status
    payload NAME the current approver (the admin step-override confirm
    dialog must name who is being skipped, ADR-0027) without a second
    client fetch. None when the empcode is blank or unknown."""
    if not empcode:
        return None
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT full_name_th FROM dbo.v_employee_budget_01 WHERE employee_code = ?", empcode)
        row = cursor.fetchone()
    finally:
        cursor.close()
    return row[0] if row else None


def _department_cost_centers(conn: pyodbc.Connection, department: str) -> set[str]:
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT DISTINCT cost_center FROM dbo.cc_filler_map WHERE department = ?", department)
        rows = cursor.fetchall()
    finally:
        cursor.close()
    return {r[0] for r in rows}


def cost_centers_for_departments(conn: pyodbc.Connection, departments: list[str]) -> set[str]:
    """Live `dbo.cc_filler_map` cost centers for a BATCH of department names —
    the plural sibling of `_department_cost_centers` above (one department at
    a time). Added for `rls.resolve_scope`'s See-overlay (ADR-0029), which may
    need several currently-pending departments' worth of CCs in a single
    call. `departments=[]` short-circuits to an empty set, no query (an empty
    SQL `IN ()` is invalid syntax and there is nothing to fetch anyway)."""
    if not departments:
        return set()
    cursor = conn.cursor()
    try:
        placeholders = ", ".join("?" for _ in departments)
        cursor.execute(
            f"SELECT DISTINCT cost_center FROM dbo.cc_filler_map WHERE department IN ({placeholders})",
            *departments,
        )
        rows = cursor.fetchall()
    finally:
        cursor.close()
    return {r[0] for r in rows}


def _department_has_pending_rows(
    conn: pyodbc.Connection, department: str, cost_centers: set[str], fiscal_year: int
) -> bool:
    """True iff `budget.pending_budget` holds >=1 row for `department` at
    `fiscal_year` — the predicate behind `DepartmentEmptyError` (bug 3,
    2026-08-07 wave). See that class's docstring for the policy; this
    function is only the query, in two mutually-exclusive shapes:

    - `cost_centers` non-empty (the department IS currently live-mapped in
      `dbo.cc_filler_map`, `cost_centers` = `dept_ccs`, already resolved by
      the caller): scoped to those LIVE cost centers, NOT to
      `pending_budget.department` — the snapshot column written at save
      time. This is the same live-first policy gate finding D2 (closed
      2026-08-07) established for the read path: once a CC is reassigned to
      a different department, its OLD department's stale snapshot rows must
      not count as "this department still has data".
    - `cost_centers` empty (the orphan-department admin door — no CC
      currently mapped to `department` at all): there is no live set to
      scope by, so this is the ONLY way to see whether the department ever
      had data — same query shape as `_department_has_admin_template_rows`
      just below, minus its `template='ADMIN'` filter. This is not a
      contradiction of the live-first policy above: live-first means "prefer
      live over snapshot when live has an answer", and an orphan
      department's live answer is exactly "no cost centers", so there is
      nothing for it to prefer over the snapshot.

    "Zero rows" means precisely zero `pending_budget` rows — verified
    sufficient because no child row can exist without one: both the detail-
    line and trip save paths always call `write_model._recompute_parent_cell`
    first, which creates the parent `pending_budget` row on its very first
    write (`rowcount == 0` -> INSERT) before touching its own
    `pending_budget_detail`/`budget_trip` rows. So a department with zero
    parent rows cannot hold any detail or trip data either — checking only
    `pending_budget` is enough, no UNION with the child tables needed."""
    cursor = conn.cursor()
    try:
        if cost_centers:
            placeholders = ", ".join("?" for _ in cost_centers)
            cursor.execute(
                f"SELECT TOP 1 1 FROM budget.pending_budget WHERE fiscal_year = ? AND cost_center IN ({placeholders})",
                fiscal_year, *cost_centers,
            )
        else:
            cursor.execute(
                "SELECT TOP 1 1 FROM budget.pending_budget WHERE department = ? AND fiscal_year = ?",
                department, fiscal_year,
            )
        row = cursor.fetchone()
    finally:
        cursor.close()
    return row is not None


def _department_has_admin_template_rows(conn: pyodbc.Connection, department: str, fiscal_year: int) -> bool:
    """Template-2 door (spec §1d): Budget dept entered this department's
    numbers directly as `template='ADMIN'` — those rows never enter the
    approver chain, so submitting them is a direct-approve, logged
    `ADMIN_SUBMIT`."""
    cursor = conn.cursor()
    try:
        cursor.execute(
            "SELECT TOP 1 1 FROM budget.pending_budget WHERE department = ? AND fiscal_year = ? AND template = 'ADMIN'",
            department, fiscal_year,
        )
        row = cursor.fetchone()
    finally:
        cursor.close()
    return row is not None


def _fetch_row(conn: pyodbc.Connection, department: str, fiscal_year: int) -> dict | None:
    cursor = conn.cursor()
    try:
        cursor.execute(
            f"SELECT {', '.join(_STATUS_COLUMNS)} FROM budget.approval_status WHERE department = ? AND fiscal_year = ?",
            department, fiscal_year,
        )
        row = cursor.fetchone()
    finally:
        cursor.close()
    return dict(zip(_STATUS_COLUMNS, row)) if row else None


def _append_log(
    conn: pyodbc.Connection, department: str, fiscal_year: int, action: str,
    by_empcode: str | None, by_email: str, previous_status: str | None, new_status: str,
    comment: str | None, now: datetime,
) -> None:
    cursor = conn.cursor()
    try:
        cursor.execute(
            """
            INSERT INTO budget.approval_log
                (department, fiscal_year, action, action_by_empcode, action_by_email, action_at,
                 previous_status, new_status, comment)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            department, fiscal_year, action, by_empcode, by_email, now, previous_status, new_status, comment,
        )
    finally:
        cursor.close()


def get_approval_status(
    conn: pyodbc.Connection, department: str, fiscal_year: int, caller_empcode: str | None = None
) -> ApprovalStatusState:
    """Current state of one `(department, fiscal_year)` unit. No DB row yet
    -> synthesized `DRAFT` (never submitted), not a 404."""
    row = _fetch_row(conn, department, fiscal_year)
    if row is None:
        return ApprovalStatusState(department=department, fiscal_year=fiscal_year, status=DRAFT)
    return _to_state(row, department, fiscal_year, caller_empcode)


def authorize_status_view(conn: pyodbc.Connection, department: str, scope: "Scope") -> None:
    """B1 gate fix: `GET /approval/status` must not be readable by just any
    authenticated caller (submitter email/empcode, rejecter, reject_reason
    are sensitive). Admin may view any department; otherwise the caller must
    See at least one cost center of the department — the same
    `dbo.cc_filler_map` mapping `submit_department` already uses via
    `_department_cost_centers`, checked against See (not Fill) since viewing
    is a broader right than submitting (ADR-0007). Raises the SAME error for
    an out-of-scope real department and a nonexistent one, so the endpoint
    can never be used to enumerate department names."""
    if scope.is_admin:
        return
    dept_ccs = _department_cost_centers(conn, department)
    if not dept_ccs & set(scope.see_cost_centers):
        raise NotAuthorizedToViewDepartmentError("not authorized to view this department's approval status")


# ---------------------------------------------------------------------------
# Chain resolution (ADR-0006)
# ---------------------------------------------------------------------------

def _active_positions(submitter_empcode: str | None, approver1_empcode: str) -> list[int]:
    """The 3 fixed positions, minus self-skip (occupant == submitter) and
    dedup (occupant already seen at an earlier position, "keep the earliest
    step"). Returns positions in order 1<2<3 — never renumbered.

    In practice this list is NEVER empty: `NIPAPORN_EMPCODE` and
    `WARAPORN_EMPCODE` are fixed, distinct constants, and a single submitter
    can equal at most one occupant, so at least one of the 3 positions always
    survives. `resolve_chain` still applies the never-cut "empty -> fall back
    to Nipaporn" safety net from ADR-0006 as defense-in-depth (unit-tested
    directly via a contrived call to this function)."""
    positions = [(1, approver1_empcode), (2, NIPAPORN_EMPCODE), (3, WARAPORN_EMPCODE)]
    seen: set[str] = set()
    active: list[int] = []
    for pos, occupant in positions:
        if submitter_empcode is not None and occupant == submitter_empcode:
            continue
        if occupant in seen:
            continue
        seen.add(occupant)
        active.append(pos)
    return active


def resolve_chain(conn: pyodbc.Connection, submitter_email: str) -> tuple[str | None, str, list[int]]:
    """Resolve + freeze one submission's chain. Returns
    `(submitter_empcode, approver1_empcode, active_positions)`.

    ADR-0006 invalid-approver1 rule: no manager resolvable (submitter not in
    the employee view, or their Primary-row manager is NULL) -> approver1
    becomes Nipaporn directly. Because position 2 is ALSO always Nipaporn,
    this makes position 1 and 2 the same occupant, which `_active_positions`'
    dedup then collapses to a single active position automatically — no
    separate branch needed for "invalid approver1" vs a genuine self-skip."""
    submitter_empcode, raw_manager = resolve_submitter(conn, submitter_email)
    approver1_empcode = raw_manager or NIPAPORN_EMPCODE
    active = _active_positions(submitter_empcode, approver1_empcode)
    if not active:
        # Never-cut safety net (ADR-0006) — see _active_positions docstring;
        # unreachable via the normal 3-constant algorithm, kept anyway.
        approver1_empcode = NIPAPORN_EMPCODE
        active = [1]
    return submitter_empcode, approver1_empcode, active


# ---------------------------------------------------------------------------
# Submit
# ---------------------------------------------------------------------------

@dataclass
class SubmitEligibility:
    """Read-only mirror of `submit_department`'s decision tree — SAME
    predicates, SAME query order, zero writes. `submit_department` (the
    write path) and `routers/approval.py`'s `_set_can_submit` (the
    button-visibility verdict on every `GET/POST /approval/*` response) both
    build off this ONE function, so a future change to a door automatically
    moves both instead of the two silently drifting apart — which is exactly
    the shape of the SIT "doomed submit button" bug this closes (2026-08-16,
    the sibling of the 2026-08-14 `is_post_deadline` fix): the admin hat used
    to decide button visibility from `status`/`is_post_deadline` alone, which
    cannot tell the 3 admin doors (Template-2/orphan/post-deadline-override)
    apart from the 4th, refused shape (not a filler, department not orphan,
    no Template-2 rows, cycle still open) — that shape always showed a
    button that then 403'd with `AdminCannotSubmitInCycleError`.

    `reason` is `None` when `can_submit` is True; otherwise one of
    `ERROR_CODE_BY_EXCEPTION`'s values — see that map for what the code means
    and `ERROR_HTTP_STATUS` for the HTTP status `submit_department` raises
    for it.

    `existing`/`dept_ccs`/`is_filler`/`has_admin_template_rows` are the data
    ALREADY fetched while deciding — `submit_department` reuses them
    directly for its write branch instead of re-querying. This is WHY the
    query count/order stays byte-identical to before this refactor (every
    pre-existing mocked-cursor test in test_approval.py still pins the same
    `fetchone`/`fetchall` sequence unchanged)."""

    can_submit: bool
    reason: str | None = None
    existing: dict | None = None
    dept_ccs: set[str] = field(default_factory=set)
    is_filler: bool = False
    has_admin_template_rows: bool = False


def evaluate_submit_eligibility(
    conn: pyodbc.Connection, department: str, fiscal_year: int, submitter_email: str, scope: "Scope",
) -> SubmitEligibility:
    """Would `submit_department(conn, department, fiscal_year, submitter_email, scope)`
    succeed right now? Same branch order as that function's docstring
    describes (department-emptiness first, then filler-normal-chain vs the 3
    admin-only doors) — see `SubmitEligibility` for why this is the ONE place
    that logic lives.

    `submitter_email` is accepted but not read in this function's body (gate
    review, 2026-08-16) — kept for signature symmetry with
    `submit_department(conn, department, fiscal_year, submitter_email, scope)`,
    the write path this mirrors call-for-call, so the two stay trivially
    swappable at every call site without a parameter-order trap. Not dropped:
    12 existing test call sites in test_approval.py already pass it
    positionally, and every branch below is decided by `scope` alone."""
    existing = _fetch_row(conn, department, fiscal_year)
    dept_ccs = _department_cost_centers(conn, department)
    if not _department_has_pending_rows(conn, department, dept_ccs, fiscal_year):
        return SubmitEligibility(can_submit=False, reason="department_empty", existing=existing, dept_ccs=dept_ccs)

    is_filler = bool(dept_ccs & set(scope.fill_cost_centers))
    if is_filler:
        if existing is not None and existing["status"] != REJECTED:
            return SubmitEligibility(
                can_submit=False, reason="invalid_approval_state", existing=existing, dept_ccs=dept_ccs, is_filler=True,
            )
        year_state = _fiscal_year_state(conn, fiscal_year)
        if year_state == YEAR_NOT_OPEN:
            return SubmitEligibility(
                can_submit=False, reason="year_not_open", existing=existing, dept_ccs=dept_ccs, is_filler=True,
            )
        if year_state == YEAR_PAST_DEADLINE:
            return SubmitEligibility(
                can_submit=False, reason="past_deadline", existing=existing, dept_ccs=dept_ccs, is_filler=True,
            )
        return SubmitEligibility(can_submit=True, existing=existing, dept_ccs=dept_ccs, is_filler=True)

    if not scope.is_admin:
        return SubmitEligibility(
            can_submit=False, reason="not_filler_of_department", existing=existing, dept_ccs=dept_ccs,
        )

    has_admin_template_rows = _department_has_admin_template_rows(conn, department, fiscal_year)
    if has_admin_template_rows:
        if existing is not None and existing["status"] in PENDING_STATUSES | {APPROVED}:
            return SubmitEligibility(
                can_submit=False, reason="mid_chain_admin_overwrite", existing=existing, dept_ccs=dept_ccs,
                has_admin_template_rows=True,
            )
        return SubmitEligibility(can_submit=True, existing=existing, dept_ccs=dept_ccs, has_admin_template_rows=True)

    if not dept_ccs:  # orphan: zero cost centers currently map to this department
        if existing is not None and existing["status"] in PENDING_STATUSES | {APPROVED}:
            return SubmitEligibility(
                can_submit=False, reason="mid_chain_admin_overwrite", existing=existing, dept_ccs=dept_ccs,
            )
        return SubmitEligibility(can_submit=True, existing=existing, dept_ccs=dept_ccs)

    if _is_post_deadline(conn, fiscal_year):
        # The query result decides `can_submit` itself (the post-deadline
        # override door) -- it is NOT also stashed on a `SubmitEligibility`
        # field, since nothing ever read one (gate review, 2026-08-16;
        # dropped). `state.is_post_deadline` on the response is a SEPARATE,
        # unconditional value the router computes itself (`_set_is_post_
        # deadline`) -- see that function's docstring for why the two must
        # stay independent rather than one reusing the other.
        return SubmitEligibility(can_submit=True, existing=existing, dept_ccs=dept_ccs)

    return SubmitEligibility(can_submit=False, reason="admin_cannot_submit_in_cycle", existing=existing, dept_ccs=dept_ccs)


def submit_department(
    conn: pyodbc.Connection, department: str, fiscal_year: int, submitter_email: str, scope: "Scope",
) -> ApprovalStatusState:
    """Submit `(department, fiscal_year)`.

    The WHOLE authorization decision (department-emptiness, filler-normal-
    chain-vs-admin-doors branch selection, the B2 fail-closed mid-chain-
    overwrite guard) lives in `evaluate_submit_eligibility` — this function
    only turns a refused verdict into the matching exception (for the HTTP
    layer, via `ERROR_CODE_BY_EXCEPTION`) and, on a go verdict, dispatches to
    the write branch the eligibility check already identified. See
    `SubmitEligibility`'s docstring for why the decision is centralized this
    way and `evaluate_submit_eligibility` for the branch order itself.

    Branch selection recap: a caller who Fills >=1 cost center of this
    department ALWAYS goes through the normal chain, regardless of
    `scope.is_admin` — this is what keeps Nipaporn/Waraporn's dual role
    correct (they Fill 5 departments themselves and must go through
    self-skip/dedup like anyone else, per ADR-0006's own worked examples).
    Only a caller who does NOT Fill this department at all can hit the admin
    direct-approve branch, and only if they are admin (ADR-0012).

    Admin-GL rows (`dbo.gl_group.edit_by='admin'`, ADR-0024) are never
    referenced here at all — they never enter `budget.approval_status`,
    approved-on-save the instant the admin (Budget dept) saves them (A5's
    write path), independent of this normal chain. A normal submit governs
    only the department's lane-2.1 (user-GL) rows, whether the submitter is
    an admin who also Fills the department or a plain non-admin filler."""
    eligibility = evaluate_submit_eligibility(conn, department, fiscal_year, submitter_email, scope)
    existing = eligibility.existing
    now = _now()

    if not eligibility.can_submit:
        if eligibility.reason == "department_empty":
            raise DepartmentEmptyError("This department has no budget data yet, so it cannot be submitted.")
        if eligibility.reason == "invalid_approval_state":
            raise InvalidApprovalStateError(
                f"{department}/{fiscal_year} is {existing['status']} — cannot submit "
                "(PENDING_* has no recall; APPROVED needs no re-submission, ADR-0013)"
            )
        if eligibility.reason == "year_not_open":
            raise YearNotOpenError(
                "This fiscal year is not open for entry on the web — its data is "
                "imported from a file by an administrator."
            )
        if eligibility.reason == "past_deadline":
            raise PastDeadlineError(f"the submission deadline for fiscal_year={fiscal_year} has passed")
        if eligibility.reason == "not_filler_of_department":
            raise NotFillerOfDepartmentError(f"{submitter_email} does not Fill any cost center of {department!r}")
        if eligibility.reason == "mid_chain_admin_overwrite":
            raise MidChainAdminOverwriteError(
                f"{department}/{fiscal_year} is {existing['status']} — mid-approval; admin cannot "
                "admin-submit until it is rejected or the submission deadline has passed"
            )
        if eligibility.reason == "admin_cannot_submit_in_cycle":
            raise AdminCannotSubmitInCycleError(
                f"admin cannot submit {department!r} while the cycle is open unless it is orphan "
                "or was entered via the Template-2 (ADMIN) door"
            )
        # Should never fire — every real branch in `evaluate_submit_eligibility`
        # is handled above. Was a bare `AssertionError` (gate review,
        # 2026-08-16): not in `ERROR_CODE_BY_EXCEPTION`, so it would have
        # surfaced as an UNCAUGHT 500 through `_run` instead of the same
        # clean, mapped 4xx every other refusal gets. Reuses
        # `InvalidApprovalStateError` (already mapped -> 409) rather than
        # inventing a new exception/code for a should-never-happen path —
        # the write is refused either way (fail-closed); this only controls
        # HOW that refusal is reported.
        raise InvalidApprovalStateError(  # pragma: no cover
            f"{department}/{fiscal_year}: unreachable SubmitEligibility.reason: {eligibility.reason!r}"
        )

    if eligibility.is_filler:
        return _submit_normal_chain(conn, department, fiscal_year, submitter_email, existing, now)

    if eligibility.has_admin_template_rows:
        return _admin_direct_approve(conn, department, fiscal_year, submitter_email, existing, now, ACTION_ADMIN_SUBMIT)

    if not eligibility.dept_ccs:  # orphan
        return _admin_direct_approve(
            conn, department, fiscal_year, submitter_email, existing, now, ACTION_ADMIN_OVERRIDE_ORPHAN
        )

    return _admin_direct_approve(
        conn, department, fiscal_year, submitter_email, existing, now, ACTION_ADMIN_OVERRIDE_DEADLINE
    )


def _insert_new_approval_row(
    cursor: pyodbc.Cursor, department: str, fiscal_year: int, status: str,
    submitter_empcode: str | None, submitter_email: str, submitted_at: datetime,
    approver1_empcode: str | None, updated_at: datetime,
) -> None:
    """Shared brand-new-row INSERT for `budget.approval_status` — used by
    both a normal first-time Submit (`ACTION_SUBMIT`) and the auto_submit
    job (`ACTION_AUTO_SUBMIT`, ADR-0006/A11) so the two paths can never
    drift on columns or on the concurrent-PK-violation ->
    `ConcurrentApprovalError` mapping (S2 gate fix). Caller owns the
    cursor/commit/log — the resubmit UPDATE path shares that same tail, so
    it stays outside this helper, same as before this extraction."""
    try:
        cursor.execute(
            """
            INSERT INTO budget.approval_status
                (department, fiscal_year, status, submitter_empcode, submitter_email, submitted_at,
                 approver1_empcode, _updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            department, fiscal_year, status, submitter_empcode, submitter_email, submitted_at,
            approver1_empcode, updated_at,
        )
    except pyodbc.IntegrityError as exc:
        raise ConcurrentApprovalError(
            f"{department}/{fiscal_year} was submitted concurrently by another request"
        ) from exc


def _submit_normal_chain(
    conn: pyodbc.Connection, department: str, fiscal_year: int, submitter_email: str, existing: dict | None, now: datetime,
) -> ApprovalStatusState:
    """The filler-chain write branch — only ever reached via `submit_department`
    after `evaluate_submit_eligibility` has already confirmed `existing` is
    either `None` or `REJECTED` (no recall of a PENDING_*/APPROVED record,
    ADR-0013) AND `fiscal_year` is OPEN (not NOT_OPEN/PAST_DEADLINE,
    2026-08-08 3-state extension) — those checks used to live here directly;
    they now live once in `evaluate_submit_eligibility` so this function and
    the button-visibility verdict can never drift on what "eligible" means.
    `submit_department` is this function's only caller."""
    submitter_empcode, approver1_empcode, active = resolve_chain(conn, submitter_email)
    first_status = _POSITION_TO_STATUS[active[0]]
    action = ACTION_RESUBMIT if existing is not None else ACTION_SUBMIT

    cursor = conn.cursor()
    try:
        if existing is None:
            _insert_new_approval_row(
                cursor, department, fiscal_year, first_status, submitter_empcode, submitter_email, now,
                approver1_empcode, now,
            )
        else:
            # Re-freeze from scratch (never-cut: resubmit RESTARTS the whole
            # chain, it never resumes mid-chain) — every prior timestamp and
            # reject reason is cleared. S3 gate fix: conditioned on
            # `status = REJECTED` (the only state resubmit is ever reached
            # from — see the guard above) so a concurrent status change
            # between the read and this UPDATE is caught instead of silently
            # overwritten — the same race guard approve/reject already use.
            cursor.execute(
                """
                UPDATE budget.approval_status
                SET status = ?, submitter_empcode = ?, submitter_email = ?, submitted_at = ?,
                    approver1_empcode = ?, approver1_actioned_at = NULL, approver2_actioned_at = NULL,
                    approver3_actioned_at = NULL, reject_reason = NULL, rejected_by_empcode = NULL,
                    _updated_at = ?
                WHERE department = ? AND fiscal_year = ? AND status = ?
                """,
                first_status, submitter_empcode, submitter_email, now, approver1_empcode, now,
                department, fiscal_year, REJECTED,
            )
            if cursor.rowcount == 0:
                raise ConcurrentApprovalError(
                    f"{department}/{fiscal_year} status changed concurrently — reload and retry"
                )
        _append_log(
            conn, department, fiscal_year, action, submitter_empcode, submitter_email,
            existing["status"] if existing else None, first_status, None, now,
        )
        conn.commit()
    finally:
        cursor.close()

    new_row = {
        "status": first_status, "submitter_empcode": submitter_empcode, "submitter_email": submitter_email,
        "submitted_at": now, "approver1_empcode": approver1_empcode, "approver1_actioned_at": None,
        "approver2_actioned_at": None, "approver3_actioned_at": None, "reject_reason": None,
        "rejected_by_empcode": None, "_updated_at": now,
    }
    return _to_state(new_row, department, fiscal_year, caller_empcode=submitter_empcode)


def auto_submit_department(
    conn: pyodbc.Connection, department: str, fiscal_year: int, last_editor_email: str, now: datetime | None = None,
) -> ApprovalStatusState:
    """A11 (`jobs/auto_submit.py`): system-triggered submit for a department
    still in TRUE DRAFT (no `approval_status` row at all) at/after the
    fiscal year's deadline (ADR-0006 — "auto-submit DRAFT ฝ่าย at
    deadline"). There is no human clicker, so approver1 resolves from the
    LAST EDITOR's manager — the job's own discovery query finds the `_user`
    on the most-recently-updated `pending_budget` row for this department
    and passes it in as `last_editor_email`. Everything else (self-skip,
    dedup, invalid-approver1 fallback) reuses `resolve_chain` UNCHANGED, so
    an auto-submitted chain can never disagree with what a human Submit by
    that same editor would have produced.

    Deliberately narrower than `submit_department`: only ever valid when
    `existing is None` (raises otherwise, defense-in-depth — the job's own
    discovery query should never call this for a department that already
    has a row). REJECTED departments are intentionally NOT covered here —
    ADR-0012 gives the admin sole ownership of every post-deadline
    straggler, REJECTED included, via `submit_department`'s post-deadline
    override branch; keeping that as the one path avoids two different
    automations racing the same row.

    Defense-in-depth (ADR-0006 — this job only ever fires at/after the
    deadline): `jobs/auto_submit.py` already checks `is_post_deadline`
    before calling this function, but the check is repeated here too so the
    function can never be misused to auto-submit a still-open department if
    some future caller forgets that precondition."""
    existing = _fetch_row(conn, department, fiscal_year)
    if existing is not None:
        raise InvalidApprovalStateError(
            f"{department}/{fiscal_year} already has an approval_status row "
            f"(status={existing['status']}) — not a true DRAFT, auto_submit_department must not run"
        )
    if not _is_post_deadline(conn, fiscal_year):
        raise InvalidApprovalStateError(
            f"{department}/{fiscal_year} — submission deadline has not passed yet; "
            "auto_submit_department must only run at/after the deadline (ADR-0006)"
        )

    now = now or _now()
    submitter_empcode, approver1_empcode, active = resolve_chain(conn, last_editor_email)
    first_status = _POSITION_TO_STATUS[active[0]]

    cursor = conn.cursor()
    try:
        _insert_new_approval_row(
            cursor, department, fiscal_year, first_status, submitter_empcode, last_editor_email, now,
            approver1_empcode, now,
        )
        _append_log(
            conn, department, fiscal_year, ACTION_AUTO_SUBMIT, submitter_empcode, last_editor_email,
            None, first_status, "auto-submitted at deadline (ADR-0006)", now,
        )
        conn.commit()
    finally:
        cursor.close()

    new_row = {
        "status": first_status, "submitter_empcode": submitter_empcode, "submitter_email": last_editor_email,
        "submitted_at": now, "approver1_empcode": approver1_empcode, "approver1_actioned_at": None,
        "approver2_actioned_at": None, "approver3_actioned_at": None, "reject_reason": None,
        "rejected_by_empcode": None, "_updated_at": now,
    }
    return _to_state(new_row, department, fiscal_year, caller_empcode=None)


def _admin_direct_approve(
    conn: pyodbc.Connection, department: str, fiscal_year: int, admin_email: str,
    existing: dict | None, now: datetime, action: str,
) -> ApprovalStatusState:
    """Write APPROVED directly — no approver chain, no PENDING_* step ever
    exists for this submission (ADR-0012 / spec §1d)."""
    admin_empcode, _ = resolve_submitter(conn, admin_email)

    cursor = conn.cursor()
    try:
        if existing is None:
            try:
                cursor.execute(
                    """
                    INSERT INTO budget.approval_status
                        (department, fiscal_year, status, submitter_empcode, submitter_email, submitted_at, _updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    department, fiscal_year, APPROVED, admin_empcode, admin_email, now, now,
                )
            except pyodbc.IntegrityError as exc:
                # Same concurrent-PK-violation mapping as _insert_new_approval_row
                # (S2 gate fix) — without it a lost race escaped as a raw
                # pyodbc.Error and the router returned a misleading 502
                # "Database unavailable" (Phase 2 P2-B3 prod finding 2026-07-28).
                raise ConcurrentApprovalError(
                    f"{department}/{fiscal_year} was submitted concurrently by another request"
                ) from exc
        else:
            cursor.execute(
                """
                UPDATE budget.approval_status
                SET status = ?, submitter_empcode = ?, submitter_email = ?, submitted_at = ?,
                    approver1_empcode = NULL, approver1_actioned_at = NULL, approver2_actioned_at = NULL,
                    approver3_actioned_at = NULL, reject_reason = NULL, rejected_by_empcode = NULL,
                    _updated_at = ?
                WHERE department = ? AND fiscal_year = ?
                """,
                APPROVED, admin_empcode, admin_email, now, now, department, fiscal_year,
            )
        _append_log(
            conn, department, fiscal_year, action, admin_empcode, admin_email,
            existing["status"] if existing else None, APPROVED, None, now,
        )
        conn.commit()
    finally:
        cursor.close()

    new_row = {
        "status": APPROVED, "submitter_empcode": admin_empcode, "submitter_email": admin_email,
        "submitted_at": now, "approver1_empcode": None, "approver1_actioned_at": None,
        "approver2_actioned_at": None, "approver3_actioned_at": None, "reject_reason": None,
        "rejected_by_empcode": None, "_updated_at": now,
    }
    return _to_state(new_row, department, fiscal_year, caller_empcode=admin_empcode)


# ---------------------------------------------------------------------------
# Approve / Reject
# ---------------------------------------------------------------------------

def _authorize_current_step(conn: pyodbc.Connection, row: dict, actor_email: str) -> tuple[str, int]:
    """Returns (actor_empcode, current_position). Raises
    `NotCurrentApproverError` if `actor_email` is not the frozen occupant of
    the record's current PENDING_* step."""
    actor_empcode, _ = resolve_submitter(conn, actor_email)
    current_position = _STATUS_TO_POSITION[row["status"]]
    current_occupant = _occupant_for_position(current_position, row["approver1_empcode"])
    if actor_empcode is None or actor_empcode != current_occupant:
        raise NotCurrentApproverError(
            f"{actor_email} is not the current approver for {row['department']}/{row['fiscal_year']}"
        )
    return actor_empcode, current_position


def _advance_one_step(
    conn: pyodbc.Connection, department: str, fiscal_year: int, row: dict, current_position: int,
    new_status: str, action: str, by_empcode: str | None, by_email: str, comment: str | None, now: datetime,
) -> None:
    """Shared conditional UPDATE + log + commit for moving `(department,
    fiscal_year)` off its CURRENT PENDING_* status to `new_status`, stamping
    the current position's `_actioned_at` column. Used by both a real
    approver's `approve_department` step (`ACTION_APPROVE`, `new_status` may
    be the next PENDING_* or the final `APPROVED`) and the admin
    step-override (`ACTION_ADMIN_STEP_OVERRIDE`, `new_status` is always the
    next PENDING_* — never `APPROVED`, see `admin_override_step`) so the two
    can never drift on the conditional-UPDATE race guard or the log shape."""
    actioned_col = f"approver{current_position}_actioned_at"
    cursor = conn.cursor()
    try:
        cursor.execute(
            f"""
            UPDATE budget.approval_status
            SET status = ?, {actioned_col} = ?, _updated_at = ?
            WHERE department = ? AND fiscal_year = ? AND status = ?
            """,
            new_status, now, now, department, fiscal_year, row["status"],
        )
        if cursor.rowcount == 0:
            raise ConcurrentApprovalError(f"{department}/{fiscal_year} status changed concurrently — reload and retry")
        _append_log(conn, department, fiscal_year, action, by_empcode, by_email, row["status"], new_status, comment, now)
        conn.commit()
    finally:
        cursor.close()


def approve_department(
    conn: pyodbc.Connection, department: str, fiscal_year: int, approver_email: str, comment: str | None = None
) -> ApprovalStatusState:
    row = _fetch_row(conn, department, fiscal_year)
    if row is None:
        raise ApprovalRecordNotFoundError(f"no approval record for {department}/{fiscal_year}")
    if row["status"] not in PENDING_STATUSES:
        raise InvalidApprovalStateError(f"cannot approve {department}/{fiscal_year} from status {row['status']}")

    approver_empcode, current_position = _authorize_current_step(conn, row, approver_email)
    active = _active_positions(row["submitter_empcode"], row["approver1_empcode"])
    idx = active.index(current_position)
    is_last_step = idx == len(active) - 1
    new_status = APPROVED if is_last_step else _POSITION_TO_STATUS[active[idx + 1]]
    now = _now()

    _advance_one_step(conn, department, fiscal_year, row, current_position, new_status,
                       ACTION_APPROVE, approver_empcode, approver_email, comment, now)

    new_row = dict(row)
    new_row["status"] = new_status
    new_row[f"approver{current_position}_actioned_at"] = now
    new_row["_updated_at"] = now
    return _to_state(new_row, department, fiscal_year, caller_empcode=approver_empcode)


def admin_override_step(
    conn: pyodbc.Connection, department: str, fiscal_year: int, admin_email: str
) -> ApprovalStatusState:
    """ADR-0027 manual admin step-override: a human ADMIN advances a stuck
    position-1 step by EXACTLY ONE step, following the same active-position
    walk a real approve uses. Replaces the retired 30-day auto-escalation —
    a person now makes the call, on the record, with their real email in the
    log (never a `system:` literal).

    Hard locks (ADR-0027): position 1 ONLY (positions 2/3 are the budget-dept
    review itself — `StepNotOverridableError`), and the override may NEVER
    land `APPROVED` (refused when position 1 is the only active position).
    No stale-time gate, no reason field (D3). Authorization (admin-only)
    lives in the router, mirroring how `submit_department` takes `scope` —
    this function assumes the caller was already verified as admin.

    Hardening (review fix, not yet reachable on live data): checking the
    POSITION NUMBER alone is not enough. ADR-0006 dedup/self-skip can
    resolve `approver1_empcode` directly to Nipaporn or Waraporn (their
    manager IS one of them, or no manager resolves and the invalid-approver1
    fallback lands on Nipaporn) — position 2 then dedups away and the
    budget-dept reviewer sits AT position 1. A pure `status ==
    PENDING_APPROVER1` check would let an override skip exactly the review
    D4 exists to protect, the moment one HR reassignment makes this live. So
    the OCCUPANT of position 1 is checked too, not just its slot number."""
    row = _fetch_row(conn, department, fiscal_year)
    if row is None:
        raise ApprovalRecordNotFoundError(f"no approval record for {department}/{fiscal_year}")
    if row["status"] != PENDING_APPROVER1:
        if row["status"] in PENDING_STATUSES:
            raise StepNotOverridableError(
                "Cannot approve on their behalf — the budget is already being reviewed by "
                "the Budget Department. The Budget Department must approve it themselves "
                "(the override button works only while the budget is still waiting at the "
                "filler's manager, which is step 1)."
            )
        raise InvalidApprovalStateError(f"cannot override {department}/{fiscal_year} from status {row['status']}")
    if row["approver1_empcode"] in (NIPAPORN_EMPCODE, WARAPORN_EMPCODE):
        # Same hard lock as positions 2/3 above, just reached via position 1:
        # dedup/self-skip put the budget-dept reviewer in the position-1 slot
        # itself, so the slot number alone cannot tell "a real manager" apart
        # from "the budget dept, coincidentally occupying slot 1".
        # Names the actual person (2026-08-02, jakkaritw: the old wording read
        # as a riddle on staging) — falls back to the role when the empcode has
        # no employee row.
        who = lookup_employee_name(conn, row["approver1_empcode"]) or "the Budget Department"
        raise StepNotOverridableError(
            "Cannot approve on their behalf — this department has no manager step. "
            f"Approver step 1 is {who}, who is the Budget Department. "
            "The override button can only skip a filler's manager step. "
            "The Budget Department must approve it themselves."
        )

    active = _active_positions(row["submitter_empcode"], row["approver1_empcode"])
    idx = active.index(1)
    if idx == len(active) - 1:
        raise StepNotOverridableError(
            "Cannot approve on their behalf — this department has only one approval step "
            "left. Overriding it would approve the budget immediately with no one actually "
            "reviewing it. The approver must approve it themselves."
        )
    new_status = _POSITION_TO_STATUS[active[idx + 1]]
    now = _now()
    # May be None — an admin with no v_employee_budget_01 row (e.g.
    # jakkaritw) still overrides; the log then carries by_empcode=NULL and
    # the real admin email (ADR-0027: expected, not an error).
    admin_empcode, _ = resolve_submitter(conn, admin_email)

    _advance_one_step(conn, department, fiscal_year, row, 1, new_status,
                      ACTION_ADMIN_STEP_OVERRIDE, admin_empcode, admin_email,
                      "admin step override (ADR-0027)", now)

    new_row = dict(row)
    new_row["status"] = new_status
    new_row["approver1_actioned_at"] = now
    new_row["_updated_at"] = now
    return _to_state(new_row, department, fiscal_year, caller_empcode=admin_empcode)


def _current_step_started_at(row: dict) -> datetime:
    """Best available signal for "when did the CURRENT PENDING_* step
    begin" — flagged: there is no dedicated per-step "turn started" column
    on `budget.approval_status` (no schema change made for this). Derived
    as the most recent `approverN_actioned_at` among EARLIER positions,
    falling back further (ultimately to `submitted_at`) whenever an earlier
    position was itself skipped by self-skip/dedup (its own `_actioned_at`
    stays NULL forever, ADR-0006) — walking back this way is always
    correct because positions are only ever skipped, never reordered."""
    position = _STATUS_TO_POSITION[row["status"]]
    if position >= 3 and row.get("approver2_actioned_at") is not None:
        return row["approver2_actioned_at"]
    if position >= 2 and row.get("approver1_actioned_at") is not None:
        return row["approver1_actioned_at"]
    return row["submitted_at"]


def current_turn_info(row: dict) -> tuple[datetime, str | None]:
    """`(turn_start, current_approver_empcode)` for a PENDING_* row —
    exposed for `jobs/send_reminders.py` Phase A (7-day turn reminders,
    2026-07-31 email-notify revamp). `turn_start` is derived by
    `_current_step_started_at` above; the 7-day reminder cadence anchors on
    it and repeats forever until the approver acts (ADR-0027: no end date,
    no cap — the reminder clock is now its only consumer). The empcode is
    the frozen occupant of the current position (None when position 1's
    `approver1_empcode` is NULL — the caller skips such rows)."""
    position = _STATUS_TO_POSITION[row["status"]]
    return _current_step_started_at(row), _occupant_for_position(position, row["approver1_empcode"])


def fetch_pending_rows(conn: pyodbc.Connection, fiscal_year: int | None = None) -> list[dict]:
    """Every `(department, fiscal_year)` row currently in a PENDING_* status,
    keyed the same shape as `_fetch_row`. Read-only — `jobs/send_reminders.py`
    Phase A (turn reminders) is the consumer, filtering via `current_turn_info`.

    `fiscal_year=None` (added for `rls.resolve_scope`'s See-overlay,
    ADR-0029) drops the year filter entirely — "is it currently this
    person's turn" must not depend on which fiscal_year happens to be open
    for web entry. Every pre-existing caller still passes a real
    `fiscal_year` and is unaffected."""
    cursor = conn.cursor()
    try:
        if fiscal_year is None:
            cursor.execute(
                f"SELECT {', '.join(_STATUS_COLUMNS)} FROM budget.approval_status "
                "WHERE status IN (?, ?, ?)",
                PENDING_APPROVER1, PENDING_APPROVER2, PENDING_APPROVER3,
            )
        else:
            cursor.execute(
                f"SELECT {', '.join(_STATUS_COLUMNS)} FROM budget.approval_status "
                "WHERE fiscal_year = ? AND status IN (?, ?, ?)",
                fiscal_year, PENDING_APPROVER1, PENDING_APPROVER2, PENDING_APPROVER3,
            )
        rows = cursor.fetchall()
    finally:
        cursor.close()
    return [dict(zip(_STATUS_COLUMNS, row)) for row in rows]


def departments_pending_for_empcode(
    conn: pyodbc.Connection, caller_empcode: str, fiscal_year: int | None = None
) -> list[str]:
    """Departments whose CURRENT PENDING_* step is frozen to `caller_empcode`
    — the ONE definition of "is it currently this person's turn", shared by:

    - `list_departments_pending_my_approval` below (A10 รออนุมัติ badge,
      one `fiscal_year` at a time, resolved from an email); and
    - `rls.resolve_scope`'s See-overlay (ADR-0029, jakkaritw decision ก,
      2026-08-08), called with `fiscal_year=None` — a department pending on
      its approver must be visible regardless of which fiscal_year it landed
      in, since `resolve_scope` itself is year-agnostic.

    Built from `fetch_pending_rows` (query shape) + `_to_state`'s `can_act`
    (the "is this empcode the frozen occupant of the CURRENT step" check) —
    neither is duplicated here, so the two callers can never silently
    disagree on who may currently act."""
    rows = fetch_pending_rows(conn, fiscal_year)
    return [
        row["department"]
        for row in rows
        if _to_state(row, row["department"], row["fiscal_year"], caller_empcode).can_act
    ]


def list_departments_pending_my_approval(
    conn: pyodbc.Connection, fiscal_year: int, caller_email: str
) -> list[str]:
    """A10 รออนุมัติ badge data source (`GET /approval/pending-for-me`):
    every department whose CURRENT PENDING_* step, for `fiscal_year`, is
    frozen to `caller_email`. A caller not found in the employee view (no
    empcode) can never be a frozen approver, so it short-circuits to an
    empty list without even querying `approval_status`. Thin email→empcode
    wrapper around `departments_pending_for_empcode` (shared with
    `rls.resolve_scope`'s See-overlay, ADR-0029) — see that function for the
    "current approver" logic itself."""
    caller_empcode, _ = resolve_submitter(conn, caller_email)
    if caller_empcode is None:
        return []
    return departments_pending_for_empcode(conn, caller_empcode, fiscal_year)


def reject_department(
    conn: pyodbc.Connection, department: str, fiscal_year: int, rejecter_email: str, reason: str
) -> ApprovalStatusState:
    if not reason or not reason.strip():
        raise MissingReasonError("reject_reason is required")

    row = _fetch_row(conn, department, fiscal_year)
    if row is None:
        raise ApprovalRecordNotFoundError(f"no approval record for {department}/{fiscal_year}")
    if row["status"] not in PENDING_STATUSES:
        raise InvalidApprovalStateError(f"cannot reject {department}/{fiscal_year} from status {row['status']}")

    rejecter_empcode, _current_position = _authorize_current_step(conn, row, rejecter_email)
    now = _now()

    cursor = conn.cursor()
    try:
        cursor.execute(
            """
            UPDATE budget.approval_status
            SET status = ?, reject_reason = ?, rejected_by_empcode = ?, _updated_at = ?
            WHERE department = ? AND fiscal_year = ? AND status = ?
            """,
            REJECTED, reason, rejecter_empcode, now, department, fiscal_year, row["status"],
        )
        if cursor.rowcount == 0:
            raise ConcurrentApprovalError(f"{department}/{fiscal_year} status changed concurrently — reload and retry")
        _append_log(conn, department, fiscal_year, ACTION_REJECT, rejecter_empcode, rejecter_email,
                    row["status"], REJECTED, reason, now)
        conn.commit()
    finally:
        cursor.close()

    new_row = dict(row)
    new_row["status"] = REJECTED
    new_row["reject_reason"] = reason
    new_row["rejected_by_empcode"] = rejecter_empcode
    new_row["_updated_at"] = now
    return _to_state(new_row, department, fiscal_year, caller_empcode=rejecter_empcode)
