"""Reset the HUMAN UAT round (2026-09-14/15) back to the pre-round state.

jakkaritw 2026-09-15: "clear uat test data now, back to start 0".

Zero point = the state on 2026-09-13, i.e. after the AI-round reset of 2026-09-10
(reset_full_fy2027.py, commit 909d200) and before the human testers started.
At that point FY2027 held exactly 14 pending_budget rows, all entered in August by
nipapornt@ / warapornt@ on 5 non-UAT departments. Those 14 rows are REAL user data
and must survive untouched.

Scope widened vs reset_full_fy2027.py: the human round also used cost center
10IT011300 (Data & Analytic's second CC), which the earlier script did not cover.

RULE 1 (2026-08-18 incident): never delete on "should be empty". This deletes ONLY
the exact counts + exact THB total verified live; any difference ABORTS.
EXTRA GUARD: every row in scope must carry _updated_at >= 2026-09-13 (UTC) - proof
that no pre-round row is caught by the cost-center filter.

    python -X utf8 reset_human_round_fy2027.py            # dry-run, no write
    python -X utf8 reset_human_round_fy2027.py --apply    # delete, one transaction
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
CCS = ("10IT011300", "10IT012000", "10IT013000")   # D&A x2 + Solution Delivery
DEPTS = ("Data & Analytic", "Solution Delivery")
EXPECTED = {"pending_budget": 24, "pending_budget_detail": 15, "budget_trip": 3, "approval_status": 2}
EXPECTED_TOTAL = Decimal("101812250.00")      # 1,039,200 + 100,171,120 + 601,930
EXPECTED_OTHER = 14                            # pre-round real rows on 5 other departments
ROUND_START = dt.datetime(2026, 9, 13, 0, 0, 0)  # UTC; DB stores UTC (write_model.py:300)
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
        "pending_budget": rows(cur, "SELECT * FROM budget.pending_budget WHERE fiscal_year=? AND cost_center IN (?,?,?)", FY, *CCS),
        "pending_budget_detail": rows(cur, "SELECT * FROM budget.pending_budget_detail WHERE fiscal_year=? AND cost_center IN (?,?,?)", FY, *CCS),
        "budget_trip": rows(cur, "SELECT * FROM budget.budget_trip WHERE fiscal_year=? AND cost_center IN (?,?,?)", FY, *CCS),
        "approval_status": rows(cur, "SELECT * FROM budget.approval_status WHERE fiscal_year=? AND department IN (?,?)", FY, *DEPTS),
    }
    found = {k: len(baseline[k]) for k in EXPECTED}
    total = sum(Decimal(str(r["total_year"])) for r in baseline["pending_budget"])
    other = cur.execute("SELECT COUNT(*) FROM budget.pending_budget WHERE fiscal_year=? "
                        "AND cost_center NOT IN (?,?,?)", FY, *CCS).fetchone()[0]
    print("found (live):", found)
    print("pending_budget total_year:", total, "| other-dept FY2027 rows (KEEP):", other)
    for r in baseline["approval_status"]:
        print("   status:", {k: r[k] for k in r if k in ("department", "status", "submitter_email", "submitted_at")})

    # time cross-check: nothing older than the round start may be in scope
    stale = [r for r in baseline["pending_budget"] if r["_updated_at"] < ROUND_START]
    if stale:
        print("ABORT:", len(stale), "in-scope rows predate", ROUND_START,
              "- they are NOT round data. Nothing changed.")
        for r in stale[:10]:
            print("   stale:", r["cost_center"], r["gl_account"], r["_user"], r["_updated_at"])
        return 1

    if found != EXPECTED or total != EXPECTED_TOTAL or other != EXPECTED_OTHER:
        print("ABORT: live state differs from what was verified (expected", EXPECTED, EXPECTED_TOTAL,
              "other=", EXPECTED_OTHER, "). Someone touched the data - a human must review. Nothing changed.")
        return 1

    if not apply:
        print("")
        print("DRY-RUN only. Re-run with --apply to delete. approval_log kept, other 14 rows untouched.")
        return 0

    stamp = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    out = OUT_DIR / ("baseline_human_round_FY2027_before_" + stamp + ".json")
    out.write_text(json.dumps(baseline, ensure_ascii=False, indent=2, default=_default), encoding="utf-8")
    print("baseline written:", out)

    try:
        d_detail = cur.execute("DELETE FROM budget.pending_budget_detail WHERE fiscal_year=? AND cost_center IN (?,?,?)", FY, *CCS).rowcount
        d_trip = cur.execute("DELETE FROM budget.budget_trip WHERE fiscal_year=? AND cost_center IN (?,?,?)", FY, *CCS).rowcount
        d_budget = cur.execute("DELETE FROM budget.pending_budget WHERE fiscal_year=? AND cost_center IN (?,?,?)", FY, *CCS).rowcount
        d_status = cur.execute("DELETE FROM budget.approval_status WHERE fiscal_year=? AND department IN (?,?)", FY, *DEPTS).rowcount
        deleted = {"pending_budget": d_budget, "pending_budget_detail": d_detail, "budget_trip": d_trip, "approval_status": d_status}
        other_after = cur.execute("SELECT COUNT(*) FROM budget.pending_budget WHERE fiscal_year=? AND cost_center NOT IN (?,?,?)", FY, *CCS).fetchone()[0]
        print("deleted (uncommitted):", deleted, "| other-dept rows now:", other_after)
        if deleted != EXPECTED or other_after != EXPECTED_OTHER:
            conn.rollback()
            print("ROLLBACK: deleted", deleted, "!= expected", EXPECTED, "or other-dept count moved. Nothing changed.")
            return 1
        conn.commit()
        print("COMMITTED - Data & Analytic and Solution Delivery FY2027 are back to the pre-round state.")
    except Exception as exc:  # noqa: BLE001
        conn.rollback()
        print("ROLLBACK on error:", exc)
        return 1

    after = {
        "pending_budget": cur.execute("SELECT COUNT(*) FROM budget.pending_budget WHERE fiscal_year=? AND cost_center IN (?,?,?)", FY, *CCS).fetchone()[0],
        "pending_budget_detail": cur.execute("SELECT COUNT(*) FROM budget.pending_budget_detail WHERE fiscal_year=? AND cost_center IN (?,?,?)", FY, *CCS).fetchone()[0],
        "budget_trip": cur.execute("SELECT COUNT(*) FROM budget.budget_trip WHERE fiscal_year=? AND cost_center IN (?,?,?)", FY, *CCS).fetchone()[0],
        "approval_status": cur.execute("SELECT COUNT(*) FROM budget.approval_status WHERE fiscal_year=? AND department IN (?,?)", FY, *DEPTS).fetchone()[0],
        "approval_log_kept": cur.execute("SELECT COUNT(*) FROM budget.approval_log WHERE fiscal_year=? AND department IN (?,?)", FY, *DEPTS).fetchone()[0],
        "other_depts_fy2027_rows": cur.execute("SELECT COUNT(*) FROM budget.pending_budget WHERE fiscal_year=? AND cost_center NOT IN (?,?,?)", FY, *CCS).fetchone()[0],
    }
    print("after (first four must be 0, other-dept must be 14):", after)
    return 0


if __name__ == "__main__":
    sys.exit(main())
