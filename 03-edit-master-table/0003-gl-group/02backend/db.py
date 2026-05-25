"""pyodbc connection to Fabric SQL Database.

Identical across all entities in the master-table skill.
"""
import os
import threading
import pyodbc

_local = threading.local()


def _conn_str(driver: str) -> str:
    return (
        f"DRIVER={{{driver}}};"
        f"SERVER={os.environ['FABRIC_SQL_SERVER']};"
        f"DATABASE={os.environ['FABRIC_SQL_DATABASE']};"
        "Authentication=ActiveDirectoryServicePrincipal;"
        f"UID={os.environ['AAD_CLIENT_ID']};"
        f"PWD={os.environ['AAD_CLIENT_SECRET']};"
    )


def get_conn() -> pyodbc.Connection:
    """Return a per-thread connection. Each request thread gets its own
    connection so concurrent requests don't collide (avoids 'busy' error)."""
    conn = getattr(_local, "conn", None)
    if conn is None:
        for driver in ("ODBC Driver 18 for SQL Server", "ODBC Driver 17 for SQL Server"):
            if driver in pyodbc.drivers():
                conn = pyodbc.connect(_conn_str(driver), autocommit=False)
                _local.conn = conn
                break
        else:
            raise RuntimeError("No supported ODBC driver found (need 17 or 18)")
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


def exists(table: str, where_clause: str, params: tuple) -> bool:
    row = fetchone(f"SELECT 1 FROM {table} WHERE {where_clause}", params)
    return row is not None


def find_group_id_by_name(group_name: str) -> str | None:
    row = fetchone(
        "SELECT TOP 1 group_id FROM cfg_master.gl_group_dim WHERE group_name = ?",
        (group_name,),
    )
    return row["group_id"] if row else None
