"""GET /scope — resolves the caller's RLS Fill/See cost-center scope (ADR-0019, A3)."""
from fastapi import APIRouter, Depends, Query

from app.auth import get_current_user_email
from app.db import get_fabric_conn
from app.rls import Scope, resolve_scope

router = APIRouter()


@router.get("/scope", response_model=Scope)
def scope(
    admin_view_enabled: bool = Query(default=False),
    email: str = Depends(get_current_user_email),
) -> Scope:
    with get_fabric_conn() as conn:
        return resolve_scope(email, conn, admin_view_enabled=admin_view_enabled)
