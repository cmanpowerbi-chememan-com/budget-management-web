"""Delete every budget row for the two "other travel expense" GLs.

Context: 5210400999 / 6210400999 were reclassified out of the `Travelling Expense`
special group into `Other manpower exp (Per diem,Health check,Uniform...etc)` — they are
ordinary monthly grid cells now, so any value entered through the old trip subform is
discarded rather than migrated (jakkaritw, 2026-09-04).

Mirrors the app's own delete contract (`write_model._delete_one_detail_line` +
`_delete_parent_if_orphaned`): drop the detail lines first, then drop the parent row ONLY
when it is genuine residue — no remaining detail line, `total_year = 0`, `remark IS NULL`.
A parent that still carries an amount or a user-authored remark is REPORTED, never deleted.

    python -X utf8 setup/wipe_other_travel_gl_rows.py            # dry run, writes nothing
    python -X utf8 setup/wipe_other_travel_gl_rows.py --apply    # actually deletes
"""
import os
import sys
from pathlib import Path

import pyodbc
from dotenv import load_dotenv

GLS = ("5210400999", "6210400999")


def connect() -> pyodbc.Connection:
    # Resolve relative to THIS file, never the caller's cwd — a relative "backend/.env"
    # silently loads nothing when run from another directory, and pyodbc then falls
    # back to Named Pipes with an empty SERVER (error 08001/53).
    load_dotenv(Path(__file__).resolve().parent.parent / "backend" / ".env")
    return pyodbc.connect(
        f"DRIVER={{ODBC Driver 17 for SQL Server}};"
        f"SERVER={os.getenv('FABRIC_SQL_SERVER')};"
        f"DATABASE={os.getenv('FABRIC_SQL_DATABASE')};"
        "Authentication=ActiveDirectoryServicePrincipal;"
        f"UID={os.getenv('ENTRA_CLIENT_ID')};"
        f"PWD={os.getenv('ENTRA_CLIENT_SECRET')};"
        "Encrypt=yes;TrustServerCertificate=no;Connection Timeout=60;"
    )


def survey(cur: pyodbc.Cursor) -> tuple[list, list]:
    cur.execute(
        "SELECT detail_id, cost_center, gl_account, fiscal_year, trip_id, line_label "
        "FROM budget.pending_budget_detail WHERE gl_account IN (?,?) "
        "ORDER BY fiscal_year, cost_center, detail_id",
        *GLS,
    )
    details = cur.fetchall()
    cur.execute(
        "SELECT cost_center, gl_account, fiscal_year, total_year, remark, department "
        "FROM budget.pending_budget WHERE gl_account IN (?,?) "
        "ORDER BY fiscal_year, cost_center",
        *GLS,
    )
    return details, cur.fetchall()


def main() -> int:
    apply = "--apply" in sys.argv
    conn = connect()
    cur = conn.cursor()

    details, parents = survey(cur)
    print(f"detail lines : {len(details)}")
    for d in details:
        print(f"  detail_id={d[0]} {d[1]} {d[2]} FY{d[3]} trip_id={d[4]} label={d[5]!r}")
    print(f"parent rows  : {len(parents)}")
    for p in parents:
        print(f"  {p[0]} {p[1]} FY{p[2]} total_year={p[3]} remark={p[4]!r} dept={p[5]!r}")

    # A parent carrying money or a remark is NOT residue — the app would keep it, so do we.
    keepers = [p for p in parents if (p[3] or 0) != 0 or p[4] is not None]
    if keepers:
        print("\nSTOP: these parent rows are not residue (non-zero total or user remark).")
        for p in keepers:
            print(f"  {p[0]} {p[1]} FY{p[2]} total_year={p[3]} remark={p[4]!r}")
        print("Re-confirm with jakkaritw before deleting anything.")
        return 2

    if not apply:
        print("\nDRY RUN — nothing written. Re-run with --apply to delete.")
        return 0

    cur.execute("DELETE FROM budget.pending_budget_detail WHERE gl_account IN (?,?)", *GLS)
    n_details = cur.rowcount
    cur.execute(
        "DELETE FROM budget.pending_budget "
        "WHERE gl_account IN (?,?) AND remark IS NULL AND total_year = 0 "
        "  AND NOT EXISTS ("
        "    SELECT 1 FROM budget.pending_budget_detail d "
        "    WHERE d.cost_center = budget.pending_budget.cost_center "
        "      AND d.gl_account = budget.pending_budget.gl_account "
        "      AND d.fiscal_year = budget.pending_budget.fiscal_year)",
        *GLS,
    )
    n_parents = cur.rowcount
    conn.commit()
    print(f"\ndeleted: {n_details} detail line(s), {n_parents} parent row(s)")

    left_details, left_parents = survey(cur)
    print(f"remaining after delete: {len(left_details)} detail line(s), {len(left_parents)} parent row(s)")
    conn.close()
    return 0 if not left_details and not left_parents else 1


if __name__ == "__main__":
    raise SystemExit(main())
