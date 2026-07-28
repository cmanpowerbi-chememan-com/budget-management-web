"""Phase 2 (sections A/B/C) production-verification harness
(plan/post-deploy-smoke-uat-plan.md, items P2-A1..A8, P2-B1..B6, P2-C1..C2).

Drives the REAL production API (Easy Auth via a copied AppServiceAuthSession
cookie, same pattern as setup/smoke_prd.py) and verifies results in the live
DB. Every write uses the sentinel `fiscal_year = 2099` ONLY; cleanup at the
start AND end (even on failure) shells out to `frontend/e2e/live_db.py
cleanup`, which deletes every 2099 row from the 5 transactional/approval
tables and verifies 0 remain.

Persona note (verified 2026-07-28): the cookie belongs to jakkaritw — ADMIN,
but a FILLER OF NO department. Consequences, by design:
- B3/B4 run through the admin Template-2 door (`template='ADMIN'` row +
  `_admin_direct_approve`) — the only submit path open to this persona. The
  concurrency/idempotency guarantees (one approval_status row, one
  approval_log row) are still genuinely exercised; the two-FILLERS normal
  chain (PENDING_APPROVER1) variant needs a filler persona -> deferred to
  the approver-loop section (F).
- B6 (403 department_locked on edit mid-approval) is untestable with this
  persona: admin BYPASSES the department lock entirely (ADR-0012,
  `_ensure_department_not_locked` returns early for admin). DEFER.

Run from repo root:
    venv/Scripts/python.exe setup/phase2_harness_abc.py
"""
import json
import subprocess
import sys
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "backend"))

import httpx  # noqa: E402

from app.db import get_fabric_conn  # noqa: E402
from app.gl_access import fetch_admin_gl_codes  # noqa: E402
from app.config import get_settings  # noqa: E402
from app.special_gl import SPECIAL_GL_GROUPS  # noqa: E402
from app.write_model import EXCLUDED_COST_CENTERS  # noqa: E402

BASE = "https://cman-budget-web-prd.kindstone-f34836dd.southeastasia.azurecontainerapps.io"
COOKIE_FILE = Path(__file__).resolve().parent / "_auth_cookie.tmp.txt"
YEAR = 2099  # sentinel — never a real planning year
MONTHS = [f"m{i:02d}" for i in range(1, 13)]

results: list[tuple[str, str, str]] = []  # (item, PASS/FAIL/DEFER, note)


def check(item: str, ok: bool, note: str) -> bool:
    results.append((item, "PASS" if ok else "FAIL", note))
    return ok


def defer(item: str, note: str) -> None:
    results.append((item, "DEFER", note))


_COOKIE: str | None = None


def make_client() -> httpx.Client:
    c = httpx.Client(timeout=60, follow_redirects=False)
    c.cookies.set("AppServiceAuthSession", _COOKIE, domain=BASE.split("//")[1])
    return c


def cleanup_2099(label: str) -> bool:
    """Shell out to the live_db cleanup subcommand (deletes + verifies 0)."""
    r = subprocess.run(
        [sys.executable, str(REPO / "frontend" / "e2e" / "live_db.py"), "cleanup"],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    out = (r.stdout or "").strip()
    print(f"[cleanup:{label}] rc={r.returncode} {out}")
    return r.returncode == 0


# ---------------------------------------------------------------------------
# Discovery (queries mirror frontend/e2e/live_db.py)
# ---------------------------------------------------------------------------

def discover() -> dict:
    with get_fabric_conn() as conn:
        cur = conn.cursor()
        placeholders = ", ".join("?" for _ in EXCLUDED_COST_CENTERS)
        cur.execute(
            f"""
            SELECT cost_center, filler_email, department
            FROM dbo.cc_filler_map
            WHERE filler_email IS NOT NULL AND LTRIM(RTRIM(filler_email)) <> ''
              AND cost_center NOT IN ({placeholders})
            ORDER BY cost_center
            """,
            *EXCLUDED_COST_CENTERS,
        )
        rows = cur.fetchall()
        if not rows:
            raise RuntimeError("no usable (cost_center, filler) pair in dbo.cc_filler_map")
        # Prefer a Thai-named department so A8 can check the ฝ่าย name too.
        thai = [r for r in rows if any("ก" <= ch <= "๙" for ch in (r[2] or ""))]
        cc, filler, dept = (thai or rows)[0]

        # Two grid-renderable, non-special, non-admin-only GLs (B2 needs two).
        admin_gls = fetch_admin_gl_codes(conn) if get_settings().gl_edit_by_enabled else frozenset()
        ph = ", ".join("?" for _ in SPECIAL_GL_GROUPS)
        cur.execute(
            f"""
            SELECT gl_code FROM dbo.gl_group
            WHERE gl_group NOT IN ({ph}) AND (gl_code LIKE '5%' OR gl_code LIKE '6%')
            ORDER BY gl_code
            """,
            *SPECIAL_GL_GROUPS,
        )
        gls = [r[0] for r in cur.fetchall() if r[0] not in admin_gls]
        if len(gls) < 2:
            raise RuntimeError("need >=2 plain GLs")

        # A traveler whose job level HAS a per-diem rate (never a 500 setup).
        cur.execute(
            """
            SELECT TOP 1 e.employee_code, e.job_level_name_en
            FROM dbo.v_employee_primary e
            JOIN dbo.per_diem_rate r ON r.job_level = e.job_level_name_en
            WHERE r.rate_domestic > 0
            ORDER BY e.employee_code
            """
        )
        traveler = cur.fetchone()
        cur.close()
    return {
        "cost_center": cc, "filler_email": filler, "department": dept,
        "gl1": gls[0], "gl2": gls[1],
        "traveler_empcode": traveler[0], "traveler_level": traveler[1],
    }


def sql_one(query: str, *params):
    with get_fabric_conn() as conn:
        cur = conn.cursor()
        try:
            cur.execute(query, *params)
            return cur.fetchone()
        finally:
            cur.close()


def pending_row(cc: str, gl: str):
    return sql_one(
        f"SELECT {', '.join(MONTHS)}, total_year, remark, gl_name, gl_group, department, _updated_at "
        "FROM budget.pending_budget WHERE cost_center=? AND gl_account=? AND fiscal_year=?",
        cc, gl, YEAR,
    )


def detail_sum(cc: str, gl: str) -> Decimal:
    row = sql_one(
        "SELECT COALESCE(SUM(total_year), 0) FROM budget.pending_budget_detail "
        "WHERE cost_center=? AND gl_account=? AND fiscal_year=?",
        cc, gl, YEAR,
    )
    return Decimal(str(row[0]))


def parent_total(cc: str, gl: str) -> Decimal | None:
    row = sql_one(
        "SELECT total_year FROM budget.pending_budget WHERE cost_center=? AND gl_account=? AND fiscal_year=?",
        cc, gl, YEAR,
    )
    return None if row is None else Decimal(str(row[0]))


def row_token(cc: str, gl: str) -> str:
    row = sql_one(
        "SELECT _updated_at FROM budget.pending_budget WHERE cost_center=? AND gl_account=? AND fiscal_year=?",
        cc, gl, YEAR,
    )
    return row[0].isoformat()


def put_row(client: httpx.Client, cc: str, gl: str, token=None, **kw):
    body = {"cost_center": cc, "gl_account": gl, "fiscal_year": YEAR,
            "expected_updated_at": token, **kw}
    return client.put(f"{BASE}/budget/rows", json=body)


def put_detail(client: httpx.Client, cc: str, gl: str, **kw):
    body = {"cost_center": cc, "gl_account": gl, "fiscal_year": YEAR, **kw}
    return client.put(f"{BASE}/budget/detail", json=body)


def trip_payload(ctx: dict, **kw):
    body = {
        "cost_center": ctx["cost_center"], "fiscal_year": YEAR,
        "traveler_empcode": ctx["traveler_empcode"], "destination": "กรุงเทพ ทดสอบ 2099",
        "country_group": 1, "days": 2, "travel_months": ["03"],
        "purpose": "phase2 harness", "side": "SGA",
    }
    body.update(kw)
    return body


# ---------------------------------------------------------------------------
# Section A — write path & validation
# ---------------------------------------------------------------------------

def section_a(client: httpx.Client, ctx: dict) -> None:
    cc, gl1, gl2, dept = ctx["cost_center"], ctx["gl1"], ctx["gl2"], ctx["department"]

    # -- A1: create -> SQL -> API reload round-trip --------------------------
    r = put_row(client, cc, gl1, m01=123.45)
    ok = r.status_code == 200
    note = f"PUT -> {r.status_code}"
    token = None
    if ok:
        token = r.json()["updated_at"]
        db = pending_row(cc, gl1)
        sql_ok = db is not None and Decimal(str(db[0])) == Decimal("123.45")
        rg = client.get(f"{BASE}/budget", params={"year": YEAR, "cost_center": cc,
                                                  "admin_view_enabled": "true"})
        api_val = None
        if rg.status_code == 200:
            for row in rg.json():
                if row["gl_account"] == gl1:
                    api_val = row["pending"]["m01"]
                    break
        api_ok = api_val is not None and abs(api_val - 123.45) < 1e-9
        ok = sql_ok and api_ok
        note += f", SQL m01={db[0] if db else None}, GET /budget m01={api_val}"
    check("P2-A1", ok, note)
    ctx["token_gl1"] = token

    # -- A2: money integrity — 2x100.005 -> 100.00 each, total == SUM --------
    if token:
        r = put_row(client, cc, gl1, token=token, m01=100.005, m02=100.005)
        if r.status_code == 200:
            ctx["token_gl1"] = r.json()["updated_at"]
            db = pending_row(cc, gl1)
            months = [Decimal(str(db[i])) for i in range(12)]
            total = Decimal(str(db[12]))
            exact = total == sum(months)
            ok = months[0] == Decimal("100.00") and months[1] == Decimal("100.00") and exact
            check("P2-A2", ok,
                  f"m01={months[0]} m02={months[1]} total_year={total} sum={sum(months)} exact={exact}")
        else:
            check("P2-A2", False, f"PUT -> {r.status_code} {r.text[:120]}")
    else:
        check("P2-A2", False, "skipped — A1 create failed")

    # -- A3: negative month -> 400; huge value -> 400 (no silent truncation) -
    r = put_row(client, cc, gl1, token=ctx.get("token_gl1"), m01=-1)
    neg_ok = r.status_code == 400
    neg_note = f"negative -> {r.status_code}"
    huge = {m: 9.9e15 for m in MONTHS}  # each < pydantic's 1e16 cap; SUM overflows DECIMAL(18,2)
    r2 = put_row(client, cc, gl1, token=ctx.get("token_gl1"), **huge)
    huge_ok = r2.status_code == 400
    check("P2-A3", neg_ok and huge_ok,
          f"{neg_note} ({r.text[:80]}), huge(12x9.9e15) -> {r2.status_code} ({r2.text[:80]})")

    # -- A4: unknown GL / unknown CC / excluded CC -> 400 ---------------------
    r1 = put_row(client, cc, "0000000000", m01=1)
    r2 = put_row(client, "ZZZUNKNOWN", gl1, m01=1)
    excluded = sorted(EXCLUDED_COST_CENTERS)[0]
    r3 = put_row(client, excluded, gl1, m01=1)
    ok = r1.status_code == 400 and r2.status_code == 400 and r3.status_code == 400
    check("P2-A4", ok,
          f"unknown_gl -> {r1.status_code}, unknown_cc -> {r2.status_code}, excluded_cc({excluded}) -> {r3.status_code}"
          " | Thai UI copy -> browser, deferred")

    # -- A5: special-GL direct edit -> 400; per-diem direct edit -> 400 -------
    r1 = put_row(client, cc, "5211900030", m01=1)  # Entertainment
    sp_ok = r1.status_code == 400
    # per-diem: a trip must exist (created in the shared setup below)
    pd_status, pd_detail = "no-trip", ""
    lines = client.get(f"{BASE}/budget/detail", params={
        "cost_center": cc, "gl_account": "6210400010", "fiscal_year": YEAR})
    if lines.status_code == 200 and lines.json():
        pd = [l for l in lines.json() if l["trip_id"] is not None]
        if pd:
            line = pd[0]
            r2 = put_detail(client, cc, "6210400010", detail_id=line["detail_id"],
                            trip_id=line["trip_id"], m01=5,
                            expected_updated_at=line["updated_at"])
            pd_status = r2.status_code
            pd_detail = r2.text[:80]
    check("P2-A5", sp_ok and pd_status == 400,
          f"special_gl(5211900030) PUT /rows -> {r1.status_code} ({r1.text[:70]}), "
          f"per-diem line PUT /detail -> {pd_status} ({pd_detail})")

    # -- A6: row delete cascades detail lines --------------------------------
    gl_a6 = "6211700020"  # Public Relation & Donation (dedicated; C1 uses ...030)
    r = put_detail(client, cc, gl_a6, m03=100, line_label="a6")
    if r.status_code == 200:
        tok = row_token(cc, gl_a6)
        rd = client.delete(f"{BASE}/budget/rows", params={
            "cost_center": cc, "gl_account": gl_a6, "fiscal_year": YEAR,
            "expected_updated_at": tok})
        row_gone = pending_row(cc, gl_a6) is None
        det = sql_one("SELECT COUNT(*) FROM budget.pending_budget_detail "
                      "WHERE cost_center=? AND gl_account=? AND fiscal_year=?", cc, gl_a6, YEAR)
        check("P2-A6", rd.status_code == 200 and row_gone and det[0] == 0,
              f"DELETE /rows -> {rd.status_code}, row gone={row_gone}, detail rows left={det[0]}"
              " (trips are never row-delete-cascaded by design — Travelling rows have no ลบ button)")
    else:
        check("P2-A6", False, f"setup detail line failed -> {r.status_code} {r.text[:100]}")

    # -- A7: add-transaction (new row) dims + dedup key -----------------------
    r = put_row(client, cc, gl2, m05=77.5, remark="a7")
    if r.status_code == 200:
        ctx["token_gl2"] = r.json()["updated_at"]
        db = pending_row(cc, gl2)
        dims_ok = db is not None and db[16] == dept and db[15] is not None and db[14] is not None
        # dedup key: re-CREATE the same (cc, gl, year) with token=None -> 409
        r2 = put_row(client, cc, gl2, token=None, m05=1)
        dup_ok = r2.status_code == 409
        check("P2-A7", dims_ok and dup_ok,
              f"dims dept={db[16]!r} gl_group={db[15]!r} gl_name={db[14]!r}, re-create same key -> {r2.status_code}")
    else:
        check("P2-A7", False, f"PUT -> {r.status_code} {r.text[:100]}")

    # -- A8: Thai text round-trip ---------------------------------------------
    remark = "หมายเหตุ ทดสอบ ภาษาไทย มี ช่องว่าง 2099"
    r = put_row(client, cc, gl2, token=ctx.get("token_gl2"), remark=remark)
    if r.status_code == 200:
        ctx["token_gl2"] = r.json()["updated_at"]
        db = pending_row(cc, gl2)
        sql_remark = db[13]
        gl_name = db[14]
        resp_remark = r.json().get("remark")
        ok = (sql_remark == remark and resp_remark == remark
              and "?" not in (sql_remark or "") and "?" not in (gl_name or ""))
        check("P2-A8", ok,
              f"SQL remark==sent: {sql_remark == remark}, API remark==sent: {resp_remark == remark}, "
              f"gl_name={gl_name!r}, gl_group={db[15]!r}, dept={db[16]!r} "
              f"(mojibake '?' absent: {'?' not in (sql_remark or '')})")
    else:
        check("P2-A8", False, f"PUT -> {r.status_code} {r.text[:100]}")


# ---------------------------------------------------------------------------
# Section B — concurrency & idempotency
# ---------------------------------------------------------------------------

def _run_concurrent(fn, n=2):
    barrier = threading.Barrier(n)

    def wrapped(i):
        c = make_client()
        try:
            barrier.wait(timeout=30)
            return fn(c, i)
        finally:
            c.close()

    with ThreadPoolExecutor(max_workers=n) as ex:
        return list(ex.map(wrapped, range(n)))


def section_b(client: httpx.Client, ctx: dict) -> None:
    cc, gl1, gl2, dept = ctx["cost_center"], ctx["gl1"], ctx["gl2"], ctx["department"]

    # -- B1: two PUTs, same row, same token -> exactly one 200, one 409 -------
    tok = ctx.get("token_gl1")
    if tok:
        outs = _run_concurrent(lambda c, i: c.put(f"{BASE}/budget/rows", json={
            "cost_center": cc, "gl_account": gl1, "fiscal_year": YEAR,
            "m07": 100 + i, "expected_updated_at": tok}))
        codes = sorted(r.status_code for r in outs)
        loser = next((r for r in outs if r.status_code != 200), None)
        note = f"same-token concurrent PUTs -> {codes}"
        if loser is not None:
            note += f" (loser: {loser.text[:80]})"
        check("P2-B1", codes == [200, 409], note)
        # refresh token after the winner
        ctx["token_gl1"] = row_token(cc, gl1)
    else:
        check("P2-B1", False, "skipped — no token from A1")

    # -- B2: different rows, same dept -> both 200 ----------------------------
    tok1, tok2 = ctx.get("token_gl1"), ctx.get("token_gl2")
    if tok1 and tok2:
        def put_diff(c, i):
            gl, t = (gl1, tok1) if i == 0 else (gl2, tok2)
            return c.put(f"{BASE}/budget/rows", json={
                "cost_center": cc, "gl_account": gl, "fiscal_year": YEAR,
                "m08": 42, "expected_updated_at": t})
        outs = _run_concurrent(put_diff)
        codes = sorted(r.status_code for r in outs)
        check("P2-B2", codes == [200, 200], f"different-row concurrent PUTs -> {codes}")
        ctx["token_gl1"], ctx["token_gl2"] = row_token(cc, gl1), row_token(cc, gl2)
    else:
        check("P2-B2", False, "skipped — missing row tokens")

    # -- B3: concurrent submits -> exactly 1 approval_status + 1 approval_log -
    # Persona caveat: jakkaritw fills no CC, so the normal filler chain is
    # closed to him. Setup takes the admin Template-2 door (template='ADMIN'
    # row in 2099 -> _admin_direct_approve). The one-row/one-log guarantee
    # under a genuine race is still exercised. Two-FILLER variant -> section F.
    r = put_row(client, cc, gl1, token=ctx.get("token_gl1"), template="ADMIN")
    if r.status_code != 200:
        check("P2-B3", False, f"template=ADMIN setup row failed -> {r.status_code} {r.text[:100]}")
    else:
        ctx["token_gl1"] = r.json()["updated_at"]
        outs = _run_concurrent(lambda c, i: c.post(f"{BASE}/approval/submit",
                                                   json={"department": dept, "fiscal_year": YEAR}))
        codes = sorted(o.status_code for o in outs)
        loser = next((o for o in outs if o.status_code != 200), None)
        n_status = sql_one("SELECT COUNT(*) FROM budget.approval_status WHERE department=? AND fiscal_year=?",
                           dept, YEAR)[0]
        n_log = sql_one("SELECT COUNT(*) FROM budget.approval_log WHERE department=? AND fiscal_year=?",
                        dept, YEAR)[0]
        st = sql_one("SELECT status FROM budget.approval_status WHERE department=? AND fiscal_year=?",
                     dept, YEAR)
        # KNOWN PRODUCT BUG (recorded, not patched): the loser's expected 409
        # concurrent_approval arrives as a 502 — _admin_direct_approve's INSERT
        # (backend/app/approval.py:655) does not catch pyodbc.IntegrityError,
        # unlike _insert_new_approval_row (approval.py:498) which maps it to
        # ConcurrentApprovalError. DB end-state is still correct (1 row, 1 log).
        check("P2-B3", codes == [200, 409] and n_status == 1 and n_log == 1,
              f"concurrent submits -> {codes} (loser body: {loser.text[:90] if loser else '—'}), "
              f"approval_status rows={n_status} ({st[0] if st else None}), approval_log rows={n_log} "
              f"[admin Template-2 door; two-filler chain -> section F; 502-instead-of-409 = product bug]")

        # -- B4: retry after success -> still one row, one log -----------------
        r2 = client.post(f"{BASE}/approval/submit", json={"department": dept, "fiscal_year": YEAR})
        n_status2 = sql_one("SELECT COUNT(*) FROM budget.approval_status WHERE department=? AND fiscal_year=?",
                            dept, YEAR)[0]
        n_log2 = sql_one("SELECT COUNT(*) FROM budget.approval_log WHERE department=? AND fiscal_year=?",
                         dept, YEAR)[0]
        check("P2-B4", r2.status_code == 409 and n_status2 == 1 and n_log2 == 1,
              f"retry submit -> {r2.status_code} ({r2.text[:70]}), status rows={n_status2}, log rows={n_log2} "
              "| 'exactly one email' + Approve-retry -> needs approver persona/mailbox, deferred")

    # -- B5: trip create idempotency (client_token) ---------------------------
    token = f"phase2-{uuid.uuid4()}"
    body = trip_payload(ctx, client_token=token, travel_months=["04"], days=1)
    r1 = client.post(f"{BASE}/budget/trip", json=body)
    r2 = client.post(f"{BASE}/budget/trip", json=body)
    if r1.status_code == 200 and r2.status_code == 200:
        id1, id2 = r1.json()["trip_id"], r2.json()["trip_id"]
        try:
            n = sql_one("SELECT COUNT(*) FROM budget.budget_trip WHERE fiscal_year=? AND client_token=?",
                        YEAR, token)[0]
            cnt_note = f"trips with token={n}"
            ok = id1 == id2 and n == 1
        except Exception:
            n = sql_one("SELECT COUNT(*) FROM budget.budget_trip WHERE fiscal_year=? AND traveler_empcode=?",
                        YEAR, ctx["traveler_empcode"])[0]
            cnt_note = f"(no client_token column?) trips for traveler={n}"
            ok = id1 == id2
        check("P2-B5", ok, f"repeat POST same client_token -> trip_id {id1} vs {id2}, {cnt_note}")
    else:
        check("P2-B5", False, f"POST /trip -> {r1.status_code} / {r2.status_code} {r1.text[:100]}")

    # -- B6: edit while mid-approval -> 403 department_locked ------------------
    defer("P2-B6",
          "untestable with admin cookie: admin BYPASSES the department lock by design "
          "(ADR-0012, _ensure_department_not_locked returns early) — needs a non-admin "
          "filler persona while the dept is PENDING_APPROVER1 -> approver-loop section F")


# ---------------------------------------------------------------------------
# Section C — subforms: special GL + trips
# ---------------------------------------------------------------------------

C1_GROUPS = [
    ("Entertainment", "5211900030", {"ประเภทการรับรอง": "Customer"}),
    ("Lease & Rental", "5211200060",
     {"สถานที่ใช้งาน": "BK", "ประเภทรถ": "Car", "ทะเบียนรถ": "6ขผ-3918", "กิจกรรม": "ทดสอบ 2099"}),
    ("Professional & Legal Fee", "5210700030", {"รายละเอียด": "ทดสอบ 2099"}),
    ("Public Relation & Donation", "6211700030", {"รายละเอียด": "ทดสอบ 2099"}),
    ("Training & Seminar", "6210100150", {"รายละเอียด": "ทดสอบ 2099"}),
]


def section_c(client: httpx.Client, ctx: dict) -> None:
    cc = ctx["cost_center"]

    # -- C1: per group add -> edit -> delete; parent total == SUM(detail) -----
    notes, all_ok = [], True
    for group, gl, meta in C1_GROUPS:
        r = put_detail(client, cc, gl, m03=100, line_label="c1", meta_json=meta)
        if r.status_code != 200:
            notes.append(f"{group}: add -> {r.status_code} {r.text[:60]}")
            all_ok = False
            continue
        line = r.json()
        p1, s1 = parent_total(cc, gl), detail_sum(cc, gl)
        r2 = put_detail(client, cc, gl, detail_id=line["detail_id"], m03=250,
                        line_label="c1", meta_json=meta,
                        expected_updated_at=line["updated_at"])
        p2, s2 = parent_total(cc, gl), detail_sum(cc, gl)
        rd = client.delete(f"{BASE}/budget/detail", params={
            "detail_id": line["detail_id"], "expected_updated_at": r2.json()["updated_at"]})
        p3, s3 = parent_total(cc, gl), detail_sum(cc, gl)
        ok = (r2.status_code == 200 and rd.status_code == 200
              and p1 == s1 == Decimal("100") and p2 == s2 == Decimal("250")
              and s3 == 0 and (p3 is None or p3 == 0))
        all_ok = all_ok and ok
        notes.append(f"{group}: add p={p1}/s={s1}, edit p={p2}/s={s2}, del p={p3}/s={s3}"
                     + ("" if ok else "  <-- MISMATCH"))

    # Travelling Expense (structural — via budget_trip, not meta_json):
    # the shared trip (section-A setup) auto-created a per-diem line under
    # 6210400010; add/edit/delete a manual transport line on 6210400020.
    trips = client.get(f"{BASE}/budget/trip", params={"cost_center": cc, "fiscal_year": YEAR})
    if trips.status_code == 200 and trips.json():
        trip = trips.json()[0]
        pd_p, pd_s = parent_total(cc, "6210400010"), detail_sum(cc, "6210400010")
        ok = pd_p is not None and pd_p == pd_s and pd_s > 0
        gl_tr = "6210400020"
        r = put_detail(client, cc, gl_tr, trip_id=trip["trip_id"], m03=300, line_label="c1-travel")
        if r.status_code == 200:
            line = r.json()
            p1, s1 = parent_total(cc, gl_tr), detail_sum(cc, gl_tr)
            rd = client.delete(f"{BASE}/budget/detail", params={
                "detail_id": line["detail_id"], "expected_updated_at": line["updated_at"]})
            p2, s2 = parent_total(cc, gl_tr), detail_sum(cc, gl_tr)
            ok = ok and rd.status_code == 200 and p1 == s1 == Decimal("300") and s2 == 0
            notes.append(f"Travelling Expense: per-diem parent={pd_p}/sum={pd_s}, "
                         f"transport add p={p1}/s={s1}, del p={p2}/s={s2}")
        else:
            ok = False
            notes.append(f"Travelling Expense: transport line add -> {r.status_code} {r.text[:70]}")
        all_ok = all_ok and ok
    else:
        all_ok = False
        notes.append(f"Travelling Expense: no trip available (GET /trip -> {trips.status_code})")
    check("P2-C1", all_ok, " | ".join(notes))

    # -- C2: invalid meta -> 400 invalid_meta ---------------------------------
    outs = []
    r1 = put_detail(client, cc, "5211900030", m03=1,
                    meta_json={"ประเภทการรับรอง": "ไม่มีในระบบ"})
    outs.append(f"Entertainment bad ประเภทการรับรอง -> {r1.status_code}")
    r2 = put_detail(client, cc, "5211200060", m03=1, meta_json={"สถานที่ใช้งาน": "ZZ"})
    outs.append(f"Lease bad สถานที่ใช้งาน -> {r2.status_code}")
    r3 = put_detail(client, cc, "5211200060", m03=1,
                    meta_json={"สถานที่ใช้งาน": "BK", "ประเภทรถ": "Car", "ทะเบียนรถ": ""})
    outs.append(f"Lease empty ทะเบียนรถ -> {r3.status_code}")
    ok = all(r.status_code == 400 for r in (r1, r2, r3))
    check("P2-C2", ok, "; ".join(outs) +
          " | other 3 groups are free-form meta by design (special_gl.py) — no option-set to reject")


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
            print(f"AUTH FAIL: /me -> {r.status_code} — cookie expired (~8h lifetime). "
                  "Copy a fresh AppServiceAuthSession cookie and re-run. Nothing was written.")
            return 1
        print(f"auth ok: {r.text[:100]}\n")
        if "jakkaritw@chememan.com" not in r.text:
            print("WARNING: session identity is not jakkaritw — persona assumptions may not hold\n")

        print("[cleanup:pre] ensuring a clean 2099 slate before the run")
        cleanup_2099("pre")

        ctx = discover()
        print(f"discovered: cc={ctx['cost_center']} dept={ctx['department']!r} "
              f"filler={ctx['filler_email']} gls={ctx['gl1']},{ctx['gl2']} "
              f"traveler={ctx['traveler_empcode']} ({ctx['traveler_level']})\n")

        # Shared setup: one trip (used by A5 per-diem check + C1 Travelling).
        r = client.post(f"{BASE}/budget/trip", json=trip_payload(ctx))
        if r.status_code == 200:
            ctx["trip_id"] = r.json()["trip_id"]
            print(f"shared trip created: trip_id={ctx['trip_id']} "
                  f"per_diem={r.json().get('per_diem_months')}\n")
        else:
            print(f"WARNING: shared trip create -> {r.status_code} {r.text[:150]}\n")

        try:
            print("== A. Write path & validation ==")
            section_a(client, ctx)
            print("== B. Concurrency & idempotency ==")
            section_b(client, ctx)
            print("== C. Subforms ==")
            section_c(client, ctx)
        finally:
            ok = cleanup_2099("post")
            check("CLEANUP", ok, "fiscal_year=2099 rows deleted, 0 remain in all 5 tables"
                  if ok else "cleanup reported leftover rows — see [cleanup:post] above")
    finally:
        client.close()

    _report()
    return 1 if any(s == "FAIL" for _, s, _ in results) else 0


def _report() -> None:
    print(f"\n{'item':<8} {'result':<6} note")
    print("-" * 120)
    for item, status, note in results:
        print(f"{item:<8} {status:<6} {note}")
    n_fail = sum(1 for _, s, _ in results if s == "FAIL")
    n_pass = sum(1 for _, s, _ in results if s == "PASS")
    n_def = sum(1 for _, s, _ in results if s == "DEFER")
    print("-" * 120)
    print(f"PASS={n_pass} FAIL={n_fail} DEFER={n_def}")


if __name__ == "__main__":
    raise SystemExit(main())
