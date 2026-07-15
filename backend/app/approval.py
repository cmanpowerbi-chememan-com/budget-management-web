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
from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

import pyodbc
from pydantic import BaseModel

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

# Append-only action log values this module writes (AUTO_SUBMIT/AUTO_ESCALATE
# are A11's scheduled jobs — not written here, just reserved nvarchar values).
ACTION_SUBMIT = "SUBMIT"
ACTION_RESUBMIT = "RESUBMIT"
ACTION_APPROVE = "APPROVE"
ACTION_REJECT = "REJECT"
ACTION_ADMIN_SUBMIT = "ADMIN_SUBMIT"
# S4 gate fix: split the old single ACTION_ADMIN_OVERRIDE value into two, so
# the audit log can tell apart "department is structurally orphan" from "the
# submission deadline has passed" — both used to log the same indistinguishable
# code. Verified live 2026-07-16: budget.approval_log.action is NVARCHAR(40),
# both values fit with room to spare.
ACTION_ADMIN_OVERRIDE_ORPHAN = "ADMIN_OVERRIDE_ORPHAN"
ACTION_ADMIN_OVERRIDE_DEADLINE = "ADMIN_OVERRIDE_DEADLINE"

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


class PastDeadlineError(PermissionError):
    """A normal user tried to submit after `dbo.submission_deadline` for this
    fiscal_year has passed — the cycle is closed to users (ADR-0012); only
    admin's direct-approve branch may act past this point."""


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


ERROR_HTTP_STATUS: dict[str, int] = {
    "not_filler_of_department": 403,
    "admin_cannot_submit_in_cycle": 403,
    "mid_chain_admin_overwrite": 409,
    "past_deadline": 403,
    "invalid_approval_state": 409,
    "approval_record_not_found": 404,
    "not_current_approver": 403,
    "not_authorized_to_view_department": 403,
    "missing_reject_reason": 400,
    "concurrent_approval": 409,
}

ERROR_CODE_BY_EXCEPTION: dict[type[Exception], str] = {
    NotFillerOfDepartmentError: "not_filler_of_department",
    AdminCannotSubmitInCycleError: "admin_cannot_submit_in_cycle",
    MidChainAdminOverwriteError: "mid_chain_admin_overwrite",
    PastDeadlineError: "past_deadline",
    InvalidApprovalStateError: "invalid_approval_state",
    ApprovalRecordNotFoundError: "approval_record_not_found",
    NotCurrentApproverError: "not_current_approver",
    NotAuthorizedToViewDepartmentError: "not_authorized_to_view_department",
    MissingReasonError: "missing_reject_reason",
    ConcurrentApprovalError: "concurrent_approval",
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
    can_act: bool = False  # True when the caller's own empcode IS current_approver_empcode


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


def _department_cost_centers(conn: pyodbc.Connection, department: str) -> set[str]:
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT DISTINCT cost_center FROM dbo.cc_filler_map WHERE department = ?", department)
        rows = cursor.fetchall()
    finally:
        cursor.close()
    return {r[0] for r in rows}


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


_BANGKOK_TZ = ZoneInfo("Asia/Bangkok")


def _bangkok_today() -> date:
    """S1 gate fix: anchor the deadline comparison to Asia/Bangkok explicitly
    instead of the server-local `date.today()` — a server running in a
    different timezone (e.g. UTC) would flip the post-deadline boundary by
    hours. Deliberately separate from `_now()` (kept UTC — used only for
    timestamp columns, never the deadline gate) so the two clocks are never
    conflated."""
    return datetime.now(_BANGKOK_TZ).date()


def _is_post_deadline(conn: pyodbc.Connection, fiscal_year: int) -> bool:
    """No `dbo.submission_deadline` row for this fiscal_year -> treat as OPEN
    (never silently lock a year nobody configured a cutoff for). Inclusive of
    the deadline day itself — only the day AFTER `deadline_date` counts as
    post-deadline (unchanged semantics; S1 only changed which clock decides
    "today")."""
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT deadline_date FROM dbo.submission_deadline WHERE fiscal_year = ?", fiscal_year)
        row = cursor.fetchone()
    finally:
        cursor.close()
    if row is None:
        return False
    return _bangkok_today() > row[0]


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


def authorize_status_view(conn: pyodbc.Connection, department: str, scope: Scope) -> None:
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

def _ensure_admin_overwrite_allowed(existing: dict | None, department: str, fiscal_year: int) -> None:
    """B2 gate fix — fail-closed guard shared by the ADMIN_SUBMIT
    (Template-2 door) and orphan-department branches: neither may silently
    overwrite a record that is already mid-chain (PENDING_APPROVER1/2/3) or
    already APPROVED. This is the DEFAULT policy until jakkaritw confirms
    whether admin should be allowed to override mid-chain in all cases —
    kept as one small shared guard so flipping that policy later means
    deleting this function's call sites, not restructuring
    `submit_department`. The post-deadline branch never calls this —
    ADR-0012's confirmed policy lets it override ANY existing status."""
    if existing is not None and existing["status"] in PENDING_STATUSES | {APPROVED}:
        raise MidChainAdminOverwriteError(
            f"{department}/{fiscal_year} is {existing['status']} — mid-approval; admin cannot "
            "admin-submit until it is rejected or the submission deadline has passed"
        )


def submit_department(
    conn: pyodbc.Connection, department: str, fiscal_year: int, submitter_email: str, scope: Scope
) -> ApprovalStatusState:
    """Submit `(department, fiscal_year)`.

    Branch selection: a caller who Fills >=1 cost center of this department
    ALWAYS goes through the normal chain, regardless of `scope.is_admin` —
    this is what keeps Nipaporn/Waraporn's dual role correct (they Fill 5
    departments themselves and must go through self-skip/dedup like anyone
    else, per ADR-0006's own worked examples). Only a caller who does NOT
    Fill this department at all can hit the admin direct-approve branch, and
    only if they are admin (ADR-0012).

    B2 gate fix: the ADMIN_SUBMIT and orphan branches are fail-closed —
    `_ensure_admin_overwrite_allowed` blocks them from overwriting a
    mid-chain/APPROVED record. The post-deadline branch is exempt (ADR-0012:
    admin may override ANY status once the cycle has closed)."""
    existing = _fetch_row(conn, department, fiscal_year)
    dept_ccs = _department_cost_centers(conn, department)
    is_filler = bool(dept_ccs & set(scope.fill_cost_centers))
    now = _now()

    if is_filler:
        return _submit_normal_chain(conn, department, fiscal_year, submitter_email, existing, now)

    if not scope.is_admin:
        raise NotFillerOfDepartmentError(f"{submitter_email} does not Fill any cost center of {department!r}")

    if _department_has_admin_template_rows(conn, department, fiscal_year):
        _ensure_admin_overwrite_allowed(existing, department, fiscal_year)
        return _admin_direct_approve(conn, department, fiscal_year, submitter_email, existing, now, ACTION_ADMIN_SUBMIT)

    is_orphan = not dept_ccs  # reuse the already-fetched set — no extra query
    if is_orphan:
        _ensure_admin_overwrite_allowed(existing, department, fiscal_year)
        return _admin_direct_approve(
            conn, department, fiscal_year, submitter_email, existing, now, ACTION_ADMIN_OVERRIDE_ORPHAN
        )

    if _is_post_deadline(conn, fiscal_year):
        return _admin_direct_approve(
            conn, department, fiscal_year, submitter_email, existing, now, ACTION_ADMIN_OVERRIDE_DEADLINE
        )

    raise AdminCannotSubmitInCycleError(
        f"admin cannot submit {department!r} while the cycle is open unless it is orphan "
        "or was entered via the Template-2 (ADMIN) door"
    )


def _submit_normal_chain(
    conn: pyodbc.Connection, department: str, fiscal_year: int, submitter_email: str, existing: dict | None, now: datetime,
) -> ApprovalStatusState:
    if existing is not None and existing["status"] != REJECTED:
        raise InvalidApprovalStateError(
            f"{department}/{fiscal_year} is {existing['status']} — cannot submit "
            "(PENDING_* has no recall; APPROVED needs no re-submission, ADR-0013)"
        )
    if _is_post_deadline(conn, fiscal_year):
        raise PastDeadlineError(f"the submission deadline for fiscal_year={fiscal_year} has passed")

    submitter_empcode, approver1_empcode, active = resolve_chain(conn, submitter_email)
    first_status = _POSITION_TO_STATUS[active[0]]
    action = ACTION_RESUBMIT if existing is not None else ACTION_SUBMIT

    cursor = conn.cursor()
    try:
        if existing is None:
            try:
                cursor.execute(
                    """
                    INSERT INTO budget.approval_status
                        (department, fiscal_year, status, submitter_empcode, submitter_email, submitted_at,
                         approver1_empcode, _updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    department, fiscal_year, first_status, submitter_empcode, submitter_email, now,
                    approver1_empcode, now,
                )
            except pyodbc.IntegrityError as exc:
                # S2 gate fix: two concurrent first-time submits for the same
                # (department, fiscal_year) race the PK — the loser used to
                # escape as an uncaught pyodbc error (-> generic 502). The PK
                # already kept the data safe (never-cut); this only fixes the
                # error semantics to match the same 409 the conditional
                # UPDATE path below returns.
                raise ConcurrentApprovalError(
                    f"{department}/{fiscal_year} was submitted concurrently by another request"
                ) from exc
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
            cursor.execute(
                """
                INSERT INTO budget.approval_status
                    (department, fiscal_year, status, submitter_empcode, submitter_email, submitted_at, _updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                department, fiscal_year, APPROVED, admin_empcode, admin_email, now, now,
            )
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
        _append_log(conn, department, fiscal_year, ACTION_APPROVE, approver_empcode, approver_email,
                    row["status"], new_status, comment, now)
        conn.commit()
    finally:
        cursor.close()

    new_row = dict(row)
    new_row["status"] = new_status
    new_row[actioned_col] = now
    new_row["_updated_at"] = now
    return _to_state(new_row, department, fiscal_year, caller_empcode=approver_empcode)


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
