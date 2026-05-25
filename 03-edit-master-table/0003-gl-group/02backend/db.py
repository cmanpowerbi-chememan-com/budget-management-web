"""pyodbc connections — Fabric SQL Database + Fabric Lakehouse SQL Analytics Endpoint.

Identical across all entities in the master-table skill.
"""
import os
import threading
import pyodbc

_local           = threading.local()
_lakehouse_local = threading.local()

_DRIVERS = ("ODBC Driver 18 for SQL Server", "ODBC Driver 17 for SQL Server")


def _conn_str(server: str, database: str, driver: str) -> str:
    return (
        f"DRIVER={{{driver}}};"
        f"SERVER={server};"
        f"DATABASE={database};"
        "Authentication=ActiveDirectoryServicePrincipal;"
        f"UID={os.environ['AAD_CLIENT_ID']};"
        f"PWD={os.environ['AAD_CLIENT_SECRET']};"
    )


def _open_conn(server: str, database: str) -> pyodbc.Connection:
    for driver in _DRIVERS:
        if driver in pyodbc.drivers():
            return pyodbc.connect(_conn_str(server, database, driver), autocommit=False)
    raise RuntimeError("No supported ODBC driver found (need 17 or 18)")


def get_conn() -> pyodbc.Connection:
    """Per-thread connection to Fabric SQL Database."""
    conn = getattr(_local, "conn", None)
    if conn is None:
        conn = _open_conn(os.environ['FABRIC_SQL_SERVER'], os.environ['FABRIC_SQL_DATABASE'])
        _local.conn = conn
    return conn


def get_lakehouse_conn() -> pyodbc.Connection:
    """Per-thread connection to Fabric Lakehouse SQL Analytics Endpoint."""
    conn = getattr(_lakehouse_local, "conn", None)
    if conn is None:
        conn = _open_conn(os.environ['FABRIC_LAKEHOUSE_SERVER'], os.environ['FABRIC_LAKEHOUSE_DATABASE'])
        _lakehouse_local.conn = conn
    return conn


def execute(sql: str, params: tuple = ()) -> None:
    conn = get_conn()
    conn.cursor().execute(sql, params)
    conn.commit()


def fetchone(sql: str, params: tuple = ()) -> dict | None:
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute(sql, params)
    row = cursor.fetchone()
    if row is None:
        return None
    cols = [d[0] for d in cursor.description]
    return dict(zip(cols, row))


def fetchall(sql: str, params: tuple = ()) -> list[dict]:
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute(sql, params)
    cols = [d[0] for d in cursor.description]
    return [dict(zip(cols, row)) for row in cursor.fetchall()]


def fetchall_lakehouse(sql: str, params: tuple = ()) -> list[dict]:
    conn = get_lakehouse_conn()
    cursor = conn.cursor()
    cursor.execute(sql, params)
    cols = [d[0] for d in cursor.description]
    return [dict(zip(cols, row)) for row in cursor.fetchall()]


def exists(table: str, where_clause: str, params: tuple) -> bool:
    row = fetchone(f"SELECT 1 FROM {table} WHERE {where_clause}", params)
    return row is not None


def find_group_id_by_name(group_name: str) -> str | None:
    row = fetchone(
        "SELECT TOP 1 group_id FROM cfg_master.gl_group_dim WHERE group_name = ?",
        (group_name,),
    )
    return row["group_id"] if row else None
