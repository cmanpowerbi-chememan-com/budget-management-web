"""RLS scope resolution — Fill/See cost centers + role (ADR-0019).

Fill = every Cost Center where the caller's email is listed as a Filler in
`dbo.cc_filler_map`. See = Fill union the Cost Centers of Fillers whose
Primary-row manager (denormalized `manager_email` on `dbo.v_employee_budget_01`)
is the caller. Both tables live in the same Fabric SQL Database — one
in-DB JOIN, no cross-store query. This module does NO budget read/write and
NO approval — those are A4-A6.
"""
from typing import Literal

import pyodbc
from pydantic import BaseModel

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

    see_cost_centers = fill_cost_centers | manager_add

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
