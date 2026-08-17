"""GET/POST /sit/impersonate — lets an admin pick which `SIT_IMPERSONATE`
target the `sit_as` cookie selects for THIS browser session (2026-08-17;
CSRF-hardened 2026-08-18).

See `app.auth.sit_targets_for` / `app.auth._apply_sit_impersonation` for the
guard and the "from:target1[,target2,...]" grammar this endpoint reads.

Decoupled from `notifications_environment_label` on purpose (jakkaritw,
2026-08-17): staging removes that label so SIT mail looks byte-identical to
production, so this endpoint's own existence check must not depend on it —
see the guard in `app.auth.sit_targets_for`.

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
from html import escape
from urllib.parse import urlsplit

from fastapi import APIRouter, Cookie, Depends, Form, HTTPException, Request, Response
from fastapi.responses import HTMLResponse

from app.auth import SIT_COOKIE_NAME, _select_sit_target, get_real_caller_email, sit_targets_for
from app.config import Settings, get_settings

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/sit")

# Session cookie (no max_age), httponly + secure + samesite=lax, whole-site
# path — shared by both the set and the clear response.
_COOKIE_FLAGS = {"httponly": True, "samesite": "lax", "secure": True, "path": "/"}

_DISCLAIMER_TH = "เครื่องมือนี้ใช้เฉพาะสำหรับทดสอบบน staging (SIT) เท่านั้น ห้ามใช้งานจริง"


def _render_page(targets: list[str], active_target: str) -> str:
    """Build the self-contained (inline CSS, no external assets) picker
    page. Every target is its own same-origin `<form method="post">` so
    selecting one is a real POST, never a GET link."""
    rows = []
    for target in targets:
        safe_target = escape(target)
        is_active = target == active_target
        marker = ' class="target active"' if is_active else ' class="target"'
        label = f"{safe_target}{' (กำลังสวมสิทธิ์อยู่)' if is_active else ''}"
        rows.append(
            f'<form method="post"><div{marker}><span>{label}</span>'
            f'<button type="submit" name="as" value="{safe_target}">สวมสิทธิ์</button></div></form>'
        )

    return f"""<!doctype html>
<html lang="th">
<head>
<meta charset="utf-8">
<title>SIT Impersonation</title>
<style>
  body {{ font-family: system-ui, sans-serif; max-width: 480px; margin: 40px auto; padding: 0 16px; color: #1a1a1a; }}
  .banner {{ background: #fff3cd; border: 1px solid #d1a300; padding: 12px 16px; border-radius: 6px; margin-bottom: 24px; font-size: 14px; }}
  .target {{ display: flex; align-items: center; justify-content: space-between; padding: 12px 0; border-bottom: 1px solid #e0e0e0; }}
  .target.active {{ font-weight: 600; }}
  button {{ padding: 8px 16px; border-radius: 6px; border: 1px solid #999; background: #f5f5f5; cursor: pointer; }}
  button.clear {{ background: #fdecea; border-color: #d9534f; }}
</style>
</head>
<body>
  <div class="banner">{_DISCLAIMER_TH}</div>
  <h1>เลือกสวมสิทธิ์ผู้อนุมัติ (SIT impersonation)</h1>
  <p>สวมสิทธิ์ปัจจุบัน: <strong>{escape(active_target)}</strong></p>
  {''.join(rows)}
  <form method="post">
    <button class="clear" type="submit" name="as" value="">หยุดสวมสิทธิ์ (clear)</button>
  </form>
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
    """Read-only picker page — mutates nothing (see module docstring)."""
    targets = sit_targets_for(email, settings)
    if targets is None:
        raise HTTPException(status_code=404)

    active_target = _select_sit_target(targets, sit_as)
    return HTMLResponse(_render_page(targets, active_target))


@router.post("/impersonate")
def impersonate_submit(
    request: Request,
    response: Response,
    as_: str = Form(default="", alias="as"),
    email: str = Depends(get_real_caller_email),
    settings: Settings = Depends(get_settings),
) -> dict:
    """Set/clear the `sit_as` cookie. Form field `as=<email>` must be one of
    the configured `SIT_IMPERSONATE` targets; empty/absent clears the
    cookie. CSRF-checked (see `_is_cross_origin`) before any other logic."""
    origin = request.headers.get("origin")
    if origin and _is_cross_origin(request, origin, settings):
        raise HTTPException(status_code=403, detail="Cross-origin request refused")

    targets = sit_targets_for(email, settings)
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
