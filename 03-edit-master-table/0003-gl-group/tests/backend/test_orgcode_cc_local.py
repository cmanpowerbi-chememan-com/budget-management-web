"""
Local test — runs directly against Fabric SQL DB, no Azure Functions runtime.
Will open browser for Azure AD login on first run.

Usage:
    cd 03-edit-master-table/0007-orgcode-costcenter/02backend
    py test_local.py
"""
import sys, os
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "02backend"))
sys.stdout.reconfigure(encoding="utf-8")

from db import get_conn

def test_connection():
    print("1. Connection ...")
    conn = get_conn()
    print("   OK")
    return conn

def test_list(conn):
    print("\n2. List mappings (top 5) ...")
    cursor = conn.cursor()
    cursor.execute("""
        SELECT TOP 5
            m.id, m.cost_center, m.orgcode,
            COALESCE(e.orgnameth, '') AS orgcode_name
        FROM cfg_master.orgcode_costcenter_map m
        LEFT JOIN (
            SELECT DISTINCT orgcode, orgnameth
            FROM dbo.mas_employee_data
            WHERE orgcode IS NOT NULL
        ) e ON e.orgcode = m.orgcode
        ORDER BY m.cost_center, m.orgcode
    """)
    rows = cursor.fetchall()
    for r in rows:
        print(f"   id={r[0]}  cc={r[1]}  org={r[2]}  name={r[3]}")
    cursor.close()
    print(f"   OK — {len(rows)} rows shown")

def test_reference(conn):
    print("\n3. Reference orgcodes (top 5) ...")
    cursor = conn.cursor()
    cursor.execute("""
        SELECT DISTINCT TOP 5
            CAST(orgcode AS NVARCHAR(20)) AS code,
            orgnameth AS name
        FROM dbo.mas_employee_data
        WHERE orgcode IS NOT NULL
        ORDER BY code
    """)
    rows = cursor.fetchall()
    for r in rows:
        print(f"   code={r[0]}  name={r[1]}")
    cursor.close()
    print(f"   OK")

def test_save(conn):
    print("\n4. Save (INSERT test row) ...")
    cursor = conn.cursor()
    try:
        cursor.execute(
            "INSERT INTO cfg_master.orgcode_costcenter_map (orgcode, cost_center) VALUES (?, ?)",
            "TEST001", "TESTCC001",
        )
        conn.commit()
        print("   OK — inserted")
    except Exception as e:
        print(f"   SKIP — {e}")
    finally:
        cursor.close()

def test_delete(conn):
    print("\n5. Delete (test row) ...")
    cursor = conn.cursor()
    cursor.execute(
        "DELETE FROM cfg_master.orgcode_costcenter_map WHERE orgcode = ? AND cost_center = ?",
        "TEST001", "TESTCC001",
    )
    conn.commit()
    print(f"   OK — deleted {cursor.rowcount} row")
    cursor.close()

def test_count(conn):
    print("\n6. Total rows ...")
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM cfg_master.orgcode_costcenter_map")
    print(f"   {cursor.fetchone()[0]:,} rows")
    cursor.close()


if __name__ == "__main__":
    conn = test_connection()
    test_list(conn)
    test_reference(conn)
    test_save(conn)
    test_delete(conn)
    test_count(conn)
    conn.close()
    print("\nAll tests passed")
