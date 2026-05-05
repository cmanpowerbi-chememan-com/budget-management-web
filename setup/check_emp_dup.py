"""Check if (empcode, poscode) is a unique composite key in API data"""
import os, requests
from datetime import datetime, timezone, timedelta
from dotenv import load_dotenv

load_dotenv(r"c:\04.budget_management_web\.env")

THAI_TZ = timezone(timedelta(hours=7))
today = datetime.now(THAI_TZ).strftime("%Y-%m-%d")

resp = requests.post(
    os.getenv("CPOP_HR_SYSTEM_API_URL"),
    headers={"Authorization": os.getenv("CPOP_HR_SYSTEM_API_KEY"), "Content-Type": "application/json"},
    json={"keyDate": today, "empCode": ""},
    timeout=30,
)
emps = resp.json()["employeeList"]
active = [e for e in emps if e.get("hr status") == "Active"]

pairs = [(e["empcode"], e["poscode"]) for e in active]
print(f"Active records : {len(active)}")
print(f"Unique (empcode, poscode): {len(set(pairs))}")

# Show duplicates if any
from collections import Counter
dupes = [(k, v) for k, v in Counter(pairs).items() if v > 1]
if dupes:
    print(f"Duplicate pairs: {dupes}")
else:
    print("No duplicates — (empcode, poscode) is a safe composite key")
