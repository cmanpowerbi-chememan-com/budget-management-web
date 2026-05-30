"""Quick check: what's currently in cfg_master.hide_document_number.

Run from anywhere:
    python 03-edit-master-table/0003-gl-group/02backend/check_hide_doc_db.py
"""
import sys, io, os
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[3] / ".env")
for v in ("FABRIC_SQL_SERVER", "FABRIC_SQL_DATABASE", "ENTRA_CLIENT_ID", "ENTRA_CLIENT_SECRET"):
    if v in os.environ:
        os.environ[v] = os.environ[v].strip("'\"")

import pyodbc
conn = pyodbc.connect(
    f"DRIVER={{ODBC Driver 17 for SQL Server}};"
    f"SERVER={os.environ['FABRIC_SQL_SERVER']};"
    f"DATABASE={os.environ['FABRIC_SQL_DATABASE']};"
    "Authentication=ActiveDirectoryServicePrincipal;"
    f"UID={os.environ['ENTRA_CLIENT_ID']};"
    f"PWD={os.environ['ENTRA_CLIENT_SECRET']};"
    "Encrypt=yes;TrustServerCertificate=no;"
)
cur = conn.cursor()
cur.execute("""
    SELECT doc_num, fiscal_year, fiscal_month
    FROM cfg_master.hide_document_number
    ORDER BY doc_num, fiscal_year DESC, fiscal_month DESC
""")
rows = cur.fetchall()

print(f"Total rows: {len(rows)}")
print("-" * 50)
print(f"{'doc_num':<15} {'year':<6} {'month':<6} {'period':<10}")
print("-" * 50)
for r in rows:
    print(f"{r[0]:<15} {r[1]:<6} {r[2]:<6} {r[1]}-{r[2]:02d}")
