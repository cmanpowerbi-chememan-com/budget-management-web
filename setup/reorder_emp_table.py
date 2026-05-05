"""
reorder_emp_table.py — Rebuild mas_employee_data with rows ordered by empcode
Run once to reset id sequence aligned to empcode order.
After this, daily sync will INSERT new rows continuing from max id.
"""
import os, requests, pyodbc
from datetime import datetime, timezone, timedelta
from dotenv import load_dotenv

load_dotenv(r"c:\04.budget_management_web\.env")

THAI_TZ = timezone(timedelta(hours=7))
DATE_FIELDS = {"hiringdate", "terminatedate", "birthdate"}

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


def fetch_active():
    today = datetime.now(THAI_TZ).strftime("%Y-%m-%d")
    resp = requests.post(
        os.getenv("CPOP_HR_SYSTEM_API_URL"),
        headers={"Authorization": os.getenv("CPOP_HR_SYSTEM_API_KEY"), "Content-Type": "application/json"},
        json={"keyDate": today, "empCode": ""},
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()
    active = [e for e in data["employeeList"] if e.get("hr status") == "Active"]
    return sorted(active, key=lambda e: e.get("empcode", ""))


def to_row(emp):
    def val(col):
        api_key = "hr status" if col == "hr_status" else col
        v = emp.get(api_key, "") or ""
        return (v if v else None) if col in DATE_FIELDS else (v if v else None)
    return tuple(val(col) for col in COLUMNS)


conn = pyodbc.connect(
    "DRIVER={ODBC Driver 17 for SQL Server};"
    f"SERVER={os.getenv('DB_SERVER')};"
    f"DATABASE={os.getenv('DB_NAME')};"
    f"UID={os.getenv('DB_USER')};"
    f"PWD={os.getenv('DB_PASSWORD')};"
    "Encrypt=yes;TrustServerCertificate=no;Connection Timeout=30;"
)
cur = conn.cursor()

print("Fetching from API...", end=" ")
active = fetch_active()
print(f"{len(active)} Active employees")

print("Clearing table...", end=" ")
cur.execute("DELETE FROM mas_employee_data")
print(f"deleted {cur.rowcount} rows")

placeholders = ", ".join(["?"] * len(COLUMNS))
col_list = ", ".join(COLUMNS)
insert_sql = f"INSERT INTO mas_employee_data (id, {col_list}) VALUES (?, {placeholders})"

print("Inserting ordered by empcode...", end=" ")
for i, emp in enumerate(active, start=1):
    cur.execute(insert_sql, (str(i),) + to_row(emp))

conn.commit()
conn.close()
print(f"{len(active)} rows inserted")
print("Done — table now ordered by empcode (id 1..N)")
