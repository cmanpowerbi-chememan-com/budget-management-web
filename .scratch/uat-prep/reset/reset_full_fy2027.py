"""Full reset of the AI-driven UAT round — delete every test row the AI entered on
Data & Analytic and Solution Delivery FY2027, returning both departments to the
pre-run initial state (never submitted, no budget rows). jakkaritw 2026-09-10:
"ที่กรอกทดสอบลบออก / back to สถานะเริ่มต้น".

RULE 1 (from 10_reset_after_ai_run.sql — the 2026-08-18 incident): never delete on
"should be empty". This script deletes ONLY the exact counts the AI created, verified
live against the inventory below; if any table's live count differs, it ABORTS —
a different count means someone else touched the data and a human must look.

Pre-run baseline (both depts were EMPTY before the AI run): D&A cleared to 0 on
2026-09-08 (clear_da_fy2027.py), SD had 0 FY2027 rows. So every row now on
10IT013000 / 10IT012000 FY2027 is AI test data.

EXPECTED (verified live 2026-09-10):
    pending_budget         D&A 9 (415,900.00) + SD 2 (30,000.00) = 11
    pending_budget_detail  D&A 11 + SD 0                          = 11
    budget_trip            trips 52, 53 (D&A)                     = 2
    approval_status        D&A APPROVED + SD REJECTED             = 2
    approval_log           KEPT (D&A 20 / SD 9 — history)
    other depts FY2027     14 rows — MUST stay unchanged

    python -X utf8 reset_full_fy2027.py            # dry-run: SELECT + show, no write
    python -X utf8 reset_full_fy2027.py --apply     # delete, one transaction, guarded
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
SERVER = "v5o4qez3u4cupase7cogkwvyke-bby6xlm3ncqexly4ozejod2vqe.database.fabric.microsoft.com,1433"
DB = "fabric_sql_database-a42ef9f3-f190-464a-8d5e-c0d41ef9ce42"
FY = 2027
CCS = ("10IT013000", "10IT012000")          # D&A + SD
DEPTS = ("Data & Analytic", "Solution Delivery")
EXPECTED = {"pending_budget": 11, "pending_budget_detail": 11, "budget_trip": 2, "approval_status": 2}
EXPECTED_TOTAL = Decimal("445900.00")        # 415,900 + 30,000
OUT_DIR = Path(r"C:\04.budget_management_web\.scratch\uat-prep\reset\out")
OUT_DIR.mkdir(parents=True, exist_ok=True)


def _default(o):
    if isinstance(o, Decimal):
        return str(o)
    if isinstance(o, (dt.datetime, dt.date)):
        return o.isoformat()
    return str(o)


def rows(cur, sql, *p):
    cur.execute(sql, *p)
    cols = [c[0] for c in cur.description]
    return [dict(zip(cols, r)) for r in cur.fetchall()]


def main() -> int:
    apply = "--apply" in sys.argv
    conn = pyodbc.connect(
        f"DRIVER={{ODBC Driver 17 for SQL Server}};SERVER={SERVER};DATABASE={DB};"
        "Authentication=ActiveDirectoryServicePrincipal;"
        f"UID={os.getenv('ENTRA_CLIENT_ID')};PWD={os.getenv('ENTRA_CLIENT_SECRET')};"
        "Encrypt=yes;TrustServerCertificate=no;", timeout=90, autocommit=False)
    cur = conn.cursor()

    baseline = {
        "captured_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(), "database": DB,
        "scope": {"cost_centers": CCS, "departments": DEPTS, "fiscal_year": FY},
        "pending_budget": rows(cur, "SELECT * FROM budget.pending_budget WHERE fiscal_year=? AND cost_center IN (?,?)", FY, *CCS),
        "pending_budget_detail": rows(cur, "SELECT * FROM budget.pending_budget_detail WHERE fiscal_year=? AND cost_center IN (?,?)", FY, *CCS),
        "budget_trip": rows(cur, "SELECT * FROM budget.budget_trip WHERE fiscal_year=? AND cost_center IN (?,?)", FY, *CCS),
        "approval_status": rows(cur, "SELECT * FROM budget.approval_status WHERE fiscal_year=? AND department IN (?,?)", FY, *DEPTS),
    }
    found = {k: len(baseline[k]) for k in EXPECTED}
    total = sum(Decimal(str(r["total_year"])) for r in baseline["pending_budget"])
    other = cur.execute("SELECT COUNT(*) FROM budget.pending_budget WHERE fiscal_year=? "
                        "AND cost_center NOT IN (?,?)", FY, *CCS).fetchone()[0]
    print("found (live):", found, "| pending_budget total_year:", total, "| other-dept FY2027 rows:", other)
    for r in baseline["approval_status"]:
        print("   status:", {k: r[k] for k in r if k in ("department", "fiscal_year", "status")})

    if found != EXPECTED or total != EXPECTED_TOTAL:
        print(f"ABORT: live counts/total differ from the AI journal (expected {EXPECTED}, {EXPECTED_TOTAL}). "
              "Someone else may have touched the data — a human must review. Nothing changed.")
        return 1

    if not apply:
        print("\nDRY-RUN only. Re-run with --apply to delete these rows (approval_log kept, other depts untouched).")
        return 0

    stamp = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    out = OUT_DIR / f"baseline_full_reset_FY2027_before_{stamp}.json"
    out.write_text(json.dumps(baseline, ensure_ascii=False, indent=2, default=_default), encoding="utf-8")
    print("baseline written:", out)

    try:
        d_detail = cur.execute("DELETE FROM budget.pending_budget_detail WHERE fiscal_year=? AND cost_center IN (?,?)", FY, *CCS).rowcount
        d_trip = cur.execute("DELETE FROM budget.budget_trip WHERE fiscal_year=? AND cost_center IN (?,?)", FY, *CCS).rowcount
        d_budget = cur.execute("DELETE FROM budget.pending_budget WHERE fiscal_year=? AND cost_center IN (?,?)", FY, *CCS).rowcount
        d_status = cur.execute("DELETE FROM budget.approval_status WHERE fiscal_year=? AND department IN (?,?)", FY, *DEPTS).rowcount
        deleted = {"pending_budget": d_budget, "pending_budget_detail": d_detail, "budget_trip": d_trip, "approval_status": d_status}
        other_after = cur.execute("SELECT COUNT(*) FROM budget.pending_budget WHERE fiscal_year=? AND cost_center NOT IN (?,?)", FY, *CCS).fetchone()[0]
        print("deleted (uncommitted):", deleted, "| other-dept rows now:", other_after)
        if deleted != EXPECTED or other_after != other:
            conn.rollback()
            print(f"ROLLBACK: deleted {deleted} != expected {EXPECTED} or other-dept count changed. Nothing changed.")
            return 1
        conn.commit()
        print("COMMITTED — Data & Analytic and Solution Delivery FY2027 are back to the pre-run empty state.")
    except Exception as exc:  # noqa: BLE001
        conn.rollback()
        print("ROLLBACK on error:", exc)
        return 1

    after = {
        "pending_budget": cur.execute("SELECT COUNT(*) FROM budget.pending_budget WHERE fiscal_year=? AND cost_center IN (?,?)", FY, *CCS).fetchone()[0],
        "pending_budget_detail": cur.execute("SELECT COUNT(*) FROM budget.pending_budget_detail WHERE fiscal_year=? AND cost_center IN (?,?)", FY, *CCS).fetchone()[0],
        "budget_trip": cur.execute("SELECT COUNT(*) FROM budget.budget_trip WHERE fiscal_year=? AND cost_center IN (?,?)", FY, *CCS).fetchone()[0],
        "approval_status": cur.execute("SELECT COUNT(*) FROM budget.approval_status WHERE fiscal_year=? AND department IN (?,?)", FY, *DEPTS).fetchone()[0],
        "approval_log_kept": cur.execute("SELECT COUNT(*) FROM budget.approval_log WHERE fiscal_year=? AND department IN (?,?)", FY, *DEPTS).fetchone()[0],
        "other_depts_fy2027_rows": cur.execute("SELECT COUNT(*) FROM budget.pending_budget WHERE fiscal_year=? AND cost_center NOT IN (?,?)", FY, *CCS).fetchone()[0],
    }
    print("after (all four scoped tables should be 0):", after)
    return 0


if __name__ == "__main__":
    sys.exit(main())
