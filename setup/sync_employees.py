"""
sync_employees.py — Daily incremental sync: C-POP HR API → Azure SQL mas_employee_data

Sync logic (keyed on empcode + poscode):
  INSERT  : in API (Active) but not in DB
  UPDATE  : in both, but any field changed
  DELETE  : in DB but not in API Active records

Usage:
  python setup/sync_employees.py           # run sync
  python setup/sync_employees.py --dry-run # show what would change, no DB writes
"""
import os, sys, hashlib, json, requests, pyodbc
from datetime import datetime, timezone, timedelta
from dotenv import load_dotenv

load_dotenv(r"c:\04.budget_management_web\.env")

API_URL = os.getenv("CPOP_HR_SYSTEM_API_URL")
API_KEY = os.getenv("CPOP_HR_SYSTEM_API_KEY")
DRY_RUN = "--dry-run" in sys.argv
THAI_TZ = timezone(timedelta(hours=7))

DATE_FIELDS = {"hiringdate", "terminatedate", "birthdate"}

# Columns in mas_employee_data (excluding id)
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
        f"SERVER={os.getenv('DB_SERVER')};"
        f"DATABASE={os.getenv('DB_NAME')};"
        f"UID={os.getenv('DB_USER')};"
        f"PWD={os.getenv('DB_PASSWORD')};"
        "Encrypt=yes;TrustServerCertificate=no;Connection Timeout=30;"
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
    active = [e for e in all_emps if e.get("hr status") == "Active"]
    print(f"API  : {len(all_emps)} total, {len(active)} Active")
    return active


def emp_to_dict(emp):
    """Normalize one API employee record into a flat dict matching DB columns."""
    def val(col):
        api_key = "hr status" if col == "hr_status" else col
        v = emp.get(api_key, "") or ""
        if col in DATE_FIELDS:
            return v if v else None
        return v if v else None
    return {col: val(col) for col in COLUMNS}


def row_hash(d):
    """Stable hash of all column values for change detection."""
    raw = json.dumps({k: str(d[k]) for k in COLUMNS}, sort_keys=True, ensure_ascii=False)
    return hashlib.md5(raw.encode()).hexdigest()


def fetch_from_db(cur):
    """Return dict keyed by (empcode, poscode) → {col: val, ..., '_id': id, '_hash': hash}"""
    cur.execute(f"SELECT id, {', '.join(COLUMNS)} FROM mas_employee_data")
    rows = {}
    for row in cur.fetchall():
        d = {"_id": row[0]}
        for i, col in enumerate(COLUMNS):
            d[col] = row[i + 1]
        d["_hash"] = row_hash(d)
        key = (d["empcode"], d["poscode"])
        rows[key] = d
    return rows


def sync():
    api_records = fetch_from_api()

    # Build API lookup keyed by (empcode, poscode), sorted by empcode for consistent id ordering
    api_map = {}
    for emp in sorted(api_records, key=lambda e: e.get("empcode", "")):
        d = emp_to_dict(emp)
        key = (d["empcode"], d["poscode"])
        api_map[key] = d

    conn = get_conn()
    cur = conn.cursor()
    db_map = fetch_from_db(cur)
    print(f"DB   : {len(db_map)} existing rows")

    api_keys = set(api_map.keys())
    db_keys  = set(db_map.keys())

    to_insert = api_keys - db_keys
    to_delete = db_keys - api_keys
    to_check  = api_keys & db_keys

    to_update = []
    for key in to_check:
        api_hash = row_hash(api_map[key])
        if api_hash != db_map[key]["_hash"]:
            to_update.append(key)

    print(f"\nDiff : +{len(to_insert)} insert  ~{len(to_update)} update  -{len(to_delete)} delete")

    if DRY_RUN:
        if to_insert:
            print("\nINSERT samples (first 3):")
            for key in list(to_insert)[:3]:
                d = api_map[key]
                print(f"  {d['empcode']} | {d['fullnameth']} | {d['posnameth']}")
        if to_update:
            print("\nUPDATE samples (first 3):")
            for key in to_update[:3]:
                print(f"  {key[0]} | {key[1]}")
        if to_delete:
            print("\nDELETE samples (first 3):")
            for key in list(to_delete)[:3]:
                d = db_map[key]
                print(f"  {d['empcode']} | {d['fullnameth']} | {d['posnameth']}")
        conn.close()
        return

    placeholders = ", ".join(["?"] * len(COLUMNS))
    col_list = ", ".join(COLUMNS)
    insert_sql = f"INSERT INTO mas_employee_data (id, {col_list}) VALUES (?, {placeholders})"

    set_clause = ", ".join(f"{c} = ?" for c in COLUMNS)
    update_sql = f"UPDATE mas_employee_data SET {set_clause} WHERE id = ?"

    # Use max existing id as base for new sequential ids
    cur.execute("SELECT ISNULL(MAX(CAST(id AS INT)), 0) FROM mas_employee_data")
    next_id = cur.fetchone()[0] + 1

    for key in to_insert:
        d = api_map[key]
        row = (str(next_id),) + tuple(d[c] for c in COLUMNS)
        cur.execute(insert_sql, row)
        next_id += 1

    for key in to_update:
        d = api_map[key]
        row = tuple(d[c] for c in COLUMNS) + (db_map[key]["_id"],)
        cur.execute(update_sql, row)

    for key in to_delete:
        cur.execute("DELETE FROM mas_employee_data WHERE id = ?", db_map[key]["_id"])

    conn.commit()
    conn.close()

    now = datetime.now(THAI_TZ).strftime("%Y-%m-%d %H:%M:%S")
    print(f"Done : inserted={len(to_insert)}  updated={len(to_update)}  deleted={len(to_delete)}  at {now} (Thai time)")


if __name__ == "__main__":
    sync()
