"""Data Integrity Audit — read-only, whole-DB sweep after heavy test rounds."""
import sys
sys.path.insert(0, ".")
from app.db import get_fabric_conn

MONTHS = ", ".join(f"m{i:02d}" for i in range(1, 13))
MONTH_SUM = "+".join(f"COALESCE(m{i:02d},0)" for i in range(1, 13))
MONTH_MIN = None  # built inline below

def check(cur, label, sql, expect_zero=True):
    cur.execute(sql)
    val = cur.fetchone()[0]
    flag = "OK " if (val == 0) == expect_zero else "FAIL"
    print(f"  [{flag}] {label}: {val}")
    return val

with get_fabric_conn() as conn:
    cur = conn.cursor()

    print("== A. transactional tables: state after all test rounds ==")
    for t in ["pending_budget", "pending_budget_detail", "budget_trip", "approval_status", "approval_log"]:
        cur.execute(f"SELECT COUNT(*) FROM budget.{t}")
        print(f"  budget.{t}: {cur.fetchone()[0]}")

    print("== A2. txn integrity (vacuously OK if empty) ==")
    check(cur, "pending_budget rows where total_year <> SUM(months)",
          f"SELECT COUNT(*) FROM budget.pending_budget WHERE ABS(total_year - ({MONTH_SUM})) > 0.005")
    check(cur, "detail rows where total_year <> SUM(months)",
          f"SELECT COUNT(*) FROM budget.pending_budget_detail WHERE ABS(total_year - ({MONTH_SUM})) > 0.005")
    check(cur, "negative month values in pending_budget",
          f"SELECT COUNT(*) FROM budget.pending_budget WHERE m01<0 OR m02<0 OR m03<0 OR m04<0 OR m05<0 OR m06<0 OR m07<0 OR m08<0 OR m09<0 OR m10<0 OR m11<0 OR m12<0")
    check(cur, "orphan detail lines (trip_id not in budget_trip)",
          "SELECT COUNT(*) FROM budget.pending_budget_detail d WHERE d.trip_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM budget.budget_trip t WHERE t.trip_id = d.trip_id)")
    check(cur, "trips with NO detail line at all",
          "SELECT COUNT(*) FROM budget.budget_trip t WHERE NOT EXISTS (SELECT 1 FROM budget.pending_budget_detail d WHERE d.trip_id = t.trip_id)")
    check(cur, "duplicate parent keys (cc,gl,fy)",
          "SELECT COUNT(*) FROM (SELECT cost_center, gl_account, fiscal_year FROM budget.pending_budget GROUP BY cost_center, gl_account, fiscal_year HAVING COUNT(*)>1) x")
    check(cur, "parent drift: rows WITH details but months <> SUM(detail months)",
          """SELECT COUNT(*) FROM budget.pending_budget p
             WHERE EXISTS (SELECT 1 FROM budget.pending_budget_detail d
                           WHERE d.cost_center=p.cost_center AND d.gl_account=p.gl_account AND d.fiscal_year=p.fiscal_year)
             AND (ABS(p.total_year - (SELECT COALESCE(SUM(d.total_year),0) FROM budget.pending_budget_detail d
                           WHERE d.cost_center=p.cost_center AND d.gl_account=p.gl_account AND d.fiscal_year=p.fiscal_year)) > 0.005)""")

    print("== B. board_budget (364 rows expected) ==")
    cur.execute("SELECT COUNT(*) FROM dbo.board_budget")
    print(f"  rows: {cur.fetchone()[0]}")
    check(cur, "board rows where total_year <> SUM(months)",
          f"SELECT COUNT(*) FROM dbo.board_budget WHERE ABS(total_year - ({MONTH_SUM})) > 0.005")
    check(cur, "duplicate board keys (cc,gl,fy)",
          "SELECT COUNT(*) FROM (SELECT cost_center, gl_account, fiscal_year FROM dbo.board_budget GROUP BY cost_center, gl_account, fiscal_year HAVING COUNT(*)>1) x")
    check(cur, "board rows with negative months",
          f"SELECT COUNT(*) FROM dbo.board_budget WHERE m01<0 OR m02<0 OR m03<0 OR m04<0 OR m05<0 OR m06<0 OR m07<0 OR m08<0 OR m09<0 OR m10<0 OR m11<0 OR m12<0")

    print("== C. masters integrity ==")
    cur.execute("SELECT COUNT(*) FROM dbo.gl_group")
    print(f"  gl_group rows: {cur.fetchone()[0]}")
    check(cur, "duplicate gl_account in gl_group",
          "SELECT COUNT(*) FROM (SELECT gl_account FROM dbo.gl_group GROUP BY gl_account HAVING COUNT(*)>1) x")
    check(cur, "duplicate (cost_center, filler_email) in cc_filler_map",
          "SELECT COUNT(*) FROM (SELECT cost_center, filler_email FROM dbo.cc_filler_map GROUP BY cost_center, filler_email HAVING COUNT(*)>1) x")
    check(cur, "cc_filler_map rows with blank email",
          "SELECT COUNT(*) FROM dbo.cc_filler_map WHERE filler_email IS NULL OR LTRIM(RTRIM(filler_email))=''")
    print("  master_currency_rate by year:")
    for r in cur.execute("SELECT fiscal_year, usd_thb FROM dbo.master_currency_rate ORDER BY fiscal_year"):
        print(f"    FY{r[0]}: {r[1]}")

    print("== D. master-completeness money gap (the IB finding, quantified globally) ==")
    cur.execute("""
        SELECT COUNT(DISTINCT gl_account) FROM (
            SELECT gl_account FROM dbo.board_budget
            UNION
            SELECT gl_account FROM gold.fact_gl_trans WHERE 1=1
        ) x WHERE gl_account NOT IN (SELECT gl_account FROM dbo.gl_group)""")
    print(f"  GLs used in board/fact but NOT in gl_group master: {cur.fetchone()[0]}")
    cur.execute("""
        SELECT COALESCE(SUM(total_year),0) FROM gold.fact_gl_trans
        WHERE fiscal_year = 2026 AND gl_account NOT IN (SELECT gl_account FROM dbo.gl_group)""")
    print(f"  FY2026 actuals on non-master GLs (THB): {cur.fetchone()[0]:,.2f}")
