"""
sync_employees.py — Daily sync: C-POP HR API -> Fabric SQL DB (mas_employee_data)

Strategy: DELETE all + INSERT fresh (simpler than incremental; table is small).

Exclusion rules (budget system only):
  - empcode LIKE '4%'   -> Gritsman subsidiary
  - orgcode LIKE '117%' -> Office of Affiliate (Vietnam)
  - joblevelnameen in L5_LEVELS -> Operator/Driver/Maid (do not use the system)

Auth: ActiveDirectoryServicePrincipal (silent, no browser popup; works in CI).
      UID=ENTRA_CLIENT_ID, PWD=ENTRA_CLIENT_SECRET against the Fabric SQL DB.

Note: Azure SQL (DB_SERVER / DB_NAME) kept in .env but no longer used here.
      Auth is Service Principal — no FABRIC_SQL_USER / FABRIC_SQL_PASSWORD needed.

Usage:
  python setup/sync_employees.py           # run sync
  python setup/sync_employees.py --dry-run # show counts, no DB writes
"""
import os, sys, requests, pyodbc
from datetime import datetime, timezone, timedelta
from dotenv import load_dotenv

load_dotenv(r"c:\04.budget_management_web\.env")

API_URL  = os.getenv("CPOP_HR_SYSTEM_API_URL")
API_KEY  = os.getenv("CPOP_HR_SYSTEM_API_KEY")
DRY_RUN  = "--dry-run" in sys.argv
THAI_TZ  = timezone(timedelta(hours=7))

DATE_FIELDS = {"hiringdate", "terminatedate", "birthdate"}

L5_LEVELS = {
    "Operator 1", "Operator 2", "Operator 3", "Driver", "Maid",
}

COLUMNS = [
    "empcode", "titlenameth", "firstnameth", "lastnameth", "fullnameth",
    "nickName", "titlenameen", "firstnameen", "lastnameen", "fullnameen",
    "posstatus", "poscode", "posnameth", "posnameen",
    "emptypecode", "emptypenameth", "emptypenameen",
    "empsubtypecode", "empsubtypenameth", "empsubtypenameen",
    "compcode", "compabbreviation", "compnameth", "compnameen",
    "orgcode", "orgnameth", "orgnameen",
    "jobcode", "jobnameth", "jobnameen",
    "joblevelcode", "joblevelnameth", "joblevelnameen",
    "managerposcode", "managerposnameth", "managerposnameen",
    "managerempcode", "managerfirstnameth", "managerlastnameth",
    "managerfirstnameen", "managerlastnameen",
    "action", "reason", "hr_status",
    "areacode", "areanameth", "areanameen",
    "subareacode", "subareanameth", "subareanameen",
    "sex", "nationalityname", "email", "mobile", "idcard",
    "hiringdate", "terminatedate", "birthdate", "maritialstatus", "religionname",
    "pemail", "addressno", "roomno", "floor", "village", "building",
    "moo", "soi", "street", "subdistrictname", "districtname", "provincename",
    "countryname", "postcode", "addressnoen", "roomnoen", "flooren",
    "villageen", "buildingen", "mooen", "soien", "streeten",
    "subdistrictnameen", "districtnameen", "provincenameen", "countrynameen", "postcodeen",
]


def get_conn():
    return pyodbc.connect(
        "DRIVER={ODBC Driver 17 for SQL Server};"
        f"SERVER={os.getenv('FABRIC_SQL_SERVER')};"
        f"DATABASE={os.getenv('FABRIC_SQL_DATABASE')};"
        "Authentication=ActiveDirectoryServicePrincipal;"
        f"UID={os.getenv('ENTRA_CLIENT_ID')};"
        f"PWD={os.getenv('ENTRA_CLIENT_SECRET')};"
        "Encrypt=yes;TrustServerCertificate=no;"
    )


def fetch_from_api():
    today = datetime.now(THAI_TZ).strftime("%Y-%m-%d")
    resp = requests.post(
        API_URL,
        headers={"Authorization": API_KEY, "Content-Type": "application/json"},
        json={"keyDate": today, "empCode": ""},
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()
    if not data.get("success"):
        raise Exception(f"API error: {data.get('errorMessage')}")

    all_emps = data["employeeList"]
    active   = [e for e in all_emps if e.get("hr status") == "Active"]

    gritsman = sum(1 for e in active if str(e.get("empcode", "")).startswith("4"))
    vietnam  = sum(1 for e in active if str(e.get("orgcode",  "")).startswith("117"))
    l5       = sum(1 for e in active if e.get("joblevelnameen", "") in L5_LEVELS)

    included = [
        e for e in active
        if not str(e.get("empcode", "")).startswith("4")
        and not str(e.get("orgcode",  "")).startswith("117")
        and e.get("joblevelnameen", "") not in L5_LEVELS
    ]

    print(f"API    : {len(all_emps)} total -> {len(active)} Active")
    print(f"Exclude: -{gritsman} Gritsman  -{vietnam} Vietnam  -{l5} L5")
    print(f"Include: {len(included)} rows")
    return included


def emp_to_dict(emp):
    def val(col):
        api_key = "hr status" if col == "hr_status" else col
        v = emp.get(api_key, "") or ""
        return (v if v else None) if col in DATE_FIELDS else (v if v else None)
    return {col: val(col) for col in COLUMNS}


def sync():
    records = fetch_from_api()
    records_sorted = sorted(records, key=lambda e: e.get("empcode", ""))
    dicts = [emp_to_dict(e) for e in records_sorted]

    if DRY_RUN:
        print("\nDry-run complete -- no DB writes.")
        return

    conn = get_conn()
    cur  = conn.cursor()

    cur.execute("DELETE FROM mas_employee_data")
    deleted = cur.rowcount
    print(f"Deleted: {deleted} existing rows")

    col_list     = ", ".join(COLUMNS)
    placeholders = ", ".join(["?"] * len(COLUMNS))
    insert_sql   = f"INSERT INTO mas_employee_data (id, {col_list}) VALUES (?, {placeholders})"

    for idx, d in enumerate(dicts, start=1):
        row = (str(idx),) + tuple(d[c] for c in COLUMNS)
        cur.execute(insert_sql, row)

    conn.commit()
    conn.close()

    now = datetime.now(THAI_TZ).strftime("%Y-%m-%d %H:%M:%S")
    print(f"Inserted: {len(dicts)} rows  at {now} (Thai time)")


if __name__ == "__main__":
    sync()
