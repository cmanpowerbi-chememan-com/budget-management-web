"""Read-only FULL inventory of FY2027 across EVERY department — used to decide the exact
target of a UAT reset. No writes. Prints who entered each row and when (UTC in DB)."""
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

print("### columns of budget.pending_budget")
print([c[0] for c in cur.execute("SELECT TOP 1 * FROM budget.pending_budget").description])

print("\n### ALL FY2027 pending_budget rows")
for r in rows(cur, "SELECT * FROM budget.pending_budget WHERE fiscal_year=? "
                   "ORDER BY cost_center, gl_account", FY):
    print("  ", {k: r[k] for k in r if k in
                 ("cost_center", "department", "gl_account", "total_year",
                  "created_by", "updated_by", "created_at", "updated_at",
                  "_user", "_updated_at", "last_updated_by", "last_updated_at")})

print("\n### FY2027 pending_budget grouped by dept/cc")
for r in rows(cur, "SELECT department, cost_center, COUNT(*) n, SUM(total_year) total,"
                   " MIN(_updated_at) first_at, MAX(_updated_at) last_at"
                   " FROM budget.pending_budget WHERE fiscal_year=?"
                   " GROUP BY department, cost_center ORDER BY department, cost_center", FY):
    print("  ", r)

print("\n### ALL FY2027 approval_status")
for r in rows(cur, "SELECT * FROM budget.approval_status WHERE fiscal_year=? ORDER BY department", FY):
    print("  ", r)

print("\n### ALL FY2027 pending_budget_detail")
for r in rows(cur, "SELECT detail_id, cost_center, gl_account, fiscal_year FROM budget.pending_budget_detail"
                   " WHERE fiscal_year=? ORDER BY detail_id", FY):
    print("  ", r)

print("\n### ALL FY2027 budget_trip")
for r in rows(cur, "SELECT trip_id, cost_center, fiscal_year FROM budget.budget_trip"
                   " WHERE fiscal_year=? ORDER BY trip_id", FY):
    print("  ", r)

print("\n### budget_trip ALL years (id range check)")
for r in rows(cur, "SELECT fiscal_year, COUNT(*) n, MIN(trip_id) lo, MAX(trip_id) hi"
                   " FROM budget.budget_trip GROUP BY fiscal_year ORDER BY fiscal_year"):
    print("  ", r)

print("\n### pending_budget rows in OTHER fiscal years (context only)")
for r in rows(cur, "SELECT fiscal_year, COUNT(*) n FROM budget.pending_budget GROUP BY fiscal_year ORDER BY fiscal_year"):
    print("  ", r)
