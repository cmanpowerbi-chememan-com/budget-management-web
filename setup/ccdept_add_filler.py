"""Add (or remove) one Cost Center -> Filler row in the SharePoint master `cc dept.xlsx`.

`dbo.cc_filler_map` is a READ-ONLY daily sync target of this Excel file (ADR-0018/0022) —
editing the table directly is overwritten by the next ~06:30 run, so the master is the only
correct place to change a filler mapping.

Default mode is a DRY RUN that changes nothing: it resolves the file, records its version and
eTag, saves a timestamped backup, prints the rows that will be touched, and stops. Pass
`--apply` to actually write, and `--remove` to undo instead of add.

SAFETY — read before using:
  * The sync carries an **RLS integrity guard**. If any `filler_email` in this file is absent
    from `dbo.v_employee_budget_01`, the whole run fails with `rows_out=0` and EVERY cc-filler
    update stays frozen until someone fixes it (28 consecutive failed runs, 2026-08-26..31).
    This script therefore refuses to write an email it cannot find in that view.
  * openpyxl saves strip a file's sensitivity label. The label parts are spliced back from the
    original bytes and the result is verified before upload.
  * A SharePoint 423 means the file is open in Excel somewhere.

Usage:
    python -X utf8 setup/ccdept_add_filler.py                     # dry run (default)
    python -X utf8 setup/ccdept_add_filler.py --apply
    python -X utf8 setup/ccdept_add_filler.py --remove --apply
"""
from __future__ import annotations

import argparse
import io
import os
import shutil
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path

import msal
import openpyxl
import pyodbc
import requests
from dotenv import load_dotenv

load_dotenv(dotenv_path=str(Path(__file__).resolve().parent.parent / ".env"))

SITE_PATH = "chememan.sharepoint.com:/sites/CMANDWPRD"
LIBRARY = "Budgeting and Management"
FILE_NAME = "cc dept.xlsx"

# The change this script exists to make (D3 on the UAT-prep map, 2026-09-06).
TARGET_COST_CENTER = "10IT012000"
TARGET_EMAIL = "pornthipp@chememan.com"

BACKUP_DIR = Path(__file__).resolve().parent.parent / ".scratch" / "uat-prep"

TENANT_ID = os.getenv("ENTRA_TENANT_ID")
CLIENT_ID = os.getenv("ENTRA_CLIENT_ID")
CLIENT_SECRET = os.getenv("ENTRA_CLIENT_SECRET")

# Parts openpyxl drops that carry the sensitivity label / custom metadata.
_LABEL_PREFIXES = ("customXml/", "docMetadata/")


def _token() -> str:
    app = msal.ConfidentialClientApplication(
        CLIENT_ID,
        authority=f"https://login.microsoftonline.com/{TENANT_ID}",
        client_credential=CLIENT_SECRET,
    )
    result = app.acquire_token_for_client(scopes=["https://graph.microsoft.com/.default"])
    if "access_token" not in result:
        raise RuntimeError(f"Token error: {result.get('error_description', result)}")
    return result["access_token"]


def _hdr(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def resolve_item(token: str) -> dict:
    """Find `cc dept.xlsx` by walking site -> drive -> root children (no share link needed)."""
    r = requests.get(f"https://graph.microsoft.com/v1.0/sites/{SITE_PATH}", headers=_hdr(token))
    r.raise_for_status()
    site_id = r.json()["id"]

    r = requests.get(
        f"https://graph.microsoft.com/v1.0/sites/{site_id}/drives", headers=_hdr(token)
    )
    r.raise_for_status()
    drives = r.json()["value"]
    drive = next((d for d in drives if d["name"] == LIBRARY), None)
    if drive is None:
        raise RuntimeError(f"library {LIBRARY!r} not found; saw {[d['name'] for d in drives]}")

    r = requests.get(
        f"https://graph.microsoft.com/v1.0/drives/{drive['id']}/root:/{FILE_NAME}",
        headers=_hdr(token),
    )
    r.raise_for_status()
    item = r.json()
    return {
        "driveId": drive["id"],
        "id": item["id"],
        "name": item["name"],
        "eTag": item.get("eTag"),
        "cTag": item.get("cTag"),
        "size": item.get("size"),
        "lastModifiedDateTime": item.get("lastModifiedDateTime"),
        "lastModifiedBy": (item.get("lastModifiedBy") or {}).get("user", {}).get("displayName"),
        "webUrl": item.get("webUrl"),
    }


def current_version(token: str, item: dict) -> str:
    r = requests.get(
        f"https://graph.microsoft.com/v1.0/drives/{item['driveId']}/items/{item['id']}/versions",
        headers=_hdr(token),
    )
    if r.status_code != 200:
        return "?"
    vs = r.json().get("value", [])
    return vs[0]["id"] if vs else "?"


def download(token: str, item: dict) -> bytes:
    r = requests.get(
        f"https://graph.microsoft.com/v1.0/drives/{item['driveId']}/items/{item['id']}/content",
        headers=_hdr(token),
    )
    r.raise_for_status()
    return r.content


def upload(token: str, item: dict, data: bytes) -> dict:
    r = requests.put(
        f"https://graph.microsoft.com/v1.0/drives/{item['driveId']}/items/{item['id']}/content",
        headers={**_hdr(token), "Content-Type": "application/octet-stream"},
        data=data,
    )
    if r.status_code == 423:
        raise RuntimeError("423 Locked — the file is open in Excel somewhere. Close it and retry.")
    if r.status_code not in (200, 201):
        raise RuntimeError(f"Upload failed {r.status_code}: {r.text[:400]}")
    return r.json()


# ── column discovery ─────────────────────────────────────────────────────────
def find_columns(ws) -> tuple[int, int, int]:
    """Return (header_row, cost_center_col, filler_col) by matching header text.

    The live header (2026-09-06) is `Cost Ctr | Description | C Level | สายงาน | ฝ่าย |
    คนกรอกข้อมูล`, so "cost ctr" must be matched as well as the spelled-out forms.
    """
    cc_keys = ("cost ctr", "cost center", "costcenter", "cost_center", "ศูนย์ต้นทุน")
    fill_keys = ("คนกรอกข้อมูล", "filler", "filler_email", "ผู้กรอก")
    for row in range(1, min(ws.max_row, 20) + 1):
        cc_col = fill_col = None
        for col in range(1, ws.max_column + 1):
            v = ws.cell(row=row, column=col).value
            if not isinstance(v, str):
                continue
            low = v.strip().lower()
            if cc_col is None and any(k in low for k in cc_keys):
                cc_col = col
            if fill_col is None and any(k in low for k in fill_keys):
                fill_col = col
        if cc_col and fill_col:
            return row, cc_col, fill_col
    raise RuntimeError("could not locate the Cost Center / filler columns in the header rows")


def split_emails(cell_value) -> list[str]:
    """One cell holds a COMMA-SEPARATED list of fillers, not a single email.

    153 of the 213 cost centers already carry more than one, in the style
    `a@chememan.com, b@chememan.com`. Trailing spaces occur in the live data.
    """
    if not cell_value:
        return []
    return [e.strip() for e in str(cell_value).split(",") if e.strip()]


def scan(ws, header_row: int, cc_col: int, fill_col: int) -> list[dict]:
    rows = []
    for r in range(header_row + 1, ws.max_row + 1):
        cc = ws.cell(row=r, column=cc_col).value
        fl = ws.cell(row=r, column=fill_col).value
        if cc is None and fl is None:
            continue
        rows.append(
            {
                "row": r,
                "cost_center": str(cc).strip() if cc else "",
                "filler": str(fl).strip() if fl else "",
                "emails": split_emails(fl),
            }
        )
    return rows


# ── label preservation ───────────────────────────────────────────────────────
def save_preserving_label(wb, original: bytes) -> bytes:
    """Save `wb`, then splice back the sensitivity-label parts openpyxl dropped."""
    buf = io.BytesIO()
    wb.save(buf)
    saved = buf.getvalue()

    with zipfile.ZipFile(io.BytesIO(original)) as zin:
        keep = [n for n in zin.namelist() if n.startswith(_LABEL_PREFIXES)]
        if not keep:
            return saved  # nothing to preserve
        parts = {n: zin.read(n) for n in keep}
        orig_ct = zin.read("[Content_Types].xml").decode("utf-8")

    with zipfile.ZipFile(io.BytesIO(saved)) as zin:
        existing = set(zin.namelist())
        new_ct = zin.read("[Content_Types].xml").decode("utf-8")

    out = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(saved)) as zin, zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zout:
        for n in zin.namelist():
            data = zin.read(n)
            if n == "[Content_Types].xml":
                # Re-add any Override the label parts need that openpyxl's writer dropped.
                adds = []
                for part in parts:
                    tag = f'PartName="/{part}"'
                    if tag in orig_ct and tag not in new_ct:
                        start = orig_ct.find(tag)
                        lt = orig_ct.rfind("<", 0, start)
                        gt = orig_ct.find(">", start) + 1
                        adds.append(orig_ct[lt:gt])
                if adds:
                    data = new_ct.replace("</Types>", "".join(adds) + "</Types>").encode("utf-8")
            zout.writestr(n, data)
        for n, data in parts.items():
            if n not in existing:
                zout.writestr(n, data)
    return out.getvalue()


def verify_parts(original: bytes, produced: bytes) -> tuple[list[str], list[str]]:
    with zipfile.ZipFile(io.BytesIO(original)) as z:
        want = {n for n in z.namelist() if n.startswith(_LABEL_PREFIXES)}
    with zipfile.ZipFile(io.BytesIO(produced)) as z:
        got = {n for n in z.namelist() if n.startswith(_LABEL_PREFIXES)}
    return sorted(want - got), sorted(want)


# ── RLS integrity guard (the one that froze the sync for 6 days) ─────────────
def _live_db() -> tuple[str, str]:
    """Read the server/database from the running production container, not from `.env`.

    The repo `.env` still points at the retired DB1 (ADR-0023), where this view does not
    exist — trusting it makes the guard fail with "Invalid object name". The container is the
    only trustworthy source. Falls back to `.env` if `az` is unavailable.
    """
    import json
    import subprocess

    try:
        out = subprocess.run(
            [
                "az", "containerapp", "show",
                "-n", "cman-budget-web-prd", "-g", "CMAN-BUDGET-MNGT-WEB-RG",
                "--query", "properties.template.containers[0].env", "-o", "json",
            ],
            capture_output=True, text=True, timeout=120, shell=True,
        )
        env = {e["name"]: e.get("value") for e in json.loads(out.stdout[out.stdout.find("["):])}
        server, database = env.get("FABRIC_SQL_SERVER"), env.get("FABRIC_SQL_DATABASE")
        if server and database:
            return server, database
    except Exception as exc:  # noqa: BLE001
        print(f"  (could not read container env: {exc.__class__.__name__}; falling back to .env)")
    return os.getenv("FABRIC_SQL_SERVER", ""), os.getenv("FABRIC_SQL_DATABASE", "")


def email_exists_in_view(email: str) -> bool:
    server, database = _live_db()
    print(f"  database: {database}")
    conn = pyodbc.connect(
        f"DRIVER={{ODBC Driver 17 for SQL Server}};"
        f"SERVER={server};"
        f"DATABASE={database};"
        "Authentication=ActiveDirectoryServicePrincipal;"
        f"UID={os.getenv('ENTRA_CLIENT_ID')};"
        f"PWD={os.getenv('ENTRA_CLIENT_SECRET')};"
        "Encrypt=yes;TrustServerCertificate=no;",
        timeout=60,
    )
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT COUNT(*) FROM dbo.v_employee_budget_01 WHERE LOWER(email) = LOWER(?)", email
        )
        return cur.fetchone()[0] > 0
    finally:
        conn.close()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="actually write to SharePoint")
    ap.add_argument("--remove", action="store_true", help="remove the row instead of adding it")
    args = ap.parse_args()

    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%SZ")
    mode = "REMOVE" if args.remove else "ADD"
    print(f"=== cc dept.xlsx · {mode} ({TARGET_COST_CENTER}, {TARGET_EMAIL}) ===")
    print(f"mode: {'APPLY (will write)' if args.apply else 'DRY RUN (writes nothing)'}\n")

    token = _token()
    item = resolve_item(token)
    ver = current_version(token, item)
    print("-- SharePoint item (pre-change baseline) --")
    for k in ("name", "id", "driveId", "eTag", "size", "lastModifiedDateTime", "lastModifiedBy"):
        print(f"  {k}: {item[k]}")
    print(f"  current version: {ver}")
    print(f"  webUrl: {item['webUrl']}\n")

    raw = download(token, item)
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    backup = BACKUP_DIR / f"ccdept_BEFORE_{stamp}.xlsx"
    backup.write_bytes(raw)
    print(f"backup saved: {backup}  ({len(raw):,} bytes)\n")

    wb = openpyxl.load_workbook(io.BytesIO(raw))
    ws = wb[wb.sheetnames[0]]
    header_row, cc_col, fill_col = find_columns(ws)
    print(f"sheet {ws.title!r} · header row {header_row} · "
          f"cost-center col {cc_col} · filler col {fill_col} · max_row {ws.max_row}")

    rows = scan(ws, header_row, cc_col, fill_col)
    print(f"data rows: {len(rows)} · distinct cost centers: {len({r['cost_center'] for r in rows})} "
          f"· distinct fillers: {len({r['filler'] for r in rows if r['filler']})}\n")

    print(f"-- verify-target: rows for {TARGET_COST_CENTER} --")
    tgt = [r for r in rows if r["cost_center"] == TARGET_COST_CENTER]
    for r in tgt:
        print(f"  row {r['row']}: cell = {r['filler']!r}")
        print(f"             parsed = {r['emails']}")
    if len(tgt) != 1:
        print(f"\nREFUSING — expected exactly 1 row for {TARGET_COST_CENTER}, found {len(tgt)}.")
        return

    print("\n-- context: the two Data & Analytic cost centers --")
    for cc in ("10IT011300", "10IT013000"):
        for r in [x for x in rows if x["cost_center"] == cc]:
            print(f"  row {r['row']}: {cc} -> {r['emails']}")

    target = tgt[0]
    have = [e for e in target["emails"] if e.lower() == TARGET_EMAIL.lower()]
    print()
    if args.remove:
        if not have:
            print(f"NOTHING TO DO — {TARGET_EMAIL} is not listed on {TARGET_COST_CENTER}.")
            return
        remaining = [e for e in target["emails"] if e.lower() != TARGET_EMAIL.lower()]
        if not remaining:
            print("REFUSING — removing it would leave the cost center with NO filler, which "
                  "would strand the department. Remove by hand if that is genuinely intended.")
            return
        new_value = ", ".join(remaining)
        print(f"WILL EDIT row {target['row']} col {fill_col}")
        print(f"  before: {target['filler']!r}")
        print(f"  after:  {new_value!r}")
    else:
        if have:
            print(f"NOTHING TO DO — {TARGET_EMAIL} is already listed on {TARGET_COST_CENTER}.")
            return
        new_value = ", ".join(target["emails"] + [TARGET_EMAIL])
        print(f"WILL EDIT row {target['row']} col {fill_col} (append, keeping every existing filler)")
        print(f"  before: {target['filler']!r}")
        print(f"  after:  {new_value!r}")
        print(f"  fillers {len(target['emails'])} -> {len(target['emails']) + 1}; "
              f"existing filler(s) {target['emails']} are PRESERVED")

        print("\n-- RLS integrity guard --")
        try:
            ok = email_exists_in_view(TARGET_EMAIL)
        except Exception as exc:  # noqa: BLE001
            print(f"  COULD NOT CHECK ({exc.__class__.__name__}: {exc}) — refusing to write.")
            return
        if not ok:
            print(f"  REFUSING — {TARGET_EMAIL} is NOT in dbo.v_employee_budget_01. Writing it "
                  "would fail the sync with rows_out=0 and freeze every cc-filler update.")
            return
        print(f"  OK — {TARGET_EMAIL} found in dbo.v_employee_budget_01.")

    if not args.apply:
        print("\nDRY RUN — nothing written. Re-run with --apply to make the change.")
        return

    # ── mutate: ONE cell, nothing else ───────────────────────────────────────
    cell = ws.cell(row=target["row"], column=fill_col)
    assert str(cell.value).strip() == target["filler"], "cell drifted between read and write"
    cell.value = new_value
    print(f"\nwrote row {target['row']} col {fill_col} = {new_value!r}")

    # Prove no other cell moved.
    check = openpyxl.load_workbook(io.BytesIO(raw))[ws.title]
    drift = [
        (r, c)
        for r in range(1, ws.max_row + 1)
        for c in range(1, ws.max_column + 1)
        if not (r == target["row"] and c == fill_col)
        and check.cell(row=r, column=c).value != ws.cell(row=r, column=c).value
    ]
    print(f"cells changed besides the target: {len(drift)}  {drift[:5]}")
    if drift:
        print("  ABORTING — the edit touched cells it should not have.")
        return

    produced = save_preserving_label(wb, raw)
    missing, wanted = verify_parts(raw, produced)
    print(f"\nsensitivity-label parts in original: {len(wanted)} · missing after save: {len(missing)}")
    if missing:
        print(f"  ABORTING — these parts would be lost: {missing}")
        return

    after = BACKUP_DIR / f"ccdept_AFTER_{stamp}.xlsx"
    after.write_bytes(produced)
    print(f"local result saved: {after}  ({len(produced):,} bytes)")

    res = upload(token, item, produced)
    print("\n-- uploaded --")
    print(f"  new eTag: {res.get('eTag')}")
    print(f"  size:     {res.get('size')}")
    print(f"  modified: {res.get('lastModifiedDateTime')}")
    print(f"  version:  {current_version(token, item)}  (was {ver})")
    print("\nNOTE: dbo.cc_filler_map does NOT change until the next ~06:30 sync run.")


if __name__ == "__main__":
    main()
