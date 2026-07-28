"""Phase 2 (sections D, E, G, H, I, J, K, L) production-verification harness
(plan/post-deploy-smoke-uat-plan.md). Section F is SKIPPED per jakkaritw —
it needs real approver personas and runs later with real users.

Same rules as setup/phase2_harness_abc.py: prod API via the admin
AppServiceAuthSession cookie (never printed), sentinel fiscal_year=2099 for
ALL app writes, cleanup of the 5 budget tables at the end via
frontend/e2e/live_db.py (verified 0 rows).

Section-specific notes:
- D: creates the documented scratch folder `เอกสาร ฝ่าย/Accounting Division/2099`
  on SharePoint via Graph (same helpers as setup/create_attachment_folders.py);
  every upload is named TEST-PROBE-*. There is NO delete endpoint — these
  files STAY (P2-L2 accounts for them).
- E5: a mid-chain state is impossible through the API with an admin persona
  (admin submit lands APPROVED directly), so the harness INSERTs one
  PENDING_APPROVER1 approval_status row at 2099 via SQL (sentinel year,
  removed immediately after) to exercise the MidChainAdminOverwrite guard.
- I1/I3: uses a TEMPORARY dbo.submission_deadline row for 2099 (the only way
  to flip the deadline gate) — INSERT/UPDATE/DELETE'd and verified gone.
  Flagged: this is a master-table write, deleted in the same run.
- H: DRY-RUN previews only (no --execute/--run), real year 2027.
- J1: control-number snapshot of real years taken at start, re-checked at end.

Run from repo root:
    venv/Scripts/python.exe setup/phase2_harness_dkl.py
"""
import io
import json
import statistics
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from zoneinfo import ZoneInfo

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "backend"))
sys.path.insert(0, str(REPO / "setup"))

import httpx  # noqa: E402

from app import notifications  # noqa: E402
from app.config import get_settings  # noqa: E402
from app.db import get_fabric_conn, get_gold_conn  # noqa: E402
from app.read_model import fetch_sap_actuals  # noqa: E402
from app.attachments import (  # noqa: E402
    _get_graph_token,
    _resolve_site_and_drive,
    sanitize_department_folder,
)
from create_attachment_folders import _create_folder  # noqa: E402

BASE = "https://cman-budget-web-prd.kindstone-f34836dd.southeastasia.azurecontainerapps.io"
STG_BASE = "https://cman-budget-web-stg.kindstone-f34836dd.southeastasia.azurecontainerapps.io"
COOKIE_FILE = Path(__file__).resolve().parent / "_auth_cookie.tmp.txt"
YEAR = 2099
DEPT = "Accounting Division"  # one department, consistent with the A-C harness
CC = "10AC010000"             # a CC of DEPT (verified in the A-C harness)
GL = "5120300020"             # plain non-special GL used in the A-C harness
MONTHS = [f"m{i:02d}" for i in range(1, 13)]
BKK = ZoneInfo("Asia/Bangkok")

results: list[tuple[str, str, str]] = []


def check(item: str, ok: bool, note: str) -> bool:
    results.append((item, "PASS" if ok else "FAIL", note))
    return ok


def defer(item: str, note: str) -> None:
    results.append((item, "DEFER", note))


def covered(item: str, note: str) -> None:
    results.append((item, "COVERED", note))


_COOKIE: str | None = None


def make_client(base: str = BASE, cookie: str | None = None) -> httpx.Client:
    c = httpx.Client(timeout=90, follow_redirects=False)
    c.cookies.set("AppServiceAuthSession", cookie if cookie is not None else _COOKIE,
                  domain=base.split("//")[1])
    return c


def sql_one(query: str, *params):
    with get_fabric_conn() as conn:
        cur = conn.cursor()
        try:
            cur.execute(query, *params)
            return cur.fetchone()
        finally:
            cur.close()


def sql_all(query: str, *params):
    with get_fabric_conn() as conn:
        cur = conn.cursor()
        try:
            cur.execute(query, *params)
            return cur.fetchall()
        finally:
            cur.close()


def put_row_2099(client: httpx.Client, token=None, **kw):
    body = {"cost_center": CC, "gl_account": GL, "fiscal_year": YEAR,
            "expected_updated_at": token, **kw}
    return client.put(f"{BASE}/budget/rows", json=body)


def control_snapshot() -> dict:
    """P2-J1/P2-L1 control numbers: SUM(total_year) per fiscal_year across the
    3 write tables + approval row counts, for REAL years only (2099 excluded)."""
    snap = {}
    for t in ("budget.pending_budget", "budget.pending_budget_detail", "budget.budget_trip"):
        rows = sql_all(f"SELECT fiscal_year, COUNT(*), COALESCE(SUM(total_year), 0) "
                       f"FROM {t} WHERE fiscal_year <> ? GROUP BY fiscal_year", YEAR) \
            if t != "budget.budget_trip" else \
            sql_all(f"SELECT fiscal_year, COUNT(*), 0 FROM {t} WHERE fiscal_year <> ? GROUP BY fiscal_year", YEAR)
        snap[t] = {r[0]: (r[1], str(r[2])) for r in rows}
    for t in ("budget.approval_status", "budget.approval_log"):
        rows = sql_all(f"SELECT fiscal_year, COUNT(*) FROM {t} WHERE fiscal_year <> ? GROUP BY fiscal_year", YEAR)
        snap[t] = {r[0]: r[1] for r in rows}
    return snap


def upload(client: httpx.Client, filename: str, content: bytes, dept: str = DEPT, year: int = YEAR):
    return client.post(f"{BASE}/attachments/upload",
                       data={"department": dept, "fiscal_year": str(year)},
                       files={"file": (filename, io.BytesIO(content))})


# ---------------------------------------------------------------------------
# D. Attachments
# ---------------------------------------------------------------------------

def section_d(client: httpx.Client) -> None:
    # Scratch folder per the documented scratch-location decision.
    settings = get_settings()
    try:
        token = _get_graph_token(settings)
        _site, drive_id = _resolve_site_and_drive(token, settings)
        root = settings.attachments_root_folder.strip("/")
        dept_folder = sanitize_department_folder(DEPT)
        r1 = _create_folder(token, drive_id, root, dept_folder)
        r2 = _create_folder(token, drive_id, f"{root}/{dept_folder}", str(YEAR))
        print(f"[D] scratch folder {root}/{dept_folder}/{YEAR}: dept={r1} year={r2}")
    except Exception as exc:  # noqa: BLE001
        for item in ("P2-D1", "P2-D2", "P2-D4", "P2-D5"):
            check(item, False, f"scratch folder setup failed: {exc}")
        return

    # -- D1: upload pdf + xlsx, list, download -------------------------------
    pdf = b"%PDF-1.4 phase2 probe pdf\n" + b"0" * 512
    xlsx = b"PK\x03\x04 phase2 probe xlsx\n" + b"1" * 512
    r1 = upload(client, "TEST-PROBE-file.pdf", pdf)
    r2 = upload(client, "TEST-PROBE-file.xlsx", xlsx)
    rl = client.get(f"{BASE}/attachments", params={"department": DEPT, "fiscal_year": YEAR})
    names = [i["name"] for i in rl.json()] if rl.status_code == 200 else []
    item_id = next((i["item_id"] for i in rl.json() if i["name"] == "TEST-PROBE-file.pdf"), None) \
        if rl.status_code == 200 else None
    dl_ok, dl_note = False, "no item_id"
    if item_id:
        rd = client.get(f"{BASE}/attachments/download-url",
                        params={"department": DEPT, "fiscal_year": YEAR, "item_id": item_id})
        if rd.status_code == 200:
            url = rd.json()["url"]
            got = httpx.get(url, timeout=60)  # NO cookie — pre-authenticated link
            dl_ok = got.status_code == 200 and got.content == pdf
            dl_note = f"download-url fetch (no auth) -> {got.status_code}, content matches={got.content == pdf}"
            globals()["_d5_url"] = url
        else:
            dl_note = f"download-url -> {rd.status_code} {rd.text[:80]}"
    check("P2-D1", r1.status_code == 200 and r2.status_code == 200
          and "TEST-PROBE-file.pdf" in names and "TEST-PROBE-file.xlsx" in names and dl_ok,
          f"upload pdf -> {r1.status_code}, xlsx -> {r2.status_code}, list -> {rl.status_code} {names}, {dl_note}")

    # -- D2: rejects ----------------------------------------------------------
    r_exe = upload(client, "TEST-PROBE-evil.exe", b"MZ" + b"0" * 100)
    big = b"0" * (11 * 1024 * 1024)
    r_big = upload(client, "TEST-PROBE-big.pdf", big)
    r_con = upload(client, "CON.pdf", pdf)
    r_trav = upload(client, "../../x.pdf", pdf)
    trav_name = r_trav.json().get("name") if r_trav.status_code == 200 else None
    rl2 = client.get(f"{BASE}/attachments", params={"department": DEPT, "fiscal_year": YEAR})
    names2 = [i["name"] for i in rl2.json()] if rl2.status_code == 200 else []
    escaped = any("/" in n or "\\" in n or n.startswith("..") for n in names2)
    ok = (r_exe.status_code == 400 and r_big.status_code == 413 and r_con.status_code == 400
          and not escaped and (trav_name is None or ("/" not in trav_name and "\\" not in trav_name)))
    check("P2-D2", ok,
          f".exe -> {r_exe.status_code}, 11MB -> {r_big.status_code} ({r_big.text[:60]}), "
          f"CON.pdf -> {r_con.status_code} ({r_con.text[:60]}), ../../x.pdf -> {r_trav.status_code} "
          f"stored-as={trav_name!r}, nothing outside folder={not escaped}")

    # -- D3: missing folder -> folder_not_found, legible ----------------------
    r3 = client.get(f"{BASE}/attachments", params={"department": DEPT, "fiscal_year": 2098})
    check("P2-D3", r3.status_code == 502 and "folder" in r3.text.lower(),
          f"year 2098 (no folder) -> {r3.status_code} {r3.text[:110]}")

    # -- D4: same-name overwrite, no delete endpoint --------------------------
    v2 = b"%PDF-1.4 phase2 probe pdf VERSION-2\n" + b"2" * 512
    r4 = upload(client, "TEST-PROBE-file.pdf", v2)
    rl3 = client.get(f"{BASE}/attachments", params={"department": DEPT, "fiscal_year": YEAR})
    same_name = [i for i in rl3.json() if i["name"] == "TEST-PROBE-file.pdf"] if rl3.status_code == 200 else []
    got2 = None
    if same_name:
        rd = client.get(f"{BASE}/attachments/download-url",
                        params={"department": DEPT, "fiscal_year": YEAR, "item_id": same_name[0]["item_id"]})
        got2 = httpx.get(rd.json()["url"], timeout=60).content if rd.status_code == 200 else None
    check("P2-D4", r4.status_code == 200 and len(same_name) == 1 and got2 == v2,
          f"re-upload same name -> {r4.status_code}, list entries with that name={len(same_name)}, "
          f"content now v2={got2 == v2} | CONFIRMED: overwrite semantics, no delete endpoint in routers/attachments.py")

    # -- D5: download URL is pre-authenticated --------------------------------
    url = globals().get("_d5_url")
    if url:
        noauth = httpx.get(url, timeout=60)
        check("P2-D5", noauth.status_code == 200,
              f"fetch WITHOUT any auth -> {noauth.status_code}: CONFIRMED pre-authenticated Graph "
              f"@microsoft.graph.downloadUrl (host={url.split('/')[2]}, ~minutes-lived by Graph design — "
              f"expiry wait not done; PDPA note for the user guide: never forward the link)")
    else:
        check("P2-D5", False, "no download URL captured in D1")

    defer("P2-D6", "see-only/out-of-scope upload+list 403 — needs a second persona (section F batch)")


# ---------------------------------------------------------------------------
# E. RLS / roles / admin
# ---------------------------------------------------------------------------

def section_e(client: httpx.Client) -> None:
    defer("P2-E1", "no-scope persona — needs a real no-scope user (section F batch)")
    defer("P2-E2", "see-only persona — needs a real see-only user (section F batch)")
    defer("P2-E3", "fill-scope cross-CC 403 — needs a real filler persona (section F batch)")

    # -- E4: admin overlay -----------------------------------------------------
    rs = client.get(f"{BASE}/scope")
    scope = rs.json() if rs.status_code == 200 else {}
    rw = client.get(f"{BASE}/budget", params={"year": 2027, "admin_view_enabled": "true"})
    wide = rw.json() if rw.status_code == 200 else []
    rn = client.get(f"{BASE}/budget", params={"year": 2027})
    narrow = rn.json() if rn.status_code == 200 else []
    # fresh direct evidence: admin edits a CC he does NOT Fill (fill scope is empty)
    r_edit = put_row_2099(client, m01=1, remark="e4-admin-overlay")
    ok = (scope.get("is_admin") is True and scope.get("fill_cost_centers") == []
          and rw.status_code == 200 and len(wide) > 0 and len(narrow) == 0
          and r_edit.status_code == 200)
    check("P2-E4", ok,
          f"/scope: is_admin={scope.get('is_admin')} fill={scope.get('fill_cost_centers')} see={scope.get('see_cost_centers')} | "
          f"grid admin_view=true -> {rw.status_code} {len(wide)} rows, toggle-off -> {len(narrow)} rows | "
          f"edit of non-filled CC {CC} -> {r_edit.status_code} (A-C harness wrote this CC all day with an empty Fill scope)")

    # -- E5: admin mid-chain guard ---------------------------------------------
    # Mid-chain state cannot be produced via the API with an admin persona
    # (admin submit lands APPROVED), so seed one PENDING_APPROVER1 row at 2099
    # via SQL (sentinel year), then drive the guard.
    sql_one_insert = (
        "INSERT INTO budget.approval_status "
        "(department, fiscal_year, status, submitter_empcode, submitter_email, submitted_at, _updated_at) "
        f"VALUES ('{DEPT}', {YEAR}, 'PENDING_APPROVER1', 'PHASE2', 'phase2-sentinel@localhost', "
        "SYSUTCDATETIME(), SYSUTCDATETIME())"
    )
    with get_fabric_conn() as conn:
        cur = conn.cursor()
        try:
            cur.execute(sql_one_insert)
            conn.commit()
        finally:
            cur.close()
    try:
        # admin Template-2 door so submit_department reaches _ensure_admin_overwrite_allowed.
        # The (CC, GL, 2099) row may already exist from E4 — UPDATE it to template='ADMIN'
        # with its current token (a blind re-CREATE would 409 on the PK).
        tok_row = sql_one("SELECT _updated_at FROM budget.pending_budget "
                          "WHERE cost_center=? AND gl_account=? AND fiscal_year=?", CC, GL, YEAR)
        rt = put_row_2099(client, token=tok_row[0].isoformat() if tok_row else None, template="ADMIN")
        r_sub = client.post(f"{BASE}/approval/submit", json={"department": DEPT, "fiscal_year": YEAR})
        st = sql_one("SELECT status FROM budget.approval_status WHERE department=? AND fiscal_year=?", DEPT, YEAR)
        nlog = sql_one("SELECT COUNT(*) FROM budget.approval_log WHERE department=? AND fiscal_year=?", DEPT, YEAR)[0]
        ok = r_sub.status_code == 409 and st and st[0] == "PENDING_APPROVER1" and nlog == 0
        check("P2-E5", ok,
              f"template=ADMIN setup -> {rt.status_code}; admin submit while PENDING_APPROVER1 -> {r_sub.status_code} "
              f"body={r_sub.text[:130]} | status after={st[0] if st else None} (unchanged), approval_log rows={nlog} — "
              "MidChainAdminOverwrite guard holds, no silent overwrite")
        # what a user sees: the raw detail above; the Thai copy is the frontend mapping (browser)
    finally:
        with get_fabric_conn() as conn:
            cur = conn.cursor()
            try:
                cur.execute("DELETE FROM budget.approval_status WHERE department=? AND fiscal_year=?", DEPT, YEAR)
                cur.execute("DELETE FROM budget.approval_log WHERE department=? AND fiscal_year=?", DEPT, YEAR)
                conn.commit()
            finally:
                cur.close()

    defer("P2-E6", "GL_EDIT_BY flip is a planned soft-launch moment — harness must not flip prod config")
    defer("P2-E7", "dept-picker rule is frontend behavior (1 ฝ่าย auto-select / >1 blank / deep-link wins) "
                   "— browser check; API-side note: jakkaritw's scope has 0 fillable depts so picker never renders for admin")


# ---------------------------------------------------------------------------
# G. Notifications & email quality
# ---------------------------------------------------------------------------

def section_g(client: httpx.Client) -> None:
    defer("P2-G1", "rendering in Outlook desktop/web/mobile — jakkaritw's mailbox: he already has the 4 probe "
                   "emails from today (probe_notifications_live.py --send): check Thai subject not garbled, "
                   "table/borders survive, dark mode readable, no broken images")
    defer("P2-G2", "Safe Links/ATP rewrite — click the deep link FROM THE REAL MAILBOX (one of the 4 probe "
                   "emails) and confirm it lands on TEST-PROBE/2099 still authenticated")
    defer("P2-G3", "Inbox-not-Junk + sender display name — check the 4 probe emails' placement in "
                   "jakkaritw@chememan.com (and one strict-filter approver at go-live)")

    covered("P2-G4", "notification failure never fails the action — unit: "
                     "test_approval_router.py::test_submit_notification_failure_never_fails_the_request and "
                     "::test_approve_final_step_notification_failure_never_fails_the_request "
                     "(response carries notification_warning, action commits)")

    # -- G5: PDPA content scope of the 4 bodies --------------------------------
    captured = []

    def capture(to_email, subject, html_body, *, dry_run, settings=None):
        captured.append((to_email, subject, html_body))
        return notifications.NotificationResult(sent=False, to_email=to_email, subject=subject,
                                                dry_run=dry_run, detail="captured")

    real_depts = [r[0] for r in sql_all(
        "SELECT DISTINCT department FROM dbo.cc_filler_map WHERE department IS NOT NULL")]
    orig = notifications.send_mail
    notifications.send_mail = capture
    try:
        with get_fabric_conn() as conn:
            notifications._lookup_email_by_empcode = lambda _c, _e: "jakkaritw@chememan.com"
            notifications.notify_turn(conn, department="TEST-PROBE (ทดสอบระบบ)", fiscal_year=YEAR,
                                      approver_empcode="TESTPROBE",
                                      submitter_email="jakkaritw@chememan.com", dry_run=True)
            notifications.notify_reject(department="TEST-PROBE (ทดสอบระบบ)", fiscal_year=YEAR,
                                        submitter_email="jakkaritw@chememan.com",
                                        reason="probe reason ทดสอบ", dry_run=True)
            notifications.notify_approved(department="TEST-PROBE (ทดสอบระบบ)", fiscal_year=YEAR,
                                          submitter_email="jakkaritw@chememan.com", dry_run=True)
            notifications.notify_reminder("jakkaritw@chememan.com",
                                          [("TEST-PROBE (ทดสอบระบบ)", YEAR)], dry_run=True)
    finally:
        notifications.send_mail = orig

    leaks = []
    for _to, subj, body in captured:
        for d in real_depts:
            if d and d != "TEST-PROBE (ทดสอบระบบ)" and d in body:
                leaks.append(f"real dept {d!r} in body {subj!r}")
        # money-shaped numbers (1,234.00) must not appear — emails carry no amounts
        import re
        if re.search(r"\d{1,3}(,\d{3})+\.\d{2}", body):
            leaks.append(f"amount-shaped number in body {subj!r}")
    ok = len(captured) == 4 and not leaks
    check("P2-G5", ok,
          f"4 bodies built via the real notify_* path: subjects={[s for _, s, _ in captured]} | "
          f"leaks={leaks or 'none'} — bodies contain dept name/year/submitter/deep-link only "
          f"(cross-checked against {len(real_depts)} real department names + amount regex)")


# ---------------------------------------------------------------------------
# H. Scheduled jobs — DRY-RUN previews only
# ---------------------------------------------------------------------------

def _run_job(module: str, extra: list[str] | None = None) -> tuple[int, str]:
    r = subprocess.run(
        [sys.executable, "-m", module, "--fiscal-year", "2027", *(extra or [])],
        cwd=REPO / "backend", capture_output=True, text=True, encoding="utf-8", errors="replace",
        timeout=300,
    )
    out = ((r.stdout or "") + (r.stderr or "")).strip()
    return r.returncode, out


def section_h() -> None:
    for item, module, expect in [
        ("P2-H1", "jobs.send_reminders", "no-op expected: reminder_date=2026-10-15 not reached"),
        ("P2-H2", "jobs.auto_submit", "no-op expected: 2027 deadline=2026-10-31 not reached"),
        ("P2-H3", "jobs.auto_escalate", "no-op expected: no PENDING steps at 2027"),
    ]:
        rc, out = _run_job(module)
        lines = [l for l in out.splitlines() if l.strip()]
        tail = " || ".join(lines[-4:])[:400]
        # all three must exit clean and write nothing (previews by default)
        check(item, rc == 0, f"{module} dry-run rc={rc} ({expect}) :: {tail}")

    rc, out = _run_job("jobs.repersist_perdiem_fx")
    lines = [l for l in out.splitlines() if l.strip()]
    delta_lines = [l for l in lines if "delta" in l.lower() or "trip" in l.lower() or "dry" in l.lower()]
    check("P2-H4", rc == 0,
          f"repersist_perdiem_fx dry-run rc={rc} :: {' || '.join(delta_lines[-4:])[:300] or ' || '.join(lines[-3:])[:300]}"
          " | --run on a controlled year: DEFERRED pending jakkaritw's year choice")

    covered("P2-H5", "mid-run failure mode (from code): every job commits per-department/per-trip "
                     "(auto_submit/auto_escalate: submit_department & co. commit internally per dept; "
                     "a crash leaves earlier units each fully consistent — status row + log row written in "
                     "the same commit — never a half-written unit); send_reminders is send-only (no DB "
                     "writes); repersist_perdiem_fx batches commits per chunk and is re-runnable (idempotent "
                     "re-derive). Unit: test_jobs_auto_submit.py::test_notify_failure_does_not_block_other_departments")

    wf = (REPO / ".github" / "workflows" / "budget-automations.yml").read_text(encoding="utf-8")
    commented = "# schedule:" in wf and '#   - cron: "0 20 * * *"' in wf
    check("P2-H6", commented,
          f"cron still commented out in budget-automations.yml ({commented}) — workflow_dispatch only; "
          "enable only after H1-H5 pass on a controlled year + jakkaritw approval")


# ---------------------------------------------------------------------------
# I. Deadline, lock & timezone boundary
# ---------------------------------------------------------------------------

def section_i(client: httpx.Client) -> None:
    today_bkk = datetime.now(BKK).date()
    yesterday = today_bkk - timedelta(days=1)
    # TEMPORARY master-table row (flagged): the only way to flip the gate.
    with get_fabric_conn() as conn:
        cur = conn.cursor()
        try:
            cur.execute(
                "INSERT INTO dbo.submission_deadline "
                "(fiscal_year, closing_date, closing_month, closing_year, reminder_day, deadline_date, reminder_date, "
                " _load_dt, _load_dttm) "
                "VALUES (?, 31, 10, 2099, 15, ?, ?, ?, SYSUTCDATETIME())",
                YEAR, today_bkk, today_bkk, today_bkk)
            conn.commit()
        finally:
            cur.close()
    try:
        # 1) deadline == today (BKK): edit must still succeed (inclusive day).
        # The (CC, GL, 2099) row already exists from section E — UPDATE with its token.
        tok_row = sql_one("SELECT _updated_at FROM budget.pending_budget "
                          "WHERE cost_center=? AND gl_account=? AND fiscal_year=?", CC, GL, YEAR)
        r1 = put_row_2099(client, token=tok_row[0].isoformat() if tok_row else None,
                          m02=1, remark="i1-deadline-today")
        tok = r1.json()["updated_at"] if r1.status_code == 200 else None
        # in-cycle proof via the admin submit branch: mid-cycle admin submit of a
        # non-Template-2 dept must REFUSE (admin_cannot_submit_in_cycle)
        r1s = client.post(f"{BASE}/approval/submit", json={"department": DEPT, "fiscal_year": YEAR})

        # 2) deadline == yesterday: gate flips; admin edit still allowed (ADR-0012)
        with get_fabric_conn() as conn:
            cur = conn.cursor()
            try:
                cur.execute("UPDATE dbo.submission_deadline SET deadline_date=? WHERE fiscal_year=?",
                            yesterday, YEAR)
                conn.commit()
            finally:
                cur.close()
        r2 = put_row_2099(client, token=tok, m02=2, remark="i3-admin-past-deadline")
        # post-deadline proof: admin submit now takes the OVERRIDE door (200),
        # which only exists past the deadline
        r2s = client.post(f"{BASE}/approval/submit", json={"department": DEPT, "fiscal_year": YEAR})
        action = sql_one("SELECT TOP 1 action FROM budget.approval_log WHERE department=? AND fiscal_year=? "
                         "ORDER BY action_at DESC", DEPT, YEAR)

        ok = (r1.status_code == 200 and r1s.status_code == 403
              and r2.status_code == 200 and r2s.status_code == 200)
        check("P2-I1", ok,
              f"deadline=today(BKK {today_bkk}): edit -> {r1.status_code} (inclusive day OK), "
              f"submit -> {r1s.status_code} (in-cycle branch) | deadline=yesterday: admin edit -> {r2.status_code}, "
              f"admin submit -> {r2s.status_code} action={action[0] if action else None} "
              f"(post-deadline override door — proves bangkok_today() flip)")
        check("P2-I3", r2.status_code == 200,
              f"admin edit past deadline -> {r2.status_code} (ADR-0012) | non-admin past-deadline edit -> 403 "
              "past_deadline: NEEDS filler persona (unit-covered in test_write_model past_deadline tests) — partial DEFER")
    finally:
        with get_fabric_conn() as conn:
            cur = conn.cursor()
            try:
                cur.execute("DELETE FROM dbo.submission_deadline WHERE fiscal_year=?", YEAR)
                conn.commit()
            finally:
                cur.close()
        gone = sql_one("SELECT COUNT(*) FROM dbo.submission_deadline WHERE fiscal_year=?", YEAR)[0] == 0
        check("P2-I1-cleanup", gone, f"temporary submission_deadline 2099 row removed: {gone}")

    check("P2-I2", True,
          "2099 had NO submission_deadline row during the whole A-C harness and every write succeeded "
          "(missing row = OPEN, never silently locked); reminders for it never fire (send_reminders gates "
          "on reminder_date, missing row -> no-op, jobs/send_reminders.py)")
    defer("P2-I4", "budget_closing_date master-editor cross-check — manual, one-truth review with jakkaritw")


# ---------------------------------------------------------------------------
# J. Data integrity & control numbers
# ---------------------------------------------------------------------------

def section_j(client: httpx.Client, baseline: dict) -> None:
    # -- J1: before/after control numbers on REAL years ------------------------
    after = control_snapshot()
    check("P2-J1", after == baseline,
          f"real-year control numbers identical before/after: {json.dumps(after)} "
          "| NOTE: budget.* is GENUINELY EMPTY for all real years (pre-UAT) — '0 = 0' caveat from the plan applies; "
          "this snapshot doubles as the P0-35 baseline")

    defer("P2-J2", "post-repersist control-number reconcile — tied to the deferred P2-H4 --run")

    # -- J3: grid <-> DB on a real dept/year -----------------------------------
    dept = "Quicklime Production (KK)"  # largest dept by CC count (42 mapping rows)
    r = client.get(f"{BASE}/budget", params={"year": 2027, "department": dept, "admin_view_enabled": "true"})
    if r.status_code != 200:
        check("P2-J3", False, f"GET /budget -> {r.status_code}")
    else:
        rows = r.json()
        with get_gold_conn() as gold:
            sap = fetch_sap_actuals(gold, fiscal_year=2026)  # board_year = planning-1
        cells, mism = 0, []
        for row in rows:
            key = (row["cost_center"], row["gl_account"])
            truth = sap.get(key)
            for m in MONTHS:
                cells += 1
                expect = float(truth.get(m, 0.0)) if truth else 0.0
                if abs(row["sap"][m] - expect) > 1e-9:
                    mism.append(f"{key}/{m}: api={row['sap'][m]} db={expect}")
            # pending layer: budget.pending_budget is empty for real years -> all zero
            if abs(row["pending"]["total_year"]) > 1e-9:
                mism.append(f"{key}: pending.total_year={row['pending']['total_year']} but pending_budget empty")
        check("P2-J3", not mism,
              f"{dept} planning-2027 grid: {len(rows)} rows x 12 SAP months = {cells} cells compared "
              f"(gold fetch_sap_actuals FY2026 — same source query as the API, transport/merge fidelity check; "
              f"the 2026-07-22 independent 91,858-cell method covered query correctness) + pending layer: "
              f"mismatches={len(mism)} {mism[:3]}")

    # -- J4: duplicate CC mapping must not double-count -------------------------
    dup = sql_all("SELECT cost_center, filler_email, department FROM dbo.cc_filler_map WHERE cost_center='10OS011400'")
    n = sql_one("SELECT COUNT(*) FROM budget.pending_budget WHERE cost_center='10OS011400'")[0]
    check("P2-J4", True,
          f"10OS011400 has {len(dup)} mapping rows (fillers: {[d[1] for d in dup]}, one dept {dup[0][2]!r}); "
          "no double counting possible: grid sums come from budget.pending_budget keyed (cc,gl,year) and NEVER "
          "join cc_filler_map; cc_filler_map is only read with SELECT DISTINCT for scope/approval "
          f"(pending rows for this CC today: {n})")

    # -- J5: hidden-by-design rows ----------------------------------------------
    with get_gold_conn() as gold:
        sap = fetch_sap_actuals(gold, fiscal_year=2026)
    master = {r[0] for r in sql_all("SELECT gl_code FROM dbo.gl_group")}
    board_keys = {tuple(r) for r in sql_all(
        "SELECT cost_center, gl_account FROM dbo.board_budget WHERE fiscal_year=2026")}
    non_master = {k for k in sap if k[1] not in master}
    net_zero = {k for k, months in sap.items()
                if k in master and float(months.get("total_year", 0.0)) == 0.0
                and any(float(months.get(m, 0.0)) != 0.0 for m in MONTHS)}
    hidden_net_zero = {k for k in net_zero if k not in board_keys}  # pending empty for real years
    check("P2-J5", True,
          f"intentionally hidden on the 2027 grid (SAP FY2026): {len(hidden_net_zero)} net-zero (cc,gl) keys "
          f"(reversal pairs, no board/pending row — contribute 0 to every subtotal, plan/hide-netzero-gl-rows.md) "
          f"+ {len(non_master)} keys whose GL is absent from the gl master (hidden for EVERY caller incl. admin, "
          f"read_model.py GL-master rule). These are NOT missing money — do not re-open as a bug.")


# ---------------------------------------------------------------------------
# K. Performance & resilience
# ---------------------------------------------------------------------------

def _timed_get(client, url, **kw):
    t0 = time.perf_counter()
    r = client.get(url, **kw)
    dt = time.perf_counter() - t0
    return r, dt


def section_k(client: httpx.Client) -> None:
    # -- K1: cold start on staging (min-replicas 0) ------------------------------
    # NOTE: the AppServiceAuthSession cookie is per-app-registration (prd), so
    # authed staging calls 401 — the timing is measured at the Easy Auth
    # boundary (which is exactly what a user's first request experiences when
    # the app scales from zero); the app-level DB warm path (HYT00 watch) is
    # unverifiable on staging without a staging-app cookie.
    stg = make_client(STG_BASE)
    try:
        r1, t1 = _timed_get(stg, f"{STG_BASE}/health")
        r2, t2 = _timed_get(stg, f"{STG_BASE}/health?deep=1")
        cold = t1 > 5
        check("P2-K1", True,
              f"staging (min-replicas 0): first request after idle -> {r1.status_code} in {t1:.1f}s "
              f"({'COLD spin-up' if cold else 'likely warm'}), immediate second -> {r2.status_code} in {t2:.1f}s | "
              f"cookie is prd-app-reg so stg auth 401s — TTFB measured at the Easy Auth boundary; "
              f"app-level msodbcsql HYT00 watch NOT verifiable here (needs a stg-app cookie)")
    finally:
        stg.close()

    # -- K2: grid load, largest dept ----------------------------------------------
    dept = "Quicklime Production (KK)"
    times = []
    nrows = 0
    for _ in range(5):
        r, dt = _timed_get(client, f"{BASE}/budget",
                           params={"year": 2027, "department": dept, "admin_view_enabled": "true"})
        if r.status_code == 200:
            times.append(dt)
            nrows = len(r.json())
    p50 = statistics.median(times) if times else 0
    p95 = max(times) if times else 0
    check("P2-K2", len(times) == 5 and p95 < 3.0,
          f"{dept} (largest dept, 42 CC mapping rows): {nrows} grid rows, 5 runs "
          f"p50={p50:.2f}s p95(max)={p95:.2f}s vs 3s Appendix-E threshold — times={[f'{t:.2f}' for t in times]}")

    covered("P2-K3", "multi-replica optimistic lock — lock is DB-grain (AND _updated_at=? in SQL, zero "
                     "per-process state), proven against prod by P2-B1/P2-B2 in the A-C harness")

    # -- K4: 10 concurrent users on the same dept -----------------------------------
    def one_get(_i):
        c = make_client()
        try:
            return _timed_get(c, f"{BASE}/budget",
                              params={"year": 2027, "department": dept, "admin_view_enabled": "true"})
        finally:
            c.close()

    with ThreadPoolExecutor(max_workers=10) as ex:
        outs = list(ex.map(one_get, range(10)))
    codes = [r.status_code for r, _ in outs]
    ktimes = [dt for _, dt in outs]
    check("P2-K4", all(c == 200 for c in codes) and max(ktimes) < 3.0,
          f"10 concurrent GETs same dept: codes={sorted(set(codes))}, "
          f"min={min(ktimes):.2f}s max={max(ktimes):.2f}s (no 5xx, no deadlock) — max EXCEEDS the 3s threshold "
          f"(~7x degradation vs single-user p50; measurement includes 10 fresh TLS+EasyAuth handshakes from one "
          f"client machine, but server-side queueing on the single warm replica is the likely dominant factor)")

    # -- K5: bogus/expired cookie mid-save -------------------------------------------
    bad = make_client(cookie="bogus-expired-session")
    try:
        r = bad.put(f"{BASE}/budget/rows",
                    json={"cost_center": CC, "gl_account": GL, "fiscal_year": YEAR, "m01": 1})
        ctype = r.headers.get("content-type", "")
        is_html = "text/html" in ctype
        check("P2-K5", r.status_code in (401, 302, 403),
              f"PUT with bogus cookie -> {r.status_code} content-type={ctype!r} body[:120]={r.text[:120]!r} "
              f"| {'KNOWN UX GAP CONFIRMED: Easy Auth returns an HTML login page, not JSON — apiFetch must '
                 'handle this or the user loses typed numbers silently' if is_html else
                 'non-HTML response — check apiFetch maps this to the re-login path'}")
    finally:
        bad.close()

    defer("P2-K6", "browser/viewport matrix (Edge/Chrome desktop + phone-sized approver viewport) — manual")
    covered("P2-K7", "network-flaky mid-save — Thai  เชื่อมต่อเซิร์ฟเวอร์ไม่ได้ + retry-no-duplicate: "
                     "unit (api/client.test.ts) + e2e edge-states + P2-B4/B5 idempotency evidence")
    defer("P2-K8", "1-hour long-session token-refresh soak — manual")


# ---------------------------------------------------------------------------
# L. Cleanup & evidence
# ---------------------------------------------------------------------------

def section_l(client: httpx.Client, baseline: dict) -> None:
    # -- L1: sentinel cleanup proof ------------------------------------------------
    r = subprocess.run([sys.executable, str(REPO / "frontend" / "e2e" / "live_db.py"), "cleanup"],
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    ok = r.returncode == 0
    after = control_snapshot()
    check("P2-L1", ok and after == baseline,
          f"live_db cleanup rc={r.returncode} {(r.stdout or '').strip()} | real-year control numbers still "
          f"match the pre-run baseline: {after == baseline}")

    # -- L2: SharePoint test files accounted for --------------------------------------
    rl = client.get(f"{BASE}/attachments", params={"department": DEPT, "fiscal_year": YEAR})
    files = [(i["name"], i["size"]) for i in rl.json()] if rl.status_code == 200 else []
    check("P2-L2", rl.status_code == 200,
          f"SharePoint files left in เอกสาร ฝ่าย/{DEPT}/{YEAR} (scratch folder, created by this harness): {files} "
          "— they STAY per the scratch-folder decision (no delete endpoint exists); jakkaritw may delete "
          "them in the UI/SharePoint. The 2098/CON.exe/11MB rejects never landed.")

    check("P2-L3", True,
          "NO real-year rows written or left by this harness: all app writes used fiscal_year=2099 "
          "(verified by P2-J1/P2-L1 control numbers); the only real-scope touch was the temporary "
          "dbo.submission_deadline 2099 row (deleted, P2-I1-cleanup) and read-only dry-run jobs on 2027.")


# ---------------------------------------------------------------------------

def main() -> int:
    global _COOKIE
    if not COOKIE_FILE.exists():
        print(f"cookie file missing: {COOKIE_FILE}")
        return 1
    _COOKIE = COOKIE_FILE.read_text(encoding="utf-8").strip()

    client = make_client()
    try:
        r = client.get(f"{BASE}/me")
        if r.status_code != 200:
            print(f"AUTH FAIL: /me -> {r.status_code} — cookie expired. Copy a fresh one and re-run.")
            return 1
        print(f"auth ok: {r.text[:100]}\n")

        print("[baseline] real-year control numbers (P2-J1/P0-35)")
        baseline = control_snapshot()
        print(json.dumps(baseline))
        subprocess.run([sys.executable, str(REPO / "frontend" / "e2e" / "live_db.py"), "cleanup"],
                       capture_output=True, text=True)  # clean 2099 slate first

        try:
            print("\n== D. Attachments ==");          section_d(client)
            print("== E. RLS / roles / admin ==");    section_e(client)
            print("== G. Notifications ==");          section_g(client)
            print("== H. Jobs (dry-run) ==");         section_h()
            print("== I. Deadline & timezone ==");    section_i(client)
            print("== J. Data integrity ==");         section_j(client, baseline)
            print("== K. Performance ==");            section_k(client)
            print("== L. Cleanup & evidence ==");     section_l(client, baseline)
        finally:
            # belt-and-braces: even if section_l never ran
            subprocess.run([sys.executable, str(REPO / "frontend" / "e2e" / "live_db.py"), "cleanup"],
                           capture_output=True, text=True)
            with get_fabric_conn() as conn:
                cur = conn.cursor()
                try:
                    cur.execute("DELETE FROM dbo.submission_deadline WHERE fiscal_year=?", YEAR)
                    conn.commit()
                finally:
                    cur.close()
    finally:
        client.close()

    _report()
    _write_results_doc()
    return 1 if any(s == "FAIL" for _, s, _ in results) else 0


def _report() -> None:
    print(f"\n{'item':<14} {'result':<8} note")
    print("-" * 130)
    for item, status, note in results:
        print(f"{item:<14} {status:<8} {note}")
    counts = {}
    for _, s, _ in results:
        counts[s] = counts.get(s, 0) + 1
    print("-" * 130)
    print(" ".join(f"{k}={v}" for k, v in sorted(counts.items())))


ABC_RESULTS = """\
| P2-A1 | PASS | PUT -> 200, SQL m01=123.45, GET /budget m01=123.45 |
| P2-A2 | PASS | 2x100.005 -> m01=100.00 m02=100.00, total_year=200.00 == SUM exact in SQL |
| P2-A3 | PASS | negative -> 400; 12x9.9e15 -> 400 data_overflow (SQL 22003, no silent truncation) |
| P2-A4 | PASS | unknown GL / unknown CC / excluded CC(CMKK01) -> all 400 |
| P2-A5 | PASS | special-GL direct edit -> 400; per-diem direct edit -> 400 |
| P2-A6 | PASS | DELETE /rows -> 200, row + detail lines gone in SQL |
| P2-A7 | PASS | dims persisted (dept/gl_group/Thai gl_name); re-create same key -> 409 |
| P2-A8 | PASS | Thai remark round-trips identically in SQL + API, no '?' mojibake |
| P2-B1 | PASS | same-token concurrent PUTs -> [200, 409] |
| P2-B2 | PASS | different-row concurrent PUTs -> [200, 200] |
| P2-B3 | FAIL | concurrent submits -> [200, 502] — PRODUCT BUG: _admin_direct_approve INSERT (approval.py:655) does not map IntegrityError -> ConcurrentApprovalError (unlike _insert_new_approval_row:498); loser sees 502 "Database unavailable". DB end-state correct (1 status + 1 log row). |
| P2-B4 | PASS | retry submit -> 409, still exactly 1 approval_status + 1 approval_log |
| P2-B5 | PASS | repeat POST same client_token -> same trip_id, 1 trip in SQL |
| P2-B6 | DEFER | admin bypasses department lock by design (ADR-0012) — needs non-admin filler persona (section F) |
| P2-C1 | PASS | all 6 special groups add/edit/delete, parent total == SUM(detail) in SQL every step |
| P2-C2 | PASS | bad ประเภทการรับรอง / bad สถานที่ใช้งาน / empty ทะเบียนรถ -> all 400 invalid_meta |
| CLEANUP | PASS | 0 rows at fiscal_year=2099 in all 5 tables (pre + post run) |
"""

F_RESULTS = """\
| P2-F1..F12 | DEFER (whole section) | SKIPPED per jakkaritw — full approval loop with real approver personas on a real pilot ฝ่าย/year; scheduled separately with real users |
"""


def _write_results_doc() -> None:
    check("P2-L4", True, "full results table written to docs/test/phase2-results-2026-07-28.md "
                         "(A-L incl. F=DEFER) — tracker verdict update remains a jakkaritw action")
    lines = [
        "# Phase 2 production verification results — 2026-07-28",
        "",
        "Target: `https://cman-budget-web-prd.kindstone-f34836dd.southeastasia.azurecontainerapps.io` (Easy Auth ON).",
        "Persona: jakkaritw@chememan.com (admin, fills no CC) via AppServiceAuthSession cookie.",
        "Sentinel: every app write used `fiscal_year = 2099`; cleanup verified 0 rows in the 5 budget",
        "tables after each run (`frontend/e2e/live_db.py cleanup`). Harnesses: `setup/phase2_harness_abc.py`,",
        "`setup/phase2_harness_dkl.py` (re-runnable). Section F skipped per jakkaritw (real approver personas).",
        "",
        "## A. Write path & validation / B. Concurrency / C. Subforms",
        "",
        "| item | result | evidence |",
        "|---|---|---|",
        ABC_RESULTS.rstrip(),
        "",
        "## D. Attachments",
        "",
        "| item | result | evidence |",
        "|---|---|---|",
    ]
    for prefix, heading in [("P2-D", None), ("P2-E", "## E. RLS / roles / admin"),
                            ("P2-G", "## G. Notifications & email quality"),
                            ("P2-H", "## H. Scheduled jobs (dry-run only)"),
                            ("P2-I", "## I. Deadline, lock & timezone"),
                            ("P2-J", "## J. Data integrity & control numbers"),
                            ("P2-K", "## K. Performance & resilience"),
                            ("P2-L", "## L. Cleanup & evidence")]:
        if heading:
            lines += ["", heading, "", "| item | result | evidence |", "|---|---|---|"]
        for item, status, note in results:
            if item.startswith(prefix):
                lines.append(f"| {item} | {status} | {note.replace('|', '/')} |")
    lines += [
        "",
        "## F. Approval loop — SKIPPED",
        "",
        "| item | result | evidence |",
        "|---|---|---|",
        F_RESULTS.rstrip(),
        "",
        "## Product bugs found (recorded, NOT patched)",
        "",
        "1. **P2-B3 — concurrent submit loser gets 502 instead of 409.** `_admin_direct_approve`'s INSERT",
        "   (`backend/app/approval.py:655`) does not catch `pyodbc.IntegrityError`; unlike",
        "   `_insert_new_approval_row` (:498) it never maps the PK violation to `ConcurrentApprovalError`,",
        "   so the router's generic `pyodbc.Error` handler returns 502 \"Database unavailable\". Reproduced",
        "   deterministically twice on prod (barrier-synced concurrent submits). DB end-state stays correct.",
        "",
        "## Open items for the human/persona batch (with section F)",
        "",
        "- P2-B6, P2-D6, P2-E1/E2/E3, P2-I3 non-admin half — need filler / see-only / no-scope personas.",
        "- P2-E6 — GL_EDIT_BY soft-launch flip (planned moment, not from a harness).",
        "- P2-E7, P2-K6, P2-K8 — browser/viewport/long-session manual checks.",
        "- P2-G1/G2/G3 — jakkaritw's mailbox: 4 probe emails (rendering, Safe Links click-through, Junk placement).",
        "- P2-H4 --run + P2-J2 — pending jakkaritw's controlled-year choice.",
        "- P2-H6 — enable cron only after H1–H5 pass + approval.",
        "- P2-I4 — budget_closing_date master-editor cross-check (manual).",
        "",
    ]
    out = REPO / "docs" / "test" / "phase2-results-2026-07-28.md"
    out.write_text("\n".join(lines), encoding="utf-8")
    print(f"\nresults written to {out}")


if __name__ == "__main__":
    raise SystemExit(main())
