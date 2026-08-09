"""RLS scope resolution — Fill/See cost centers + role (ADR-0019).

Fill = every Cost Center where the caller's email is listed as a Filler in
`dbo.cc_filler_map`. See = Fill UNION the Cost Centers of Fillers whose
Primary-row manager (denormalized `manager_email` on `dbo.v_employee_budget_01`)
is the caller, UNION the "approver see-overlay" (ADR-0029, jakkaritw decision
ก, 2026-08-08): the Cost Centers of any department currently PENDING on the
caller as its CURRENT approver, for ANY fiscal_year. The overlay exists
because the two FIXED step-2/3 approvers (Nipaporn/Waraporn, ADR-0006) are
not in anyone's manager chain — without it, a department pending on THEM is
invisible in their own DeptPicker and they can never reach the Approve
button. See `_pending_approval_overlay` below for the detail; it is See-only,
never Fill (ADR-0013's read-only lock already renders those rows locked).
Both `dbo.cc_filler_map` and `dbo.v_employee_budget_01` live in the same
Fabric SQL Database as `budget.approval_status` — every query here is a
single in-DB read, no cross-store query. This module performs NO budget
write and NO approval ACTION (submit/approve/reject remain A6-only in
`app.approval`) — it only READS `budget.approval_status` (via `app.approval`'s
shared helpers) to compute the overlay.
"""
from typing import Literal

import pyodbc
from pydantic import BaseModel

from app.approval import (
    cost_centers_for_departments,
    departments_pending_for_empcode,
    resolve_submitter,
)
from app.config import Settings, get_settings

Role = Literal["admin", "filler", "see_only", "none"]

_FILL_SQL = """
    SELECT DISTINCT cost_center
    FROM dbo.cc_filler_map
    WHERE LOWER(filler_email) = LOWER(?)
"""

_MANAGER_SEE_ADD_SQL = """
    SELECT DISTINCT f.cost_center
    FROM dbo.cc_filler_map f
    JOIN dbo.v_employee_budget_01 e ON LOWER(e.email) = LOWER(f.filler_email)
    WHERE LOWER(e.manager_email) = LOWER(?)
"""


class Scope(BaseModel):
    """A resolved user's RLS scope, returned by GET /scope."""

    email: str
    is_admin: bool
    role: Role
    fill_cost_centers: list[str]
    see_cost_centers: list[str]


def _pending_approval_overlay(conn: pyodbc.Connection, email: str) -> set[str]:
    """ADR-0029 approver see-overlay: live Cost Centers of every department
    currently PENDING on `email` as its CURRENT approver, across ANY
    fiscal_year. See-only, by construction — this is unioned into
    `see_cost_centers` alone (never `fill_cost_centers`) by the caller below;
    an approver reviews a department, they never gain write access to it
    (ADR-0013's read-only lock already renders those rows locked, with the
    "🔒 ดูรายละเอียด" affordance).

    Lifetime is deliberately minimal: this is recomputed fresh on every
    `resolve_scope` call from `budget.approval_status`'s CURRENT state,
    nothing is cached or remembered. The moment the department leaves a
    PENDING_* status (this caller approves it, someone else rejects it, ...),
    it drops out of the overlay on the very next call.

    Graceful no-ops (both proven by construction, not by a special case):
    - A caller with no `dbo.v_employee_budget_01` row (e.g. a pure admin like
      jakkaritw) can never be a frozen approver — `resolve_submitter` returns
      `(None, None)`, short-circuiting to an empty overlay with no
      `budget.approval_status` query at all.
    - A position-1 approver who already sees the department via
      `_MANAGER_SEE_ADD_SQL` (the common case — most departments' step 1 is
      the filler's own manager) gains nothing new: the result here is
      unioned into a `set` by the caller, so a cost_center already present
      is simply a no-op, never a duplicate."""
    caller_empcode, _ = resolve_submitter(conn, email)
    if caller_empcode is None:
        return set()
    pending_departments = departments_pending_for_empcode(conn, caller_empcode)
    if not pending_departments:
        return set()
    return cost_centers_for_departments(conn, pending_departments)


def resolve_scope(
    email: str,
    conn: pyodbc.Connection,
    admin_view_enabled: bool = False,
    settings: Settings | None = None,
) -> Scope:
    """Resolve one user's Fill/See cost-center scope and role.

    `admin_view_enabled` is accepted as a forward-looking hook for A4's read
    path (admin-wide vs personal scope, ADR-0014) — it does not change the
    scope computed here; an admin still gets their own Fill/See.

    A blank/whitespace-only `email` short-circuits to a `role="none"` empty
    scope with no SQL executed — defense-in-depth for the fact that this is
    a public function A4–A6 may call directly (auth.py already 401s on a
    missing caller before this is ever reached in the request path).

    See also picks up the ADR-0029 approver overlay (`_pending_approval_overlay`):
    a caller whose ONLY scope is a department currently pending on them (zero
    Fill, zero personal See-add) still comes out `role="see_only"`, never
    `"none"` — the role check below only tests whether `see_cost_centers` is
    non-empty, and the overlay is unioned into it before that check runs.
    """
    if not email or not email.strip():
        return Scope(
            email=email or "",
            is_admin=False,
            role="none",
            fill_cost_centers=[],
            see_cost_centers=[],
        )

    settings = settings or get_settings()
    is_admin = email.strip().lower() in settings.admin_emails_set

    cursor = conn.cursor()
    try:
        cursor.execute(_FILL_SQL, email)
        fill_cost_centers = {row[0] for row in cursor.fetchall()}

        cursor.execute(_MANAGER_SEE_ADD_SQL, email)
        manager_add = {row[0] for row in cursor.fetchall()}
    finally:
        cursor.close()

    overlay_add = _pending_approval_overlay(conn, email)
    see_cost_centers = fill_cost_centers | manager_add | overlay_add

    if is_admin:
        role: Role = "admin"
    elif fill_cost_centers:
        role = "filler"
    elif see_cost_centers:
        role = "see_only"
    else:
        role = "none"

    return Scope(
        email=email,
        is_admin=is_admin,
        role=role,
        fill_cost_centers=sorted(fill_cost_centers),
        see_cost_centers=sorted(see_cost_centers),
    )
