"""GET /scope — resolves the caller's RLS Fill/See cost-center scope (ADR-0019, A3)."""
import logging

import pyodbc
from fastapi import APIRouter, Depends, HTTPException, Query

from app.auth import get_current_user_email
from app.db import get_fabric_conn
from app.rls import Scope, resolve_scope

logger = logging.getLogger(__name__)
router = APIRouter()

_DB_UNAVAILABLE_DETAIL = "Database unavailable, please try again later"


@router.get("/scope", response_model=Scope)
def scope(
    admin_view_enabled: bool = Query(default=False),
    email: str = Depends(get_current_user_email),
) -> Scope:
    try:
        # Connection-open inside the try: an open-time failure (driver
        # pyodbc.Error, or msal token failure — DbConnectionError, a
        # pyodbc.Error subclass) → 502, same as a query-time failure.
        with get_fabric_conn() as conn:
            return resolve_scope(email, conn, admin_view_enabled=admin_view_enabled)
    except pyodbc.Error as exc:
        logger.exception("resolve_scope failed for %s", email)
        raise HTTPException(status_code=502, detail=_DB_UNAVAILABLE_DETAIL) from exc
