"""GET /health — liveness + optional deep DB check.

`?deep=1` attempts a `SELECT 1` on the Fabric SQL connection and reports
ok/fail/not_configured. Never leaks connection details or secrets — only a
status word.
"""
import logging

import pyodbc
from fastapi import APIRouter, Depends, Query

from app.config import Settings, get_settings
from app.db import get_fabric_conn

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/health")
def health(
    deep: bool = Query(default=False),
    settings: Settings = Depends(get_settings),
) -> dict:
    if not deep:
        return {"status": "ok"}

    if not settings.fabric_sql_server or not settings.fabric_sql_database:
        return {"status": "ok", "db": "not_configured"}

    try:
        with get_fabric_conn(settings) as conn:
            conn.cursor().execute("SELECT 1").fetchone()
        db_status = "ok"
    except pyodbc.Error:
        logger.exception("Deep health check: Fabric SQL connection failed")
        db_status = "fail"
    except RuntimeError:
        # Raised by app.db._acquire_access_token on msal token failure —
        # a connection-layer failure just like pyodbc.Error, same degrade.
        logger.exception("Deep health check: Fabric SQL token acquisition failed")
        db_status = "fail"

    return {"status": "ok", "db": db_status}
