"""Trigger the budget-masters sync for `cc_filler_map` on demand, then verify it landed.

`dbo.cc_filler_map` is a daily ~06:30 sync of SharePoint `cc dept.xlsx` (ADR-0018/0022). After
editing that master you either wait for the next run or trigger it here.

The notebook lives in the DW workspace, NOT this repo:
  workspace `cman-dw-ws`  adeb7108-689b-4ba0-af1c-7648970f5581
  notebook  NB_budget_masters_sync  c2908a41-5508-420c-b1cb-d5fc2891b64b
Its cell 0 is tagged `parameters` and declares `env`, `batch_id`, `only_spec`; the per-file loop
skips any entry whose `spec_name != only_spec`, so passing `Budget_Masters_cc_filler_map` runs
exactly one file and leaves the other seven masters untouched.

Two gotchas this script is written around:
  * C4 — the DW repo's `run_notebook.py --param` sends a broken body shape. The shape used here
    (`executionData.parameters.<name>.{value,type}`, type = the DATA type, "string") is the one
    proven to work by REST.
  * C1 — "Completed" is not proof. The run is only believed after `dbo.cc_filler_map` is
    re-read and the expected row is actually present.

The sync carries an RLS integrity guard: any `filler_email` missing from
`dbo.v_employee_budget_01` fails the WHOLE run with `rows_out=0` and leaves the live table
frozen at its last-good contents (28 consecutive failures, 2026-08-26..31). A "failed" status
here therefore means the table did NOT change, not that it half-changed.

Usage:
    python -X utf8 setup/run_ccfiller_sync.py
"""
from __future__ import annotations

import os
import time
from datetime import datetime, timezone
from pathlib import Path

import msal
import pyodbc
import requests
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(dotenv_path=str(ROOT / "backend" / ".env"))
load_dotenv(dotenv_path=str(ROOT / ".env"))

WORKSPACE = "adeb7108-689b-4ba0-af1c-7648970f5581"
NOTEBOOK = "c2908a41-5508-420c-b1cb-d5fc2891b64b"
SPEC = "Budget_Masters_cc_filler_map"

WATCH = ("10IT012000", "10IT011300", "10IT013000")
EXPECT_EMAIL = "pornthipp@chememan.com"
EXPECT_CC = "10IT012000"


def fabric_token() -> str:
    app = msal.ConfidentialClientApplication(
        os.getenv("ENTRA_CLIENT_ID"),
        authority=f"https://login.microsoftonline.com/{os.getenv('ENTRA_TENANT_ID')}",
        client_credential=os.getenv("ENTRA_CLIENT_SECRET"),
    )
    res = app.acquire_token_for_client(scopes=["https://api.fabric.microsoft.com/.default"])
    if "access_token" not in res:
        raise RuntimeError(f"Fabric token error: {res.get('error_description', res)}")
    return res["access_token"]


def sql_conn() -> pyodbc.Connection:
    """Connect to the app's live Fabric SQL DB, reading host/db from the prd container.

    The repo `.env` still points at the retired DB1 (ADR-0023), where these objects do not
    exist, so it is not trusted here.
    """
    import json
    import subprocess

    server = database = None
    try:
        out = subprocess.run(
            ["az", "containerapp", "show", "-n", "cman-budget-web-prd",
             "-g", "CMAN-BUDGET-MNGT-WEB-RG",
             "--query", "properties.template.containers[0].env", "-o", "json"],
            capture_output=True, text=True, timeout=120, shell=True,
        )
        env = {e["name"]: e.get("value") for e in json.loads(out.stdout[out.stdout.find("["):])}
        server, database = env.get("FABRIC_SQL_SERVER"), env.get("FABRIC_SQL_DATABASE")
    except Exception as exc:  # noqa: BLE001
        print(f"  (container env unreadable: {exc.__class__.__name__}; falling back to .env)")
    server = server or os.getenv("FABRIC_SQL_SERVER")
    database = database or os.getenv("FABRIC_SQL_DATABASE")
    return pyodbc.connect(
        f"DRIVER={{ODBC Driver 17 for SQL Server}};SERVER={server};DATABASE={database};"
        "Authentication=ActiveDirectoryServicePrincipal;"
        f"UID={os.getenv('ENTRA_CLIENT_ID')};PWD={os.getenv('ENTRA_CLIENT_SECRET')};"
        "Encrypt=yes;TrustServerCertificate=no;",
        timeout=90,
    )


def snapshot(tag: str) -> dict:
    with sql_conn() as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT COUNT(*), COUNT(DISTINCT cost_center), MAX(_load_dttm) FROM dbo.cc_filler_map"
        )
        rows, ccs, load = cur.fetchone()
        cur.execute(
            "SELECT cost_center, filler_email FROM dbo.cc_filler_map "
            "WHERE cost_center IN (?,?,?) ORDER BY cost_center, filler_email", *WATCH
        )
        watch = [(r[0], r[1]) for r in cur.fetchall()]
    print(f"\n-- {tag} --")
    print(f"  rows={rows}  cost_centers={ccs}  _load_dttm={load}")
    for cc, em in watch:
        print(f"    {cc} | {em}")
    return {"rows": rows, "ccs": ccs, "load": load, "watch": watch}


def main() -> None:
    print(f"=== on-demand sync · spec {SPEC} ===")
    before = snapshot("BEFORE")

    token = fabric_token()
    body = {
        "executionData": {
            "parameters": {
                "env": {"value": "PRD", "type": "string"},
                "only_spec": {"value": SPEC, "type": "string"},
            }
        }
    }
    r = requests.post(
        f"https://api.fabric.microsoft.com/v1/workspaces/{WORKSPACE}"
        f"/items/{NOTEBOOK}/jobs/instances?jobType=RunNotebook",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        json=body,
    )
    print(f"\nsubmit: HTTP {r.status_code}")
    if r.status_code not in (200, 202):
        raise SystemExit(f"submit failed: {r.text[:600]}")
    job_url = r.headers.get("Location")
    print(f"job: {job_url}")

    started = time.time()
    status = "Unknown"
    detail = {}
    while time.time() - started < 1500:
        time.sleep(15)
        p = requests.get(job_url, headers={"Authorization": f"Bearer {token}"})
        if p.status_code != 200:
            print(f"  poll HTTP {p.status_code}: {p.text[:200]}")
            continue
        detail = p.json()
        status = detail.get("status", "Unknown")
        print(f"  [{int(time.time() - started):4d}s] {status}")
        if status in ("Completed", "Failed", "Cancelled", "Deduped"):
            break

    print(f"\nfinal status: {status}")
    if detail.get("failureReason"):
        print(f"failureReason: {detail['failureReason']}")

    # C1 — "Completed" is not proof. Verify the table.
    after = snapshot("AFTER")

    moved = after["load"] != before["load"]
    landed = (EXPECT_CC, EXPECT_EMAIL) in after["watch"]
    print("\n-- verdict --")
    print(f"  _load_dttm advanced : {moved}  ({before['load']} -> {after['load']})")
    print(f"  ({EXPECT_CC}, {EXPECT_EMAIL}) present : {landed}")
    print(f"  row count {before['rows']} -> {after['rows']}  (expect +1)")
    if status == "Completed" and moved and landed:
        print("\nPASS — the sync ran and the new filler row is live.")
    elif status == "Completed" and not landed:
        print("\nFAIL — job reported Completed but the row is NOT in the table. Do not trust the "
              "status; check config.ingest_run_log for this spec (the RLS guard fails a run with "
              "rows_out=0 and leaves the table unchanged).")
    else:
        print("\nFAIL — the table did not change. The live table keeps its last-good contents.")
    print(f"\nchecked at {datetime.now(timezone.utc).isoformat(timespec='seconds')}")


if __name__ == "__main__":
    main()
