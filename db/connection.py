import os
import pyodbc
from dotenv import load_dotenv

load_dotenv()

_SERVER   = os.getenv("DB_SERVER")
_DATABASE = os.getenv("DB_NAME")
_USER     = os.getenv("DB_USER")
_PASSWORD = os.getenv("DB_PASSWORD")
_DRIVER   = "ODBC Driver 17 for SQL Server"

_CONN_STR = (
    f"DRIVER={{{_DRIVER}}};"
    f"SERVER={_SERVER};"
    f"DATABASE={_DATABASE};"
    f"UID={_USER};"
    f"PWD={_PASSWORD};"
    "Encrypt=yes;"
    "TrustServerCertificate=no;"
    "Connection Timeout=30;"
)


def get_connection() -> pyodbc.Connection:
    return pyodbc.connect(_CONN_STR)


def test_connection() -> bool:
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT 1")
        conn.close()
        return True
    except Exception as e:
        print(f"Connection failed: {e}")
        return False


if __name__ == "__main__":
    print("Testing Azure SQL connection...")
    print(f"  Server  : {_SERVER}")
    print(f"  Database: {_DATABASE}")
    print(f"  User    : {_USER}")
    print(f"  Driver  : {_DRIVER}")
    print()
    ok = test_connection()
    print("Result:", "SUCCESS" if ok else "FAILED")
