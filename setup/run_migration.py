import pyodbc
import os
from dotenv import load_dotenv

load_dotenv(dotenv_path=r"c:\04.budget_management_web\.env")

conn_str = (
    f"DRIVER={{ODBC Driver 17 for SQL Server}};"
    f"SERVER={os.getenv('DB_SERVER')};"
    f"DATABASE={os.getenv('DB_NAME')};"
    f"UID={os.getenv('DB_USER')};"
    f"PWD={os.getenv('DB_PASSWORD')};"
    "Encrypt=yes;TrustServerCertificate=no;Connection Timeout=30;"
)

conn = pyodbc.connect(conn_str)
cursor = conn.cursor()

sql_file = r"c:\01.besties\cman-prd-chatbot-backend\docs\sql_migration\create_tables.sql"
sql = open(sql_file, encoding="utf-8").read()

batches = [b.strip() for b in sql.split("GO") if b.strip()]
for batch in batches:
    lines = [l for l in batch.splitlines() if l.strip() and not l.strip().startswith("--")]
    if not lines:
        continue
    try:
        cursor.execute(batch)
        conn.commit()
        print("OK:", batch[:80].replace("\n", " "))
    except Exception as e:
        print("ERR:", str(e)[:150])

conn.close()
print("\nDone.")
