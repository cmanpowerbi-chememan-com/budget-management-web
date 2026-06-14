"""
Seed cfg_master.orgcode_costcenter_map from docs/09orgcode & costcenter.xlsx
Usage:
    python setup/seed_orgcode_costcenter.py           # live insert
    python setup/seed_orgcode_costcenter.py --dry-run # preview only
"""

import sys
import os
import openpyxl
import pyodbc

DRY_RUN = "--dry-run" in sys.argv
XLSX = os.path.join(os.path.dirname(__file__), "..", "docs", "09orgcode & costcenter.xlsx")

FABRIC_SERVER = "v5o4qez3u4cupase7cogkwvyke-w4l3zd35yzkuzfgnonsogpi55e.database.fabric.microsoft.com,1433"
FABRIC_DB     = "fabric sql db-036a3270-82dd-40f4-aea4-6c27f55cff07"


def get_conn():
    # Azure AD Interactive — will open browser/MFA prompt on first run
    return pyodbc.connect(
        f"DRIVER={{ODBC Driver 17 for SQL Server}};"
        f"SERVER={FABRIC_SERVER};"
        f"DATABASE={FABRIC_DB};"
        "Authentication=ActiveDirectoryInteractive;"
        "Encrypt=yes;TrustServerCertificate=no;"
    )


def load_xlsx():
    wb = openpyxl.load_workbook(XLSX, read_only=True)
    ws = wb.active
    rows = []
    for row in ws.iter_rows(min_row=2, values_only=True):
        orgcode = str(row[0]).strip() if row[0] is not None else None
        cost_center = str(row[2]).strip() if row[2] is not None else None
        if orgcode and cost_center:
            rows.append((orgcode, cost_center))
    wb.close()
    return rows


def main():
    rows = load_xlsx()
    print(f"Loaded {len(rows):,} rows from Excel")

    if DRY_RUN:
        print("-- DRY RUN -- first 10 rows:")
        for r in rows[:10]:
            print(f"  orgcode={r[0]}  cost_center={r[1]}")
        return

    conn = get_conn()
    cursor = conn.cursor()

    sql = """
        IF NOT EXISTS (
            SELECT 1 FROM cfg_master.orgcode_costcenter_map
            WHERE orgcode = ? AND cost_center = ?
        )
        INSERT INTO cfg_master.orgcode_costcenter_map (orgcode, cost_center)
        VALUES (?, ?)
    """

    inserted = skipped = 0
    for orgcode, cost_center in rows:
        cursor.execute(sql, orgcode, cost_center, orgcode, cost_center)
        if cursor.rowcount > 0:
            inserted += 1
        else:
            skipped += 1

    conn.commit()
    cursor.close()
    conn.close()

    print(f"Done — inserted: {inserted:,}  skipped (duplicate): {skipped:,}")


if __name__ == "__main__":
    main()
