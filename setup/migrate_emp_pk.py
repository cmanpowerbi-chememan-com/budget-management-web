"""
migrate_emp_pk.py — Move PK from empcode to id so raw (multi-position) records can be stored
"""
import pyodbc, os
from dotenv import load_dotenv

load_dotenv(r"c:\04.budget_management_web\.env")

conn = pyodbc.connect(
    "DRIVER={ODBC Driver 17 for SQL Server};"
    f"SERVER={os.getenv('DB_SERVER')};"
    f"DATABASE={os.getenv('DB_NAME')};"
    f"UID={os.getenv('DB_USER')};"
    f"PWD={os.getenv('DB_PASSWORD')};"
    "Encrypt=yes;TrustServerCertificate=no;Connection Timeout=30;"
)
cur = conn.cursor()

steps = [
    ("Clear existing data",         "DELETE FROM mas_employee_data"),
    ("Drop old PK on empcode",      "ALTER TABLE mas_employee_data DROP CONSTRAINT PK_mas_employee_data"),
    ("Add new PK on id",            "ALTER TABLE mas_employee_data ADD CONSTRAINT PK_mas_employee_data PRIMARY KEY (id)"),
]

for label, sql in steps:
    print(f"  {label}...", end=" ")
    cur.execute(sql)
    conn.commit()
    print("OK")

conn.close()
print("Done.")
