"""Clear Data & Analytic FY2027 to a never-submitted state before the AI-driven UAT run.

Approved by jakkaritw on 2026-09-08 after seeing the exact target rows:
  budget.pending_budget         2 rows   (10IT013000 / 6210400010, 6211100110) = 41,040.00 THB
  budget.pending_budget_detail  1 row    (detail_id 231, trip 43)
  budget.budget_trip            1 row    (trip_id 43, China)
  budget.approval_status        1 row    (Data & Analytic / 2027, REJECTED)
  budget.approval_log           KEPT     (history; nothing reads it)

Safety: every target row is written to a JSON baseline file BEFORE any delete;
the deletes run in ONE transaction and commit only if every rowcount equals
the expected count above. Any mismatch -> rollback, nothing changed.
Scope is pinned to cost_center 10IT013000 + fiscal_year 2027 + the one trip id,
so the five other departments holding FY2027 data are never in the predicate.
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

# Production budget DB — the app's own target. The value in .env is the retired DB.
SERVER = "v5o4qez3u4cupase7cogkwvyke-bby6xlm3ncqexly4ozejod2vqe.database.fabric.microsoft.com,1433"
DB = "fabric_sql_database-a42ef9f3-f190-464a-8d5e-c0d41ef9ce42"

DEPT = "Data & Analytic"
CC = "10IT013000"
FY = 2027
TRIP_ID = 43

EXPECTED = {"pending_budget": 2, "pending_budget_detail": 1, "budget_trip": 1, "approval_status": 1}

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
    conn = pyodbc.connect(
        f"DRIVER={{ODBC Driver 17 for SQL Server}};SERVER={SERVER};DATABASE={DB};"
        "Authentication=ActiveDirectoryServicePrincipal;"
        f"UID={os.getenv('ENTRA_CLIENT_ID')};PWD={os.getenv('ENTRA_CLIENT_SECRET')};"
        "Encrypt=yes;TrustServerCertificate=no;",
        timeout=90,
        autocommit=False,
    )
    cur = conn.cursor()

    # ---- 1. capture the exact rows about to be deleted ---------------------
    baseline = {
        "captured_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "database": DB,
        "scope": {"department": DEPT, "cost_center": CC, "fiscal_year": FY, "trip_id": TRIP_ID},
        "pending_budget": _rows(cur,
            "SELECT * FROM budget.pending_budget WHERE cost_center=? AND fiscal_year=?", CC, FY),
        "pending_budget_detail": _rows(cur,
            "SELECT * FROM budget.pending_budget_detail WHERE cost_center=? AND fiscal_year=?", CC, FY),
        "budget_trip": _rows(cur,
            "SELECT * FROM budget.budget_trip WHERE trip_id=? AND cost_center=? AND fiscal_year=?", TRIP_ID, CC, FY),
        "approval_status": _rows(cur,
            "SELECT * FROM budget.approval_status WHERE department=? AND fiscal_year=?", DEPT, FY),
    }
    found = {k: len(baseline[k]) for k in EXPECTED}
    print("found before delete:", found)
    if found != EXPECTED:
        print(f"ABORT: found {found} but expected {EXPECTED}. Nothing deleted.")
        return 1

    # sanity: the two budget rows really are the ones approved for deletion
    gls = sorted(r["gl_account"] for r in baseline["pending_budget"])
    total = sum(Decimal(str(r["total_year"])) for r in baseline["pending_budget"])
    print("gl_accounts:", gls, "| total_year sum:", total)
    if gls != ["6210400010", "6211100110"] or total != Decimal("41040.00"):
        print("ABORT: rows differ from the approved target. Nothing deleted.")
        return 1

    stamp = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    out = OUT_DIR / f"baseline_DA_FY2027_before_clear_{stamp}.json"
    out.write_text(json.dumps(baseline, ensure_ascii=False, indent=2, default=_json_default), encoding="utf-8")
    print("baseline written:", out)

    # ---- 2. delete in one transaction, child rows first ---------------------
    try:
        n_detail = cur.execute(
            "DELETE FROM budget.pending_budget_detail WHERE cost_center=? AND fiscal_year=?", CC, FY).rowcount
        n_trip = cur.execute(
            "DELETE FROM budget.budget_trip WHERE trip_id=? AND cost_center=? AND fiscal_year=?", TRIP_ID, CC, FY).rowcount
        n_budget = cur.execute(
            "DELETE FROM budget.pending_budget WHERE cost_center=? AND fiscal_year=?", CC, FY).rowcount
        n_status = cur.execute(
            "DELETE FROM budget.approval_status WHERE department=? AND fiscal_year=?", DEPT, FY).rowcount
        deleted = {"pending_budget": n_budget, "pending_budget_detail": n_detail,
                   "budget_trip": n_trip, "approval_status": n_status}
        print("deleted (uncommitted):", deleted)
        if deleted != EXPECTED:
            conn.rollback()
            print(f"ROLLBACK: deleted {deleted} != expected {EXPECTED}. Nothing changed.")
            return 1
        conn.commit()
        print("COMMITTED.")
    except Exception as exc:  # noqa: BLE001
        conn.rollback()
        print("ROLLBACK on error:", exc)
        return 1

    # ---- 3. verify after -----------------------------------------------------
    after = {
        "pending_budget": cur.execute("SELECT COUNT(*) FROM budget.pending_budget WHERE cost_center=? AND fiscal_year=?", CC, FY).fetchone()[0],
        "pending_budget_detail": cur.execute("SELECT COUNT(*) FROM budget.pending_budget_detail WHERE cost_center=? AND fiscal_year=?", CC, FY).fetchone()[0],
        "budget_trip": cur.execute("SELECT COUNT(*) FROM budget.budget_trip WHERE cost_center=? AND fiscal_year=?", CC, FY).fetchone()[0],
        "approval_status": cur.execute("SELECT COUNT(*) FROM budget.approval_status WHERE department=? AND fiscal_year=?", DEPT, FY).fetchone()[0],
        "approval_log_kept": cur.execute("SELECT COUNT(*) FROM budget.approval_log WHERE department=? AND fiscal_year=?", DEPT, FY).fetchone()[0],
        "other_depts_fy2027_rows_untouched": cur.execute(
            "SELECT COUNT(*) FROM budget.pending_budget WHERE fiscal_year=? AND cost_center<>?", FY, CC).fetchone()[0],
    }
    print("after:", after)
    return 0


if __name__ == "__main__":
    sys.exit(main())
