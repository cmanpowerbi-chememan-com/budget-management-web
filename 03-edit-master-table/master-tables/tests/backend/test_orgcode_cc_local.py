"""
Local test — runs directly against Fabric SQL DB, no Azure Functions runtime.
Auth = Service Principal (db.py), no browser popup.

Usage:
    cd 03-edit-master-table/0007-orgcode-costcenter/02backend
    py test_local.py

`test_list_handler_query_targets_employee_master` and
`test_reference_handler_orgcodes_query_targets_employee_master` need NO live DB —
they mock fetchall and pin the SQL text the handlers send, so a future edit that
silently reverts to the retired dbo.mas_employee_data (DB1, dead since
2026-08-07) fails loud without needing Fabric credentials.
"""
import sys, os
from pathlib import Path
from unittest.mock import patch, MagicMock
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
            COALESCE(e.org_name_th, '') AS orgcode_name
        FROM cfg_master.orgcode_costcenter_map m
        LEFT JOIN (
            SELECT DISTINCT org_code, org_name_th
            FROM dbo.employee_master
            WHERE org_code IS NOT NULL
        ) e ON e.org_code = m.orgcode
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
            CAST(org_code AS NVARCHAR(20)) AS code,
            org_name_th AS name
        FROM dbo.employee_master
        WHERE org_code IS NOT NULL
          AND record_status = 'active'
          AND employee_code NOT LIKE '4%'
          AND org_code NOT LIKE '117%'
          AND job_level_name_en NOT IN ('Operator 1','Operator 2','Operator 3','Driver','Maid')
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


# ---------------------------------------------------------------------------
# Query-shape pin tests — mock fetchall, no live DB needed. These are the
# ones `pytest test_orgcode_cc_local.py -v` can actually run and pass; the
# functions above need a live Fabric SQL DB connection (run via `py
# test_local.py` per the module docstring) and are expected to error/fail
# under plain pytest — that is pre-existing, unrelated to this pin.
# ---------------------------------------------------------------------------

def _admin_request(route_params=None):
    req = MagicMock()
    req.headers = {"x-ms-client-principal-name": "admin@chememan.com"}
    req.method = "GET"
    req.route_params = route_params or {}
    return req


def test_list_handler_query_targets_employee_master():
    """Pin: list_handler's join reads dbo.employee_master (org_code/org_name_th),
    never the retired dbo.mas_employee_data (DB1, dead since 2026-08-07)."""
    from modules.orgcode_costcenter import list_handler

    with patch("modules.orgcode_costcenter.list_handler.authenticate") as mock_auth, \
         patch("modules.orgcode_costcenter.list_handler.fetchall") as mock_fetchall:
        mock_auth.return_value = {"email": "admin@chememan.com"}
        mock_fetchall.return_value = []
        list_handler.handle(_admin_request())

    sql = mock_fetchall.call_args[0][0]
    assert "dbo.employee_master" in sql, "must read the consolidated source"
    assert "mas_employee_data" not in sql, "must not read the retired DB1 table"
    assert "org_code" in sql and "org_name_th" in sql
    assert "orgnameth" not in sql, "must not use the old DB1 column name"
    assert "DISTINCT" in sql, "DISTINCT semantics must be preserved"
    assert "IS NOT NULL" in sql, "the NULL orgcode guard must be preserved"
    assert "COALESCE(e.org_name_th, '')" in sql, (
        "COALESCE-to-empty-string must be preserved (frontend keys on orgcode_name)"
    )
    assert "AS orgcode_name" in sql, (
        "db.fetchall() builds each dict from cursor.description — the SQL alias "
        "IS the JSON key; an alias rename must fail this test, not just the mock"
    )


def test_reference_handler_orgcodes_query_targets_employee_master():
    """Pin: reference_handler's `orgcodes` ref reads dbo.employee_master AND
    re-applies the old sync_employees.py:90-101 filter (employee_master is the
    RAW mirror — mas_employee_data was pre-filtered at sync time, so this ref
    is the one query in the module that must exclude what the old sync used to
    exclude, or an admin could map a cost center to a subsidiary org code)."""
    from modules.orgcode_costcenter import reference_handler

    with patch("modules.orgcode_costcenter.reference_handler.authenticate") as mock_auth, \
         patch("modules.orgcode_costcenter.reference_handler.fetchall") as mock_fetchall:
        mock_auth.return_value = {"email": "admin@chememan.com"}
        mock_fetchall.return_value = []
        reference_handler.handle(_admin_request(route_params={"ref_name": "orgcodes"}))

    sql = mock_fetchall.call_args[0][0]
    assert "dbo.employee_master" in sql, "must read the consolidated source"
    assert "mas_employee_data" not in sql, "must not read the retired DB1 table"
    assert "org_code" in sql and "org_name_th" in sql
    assert "orgnameth" not in sql, "must not use the old DB1 column name"
    assert "DISTINCT" in sql, "DISTINCT semantics must be preserved"
    assert "IS NOT NULL" in sql, "the NULL orgcode guard must be preserved"
    assert "AS code" in sql and "AS name" in sql, (
        "db.fetchall() builds each dict from cursor.description — the SQL alias "
        "IS the JSON key; an alias rename must fail this test, not just the mock"
    )
    # sync_employees.py:90-101 parity — the 4 exclusions the old pre-filtered
    # mas_employee_data applied at sync time, now re-applied here explicitly.
    assert "record_status = 'active'" in sql, "hr status=='Active' parity"
    assert "employee_code NOT LIKE '4%'" in sql, "Gritsman subsidiary exclusion"
    assert "org_code NOT LIKE '117%'" in sql, "Vietnam + Australia (both 117-prefix) exclusion"
    assert "job_level_name_en NOT IN" in sql, "L5 Operator/Driver/Maid exclusion"
    for level in ("Operator 1", "Operator 2", "Operator 3", "Driver", "Maid"):
        assert level in sql, f"L5 exclusion list must include {level}"


if __name__ == "__main__":
    conn = test_connection()
    test_list(conn)
    test_reference(conn)
    test_save(conn)
    test_delete(conn)
    test_count(conn)
    conn.close()
    print("\nAll tests passed")
