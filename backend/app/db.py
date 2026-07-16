"""Fabric SQL connection factories — two stores (ADR-0023):

1. `get_fabric_conn()` — the ONE Fabric SQL Database `fabric_sql_database`,
   both schemas (`budget.*` transactional + `dbo.*` masters/employee) live
   behind this single connection.
2. `get_gold_conn()`   — the SAP gold warehouse, read-only, a separate store
   (query contract belongs to A4 — this module only opens the connection).

Auth = Service Principal `cman-fabric-write`, ODBC Driver 17. The token is
acquired in Python via msal (client-credentials flow) and injected into the
ODBC connection through the SQL_COPT_SS_ACCESS_TOKEN attribute, instead of
letting the driver do its own `Authentication=ActiveDirectoryServicePrincipal`
flow. Why: in the production Linux container (python:3.12-slim-bookworm +
msodbcsql17), the driver's internal AAD token acquisition stalls ~20s (both
driver 17 and 18), exceeding pyodbc's default 15s login timeout (`HYT00
Login timeout expired`) even though TCP/TDS/TLS to the Fabric gateway is
sub-second. msal's own call to login.microsoftonline.com takes ~0.12s from
the same environment and caches the token, so this path is fast on every
call after the first.

The app filters rows in code (app-layer RLS, ADR-0019); this is the shared
SP connection, not a per-user one. Connections are opened lazily on use,
never at import time, and always closed via the context manager.
"""
import logging
import struct
from collections.abc import Iterator
from contextlib import contextmanager

import msal
import pyodbc

from app.config import Settings, get_settings

logger = logging.getLogger(__name__)


class DbConnectionError(pyodbc.Error, RuntimeError):
    """Connection-OPEN failure: msal token acquisition failed before
    pyodbc.connect was ever attempted.

    Deliberately subclasses BOTH parents:

    - ``pyodbc.Error`` — every DB-backed router already maps pyodbc.Error to
      HTTP 502 with a generic detail, so an open-time token failure follows
      the same "Fabric failure -> 502, never 500, never leak" contract as a
      query-time driver error, with no per-router special-casing.
    - ``RuntimeError`` — the pre-existing open-failure surface (health.py's
      deep check, jobs, scripts caught RuntimeError) stays valid unchanged.

    Raw RuntimeError must NOT be mapped to 502 by routers: this codebase uses
    RuntimeError subclasses as business errors (ConcurrentApprovalError -> 409,
    MissingFxRateError -> 500, ...), so the open failure gets its own type.
    """


_ODBC_DRIVER = "ODBC Driver 17 for SQL Server"

# ODBC connection attribute for injecting a pre-acquired AAD access token
# (SQL_COPT_SS_ACCESS_TOKEN, msodbcsql.h) — bypasses the driver's own slow
# Authentication= flow entirely (see module docstring for why).
_SQL_COPT_SS_ACCESS_TOKEN = 1256

# TDS resource scope — the same audience for both the Fabric SQL Database
# (.database.fabric.microsoft.com) and the gold warehouse SQL endpoint
# (.datawarehouse.fabric.microsoft.com); both are SQL Server-protocol targets.
_TOKEN_SCOPE = "https://database.windows.net/.default"

# Safety net, not the fix — the real fix is bypassing the driver's slow
# internal AAD flow above.
_CONNECT_TIMEOUT_SECONDS = 30

# One ConfidentialClientApplication per (tenant_id, client_id), kept for the
# process lifetime. msal's own token cache lives inside the instance, so
# reusing it (rather than rebuilding on every connection) is what keeps
# repeat token acquisitions fast. Keyed by tenant too, not just client_id,
# so a client_id reused across tenants can never reuse the wrong tenant's
# cached app/token.
_msal_apps: dict[tuple[str, str], msal.ConfidentialClientApplication] = {}


def _get_msal_app(tenant_id: str, client_id: str, client_secret: str) -> msal.ConfidentialClientApplication:
    cache_key = (tenant_id, client_id)
    app = _msal_apps.get(cache_key)
    if app is None:
        app = msal.ConfidentialClientApplication(
            client_id,
            authority=f"https://login.microsoftonline.com/{tenant_id}",
            client_credential=client_secret,
        )
        _msal_apps[cache_key] = app
    return app


def _acquire_access_token(tenant_id: str, client_id: str, client_secret: str) -> str:
    app = _get_msal_app(tenant_id, client_id, client_secret)
    result = app.acquire_token_for_client(scopes=[_TOKEN_SCOPE])
    token = result.get("access_token")
    if not token:
        raise DbConnectionError(
            f"msal token acquisition failed: {result.get('error')} - {result.get('error_description')}"
        )
    return token


def _pack_access_token(token: str) -> bytes:
    """Pack per the ODBC SQL_COPT_SS_ACCESS_TOKEN spec: a 4-byte
    little-endian length prefix followed by the token as UTF-16-LE bytes."""
    raw = token.encode("utf-16-le")
    return struct.pack("<i", len(raw)) + raw


def _build_conn_string(server: str, database: str) -> str:
    return (
        f"DRIVER={{{_ODBC_DRIVER}}};"
        f"SERVER={server};"
        f"DATABASE={database};"
        "Encrypt=yes;TrustServerCertificate=no;"
    )


def _connect(server: str, database: str, settings: Settings) -> pyodbc.Connection:
    token = _acquire_access_token(settings.entra_tenant_id, settings.entra_client_id, settings.entra_client_secret)
    conn_str = _build_conn_string(server, database)
    return pyodbc.connect(
        conn_str,
        attrs_before={_SQL_COPT_SS_ACCESS_TOKEN: _pack_access_token(token)},
        timeout=_CONNECT_TIMEOUT_SECONDS,
    )


@contextmanager
def get_fabric_conn(settings: Settings | None = None) -> Iterator[pyodbc.Connection]:
    """Context-managed connection to the ONE Fabric SQL Database."""
    settings = settings or get_settings()
    conn = _connect(settings.fabric_sql_server, settings.fabric_sql_database, settings)
    try:
        yield conn
    finally:
        conn.close()


@contextmanager
def get_gold_conn(settings: Settings | None = None) -> Iterator[pyodbc.Connection]:
    """Context-managed connection to the SAP gold warehouse (read-only)."""
    settings = settings or get_settings()
    conn = _connect(settings.gold_sql_server, settings.gold_sql_database, settings)
    try:
        yield conn
    finally:
        conn.close()
