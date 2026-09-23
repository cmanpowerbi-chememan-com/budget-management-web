"""GET/POST /sit/impersonate — lets the configured admin pick who the
`sit_as` cookie impersonates for THIS browser session (2026-08-17;
CSRF-hardened 2026-08-18; widened to permanent production impersonation with
a live, DB-backed target set by ADR-0031, 2026-09-23).

See `app.auth.sit_targets_for` / `app.auth._apply_sit_impersonation` for the
guard and `app.auth.live_sit_targets` for the live target set (every Filler
in `dbo.cc_filler_map` UNION each Filler's manager). `SIT_IMPERSONATE` now
only names the from-side (who may impersonate) — see `app.config` and
`app.auth._parse_sit_from_email`.

Decoupled from `notifications_environment_label` on purpose (jakkaritw,
2026-08-17): staging removes that label so SIT mail looks byte-identical to
production, so this endpoint's own existence check must not depend on it —
see the guard in `app.auth.sit_targets_for`.

ADR-0031 (2026-09-23): the picker now also shows, per target, an English
display name, a role (Filler / Manager / Filler + Manager), and the
department(s) that role covers — resolved live via `app.approval
.resolve_submitter` / `lookup_employee_name` (the SAME name-resolution path
the rest of the app already uses). `_load_target_directory` is a SEPARATE
query from `app.auth.live_sit_targets` because it needs per-row department
detail the flat target-set query does not; both are Filler ∪
manager-of-Filler, kept in sync intentionally, defined once each. ANY
failure at EITHER step (a DB error, or an msal/token-acquisition error the
connection depends on — see `app.auth.live_sit_targets`) turns into a 503
here (never a 500, never a silently empty page) — this is the one SIT
surface allowed to fail loud, since `app.auth._apply_sit_impersonation` on
every OTHER request already fails closed to "act as yourself" instead.

CSRF fix (2026-08-18 gate finding): the original design was a single
state-changing GET (`?as=<email>` set the cookie directly), which SameSite=Lax
still attaches to on a top-level navigation — a link sent to an admin could
silently switch their session's impersonated identity with no visible
indicator. Split into a read-only GET (renders an HTML picker page, mutates
nothing) and a POST that performs the actual set/clear, with a same-origin
check on `Origin` (present-and-mismatched => reject; ABSENT => allowed, so
legitimate same-origin clients that omit the header are not broken).

Same-origin check topology fix (2026-08-18 gate re-verify): Azure Container
Apps terminates TLS at the edge and forwards to uvicorn (run with no
`--proxy-headers`, see `backend/Dockerfile`) over a PLAIN internal
connection, so `request.url.scheme` reads "http" even on the real
https-only deployment. Comparing `Origin` only against the request-derived
scheme+host made every genuine click 403 in production/staging — the
picker would have been dead on arrival. `_is_cross_origin` now ALSO accepts
a match against `settings.app_base_url` (the app's own configured public
origin); a blank `app_base_url` falls back to the request-derived
comparison only (local dev has no such edge proxy either).

Both verbs 404 (never 403) whenever `sit_targets_for` refuses an
AUTHENTICATED caller (production / non-admin / unset / not the configured
`from_email`), so the endpoint's existence is never revealed to a caller the
guard would refuse anyway. This does NOT extend to an UNAUTHENTICATED
caller: a bare probe with no Easy Auth header (and no local DEV override)
still gets the same plain 401 every other protected route in this app
answers with — this endpoint is not special-cased to hide itself from an
anonymous prober, only from a logged-in non-privileged one.
"""
import logging
from collections import defaultdict
from html import escape
from urllib.parse import urlsplit

from fastapi import APIRouter, Cookie, Depends, Form, HTTPException, Request, Response
from fastapi.responses import HTMLResponse

from app.approval import lookup_employee_name, resolve_submitter
from app.auth import SIT_COOKIE_NAME, _select_sit_target, get_real_caller_email, sit_targets_for
from app.cache import TTLCache
from app.config import Settings, get_settings
from app.db import get_fabric_conn

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/sit")

# Session cookie (no max_age), httponly + secure + samesite=lax, whole-site
# path — shared by both the set and the clear response.
_COOKIE_FLAGS = {"httponly": True, "samesite": "lax", "secure": True, "path": "/"}

# 503 detail shown on the picker page when either DB read fails (ADR-0031
# item 5) — the guard/existence check (404) and a DB failure (503) must
# never be confused with one another.
_DB_UNAVAILABLE_TH = "ไม่สามารถโหลดรายชื่อผู้ถูกสวมสิทธิ์ได้ในขณะนี้ กรุณาลองใหม่อีกครั้ง"

_ROLE_FILLER = "Filler"
_ROLE_MANAGER = "Manager"
_ROLE_BOTH = "Filler + Manager"

# Per-row department detail for the picker (ADR-0031) — a SEPARATE query
# from `app.auth._SIT_LIVE_TARGETS_SQL` because that one only needs the flat
# email set. Both define "Filler" / "manager of a Filler" the same way
# (`dbo.cc_filler_map` + `dbo.v_employee_budget_01.manager_email`) — kept in
# sync by construction, not by sharing SQL text, since this one also needs
# `department`.
_FILLER_DEPARTMENTS_SQL = """
    SELECT DISTINCT LOWER(LTRIM(RTRIM(filler_email))) AS target_email, department
    FROM dbo.cc_filler_map
    WHERE filler_email IS NOT NULL AND LTRIM(RTRIM(filler_email)) <> ''
"""

_MANAGER_DEPARTMENTS_SQL = """
    SELECT DISTINCT LOWER(LTRIM(RTRIM(e.manager_email))) AS target_email, f.department AS department
    FROM dbo.cc_filler_map f
    JOIN dbo.v_employee_budget_01 e
      ON LOWER(LTRIM(RTRIM(e.email))) = LOWER(LTRIM(RTRIM(f.filler_email)))
    WHERE e.manager_email IS NOT NULL AND LTRIM(RTRIM(e.manager_email)) <> ''
      AND e.is_primary_row = 1
"""


_TARGET_DIRECTORY_CACHE_KEY = "target_directory"
_target_directory_cache: TTLCache[list[dict]] = TTLCache()


def clear_sit_target_directory_cache() -> None:
    """Test-only reset — mirrors `app.auth.clear_sit_targets_cache`. The
    conftest autouse fixture calls both, so neither cache ever leaks a
    mocked directory/target-set from one test into another."""
    _target_directory_cache.clear()


def _load_target_directory(settings: Settings, targets: list[str]) -> list[dict]:
    """TTL-cached (`settings.sit_targets_cache_ttl_seconds` — same TTL as
    `app.auth.live_sit_targets`) wrapper around `_query_target_directory`.
    Cached under one fixed key: `targets` itself already comes from the
    (independently cached) live target set, so it does not vary within a
    TTL window in practice, and a fixed key avoids hashing a ~95-item list
    on every GET. A failed load is never cached (`TTLCache` guarantees
    this), so a DB hiccup recovers on the very next request."""
    return _target_directory_cache.get_or_load(
        _TARGET_DIRECTORY_CACHE_KEY,
        settings.sit_targets_cache_ttl_seconds,
        lambda: _query_target_directory(settings, targets),
    )


def _query_target_directory(settings: Settings, targets: list[str]) -> list[dict]:
    """One-shot DB read behind `_load_target_directory`'s cache. One row per
    live impersonation target: an English display name
    (`app.approval.resolve_submitter` + `lookup_employee_name` — the same
    name-resolution path the rest of the app already uses), a role (Filler /
    Manager / Filler + Manager), and the department(s) that role covers
    (Filler: departments they fill; Manager: departments of the Fillers they
    manage; both roles: the union). Opens its own connection — called only
    once the SIT guard has already passed, for a `GET /sit/impersonate`
    render (admin-only, ~95 rows, occasional). Raises on a connection/query
    failure (`pyodbc.Error`, or an msal/token-acquisition exception — see
    `app.auth.live_sit_targets`'s docstring for why it is not always a
    pyodbc type) — the router turns that into a 503, per ADR-0031."""
    with get_fabric_conn(settings) as conn:
        cursor = conn.cursor()
        try:
            cursor.execute(_FILLER_DEPARTMENTS_SQL)
            filler_rows = cursor.fetchall()
            cursor.execute(_MANAGER_DEPARTMENTS_SQL)
            manager_rows = cursor.fetchall()
        finally:
            cursor.close()

        filler_departments: dict[str, set[str]] = defaultdict(set)
        for target_email, department in filler_rows:
            if target_email and department:
                filler_departments[target_email].add(department)

        manager_departments: dict[str, set[str]] = defaultdict(set)
        for target_email, department in manager_rows:
            if target_email and department:
                manager_departments[target_email].add(department)

        rows = []
        for target_email in targets:
            is_filler = target_email in filler_departments
            is_manager = target_email in manager_departments
            if is_filler and is_manager:
                role = _ROLE_BOTH
            elif is_filler:
                role = _ROLE_FILLER
            else:
                role = _ROLE_MANAGER
            departments = sorted(
                filler_departments.get(target_email, set()) | manager_departments.get(target_email, set())
            )

            empcode, _ = resolve_submitter(conn, target_email)
            name = lookup_employee_name(conn, empcode) or target_email

            rows.append({"email": target_email, "name": name, "role": role, "departments": departments})
        return rows

# The banner is derived from `app_env`, never hardcoded, because the same picker now
# serves two very different situations and a wrong banner is worse than none:
#
#   app_env="local"  -> staging. Historically the only place this ran.
#   app_env="uat"    -> PRODUCTION, during a UAT round (2026-09-06). Saying "staging only,
#                       do not use for real" there is actively false, and it is the exact
#                       moment the operator most needs to be told the opposite.
#
# Deriving it also means the revert (APP_ENV back to "production") needs no second code
# change — the page 404s again and the banner question disappears with it.
_DISCLAIMER_STAGING_TH = "เครื่องมือนี้ใช้เฉพาะสำหรับทดสอบบน staging (SIT) เท่านั้น ห้ามใช้งานจริง"
_DISCLAIMER_UAT_TH = (
    "โหมด UAT บนระบบจริง (production) — ทุกการกดบันทึก อนุมัติ หรือตีกลับ "
    "มีผลกับข้อมูลจริงและส่งอีเมลจริงถึงคนจริง "
    "ระบบจะบันทึกชื่อผู้ที่ถูกสวมสิทธิ์ ไม่ใช่ชื่อผู้ที่กดจริง"
)
_UAT_ENV = "uat"


def _mode_copy(settings: Settings) -> tuple[str, str]:
    """Return `(banner, heading_suffix)` for the current environment."""
    if settings.app_env.strip().lower() == _UAT_ENV:
        return _DISCLAIMER_UAT_TH, "UAT"
    return _DISCLAIMER_STAGING_TH, "SIT"


def _render_page(directory: list[dict], active_target: str, self_email: str, settings: Settings) -> str:
    """Build the self-contained (inline CSS, no external assets) picker
    page for ~95 targets. Every target is its own same-origin
    `<form method="post">` so selecting one is a real POST, never a GET
    link. Rows are sorted by name, with the currently active target (if
    any) moved to the front. Works with NO JavaScript — every row is
    always present in the markup and visible by default; the inline
    `<script>` only adds a client-side search filter on top."""
    disclaimer, mode = _mode_copy(settings)
    is_impersonating = active_target != self_email

    sorted_rows = sorted(directory, key=lambda r: r["name"].lower())
    if is_impersonating:
        sorted_rows.sort(key=lambda r: 0 if r["email"] == active_target else 1)

    if is_impersonating:
        active_row = next((r for r in sorted_rows if r["email"] == active_target), None)
        active_label = (
            f'{escape(active_row["name"])} ({escape(active_target)})' if active_row else escape(active_target)
        )
        status_html = f'<p class="status">กำลังสวมสิทธิ์อยู่: <strong>{active_label}</strong></p>'
    else:
        status_html = (
            f'<p class="status">ยังไม่ได้สวมสิทธิ์ — ทำงานในนามตัวเอง: '
            f'<strong>ตัวเอง ({escape(self_email)})</strong></p>'
        )

    rows_html = []
    for row in sorted_rows:
        safe_email = escape(row["email"])
        safe_name = escape(row["name"])
        safe_role = escape(row["role"])
        safe_departments = escape(", ".join(row["departments"])) if row["departments"] else "-"
        search_blob = escape(" ".join([row["name"], row["email"], row["role"], *row["departments"]]).lower())
        is_active = row["email"] == active_target
        marker = ' class="target active"' if is_active else ' class="target"'
        active_suffix = " (กำลังสวมสิทธิ์อยู่)" if is_active else ""
        rows_html.append(
            f'<form method="post"><div{marker} data-search="{search_blob}">'
            f'<div class="who"><span class="name">{safe_name}{active_suffix}</span>'
            f'<span class="email">{safe_email}</span>'
            f'<span class="meta">{safe_role} · {safe_departments}</span></div>'
            f'<button type="submit" name="as" value="{safe_email}">สวมสิทธิ์</button></div></form>'
        )

    return f"""<!doctype html>
<html lang="th">
<head>
<meta charset="utf-8">
<title>{mode} Impersonation</title>
<style>
  body {{ font-family: system-ui, sans-serif; max-width: 640px; margin: 40px auto; padding: 0 16px; color: #1a1a1a; }}
  .banner {{ background: #fff3cd; border: 1px solid #d1a300; padding: 12px 16px; border-radius: 6px; margin-bottom: 24px; font-size: 14px; }}
  .status {{ font-size: 14px; margin-bottom: 16px; }}
  input[type="search"] {{ width: 100%; padding: 8px 12px; margin-bottom: 16px; border: 1px solid #ccc; border-radius: 6px; box-sizing: border-box; font-size: 14px; }}
  .target {{ display: flex; align-items: center; justify-content: space-between; padding: 12px 0; border-bottom: 1px solid #e0e0e0; gap: 12px; }}
  .target.active {{ font-weight: 600; background: #f0f8ff; }}
  .who {{ display: flex; flex-direction: column; }}
  .who .email, .who .meta {{ font-size: 12px; color: #666; font-weight: normal; }}
  button {{ padding: 8px 16px; border-radius: 6px; border: 1px solid #999; background: #f5f5f5; cursor: pointer; flex-shrink: 0; }}
  button.clear {{ background: #fdecea; border-color: #d9534f; }}
</style>
</head>
<body>
  <div class="banner">{disclaimer}</div>
  <h1>เลือกสวมสิทธิ์ผู้อนุมัติ ({mode} impersonation)</h1>
  {status_html}
  <input type="search" id="sitSearch" placeholder="ค้นหาชื่อ อีเมล หรือฝ่าย..." oninput="sitFilterRows()">
  <div id="sitRows">{''.join(rows_html)}</div>
  <form method="post">
    <button class="clear" type="submit" name="as" value="">หยุดสวมสิทธิ์ (clear)</button>
  </form>
  <script>
    function sitFilterRows() {{
      var q = document.getElementById('sitSearch').value.trim().toLowerCase();
      var rows = document.querySelectorAll('#sitRows .target');
      for (var i = 0; i < rows.length; i++) {{
        var haystack = rows[i].getAttribute('data-search') || '';
        rows[i].parentElement.style.display = (q === '' || haystack.indexOf(q) !== -1) ? '' : 'none';
      }}
    }}
  </script>
</body>
</html>"""


def _origin_of(url: str) -> str | None:
    """`scheme://host[:port]` of `url`, or `None` if it doesn't parse to a
    usable origin (blank, or missing scheme/host)."""
    parsed = urlsplit(url)
    if not parsed.scheme or not parsed.netloc:
        return None
    return f"{parsed.scheme}://{parsed.netloc}"


def _is_cross_origin(request: Request, origin: str, settings: Settings) -> bool:
    """True only when `origin` is present AND matches NEITHER of the two
    origins this app can legitimately be reached on:

    1. `settings.app_base_url` — the app's own configured public origin.
       Required because Container Apps terminates TLS at the edge and
       forwards to uvicorn over a plain connection (no `--proxy-headers`),
       so `request.url.scheme` reads "http" even though a real browser's
       `Origin` is "https://<the deployed host>".
    2. This request's own scheme+host — covers local dev (no such edge
       proxy) and a blank `app_base_url` (fallback).

    A missing `Origin` is never treated as cross-origin — some legitimate
    same-origin clients omit it.
    """
    request_origin = f"{request.url.scheme}://{request.url.netloc}"
    if origin == request_origin:
        return False

    configured_origin = _origin_of(settings.app_base_url) if settings.app_base_url else None
    if configured_origin and origin == configured_origin:
        return False

    return True


@router.get("/impersonate", response_class=HTMLResponse)
def impersonate_page(
    sit_as: str | None = Cookie(default=None, alias=SIT_COOKIE_NAME),
    email: str = Depends(get_real_caller_email),
    settings: Settings = Depends(get_settings),
) -> HTMLResponse:
    """Read-only picker page — mutates nothing (see module docstring). Both
    live-DB reads (the target set, the display directory) turn a failure
    into a 503 — never a 500, never a silently empty page (ADR-0031)."""
    try:
        targets = sit_targets_for(email, settings)
    except Exception:
        logger.warning("sit: failed to load the live impersonation target set", exc_info=True)
        raise HTTPException(status_code=503, detail=_DB_UNAVAILABLE_TH) from None
    if targets is None:
        raise HTTPException(status_code=404)

    try:
        directory = _load_target_directory(settings, targets)
    except Exception:
        logger.warning("sit: failed to load the impersonation target directory", exc_info=True)
        raise HTTPException(status_code=503, detail=_DB_UNAVAILABLE_TH) from None

    active_target = _select_sit_target(targets, sit_as, self_email=email)
    return HTMLResponse(_render_page(directory, active_target, email, settings))


@router.post("/impersonate")
def impersonate_submit(
    request: Request,
    response: Response,
    as_: str = Form(default="", alias="as"),
    email: str = Depends(get_real_caller_email),
    settings: Settings = Depends(get_settings),
) -> dict:
    """Set/clear the `sit_as` cookie. Form field `as=<email>` must be one of
    the LIVE impersonation targets (`app.auth.live_sit_targets`);
    empty/absent clears the cookie. CSRF-checked (see `_is_cross_origin`)
    before any other logic."""
    origin = request.headers.get("origin")
    if origin and _is_cross_origin(request, origin, settings):
        raise HTTPException(status_code=403, detail="Cross-origin request refused")

    try:
        targets = sit_targets_for(email, settings)
    except Exception:
        logger.warning("sit: failed to load the live impersonation target set", exc_info=True)
        raise HTTPException(status_code=503, detail=_DB_UNAVAILABLE_TH) from None
    if targets is None:
        raise HTTPException(status_code=404)

    if not as_.strip():
        response.delete_cookie(key=SIT_COOKIE_NAME, **_COOKIE_FLAGS)
        return {"impersonating": None}

    requested = as_.strip()
    match = next((t for t in targets if t.lower() == requested.lower()), None)
    if match is None:
        raise HTTPException(status_code=400, detail="Unknown SIT impersonation target")

    response.set_cookie(key=SIT_COOKIE_NAME, value=match, **_COOKIE_FLAGS)
    return {"impersonating": match}
