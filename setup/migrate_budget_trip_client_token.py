"""
migrate_budget_trip_client_token.py — one-time schema migration for the
POST /budget/trip idempotency feature (client_token dedup).

Adds to budget.budget_trip on the live Fabric SQL DB:
  1. [client_token] NVARCHAR(64) NULL         (nullable — legacy rows stay untouched)
  2. UNIQUE FILTERED index ux_trip_client_token_user
       ON ([client_token], [_user]) WHERE [client_token] IS NOT NULL
     Dedup key = (client_token, _user) ONLY — never trip content (two
     genuinely-identical trips are legitimate). NULL-token rows unconstrained.

Idempotent + safe:
  - checks INFORMATION_SCHEMA.COLUMNS / sys.indexes before each DDL step —
    re-running is a no-op
  - DRY RUN by default (prints current state + planned DDL, writes nothing);
    pass --apply to execute
  - NEVER run automatically (no CI hook) — jakkaritw approves, then the main
    session runs:  python setup/migrate_budget_trip_client_token.py --apply

Auth: ActiveDirectoryServicePrincipal (silent; same pattern as sync_employees.py).
"""
import sys

import pyodbc

# Reuse the app's OWN connection factory (backend/.env values + msal
# access-token injection) — the SAME path the running app uses. The repo-root
# .env holds STALE/WRONG Fabric coordinates (a different workspace GUID + a
# "fabric sql db" name with spaces) that time out; only backend/.env is correct
# (see memory reference_fabric_sql_connection_formula). Never hand-roll the
# connection string here again.
sys.path.insert(0, r"c:\04.budget_management_web\backend")
from app.config import get_settings  # noqa: E402
from app.db import get_fabric_conn  # noqa: E402

APPLY = "--apply" in sys.argv

TABLE_SCHEMA = "budget"
TABLE_NAME = "budget_trip"
COLUMN_NAME = "client_token"
INDEX_NAME = "ux_trip_client_token_user"

DDL_ADD_COLUMN = (
    f"ALTER TABLE {TABLE_SCHEMA}.{TABLE_NAME} ADD [{COLUMN_NAME}] NVARCHAR(64) NULL"
)
DDL_CREATE_INDEX = (
    f"CREATE UNIQUE INDEX {INDEX_NAME} "
    f"ON {TABLE_SCHEMA}.{TABLE_NAME} ([{COLUMN_NAME}], [_user]) "
    f"WHERE [{COLUMN_NAME}] IS NOT NULL"
)


def column_exists(cursor: pyodbc.Cursor) -> bool:
    cursor.execute(
        "SELECT 1 FROM INFORMATION_SCHEMA.COLUMNS "
        "WHERE TABLE_SCHEMA = ? AND TABLE_NAME = ? AND COLUMN_NAME = ?",
        TABLE_SCHEMA, TABLE_NAME, COLUMN_NAME,
    )
    return cursor.fetchone() is not None


def index_exists(cursor: pyodbc.Cursor) -> bool:
    cursor.execute(
        "SELECT 1 FROM sys.indexes "
        "WHERE name = ? AND object_id = OBJECT_ID(?)",
        INDEX_NAME, f"{TABLE_SCHEMA}.{TABLE_NAME}",
    )
    return cursor.fetchone() is not None


def print_state(label: str, has_column: bool, has_index: bool) -> None:
    print(f"[{label}] {TABLE_SCHEMA}.{TABLE_NAME}.{COLUMN_NAME} column: "
          f"{'EXISTS' if has_column else 'missing'}")
    print(f"[{label}] {INDEX_NAME} unique filtered index:            "
          f"{'EXISTS' if has_index else 'missing'}")


def main() -> None:
    print(f"Mode: {'APPLY (writes DDL)' if APPLY else 'DRY RUN (no writes; pass --apply to execute)'}")
    _s = get_settings()
    print(f"Target: {_s.fabric_sql_server} / {_s.fabric_sql_database} (via app.db.get_fabric_conn)")

    with get_fabric_conn() as conn:
        cursor = conn.cursor()
        try:
            has_column = column_exists(cursor)
            has_index = index_exists(cursor)
            print_state("before", has_column, has_index)

            if has_column and has_index:
                print("Nothing to do — migration already applied.")
                return

            if not has_column:
                print(f"Planned DDL 1: {DDL_ADD_COLUMN}")
            if not has_index:
                print(f"Planned DDL 2: {DDL_CREATE_INDEX}")

            if not APPLY:
                print("DRY RUN — no DDL executed.")
                return

            if not has_column:
                cursor.execute(DDL_ADD_COLUMN)
                print("Executed: ADD COLUMN")
            if not has_index:
                cursor.execute(DDL_CREATE_INDEX)
                print("Executed: CREATE UNIQUE INDEX")
            conn.commit()

            print_state("after", column_exists(cursor), index_exists(cursor))
        finally:
            cursor.close()


if __name__ == "__main__":
    main()
