"""
migrate_budget_trip_project.py — one-time schema migration for the trip
`project` field (Excel template col F, free text on the trip header).

Adds to budget.budget_trip on the live Fabric SQL DB:
  1. [project] NVARCHAR(200) NULL   (nullable — legacy rows stay untouched)

Idempotent + safe:
  - checks INFORMATION_SCHEMA.COLUMNS before the DDL step — re-running is
    a no-op
  - DRY RUN by default (prints current state + planned DDL, writes nothing);
    pass --apply to execute
  - NEVER run automatically (no CI hook) — jakkaritw approves, then the main
    session runs:  python setup/migrate_budget_trip_project.py --apply

⚠ Deploy ordering: the write path is deploy-safe pre-migration (the column is
referenced ONLY when a non-null project is sent), but `subform_read.fetch_trips`
SELECTs the column unconditionally — run this migration BEFORE deploying the
backend that carries it, or every GET /budget/trip returns 502.

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
COLUMN_NAME = "project"

DDL_ADD_COLUMN = (
    f"ALTER TABLE {TABLE_SCHEMA}.{TABLE_NAME} ADD [{COLUMN_NAME}] NVARCHAR(200) NULL"
)


def column_exists(cursor: pyodbc.Cursor) -> bool:
    cursor.execute(
        "SELECT 1 FROM INFORMATION_SCHEMA.COLUMNS "
        "WHERE TABLE_SCHEMA = ? AND TABLE_NAME = ? AND COLUMN_NAME = ?",
        TABLE_SCHEMA, TABLE_NAME, COLUMN_NAME,
    )
    return cursor.fetchone() is not None


def print_state(label: str, has_column: bool) -> None:
    print(f"[{label}] {TABLE_SCHEMA}.{TABLE_NAME}.{COLUMN_NAME} column: "
          f"{'EXISTS' if has_column else 'missing'}")


def main() -> None:
    print(f"Mode: {'APPLY (writes DDL)' if APPLY else 'DRY RUN (no writes; pass --apply to execute)'}")
    _s = get_settings()
    print(f"Target: {_s.fabric_sql_server} / {_s.fabric_sql_database} (via app.db.get_fabric_conn)")

    with get_fabric_conn() as conn:
        cursor = conn.cursor()
        try:
            has_column = column_exists(cursor)
            print_state("before", has_column)

            if has_column:
                print("Nothing to do — migration already applied.")
                return

            print(f"Planned DDL 1: {DDL_ADD_COLUMN}")

            if not APPLY:
                print("DRY RUN — no DDL executed.")
                return

            cursor.execute(DDL_ADD_COLUMN)
            print("Executed: ADD COLUMN")
            conn.commit()

            print_state("after", column_exists(cursor))
        finally:
            cursor.close()


if __name__ == "__main__":
    main()
