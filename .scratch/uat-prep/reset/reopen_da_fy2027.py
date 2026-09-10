"""Re-open Data & Analytic FY2027 for editing WITHOUT wiping the budget.

jakkaritw asked (2026-09-10) to clear the terminal `Approved` status so the
department is fillable again, keeping the 415,900.00 THB of budget rows in place.
Deleting the single budget.approval_status row (department|fiscal_year) does exactly
that: the app has no APPROVED row to read, so approval.get_approval_status()
synthesizes DRAFT from the absence, the grid unlocks and the Submit button returns.
pending_budget / pending_budget_detail / budget_trip are NOT touched.

Two-phase for safety:
    python -X utf8 reopen_da_fy2027.py            # dry-run: SELECT + show, no write
    python -X utf8 reopen_da_fy2027.py --apply     # delete the ONE status row (guard = 1)

The row is written to a JSON baseline before the delete; the delete runs in one
transaction and commits only if exactly one approval_status row is removed and the
budget-row count is unchanged. Any mismatch -> rollback.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import sys
from decimal import Decimal
from pathlib import Path

import pyodbc
from dotenv import load_dotenv

load_dotenv(r"C:\04.budget_management_web\.env")

# Production budget DB — the value in .env is the retired DB, so pin it here.
SERVER = "v5o4qez3u4cupase7cogkwvyke-bby6xlm3ncqexly4ozejod2vqe.database.fabric.microsoft.com,1433"
DB = "fabric_sql_database-a42ef9f3-f190-464a-8d5e-c0d41ef9ce42"

DEPT = "Data & Analytic"
FY = 2027
OUT_DIR = Path(r"C:\04.budget_management_web\.scratch\uat-prep\reset\out")
OUT_DIR.mkdir(parents=True, exist_ok=True)


def _json_default(o):
    if isinstance(o, Decimal):
        return str(o)
    if isinstance(o, (dt.datetime, dt.date)):
        return o.isoformat()
    return str(o)


def _rows(cur, sql, *params):
    cur.execute(sql, *params)
    cols = [c[0] for c in cur.description]
    return [dict(zip(cols, r)) for r in cur.fetchall()]


def main() -> int:
    apply = "--apply" in sys.argv
    conn = pyodbc.connect(
        f"DRIVER={{ODBC Driver 17 for SQL Server}};SERVER={SERVER};DATABASE={DB};"
        "Authentication=ActiveDirectoryServicePrincipal;"
        f"UID={os.getenv('ENTRA_CLIENT_ID')};PWD={os.getenv('ENTRA_CLIENT_SECRET')};"
        "Encrypt=yes;TrustServerCertificate=no;",
        timeout=90,
        autocommit=False,
    )
    cur = conn.cursor()

    status_rows = _rows(cur, "SELECT * FROM budget.approval_status WHERE department=? AND fiscal_year=?", DEPT, FY)
    budget_rows = _rows(cur,
        "SELECT cost_center, gl_account, total_year FROM budget.pending_budget WHERE fiscal_year=? "
        "AND cost_center IN (SELECT cost_center FROM budget.pending_budget WHERE fiscal_year=?)", FY, FY)
    # scope the budget count to D&A's cost centers only (10IT013000 + any sibling that carries D&A rows)
    da_budget = _rows(cur,
        "SELECT cost_center, COUNT(*) AS n, SUM(total_year) AS total FROM budget.pending_budget "
        "WHERE fiscal_year=? AND cost_center LIKE '10IT013%' GROUP BY cost_center", FY)

    print(f"target: department='{DEPT}'  fiscal_year={FY}")
    print("approval_status rows found:", len(status_rows))
    for r in status_rows:
        print("   ", {k: r[k] for k in r if k in ("department", "fiscal_year", "status", "current_step", "updated_at", "updated_by")})
    print("D&A pending_budget (kept, NOT deleted):", da_budget)

    if len(status_rows) != 1:
        print(f"ABORT: expected exactly 1 approval_status row, found {len(status_rows)}. Nothing changed.")
        return 1
    cur_status = str(status_rows[0].get("status", ""))
    print("current status =", cur_status)

    if not apply:
        print("\nDRY-RUN only. Re-run with --apply to delete this one approval_status row (budget rows stay).")
        return 0

    stamp = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    out = OUT_DIR / f"baseline_DA_FY2027_approval_status_before_reopen_{stamp}.json"
    out.write_text(json.dumps({"captured_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
                               "database": DB, "scope": {"department": DEPT, "fiscal_year": FY},
                               "approval_status": status_rows, "da_pending_budget_kept": da_budget},
                              ensure_ascii=False, indent=2, default=_json_default), encoding="utf-8")
    print("baseline written:", out)

    budget_before = cur.execute("SELECT COUNT(*) FROM budget.pending_budget WHERE fiscal_year=? AND cost_center LIKE '10IT013%'", FY).fetchone()[0]
    try:
        n = cur.execute("DELETE FROM budget.approval_status WHERE department=? AND fiscal_year=?", DEPT, FY).rowcount
        budget_after = cur.execute("SELECT COUNT(*) FROM budget.pending_budget WHERE fiscal_year=? AND cost_center LIKE '10IT013%'", FY).fetchone()[0]
        print(f"deleted approval_status rows (uncommitted): {n}  | D&A budget rows {budget_before} -> {budget_after}")
        if n != 1 or budget_after != budget_before:
            conn.rollback()
            print("ROLLBACK: guard failed (status delete != 1 or budget count changed). Nothing changed.")
            return 1
        conn.commit()
        print("COMMITTED — Data & Analytic FY2027 is now DRAFT (fillable), budget kept.")
    except Exception as exc:  # noqa: BLE001
        conn.rollback()
        print("ROLLBACK on error:", exc)
        return 1

    after = _rows(cur, "SELECT * FROM budget.approval_status WHERE department=? AND fiscal_year=?", DEPT, FY)
    print("approval_status rows after:", len(after), "(0 = DRAFT synthesized)")
    print("approval_log kept:", cur.execute("SELECT COUNT(*) FROM budget.approval_log WHERE department=? AND fiscal_year=?", DEPT, FY).fetchone()[0])
    return 0


if __name__ == "__main__":
    sys.exit(main())
