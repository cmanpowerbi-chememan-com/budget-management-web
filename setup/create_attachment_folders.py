"""Bulk-create SharePoint attachment folders `เอกสาร ฝ่าย/<ฝ่าย>/<year>/`
for every department (Appendix E decision 4, P3-39 — the app never
auto-creates these, `app/attachments.py` returns folder_not_found for a
missing folder, so each rollout wave needs them pre-created).

Department list = every distinct department resolvable from
`dbo.cc_filler_map` (same source the app uses), folder names sanitized with
the app's own `sanitize_department_folder` so paths match exactly what the
upload endpoint will look up.

Safety:
- Default = DRY-RUN (lists what WOULD be created, zero Graph writes).
  `--apply` is required to actually create folders.
- Existing folders are never touched (`conflictBehavior: fail`; a 409
  conflict is reported as "exists", not an error).

Run from repo root:
    python setup/create_attachment_folders.py --fiscal-year 2027            # dry-run
    python setup/create_attachment_folders.py --fiscal-year 2027 --apply    # create
"""
import argparse
import sys
from pathlib import Path

# Windows console defaults to cp1252 which cannot encode Thai folder names.
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# Make `app.*` importable regardless of the caller's cwd.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

import httpx  # noqa: E402

from app.attachments import (  # noqa: E402
    GRAPH_BASE,
    AttachmentTransportError,
    _get_graph_token,
    _resolve_site_and_drive,
    sanitize_department_folder,
)
from app.config import get_settings  # noqa: E402
from app.db import get_fabric_conn  # noqa: E402
from app.read_model import fetch_cc_dims  # noqa: E402


def _all_departments(conn) -> list[str]:
    """Every distinct department in dbo.cc_filler_map, sorted — the same
    cc→department mapping the app itself uses (fetch_cc_dims, D11 tie-break)."""
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT DISTINCT cost_center FROM dbo.cc_filler_map WHERE cost_center IS NOT NULL")
        cost_centers = [r[0] for r in cursor.fetchall()]
    finally:
        cursor.close()
    dims = fetch_cc_dims(conn, cost_centers)
    return sorted({d["department"] for d in dims.values() if d.get("department")})


def _create_folder(token: str, drive_id: str, parent_path: str, name: str) -> str:
    """Create ONE folder level. Returns 'created' | 'exists'.
    parent_path is the library-relative path of the parent ('' = drive root)."""
    if parent_path:
        url = f"{GRAPH_BASE}/drives/{drive_id}/root:/{parent_path}:/children"
    else:
        url = f"{GRAPH_BASE}/drives/{drive_id}/root/children"
    resp = httpx.post(
        url,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        json={"name": name, "folder": {}, "@microsoft.graph.conflictBehavior": "fail"},
        timeout=30,
    )
    if resp.status_code == 409:
        return "exists"
    if resp.status_code in (200, 201):
        return "created"
    raise AttachmentTransportError(f"create folder {parent_path}/{name} failed: {resp.status_code} {resp.text}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fiscal-year", type=int, required=True, help="planning fiscal year folder to create")
    parser.add_argument("--apply", action="store_true", help="actually create folders (default: dry-run)")
    args = parser.parse_args()

    settings = get_settings()
    root = settings.attachments_root_folder.strip("/")

    with get_fabric_conn(settings) as conn:
        departments = _all_departments(conn)
    print(f"mode={'APPLY' if args.apply else 'DRY-RUN'} root={root!r} year={args.fiscal_year} departments={len(departments)}")

    # Read-only connectivity check in BOTH modes: token + site + library must
    # resolve before we promise anything (catches bad config in dry-run too).
    token = _get_graph_token(settings)
    _site_id, drive_id = _resolve_site_and_drive(token, settings)
    print(f"graph OK: site={settings.attachments_site_name} library={settings.attachments_library_name!r} resolved")

    if not args.apply:
        for dept in departments:
            print(f"  would create: {root}/{sanitize_department_folder(dept)}/{args.fiscal_year}")
        print("\ndry-run complete — re-run with --apply to create")
        return 0

    created = existed = failed = 0
    for dept in departments:
        dept_folder = sanitize_department_folder(dept)
        try:
            # Two levels: <root>/<ฝ่าย> then <root>/<ฝ่าย>/<year> (Graph has
            # no recursive mkdir; a 409 on the parent just means it exists).
            r1 = _create_folder(token, drive_id, root, dept_folder)
            r2 = _create_folder(token, drive_id, f"{root}/{dept_folder}", str(args.fiscal_year))
            status = f"dept:{r1} year:{r2}"
            created += (r1 == "created") + (r2 == "created")
            existed += (r1 == "exists") + (r2 == "exists")
            print(f"  OK {dept}: {status}")
        except AttachmentTransportError as exc:
            failed += 1
            print(f"  FAIL {dept}: {exc}")

    print(f"\nsummary: created={created} existed={existed} failed={failed} (departments={len(departments)})")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
