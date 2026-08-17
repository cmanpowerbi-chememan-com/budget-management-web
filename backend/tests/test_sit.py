"""Unit tests for GET/POST /sit/impersonate — the SIT-admin cookie-selection
endpoint (2026-08-17; CSRF-hardened 2026-08-18 per gate finding — a
state-changing GET had no CSRF defense, see `app.routers.sit`).

GET renders a self-contained HTML page (inline CSS only, no external
assets) listing the configured targets as same-origin POST forms; it must
NEVER mutate the cookie itself. POST performs the actual set/clear and
enforces a same-origin check on the `Origin` header (present + mismatched
=> reject; absent => allowed, so non-browser/legit same-origin clients that
omit `Origin` are not broken).

Both verbs 404 (never 403) whenever `app.auth.sit_targets_for`'s guard
would not pass for an AUTHENTICATED caller (production / non-admin / unset
/ not-the-configured-`from_email`). An UNAUTHENTICATED caller (no header,
no local DEV override) still gets the same 401 every other protected route
in this app gives — this endpoint does not hide its existence from a bare
probe, only from a logged-in non-privileged one.
"""
from http.cookies import SimpleCookie

from app.auth import SIT_COOKIE_NAME
from app.config import Settings, get_settings
from app.main import app

ADMIN_EMAIL = "jakkaritw@chememan.com"
TARGET_1 = "nipapornt@chememan.com"
TARGET_2 = "warapornt@chememan.com"
SECOND_ADMIN_EMAIL = "piyadad@chememan.com"  # a real admin, NOT the configured from_email

SIT_SETTINGS = Settings(
    _env_file=None,
    app_env="local",
    admin_emails=ADMIN_EMAIL,
    sit_impersonate=f"{ADMIN_EMAIL}:{TARGET_1},{TARGET_2}",
)


def _override_settings(settings: Settings) -> None:
    app.dependency_overrides[get_settings] = lambda: settings


def _admin_headers(email: str = ADMIN_EMAIL) -> dict:
    return {"x-ms-client-principal-name": email}


# --- GET /sit/impersonate — read-only page ---------------------------------


def test_get_page_200_lists_targets_with_thai_disclaimer_no_external_assets(client):
    _override_settings(SIT_SETTINGS)
    response = client.get("/sit/impersonate", headers=_admin_headers())
    assert response.status_code == 200
    assert "text/html" in response.headers.get("content-type", "")
    body = response.text
    assert TARGET_1 in body
    assert TARGET_2 in body
    assert "staging" in body.lower() or "SIT" in body  # names itself as a test aid
    assert "ทดสอบ" in body  # Thai disclaimer text is present
    assert 'method="post"' in body.lower()
    # no external asset references — everything must be inline
    assert "<link" not in body.lower()
    assert "src=\"http" not in body.lower()
    assert "src='http" not in body.lower()
    assert "<script src" not in body.lower()


def test_get_page_never_sets_or_mutates_the_cookie(client):
    """A GET must be side-effect-free — only POST may write the cookie."""
    _override_settings(SIT_SETTINGS)
    response = client.get(
        "/sit/impersonate",
        headers={**_admin_headers(), "cookie": f"{SIT_COOKIE_NAME}={TARGET_1}"},
    )
    assert response.status_code == 200
    assert "set-cookie" not in response.headers


def test_get_page_marks_the_cookie_selected_target_as_active(client):
    _override_settings(SIT_SETTINGS)
    response = client.get(
        "/sit/impersonate",
        headers={**_admin_headers(), "cookie": f"{SIT_COOKIE_NAME}={TARGET_2}"},
    )
    assert response.status_code == 200
    # crude but sufficient: TARGET_2 must appear closer to an "active" marker
    # than a bare listing would — assert the word appears at all near it.
    assert TARGET_2 in response.text


def test_get_404_in_production(client):
    prod_settings = Settings(
        _env_file=None,
        app_env="production",
        admin_emails=ADMIN_EMAIL,
        sit_impersonate=f"{ADMIN_EMAIL}:{TARGET_1}",
    )
    _override_settings(prod_settings)
    response = client.get("/sit/impersonate", headers=_admin_headers())
    assert response.status_code == 404


def test_get_404_for_non_admin_caller(client):
    _override_settings(SIT_SETTINGS)
    response = client.get("/sit/impersonate", headers=_admin_headers("somchai.j@chememan.com"))
    assert response.status_code == 404


def test_get_404_for_a_different_admin_not_the_configured_from_email(client):
    """Fix 2 (2026-08-18 gate): the router gate is exactly as strict as the
    rewrite gate — a DIFFERENT admin than the configured from_email is
    refused too."""
    settings = Settings(
        _env_file=None,
        app_env="local",
        admin_emails=f"{ADMIN_EMAIL},{SECOND_ADMIN_EMAIL}",
        sit_impersonate=f"{ADMIN_EMAIL}:{TARGET_1},{TARGET_2}",
    )
    _override_settings(settings)
    response = client.get("/sit/impersonate", headers=_admin_headers(SECOND_ADMIN_EMAIL))
    assert response.status_code == 404


def test_get_404_when_sit_impersonate_unset(client):
    no_alias_settings = Settings(_env_file=None, app_env="local", admin_emails=ADMIN_EMAIL)
    _override_settings(no_alias_settings)
    response = client.get("/sit/impersonate", headers=_admin_headers())
    assert response.status_code == 404


def test_get_401_without_auth_header(client):
    """An unauthenticated caller still gets a plain 401 (no header, no local
    DEV override) — this endpoint's 404 only applies to an AUTHENTICATED
    caller the guard refuses."""
    _override_settings(SIT_SETTINGS)
    response = client.get("/sit/impersonate")
    assert response.status_code == 401


# --- POST /sit/impersonate — the actual mutation ---------------------------


def test_post_200_sets_cookie_for_a_valid_target(client):
    _override_settings(SIT_SETTINGS)
    response = client.post(
        "/sit/impersonate", data={"as": TARGET_2}, headers=_admin_headers()
    )
    assert response.status_code == 200
    assert response.json() == {"impersonating": TARGET_2}
    set_cookie = response.headers.get("set-cookie", "")
    parsed = SimpleCookie()
    parsed.load(set_cookie)
    assert parsed[SIT_COOKIE_NAME].value == TARGET_2
    assert "httponly" in set_cookie.lower()
    assert "secure" in set_cookie.lower()
    assert "samesite=lax" in set_cookie.lower()
    assert "max-age" not in set_cookie.lower()  # session cookie


def test_post_clears_cookie_when_as_is_empty(client):
    _override_settings(SIT_SETTINGS)
    response = client.post("/sit/impersonate", data={"as": ""}, headers=_admin_headers())
    assert response.status_code == 200
    assert response.json() == {"impersonating": None}
    assert SIT_COOKIE_NAME in response.headers.get("set-cookie", "")


def test_post_clears_cookie_when_as_field_is_absent(client):
    _override_settings(SIT_SETTINGS)
    response = client.post("/sit/impersonate", data={}, headers=_admin_headers())
    assert response.status_code == 200
    assert response.json() == {"impersonating": None}


def test_post_400_for_off_allowlist_target_leaves_cookie_untouched(client):
    _override_settings(SIT_SETTINGS)
    response = client.post(
        "/sit/impersonate", data={"as": "nobody@chememan.com"}, headers=_admin_headers()
    )
    assert response.status_code == 400
    assert "set-cookie" not in response.headers


def test_post_404_in_production(client):
    prod_settings = Settings(
        _env_file=None,
        app_env="production",
        admin_emails=ADMIN_EMAIL,
        sit_impersonate=f"{ADMIN_EMAIL}:{TARGET_1}",
    )
    _override_settings(prod_settings)
    response = client.post("/sit/impersonate", data={"as": TARGET_1}, headers=_admin_headers())
    assert response.status_code == 404


def test_post_404_for_non_admin_caller(client):
    _override_settings(SIT_SETTINGS)
    response = client.post(
        "/sit/impersonate", data={"as": TARGET_1}, headers=_admin_headers("somchai.j@chememan.com")
    )
    assert response.status_code == 404


def test_post_404_when_sit_impersonate_unset(client):
    no_alias_settings = Settings(_env_file=None, app_env="local", admin_emails=ADMIN_EMAIL)
    _override_settings(no_alias_settings)
    response = client.post("/sit/impersonate", data={"as": TARGET_1}, headers=_admin_headers())
    assert response.status_code == 404


def test_post_401_without_auth_header(client):
    _override_settings(SIT_SETTINGS)
    response = client.post("/sit/impersonate", data={"as": TARGET_1})
    assert response.status_code == 401


# --- CSRF: same-origin check on POST (2026-08-18 gate fix 1) --------------


def test_post_cross_origin_rejected(client):
    _override_settings(SIT_SETTINGS)
    response = client.post(
        "/sit/impersonate",
        data={"as": TARGET_1},
        headers={**_admin_headers(), "origin": "https://evil.example.com"},
    )
    assert response.status_code == 403
    assert "set-cookie" not in response.headers


def test_post_same_origin_accepted(client):
    """A same-origin Origin header (matching the request's own scheme+host)
    must NOT be rejected."""
    _override_settings(SIT_SETTINGS)
    response = client.post(
        "/sit/impersonate",
        data={"as": TARGET_1},
        headers={**_admin_headers(), "origin": "http://testserver"},
    )
    assert response.status_code == 200
    assert response.json() == {"impersonating": TARGET_1}


def test_post_missing_origin_is_allowed(client):
    """Do NOT reject on a missing Origin — that would break legitimate
    same-origin form posts from clients that omit the header."""
    _override_settings(SIT_SETTINGS)
    response = client.post("/sit/impersonate", data={"as": TARGET_1}, headers=_admin_headers())
    assert response.status_code == 200
    assert response.json() == {"impersonating": TARGET_1}


def test_get_never_answers_with_a_403_csrf_style_rejection(client):
    """The CSRF check only applies to the mutating POST — GET must never be
    refused for an Origin/CSRF reason (it has no side effects to protect)."""
    _override_settings(SIT_SETTINGS)
    response = client.get(
        "/sit/impersonate",
        headers={**_admin_headers(), "origin": "https://evil.example.com"},
    )
    assert response.status_code == 200


# --- CSRF fix follow-up (2026-08-18 gate re-verify): Azure Container Apps
# terminates TLS at the edge and forwards to uvicorn over a plain internal
# connection (no `--proxy-headers`), so `request.url.scheme` reads "http"
# on the real deployment even though the browser's genuine Origin is
# "https://<staging-host>". The pre-fix same-origin check only ever
# compared against the REQUEST-derived origin, so every legitimate click on
# the picker's own buttons would 403 in production/staging — the feature
# would be dead on arrival. Fix: also accept a match against
# `settings.app_base_url` (the app's own configured public origin).

STAGING_HOST = "https://cman-budget-web-stg.kindstone-f34836dd.southeastasia.azurecontainerapps.io"


def test_post_same_origin_accepted_via_configured_app_base_url(client):
    """Regression test for the exact Container Apps TLS-termination bug: a
    genuine browser POST arrives with `Origin: https://<host>`, but the
    request itself is seen as plain http (simulated here — TestClient
    always sends plain http, matching the real topology where uvicorn never
    sees TLS). Must be accepted when Origin matches `settings.app_base_url`,
    not just the request-derived scheme+host."""
    settings = Settings(
        _env_file=None,
        app_env="local",
        admin_emails=ADMIN_EMAIL,
        sit_impersonate=f"{ADMIN_EMAIL}:{TARGET_1},{TARGET_2}",
        app_base_url=STAGING_HOST,
    )
    _override_settings(settings)
    response = client.post(
        "/sit/impersonate",
        data={"as": TARGET_1},
        headers={**_admin_headers(), "origin": STAGING_HOST},
    )
    assert response.status_code == 200
    assert response.json() == {"impersonating": TARGET_1}


def test_post_cross_origin_still_rejected_with_app_base_url_configured(client):
    settings = Settings(
        _env_file=None,
        app_env="local",
        admin_emails=ADMIN_EMAIL,
        sit_impersonate=f"{ADMIN_EMAIL}:{TARGET_1}",
        app_base_url=STAGING_HOST,
    )
    _override_settings(settings)
    response = client.post(
        "/sit/impersonate",
        data={"as": TARGET_1},
        headers={**_admin_headers(), "origin": "https://evil.example.com"},
    )
    assert response.status_code == 403
    assert "set-cookie" not in response.headers


def test_post_blank_app_base_url_falls_back_to_request_derived_origin(client):
    """When `app_base_url` is blank, the same-origin check must fall back
    to comparing against the request's own scheme+host — the pre-fix
    behaviour, preserved on purpose (local dev has no TLS-terminating edge
    proxy either)."""
    settings = Settings(
        _env_file=None,
        app_env="local",
        admin_emails=ADMIN_EMAIL,
        sit_impersonate=f"{ADMIN_EMAIL}:{TARGET_1}",
        app_base_url="",
    )
    _override_settings(settings)
    response = client.post(
        "/sit/impersonate",
        data={"as": TARGET_1},
        headers={**_admin_headers(), "origin": "http://testserver"},
    )
    assert response.status_code == 200
    assert response.json() == {"impersonating": TARGET_1}


def test_post_blank_app_base_url_still_rejects_cross_origin(client):
    settings = Settings(
        _env_file=None,
        app_env="local",
        admin_emails=ADMIN_EMAIL,
        sit_impersonate=f"{ADMIN_EMAIL}:{TARGET_1}",
        app_base_url="",
    )
    _override_settings(settings)
    response = client.post(
        "/sit/impersonate",
        data={"as": TARGET_1},
        headers={**_admin_headers(), "origin": "https://evil.example.com"},
    )
    assert response.status_code == 403


# --- Hardening (gate-suggested): an env-controlled target value must never
# be able to inject markup into the picker page.

def test_get_page_escapes_a_pathological_script_tag_target(client):
    settings = Settings(
        _env_file=None,
        app_env="local",
        admin_emails=ADMIN_EMAIL,
        sit_impersonate=f"{ADMIN_EMAIL}:<script>alert(1)</script>,{TARGET_1}",
    )
    _override_settings(settings)
    response = client.get("/sit/impersonate", headers=_admin_headers())
    assert response.status_code == 200
    body = response.text
    assert "<script>alert(1)</script>" not in body
    assert "&lt;script&gt;" in body
