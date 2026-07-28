"""Phase 1 automated smoke harness for the PRODUCTION deployment
(plan/post-deploy-smoke-uat-plan.md §Phase 1, P1-01..P1-20) — one compact
PASS/FAIL table, no screenshots. Re-run after EVERY deploy/revision.

How auth works here: Easy Auth on the Container App accepts AAD Bearer tokens
whose audience is the prd app registration (auto-created 2026-07-28,
client id 61d5d556-…). This script fetches a client-credentials token for
the SP `cman-fabric-write` (creds from backend/.env via app.config — never
printed) and uses it for the authenticated checks. Items that genuinely
need a human persona (filler / see-only / no-scope / real browser rendering)
are reported as DEFER, not silently skipped.

Run from repo root:
    python setup/smoke_prd.py                 # prod
    python setup/smoke_prd.py --staging       # staging app + stg app reg
"""
import argparse
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

import httpx  # noqa: E402

from app.config import get_settings  # noqa: E402

PRD_BASE = "https://cman-budget-web-prd.kindstone-f34836dd.southeastasia.azurecontainerapps.io"
STG_BASE = "https://cman-budget-web-stg.kindstone-f34836dd.southeastasia.azurecontainerapps.io"
PRD_APP_REG = "61d5d556-ee48-44f7-91b3-b8e05d6419aa"
STG_APP_REG = "7035aa47-0398-4b71-8411-7fc372e82123"

FORGED = "jakkaritw@chememan.com"  # an admin's email — the spoof must NEVER win
SECURITY_HEADERS = {
    "x-content-type-options": "nosniff",
    "x-frame-options": "SAMEORIGIN",
    "referrer-policy": "strict-origin-when-cross-origin",
    "strict-transport-security": "max-age=31536000; includeSubDomains",
}

results: list[tuple[str, str, str]] = []  # (item, PASS/FAIL/DEFER, note)


def check(item: str, ok: bool, note: str) -> bool:
    results.append((item, "PASS" if ok else "FAIL", note))
    return ok


def defer(item: str, note: str) -> None:
    results.append((item, "DEFER", note))


def _token(settings, app_reg: str) -> str | None:
    resp = httpx.post(
        f"https://login.microsoftonline.com/{settings.entra_tenant_id}/oauth2/v2.0/token",
        data={
            "client_id": settings.entra_client_id,
            "client_secret": settings.entra_client_secret,
            "scope": f"api://{app_reg}/.default",
            "grant_type": "client_credentials",
        },
        timeout=30,
    )
    if resp.status_code != 200:
        return None
    return resp.json()["access_token"]


COOKIE_FILE = Path(__file__).resolve().parent / "_auth_cookie.tmp.txt"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--staging", action="store_true")
    args = parser.parse_args()
    base = STG_BASE if args.staging else PRD_BASE
    settings = get_settings()
    client = httpx.Client(timeout=30, follow_redirects=False)

    print(f"smoke target: {base}\n")

    # --- 1.1 Platform & auth (unauthenticated) ---
    r = client.get(f"{base}/health")
    check("P1-01", r.status_code in (401, 302), f"unauth /health -> {r.status_code}")

    r = client.get(f"{base}/docs")
    ok1 = r.status_code in (401, 302)
    r2 = client.get(f"{base}/openapi.json")
    check("P1-02", ok1 and r2.status_code in (401, 302),
          f"unauth /docs -> {r.status_code}, /openapi.json -> {r2.status_code}")

    # P1-06a — forged Easy Auth header, NO session: must never reach the app.
    r = client.get(f"{base}/me", headers={"x-ms-client-principal-name": FORGED})
    forged_won = r.status_code == 200 and FORGED in r.text
    check("P1-06a", not forged_won, f"unauth+forged /me -> {r.status_code} (forged must not win)")

    # --- authenticated via a real browser session cookie ---
    # NOTE: SP client-credentials Bearer tokens get a 403 from Easy Auth's
    # "client application requirement: allow requests only from this
    # application itself" (verified on prod 2026-07-28) — that is the DESIRED
    # prod posture, so the harness uses a copied AppServiceAuthSession cookie
    # from jakkaritw's browser instead (gitignored tmp file, expires ~8h).
    if not COOKIE_FILE.exists():
        check("AUTH", False,
              f"cookie file missing: {COOKIE_FILE.name} — copy the AppServiceAuthSession cookie value from browser devtools into it")
        _report()
        return 1
    cookie = COOKIE_FILE.read_text(encoding="utf-8").strip()
    client.cookies.set("AppServiceAuthSession", cookie, domain=base.split("//")[1])
    auth: dict[str, str] = {}
    check("AUTH", True, "AppServiceAuthSession cookie loaded")

    r = client.get(f"{base}/health", headers=auth)
    shallow = r.status_code == 200 and '"ok"' in r.text
    r = client.get(f"{base}/health?deep=1", headers=auth)
    deep = r.status_code == 200 and '"db":"ok"' in r.text.replace(" ", "")
    check("P1-04", shallow and deep, f"/health ok={shallow}, deep db:ok={deep}")

    # P1-05 — /me returns the session's REAL identity.
    r = client.get(f"{base}/me", headers=auth)
    check("P1-05", r.status_code == 200 and FORGED in r.text and "production" in r.text,
          f"/me -> {r.status_code} {r.text[:80]!r}")

    # P1-06b — forged header INSIDE a valid session: forged must lose.
    # Session owner is jakkaritw; forge a DIFFERENT identity so the test can
    # actually tell them apart.
    FORGED_OTHER = "nipapornt@chememan.com"
    r = client.get(f"{base}/me", headers={**auth, "x-ms-client-principal-name": FORGED_OTHER})
    forged_won = FORGED_OTHER in r.text
    check("P1-06b", not forged_won,
          f"session+forged({FORGED_OTHER}) /me -> {r.status_code} (CRITICAL if forged wins)")

    # P1-07 — app-level security headers on an app-served response.
    r = client.get(f"{base}/health", headers=auth)
    missing = [h for h, v in SECURITY_HEADERS.items() if r.headers.get(h) != v]
    check("P1-07", not missing, f"missing/wrong: {missing or 'none'}")

    # --- 1.2 App shell & assets ---
    r = client.get(f"{base}/", headers=auth)
    is_spa = r.status_code == 200 and "text/html" in r.headers.get("content-type", "")
    check("P1-08", is_spa, f"/ -> {r.status_code} {r.headers.get('content-type')}")

    r = client.get(f"{base}/some/client-side/route", headers=auth)
    check("P1-09", r.status_code == 200 and "text/html" in r.headers.get("content-type", ""),
          f"SPA fallback -> {r.status_code}")

    defer("P1-03", "browser login — jakkaritw did it on stg+prd 2026-07-28 (manual, PASS)")
    defer("P1-10", "deep-link render — needs real browser session; covered by live e2e locally")
    defer("P1-11", "fonts-blocked degradation — covered by font-blocked-degradation work 2026-07-24")

    # --- 1.3 Read-API sweep (SP persona = no scope; shape/status must be clean) ---
    r = client.get(f"{base}/budget", params={"department": "Accounting", "year": 2027}, headers=auth)
    check("P1-13", r.status_code in (200, 400, 401, 403), f"/budget -> {r.status_code} (no 5xx)")

    r = client.get(f"{base}/budget/gl-accounts", headers=auth)
    check("P1-14a", r.status_code in (200, 401, 403), f"/budget/gl-accounts -> {r.status_code}")

    r = client.get(f"{base}/reference/countries", headers=auth)
    check("P1-14b", r.status_code in (200, 401, 403), f"/reference/countries -> {r.status_code}")

    r = client.get(f"{base}/approval/pending-for-me", params={"fiscal_year": 2027}, headers=auth)
    ok15 = r.status_code in (200, 401, 403)
    r2 = client.get(f"{base}/approval/status", params={"department": "Accounting", "fiscal_year": 2027}, headers=auth)
    check("P1-15", ok15 and r2.status_code in (200, 401, 403, 404),
          f"/approval/pending-for-me -> {r.status_code}, /approval/status -> {r2.status_code}")

    r = client.get(f"{base}/attachments", params={"department": "Accounting", "fiscal_year": 2027}, headers=auth)
    note = f"/attachments -> {r.status_code}"
    # folders not yet created on prod (P0-19): 502 folder_not_found is EXPECTED.
    check("P1-16", r.status_code in (200, 502, 401, 403), note + (" (502=folder not created yet, expected)" if r.status_code == 502 else ""))

    defer("P1-12", "per-role /scope sweep (admin/filler/see-only/no-scope) — needs real personas, Phase 2")
    defer("P1-17", "cross-scope 403 — needs a real filler persona, Phase 2")
    defer("P1-18", "status mapping — unit-covered (write_model.ERROR_HTTP_STATUS, 126 tests)")
    defer("P1-19", "502 on DB-down — unit-covered (test_conn_open_502) + stg db:fail evidence today")
    defer("P1-20", "Thai error copy — unit-covered (api/client.test.ts) + e2e edge-states")

    _report()
    return 1 if any(s == "FAIL" for _, s, _ in results) else 0


def _report() -> None:
    print(f"\n{'item':<8} {'result':<6} note")
    print("-" * 100)
    for item, status, note in results:
        print(f"{item:<8} {status:<6} {note}")
    n_fail = sum(1 for _, s, _ in results if s == "FAIL")
    n_pass = sum(1 for _, s, _ in results if s == "PASS")
    n_def = sum(1 for _, s, _ in results if s == "DEFER")
    print("-" * 100)
    print(f"PASS={n_pass} FAIL={n_fail} DEFER={n_def}")


if __name__ == "__main__":
    raise SystemExit(main())
