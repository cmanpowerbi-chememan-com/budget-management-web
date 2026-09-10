"""Read-only inventory of everything the AI-driven UAT run left on Data & Analytic and
Solution Delivery FY2027, so the full reset back to the pre-run initial state can be
verified before any delete. No writes."""
from __future__ import annotations
import os
from decimal import Decimal

import pyodbc
from dotenv import load_dotenv

load_dotenv(r"C:\04.budget_management_web\.env")
SERVER = "v5o4qez3u4cupase7cogkwvyke-bby6xlm3ncqexly4ozejod2vqe.database.fabric.microsoft.com,1433"
DB = "fabric_sql_database-a42ef9f3-f190-464a-8d5e-c0d41ef9ce42"
FY = 2027


def rows(cur, sql, *p):
    cur.execute(sql, *p)
    cols = [c[0] for c in cur.description]
    return [dict(zip(cols, r)) for r in cur.fetchall()]


conn = pyodbc.connect(
    f"DRIVER={{ODBC Driver 17 for SQL Server}};SERVER={SERVER};DATABASE={DB};"
    "Authentication=ActiveDirectoryServicePrincipal;"
    f"UID={os.getenv('ENTRA_CLIENT_ID')};PWD={os.getenv('ENTRA_CLIENT_SECRET')};"
    "Encrypt=yes;TrustServerCertificate=no;", timeout=90)
cur = conn.cursor()

print("=== approval_status FY2027 (both target depts) ===")
for r in rows(cur, "SELECT department, fiscal_year, status FROM budget.approval_status "
                   "WHERE fiscal_year=? AND department IN (N'Data & Analytic', N'Solution Delivery') "
                   "ORDER BY department", FY):
    print("  ", r)

print("=== pending_budget by cost_center (D&A=10IT013*, SD=10IT012*) FY2027 ===")
for r in rows(cur, "SELECT cost_center, COUNT(*) n, SUM(total_year) total FROM budget.pending_budget "
                   "WHERE fiscal_year=? AND (cost_center LIKE '10IT012%' OR cost_center LIKE '10IT013%') "
                   "GROUP BY cost_center ORDER BY cost_center", FY):
    print("  ", r)

print("=== pending_budget_detail (subform rows) ===")
for r in rows(cur, "SELECT cost_center, COUNT(*) n FROM budget.pending_budget_detail "
                   "WHERE fiscal_year=? AND (cost_center LIKE '10IT012%' OR cost_center LIKE '10IT013%') "
                   "GROUP BY cost_center ORDER BY cost_center", FY):
    print("  ", r)

print("=== budget_trip ===")
for r in rows(cur, "SELECT trip_id, cost_center, fiscal_year FROM budget.budget_trip "
                   "WHERE fiscal_year=? AND (cost_center LIKE '10IT012%' OR cost_center LIKE '10IT013%') "
                   "ORDER BY trip_id", FY):
    print("  ", r)

print("=== approval_log (KEPT — history, just counting) ===")
for r in rows(cur, "SELECT department, COUNT(*) n FROM budget.approval_log "
                   "WHERE fiscal_year=? AND department IN (N'Data & Analytic', N'Solution Delivery') "
                   "GROUP BY department", FY):
    print("  ", r)

print("=== other departments' FY2027 rows (MUST stay untouched) ===")
print("  other pending_budget rows:", cur.execute(
    "SELECT COUNT(*) FROM budget.pending_budget WHERE fiscal_year=? "
    "AND cost_center NOT LIKE '10IT012%' AND cost_center NOT LIKE '10IT013%'", FY).fetchone()[0])
