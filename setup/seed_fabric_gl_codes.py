"""One-time script: create cfg_master.sap_gl_code_ref and seed 137 GL codes.

Run from repo root:
    python setup/seed_fabric_gl_codes.py

Requires .env with:
    FABRIC_SQL_SERVER, FABRIC_SQL_DATABASE, AAD_CLIENT_ID, AAD_CLIENT_SECRET
"""
import os
import sys
from pathlib import Path

# Load .env
env_path = Path(__file__).parent.parent / ".env"
if env_path.exists():
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())

import pyodbc

CONN_STR = (
    "DRIVER={ODBC Driver 17 for SQL Server};"
    f"SERVER={os.environ['FABRIC_SQL_SERVER']};"
    f"DATABASE={os.environ['FABRIC_SQL_DATABASE']};"
    "Authentication=ActiveDirectoryServicePrincipal;"
    f"UID={os.environ['AAD_CLIENT_ID']};"
    f"PWD={os.environ['AAD_CLIENT_SECRET']};"
)

SQL_DIR = Path(__file__).parent.parent / "03-edit-master-table/0003-gl-group/03sql"

CREATE_SQL = """
IF NOT EXISTS (
    SELECT 1 FROM sys.tables t
    JOIN sys.schemas s ON t.schema_id = s.schema_id
    WHERE s.name = 'cfg_master' AND t.name = 'sap_gl_code_ref'
)
CREATE TABLE cfg_master.sap_gl_code_ref (
    code  NVARCHAR(20)  NOT NULL,
    name  NVARCHAR(200) NOT NULL,
    CONSTRAINT pk_sap_gl_code_ref PRIMARY KEY (code)
);
"""

SEED_SQL = """
IF NOT EXISTS (SELECT 1 FROM cfg_master.sap_gl_code_ref)
INSERT INTO cfg_master.sap_gl_code_ref (code, name) VALUES
    ('5211900030', 'Entertainment Expenses'),
    ('6211900031', 'Entertainment Exter.'),
    ('6211900030', 'Entertainment Expenses (External)'),
    ('5211200020', 'Lease & Rental - Building'),
    ('6211200020', 'Lease & Rental - Building'),
    ('5211200050', 'Lease & Rental - Computer Equipment'),
    ('6211200050', 'Lease & Rental - Computer Equipment'),
    ('5211200010', 'Lease & Rental - Land'),
    ('5211200030', 'Lease & Rental - Machinery & Equipment'),
    ('6211200030', 'Lease & Rental - Machinery & Equipment'),
    ('5211200040', 'Lease & Rental - Office Equipment'),
    ('5211200999', 'Lease & Rental - Other'),
    ('6211200999', 'Lease & Rental - Other'),
    ('5211200060', 'Lease & Rental - Vehicles'),
    ('6211200060', 'Lease & Rental - Vehicles'),
    ('6211200010', 'Lease&Rental-Land'),
    ('6211200040', 'Lease&Rental-Office'),
    ('6210700050', 'Audit Fee'),
    ('6210700030', 'Consulting fee-Legal'),
    ('6210700999', 'Consulting fee-Other'),
    ('6210700040', 'Consulting fee - Finance'),
    ('5210700030', 'Consulting fee - Legal'),
    ('5210700999', 'Consulting fee - Others'),
    ('5210700010', 'Consulting fee - Research and development'),
    ('6210700010', 'Consulting fee - Research and development'),
    ('5210700020', 'Consulting fee - Technical'),
    ('6210700020', 'Consulting fee - Technical'),
    ('5211900020', 'ISO Expense'),
    ('6210800020', 'Management fee - Related'),
    ('6210800010', 'Management fee - Subsidiaries'),
    ('6211700020', 'Community Relations Expenses'),
    ('6211700030', 'Donation'),
    ('6211700010', 'PR Production expenses'),
    ('6211400040', 'Bank Charge'),
    ('5211400040', 'Bank Charge'),
    ('6510200010', 'Front end fee'),
    ('5210600020', 'Communication Circuit - Rent/Service'),
    ('6210600020', 'Communication Circuit - Rent/Service'),
    ('5210600999', 'Other communication expenses'),
    ('6210600999', 'Other communication expenses'),
    ('5210900060', 'Service fee - Postage and Courier'),
    ('6210900060', 'Service fee - Postage and Courier'),
    ('6210600010', 'Telephone / Mobile'),
    ('5210600010', 'Telephone / Mobile'),
    ('6210500010', 'Electricity'),
    ('6210500020', 'Water'),
    ('5210500020', 'Water'),
    ('6210100070', 'Employee Benefit'),
    ('5210100070', 'Employee Benefit Expenses'),
    ('6211300999', 'Insurance Premium - Others'),
    ('5211300999', 'Insurance Premium - Others'),
    ('5211100110', 'Maintenance - License for software'),
    ('6211100110', 'Maintence- software'),
    ('5211800030', 'Expense Office Equipment, F&F (< 5,000 Baht)'),
    ('6211800030', 'Expense Office Equipment, F&F (< 5,000 Baht)'),
    ('5211800070', 'Gardening supplies'),
    ('6211800070', 'Gardening supplies'),
    ('5211800020', 'Janitorial Supplies'),
    ('6211800020', 'Janitorial Supplies'),
    ('5211800040', 'Office & Plant Supplies used'),
    ('6211800040', 'Office & Plant Supplies used'),
    ('5210900010', 'Service fee - Messenger'),
    ('6210900010', 'Service fee - Messenger'),
    ('5210900999', 'Service fee - Others'),
    ('6210900999', 'Service fee - Others'),
    ('5211800010', 'Stationery and printing supplies'),
    ('6211800010', 'Stationery and printing supplies'),
    ('6120300010', 'Diesel Usage'),
    ('6211400050', 'Fees for Listed Company'),
    ('5211800060', 'Laboratory & QC Supplies'),
    ('6211800060', 'Laboratory & QC Supplies'),
    ('6211400010', 'Membership fee'),
    ('5211400010', 'Membership fee'),
    ('6211900050', 'Miscelleneous Exp.'),
    ('5211900050', 'Miscelleneous Exp.'),
    ('5120300020', 'Oil Expenses'),
    ('6211400999', 'Other Fee'),
    ('5211400999', 'Other Fee - Cost Operation'),
    ('5211900040', 'Other Meeting'),
    ('6211900040', 'Other Meeting'),
    ('5211400020', 'Other Penalty & Claim'),
    ('6211400020', 'Other Penalty & Claim'),
    ('5210500999', 'Other Utility Expense'),
    ('6210500999', 'Other Utility Expense'),
    ('5120300030', 'Packaging Used'),
    ('6212000010', 'Property&Other Tax'),
    ('5212000010', 'Property, Sign - board & Other Tax'),
    ('5211800050', 'Safety Supplies'),
    ('6211800050', 'Safety Supplies'),
    ('6119900010', 'Sample Exp-Inven Cos'),
    ('5210900050', 'Service fee - Driver Services'),
    ('5210900040', 'Service fee - Packing Service'),
    ('5210900020', 'Service fee - Security Guard'),
    ('6210900020', 'Service fee - Security Guard'),
    ('5210900030', 'Service fee - Waste Treatment'),
    ('6211900070', 'Stockholder Meeting'),
    ('5211400030', 'Tax Penalty, Adjust, Non - refundable'),
    ('6211400030', 'Tax Penalty, Adjust, Non - refundable'),
    ('6211900060', 'Vehicle Expense'),
    ('5211900060', 'Vehicle Expense'),
    ('5210500030', 'Water plant supply'),
    ('6210300020', 'Compensation Fund'),
    ('6210300040', 'Fund for Empowerment of Persons with Disabilities'),
    ('5210100100', 'Health & Accidental Insurance'),
    ('6210100100', 'Health & Accidental Insurance'),
    ('5210100110', 'Health Check'),
    ('6210100110', 'Health Check'),
    ('6210100080', 'Other welfare'),
    ('5210100080', 'Other welfare'),
    ('5210400010', 'Per Diem'),
    ('6210400010', 'Per Diem'),
    ('5210100130', 'Recruiting Expenses'),
    ('5210100090', 'Uniform'),
    ('6210100090', 'Uniform'),
    ('5210100140', 'Personal Activity & Function'),
    ('6210100140', 'Personal Activity & Function'),
    ('6210100130', 'Recruiting Expenses'),
    ('6210200010', 'Remuneration of directors'),
    ('6211100030', 'Repair & Maintenance - Building Improvement'),
    ('5211100080', 'Repair & Maintenance - Computer Equipment'),
    ('6211100080', 'Repair & Maintenance - Computer Equipment'),
    ('5211100060', 'Repair & Maintenance - Furniture & Fixture'),
    ('6211100060', 'Repair & Maintenance - Furniture & Fixture'),
    ('6211100010', 'Repair & Maintenance - Land Improvement'),
    ('6211100040', 'Repair & Maintenance - Machinery & Equipment'),
    ('5211100070', 'Repair & Maintenance - Office Equipment'),
    ('6211100070', 'Repair & Maintenance - Office Equipment'),
    ('6211100090', 'RM-Vehicle'),
    ('6120500010', 'Spare parts & Consumables Usage'),
    ('6210100150', 'Training & Seminars Fee'),
    ('5210100150', 'Training & Seminars Fee'),
    ('5210400030', 'Accommodation'),
    ('6210400030', 'Accommodation'),
    ('6210400999', 'Other Travel Exp.'),
    ('5210400999', 'Other Travelling Expenses'),
    ('5210400020', 'Transportation'),
    ('6210400020', 'Transportation');
"""


def main():
    print("Connecting to Fabric SQL Database...")
    try:
        conn = pyodbc.connect(CONN_STR, autocommit=True)
    except Exception as e:
        print(f"Connection failed: {e}")
        sys.exit(1)

    cursor = conn.cursor()

    print("Creating cfg_master.sap_gl_code_ref (if not exists)...")
    cursor.execute(CREATE_SQL)
    print("  Done.")

    print("Seeding 137 GL codes (skipped if table already has rows)...")
    cursor.execute(SEED_SQL)
    print("  Done.")

    count = cursor.execute("SELECT COUNT(*) FROM cfg_master.sap_gl_code_ref").fetchone()[0]
    print(f"Rows in sap_gl_code_ref: {count}")
    conn.close()
    print("All done.")


if __name__ == "__main__":
    main()
