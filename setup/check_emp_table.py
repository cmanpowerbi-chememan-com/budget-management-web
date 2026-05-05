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

cur.execute("""
    SELECT kc.name, kc.type_desc, c.name AS col_name
    FROM sys.key_constraints kc
    JOIN sys.index_columns ic ON ic.object_id = kc.parent_object_id AND ic.index_id = kc.unique_index_id
    JOIN sys.columns c ON c.object_id = ic.object_id AND c.column_id = ic.column_id
    WHERE kc.parent_object_id = OBJECT_ID('mas_employee_data')
""")
print("Key constraints:")
for r in cur.fetchall():
    print(f"  {r[0]} | {r[1]} | col={r[2]}")

cur.execute("""
    SELECT i.name, i.is_unique, c.name AS col_name
    FROM sys.indexes i
    JOIN sys.index_columns ic ON ic.object_id = i.object_id AND ic.index_id = i.index_id
    JOIN sys.columns c ON c.object_id = ic.object_id AND c.column_id = ic.column_id
    WHERE i.object_id = OBJECT_ID('mas_employee_data') AND i.name IS NOT NULL
""")
print("\nAll indexes:")
for r in cur.fetchall():
    print(f"  {r[0]} | unique={r[1]} | col={r[2]}")

cur.execute("SELECT COUNT(*) FROM mas_employee_data")
print(f"\nCurrent row count: {cur.fetchone()[0]}")

conn.close()
