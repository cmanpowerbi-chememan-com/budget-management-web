"""Fabric SQL connection factories — two stores (ADR-0023):

1. `get_fabric_conn()` — the ONE Fabric SQL Database `fabric_sql_database`,
   both schemas (`budget.*` transactional + `dbo.*` masters/employee) live
   behind this single connection.
2. `get_gold_conn()`   — the SAP gold warehouse, read-only, a separate store
   (query contract belongs to A4 — this module only opens the connection).

Both use Service Principal auth (`cman-fabric-write`) via ODBC Driver 17 —
see CLAUDE.md "Fabric SQL DB — Local Connection Pattern". The app filters
rows in code (app-layer RLS, ADR-0019); this is the shared SP connection,
not a per-user one. Connections are opened lazily on use, never at import
time, and always closed via the context manager.
"""
import logging
from collections.abc import Iterator
from contextlib import contextmanager

import pyodbc

from app.config import Settings, get_settings

logger = logging.getLogger(__name__)

_ODBC_DRIVER = "ODBC Driver 17 for SQL Server"


def _build_conn_string(server: str, database: str, client_id: str, client_secret: str) -> str:
    return (
        f"DRIVER={{{_ODBC_DRIVER}}};"
        f"SERVER={server};"
        f"DATABASE={database};"
        "Authentication=ActiveDirectoryServicePrincipal;"
        f"UID={client_id};"
        f"PWD={client_secret};"
        "Encrypt=yes;TrustServerCertificate=no;"
    )


@contextmanager
def get_fabric_conn(settings: Settings | None = None) -> Iterator[pyodbc.Connection]:
    """Context-managed connection to the ONE Fabric SQL Database."""
    settings = settings or get_settings()
    conn_str = _build_conn_string(
        settings.fabric_sql_server,
        settings.fabric_sql_database,
        settings.entra_client_id,
        settings.entra_client_secret,
    )
    conn = pyodbc.connect(conn_str)
    try:
        yield conn
    finally:
        conn.close()


@contextmanager
def get_gold_conn(settings: Settings | None = None) -> Iterator[pyodbc.Connection]:
    """Context-managed connection to the SAP gold warehouse (read-only)."""
    settings = settings or get_settings()
    conn_str = _build_conn_string(
        settings.gold_sql_server,
        settings.gold_sql_database,
        settings.entra_client_id,
        settings.entra_client_secret,
    )
    conn = pyodbc.connect(conn_str)
    try:
        yield conn
    finally:
        conn.close()
