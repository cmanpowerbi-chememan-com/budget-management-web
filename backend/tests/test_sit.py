"""Unit tests for GET/POST /sit/impersonate — the SIT/production-impersonation
cookie-selection endpoint (2026-08-17; CSRF-hardened 2026-08-18; widened to a
live, DB-backed target set + display directory by ADR-0031, 2026-09-23).

GET renders a self-contained HTML page (inline CSS + one inline `<script>`
for a client-side search filter, no external assets) listing the live
targets as same-origin POST forms; it must NEVER mutate the cookie itself.
POST performs the actual set/clear and enforces a same-origin check on the
`Origin` header (present + mismatched => reject; absent => allowed, so
non-browser/legit same-origin clients that omit `Origin` are not broken).

Both verbs 404 (never 403) whenever `app.auth.sit_targets_for`'s guard
would not pass for an AUTHENTICATED caller (production / non-admin / unset
/ not-the-configured-from-email). An UNAUTHENTICATED caller (no header, no
local DEV override) still gets the same 401 every other protected route in
this app gives. A DB failure while loading the live target set OR the
display directory turns into a 503 (ADR-0031 item 5) — never a 500, never a
silently empty page.

No live DB — `app.auth.get_fabric_conn` (the flat target-set query) and
`app.routers.sit.get_fabric_conn` (the display-directory query) are both
mocked via `_install_live_directory` below.
"""
from dataclasses import dataclass, field
from http.cookies import SimpleCookie
from unittest.mock import MagicMock

import pyodbc

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
    sit_impersonate=ADMIN_EMAIL,
)


def _override_settings(settings: Settings) -> None:
    app.dependency_overrides[get_settings] = lambda: settings


def _admin_headers(email: str = ADMIN_EMAIL) -> dict:
    return {"x-ms-client-principal-name": email}


@dataclass
class _Person:
    """One live impersonation target, as the picker should describe them."""

    email: str
    name: str
    role: str  # "filler" | "manager" | "both"
    empcode: str
    departments: list[str] = field(default_factory=lambda: ["Finance"])


@dataclass
class _Doubles:
    """The two mocked cursors `_install_live_directory` wires up, for tests
    that need to assert on call counts (e.g. cache-hit-avoids-a-requery)."""

    target_emails: list[str]
    targets_cursor: MagicMock  # behind app.auth.get_fabric_conn (flat target set)
    directory_cursor: MagicMock  # behind app.routers.sit.get_fabric_conn (display directory)


def _install_live_directory(monkeypatch, people: list[_Person]) -> _Doubles:
    """Wires BOTH `app.auth.get_fabric_conn` (the flat live target-set query
    `sit_targets_for` reads) and `app.routers.sit.get_fabric_conn` (the
    display-directory query `_load_target_directory` reads) so the picker
    sees exactly `people`, with no live connection ever opened. Returns a
    `_Doubles` — most callers only need the side effect (ignore the return
    value); tests only need `.target_emails` in `people` order."""
    target_emails = [p.email for p in people]

    targets_cursor = MagicMock()
    targets_cursor.fetchall.return_value = [(e,) for e in target_emails]
    targets_conn = MagicMock()
    targets_conn.cursor.return_value = targets_cursor
    targets_ctx = MagicMock()
    targets_ctx.__enter__.return_value = targets_conn
    targets_ctx.__exit__.return_value = False
    monkeypatch.setattr("app.auth.get_fabric_conn", lambda settings=None: targets_ctx)

    filler_rows = [(p.email, dept) for p in people if p.role in ("filler", "both") for dept in p.departments]
    manager_rows = [(p.email, dept) for p in people if p.role in ("manager", "both") for dept in p.departments]
    by_empcode = {p.empcode: p for p in people}
    by_email = {p.email: p for p in people}

    directory_cursor = MagicMock()
    state: dict = {}

    def _execute(sql, *params):
        state["sql"] = sql
        state["params"] = params

    def _fetchall():
        sql = state["sql"]
        if "FROM dbo.cc_filler_map\n    WHERE filler_email" in sql:
            return filler_rows
        if "JOIN dbo.v_employee_budget_01 e" in sql:
            return manager_rows
        raise AssertionError(f"unexpected fetchall after: {sql!r}")

    def _fetchone():
        sql, params = state["sql"], state["params"]
        if "SELECT employee_code, manager_employee_code" in sql:
            person = by_email.get(params[0].lower())
            return (person.empcode, None) if person else None
        if "SELECT TOP 1 full_name_en" in sql:
            person = by_empcode.get(params[0])
            return (person.name,) if person else None
        if "SELECT full_name_th" in sql:
            return None
        raise AssertionError(f"unexpected fetchone after: {sql!r}")

    directory_cursor.execute.side_effect = _execute
    directory_cursor.fetchall.side_effect = _fetchall
    directory_cursor.fetchone.side_effect = _fetchone

    directory_conn = MagicMock()
    directory_conn.cursor.return_value = directory_cursor
    directory_ctx = MagicMock()
    directory_ctx.__enter__.return_value = directory_conn
    directory_ctx.__exit__.return_value = False
    monkeypatch.setattr("app.routers.sit.get_fabric_conn", lambda settings=None: directory_ctx)

    return _Doubles(target_emails=target_emails, targets_cursor=targets_cursor, directory_cursor=directory_cursor)


_PEOPLE = [
    _Person(TARGET_1, "Nipaporn Tongking", "filler", "E001", ["Finance"]),
    _Person(TARGET_2, "Waraporn S.", "manager", "E002", ["HR"]),
]


# --- GET /sit/impersonate — read-only page ---------------------------------


def test_get_page_200_lists_targets_with_thai_disclaimer_no_external_assets(client, monkeypatch):
    _install_live_directory(monkeypatch, _PEOPLE)
    _override_settings(SIT_SETTINGS)
    response = client.get("/sit/impersonate", headers=_admin_headers())
    assert response.status_code == 200
    assert "text/html" in response.headers.get("content-type", "")
    body = response.text
    assert TARGET_1 in body
    assert TARGET_2 in body
    assert "Nipaporn Tongking" in body
    assert "staging" in body.lower() or "SIT" in body  # names itself as a test aid
    assert "ทดสอบ" in body  # Thai disclaimer text is present
    assert 'method="post"' in body.lower()
    # no external asset references — everything must be inline
    assert "<link" not in body.lower()
    assert "src=\"http" not in body.lower()
    assert "src='http" not in body.lower()
    assert "<script src" not in body.lower()


def test_get_page_shows_role_and_department_per_target(client, monkeypatch):
    _install_live_directory(monkeypatch, _PEOPLE)
    _override_settings(SIT_SETTINGS)
    body = client.get("/sit/impersonate", headers=_admin_headers()).text
    assert "Filler" in body
    assert "Manager" in body
    assert "Finance" in body
    assert "HR" in body


def test_get_page_combined_role_labeled_filler_plus_manager(client, monkeypatch):
    both = _Person(TARGET_1, "Both Person", "both", "E003", ["Finance", "Ops"])
    _install_live_directory(monkeypatch, [both])
    _override_settings(SIT_SETTINGS)
    body = client.get("/sit/impersonate", headers=_admin_headers()).text
    assert "Filler + Manager" in body


def test_get_page_has_a_search_input_and_all_rows_visible_without_js(client, monkeypatch):
    """The picker must work with NO JavaScript — every row is in the
    markup with no inline `display:none`, so a JS-disabled browser still
    sees the full list. The search box only ADDS client-side filtering."""
    _install_live_directory(monkeypatch, _PEOPLE)
    _override_settings(SIT_SETTINGS)
    body = client.get("/sit/impersonate", headers=_admin_headers()).text
    assert 'type="search"' in body
    assert "display:none" not in body.replace(" ", "")
    assert "display: none" not in body


def test_get_page_never_sets_or_mutates_the_cookie(client, monkeypatch):
    """A GET must be side-effect-free — only POST may write the cookie."""
    _install_live_directory(monkeypatch, _PEOPLE)
    _override_settings(SIT_SETTINGS)
    response = client.get(
        "/sit/impersonate",
        headers={**_admin_headers(), "cookie": f"{SIT_COOKIE_NAME}={TARGET_1}"},
    )
    assert response.status_code == 200
    assert "set-cookie" not in response.headers


def test_get_page_no_cookie_shows_self_at_top_not_a_target(client, monkeypatch):
    """Default (no `sit_as` cookie) = acting as yourself — never
    `targets[0]` (ADR-0031: jakkaritw is not himself in the live set)."""
    _install_live_directory(monkeypatch, _PEOPLE)
    _override_settings(SIT_SETTINGS)
    body = client.get("/sit/impersonate", headers=_admin_headers()).text
    assert "ตัวเอง" in body
    assert ADMIN_EMAIL in body


def test_get_page_marks_the_cookie_selected_target_as_active(client, monkeypatch):
    _install_live_directory(monkeypatch, _PEOPLE)
    _override_settings(SIT_SETTINGS)
    response = client.get(
        "/sit/impersonate",
        headers={**_admin_headers(), "cookie": f"{SIT_COOKIE_NAME}={TARGET_2}"},
    )
    assert response.status_code == 200
    body = response.text
    assert "กำลังสวมสิทธิ์อยู่" in body
    # the active target's row must come before the non-active one — "shown at the top"
    assert body.index(TARGET_2) < body.index(TARGET_1)


def test_get_page_stale_cookie_falls_back_to_self_not_404(client, monkeypatch):
    """A cookie naming someone no longer in the live set (e.g. dropped from
    `cc_filler_map`) must render self as active, never 404/500."""
    _install_live_directory(monkeypatch, _PEOPLE)
    _override_settings(SIT_SETTINGS)
    response = client.get(
        "/sit/impersonate",
        headers={**_admin_headers(), "cookie": f"{SIT_COOKIE_NAME}=pornthipp@chememan.com"},
    )
    assert response.status_code == 200
    assert "ตัวเอง" in response.text


def test_get_page_escapes_a_pathological_department_name(client, monkeypatch):
    """A department name coming from the DB must never inject markup into
    the picker page (targets are DB-backed now, not env-configured)."""
    pathological = _Person(TARGET_1, "Nipaporn Tongking", "filler", "E001", ["<script>alert(1)</script>"])
    _install_live_directory(monkeypatch, [pathological])
    _override_settings(SIT_SETTINGS)
    response = client.get("/sit/impersonate", headers=_admin_headers())
    assert response.status_code == 200
    body = response.text
    assert "<script>alert(1)</script>" not in body
    assert "&lt;script&gt;" in body


def test_get_page_escapes_quotes_and_script_tags_in_name_and_department(client, monkeypatch):
    """A name/department containing an unescaped quote could break out of an
    HTML attribute (e.g. `data-search="..."`) and inject a new attribute
    (`" onmouseover=...`); an unescaped `</script>` could break out of the
    page's own inline filter script. Both must come out `html.escape`d."""
    pathological = _Person(
        TARGET_1,
        'Nip "the boss" O\'Brien</script>',
        "filler",
        "E001",
        ['Finance "R&D" </script>'],
    )
    _install_live_directory(monkeypatch, [pathological])
    _override_settings(SIT_SETTINGS)
    response = client.get("/sit/impersonate", headers=_admin_headers())
    assert response.status_code == 200
    body = response.text
    assert "&quot;" in body
    assert '" onmouseover=' not in body
    # the page's own inline filter <script> must be the ONLY one — an
    # injected `</script>` from data would have produced a second one
    assert body.count("<script>") == 1
    assert body.count("</script>") == 1


def test_get_503_when_live_target_set_query_fails(client, monkeypatch):
    monkeypatch.setattr(
        "app.auth.get_fabric_conn", MagicMock(side_effect=pyodbc.Error("connection refused"))
    )
    _override_settings(SIT_SETTINGS)
    response = client.get("/sit/impersonate", headers=_admin_headers())
    assert response.status_code == 503


def test_get_503_when_directory_query_fails(client, monkeypatch):
    _install_live_directory(monkeypatch, _PEOPLE)
    monkeypatch.setattr(
        "app.routers.sit.get_fabric_conn", MagicMock(side_effect=pyodbc.Error("timeout"))
    )
    _override_settings(SIT_SETTINGS)
    response = client.get("/sit/impersonate", headers=_admin_headers())
    assert response.status_code == 503


def test_get_503_when_live_target_set_query_raises_a_non_pyodbc_exception(client, monkeypatch):
    """msal token acquisition (`app.db._acquire_access_token`) can fail
    before pyodbc is ever involved — that must still 503, not 500 (gate
    finding, 2026-09-23)."""
    monkeypatch.setattr(
        "app.auth.get_fabric_conn", MagicMock(side_effect=RuntimeError("msal token acquisition failed"))
    )
    _override_settings(SIT_SETTINGS)
    response = client.get("/sit/impersonate", headers=_admin_headers())
    assert response.status_code == 503


def test_get_503_when_directory_query_raises_a_non_pyodbc_exception(client, monkeypatch):
    _install_live_directory(monkeypatch, _PEOPLE)
    monkeypatch.setattr(
        "app.routers.sit.get_fabric_conn", MagicMock(side_effect=RuntimeError("msal token acquisition failed"))
    )
    _override_settings(SIT_SETTINGS)
    response = client.get("/sit/impersonate", headers=_admin_headers())
    assert response.status_code == 503


def test_post_503_when_live_target_set_query_raises_a_non_pyodbc_exception(client, monkeypatch):
    monkeypatch.setattr(
        "app.auth.get_fabric_conn", MagicMock(side_effect=RuntimeError("msal token acquisition failed"))
    )
    _override_settings(SIT_SETTINGS)
    response = client.post("/sit/impersonate", data={"as": TARGET_1}, headers=_admin_headers())
    assert response.status_code == 503
    assert "set-cookie" not in response.headers


def test_get_page_second_load_within_ttl_does_not_requery_the_directory(client, monkeypatch):
    doubles = _install_live_directory(monkeypatch, _PEOPLE)
    settings = Settings(
        _env_file=None,
        app_env="local",
        admin_emails=ADMIN_EMAIL,
        sit_impersonate=ADMIN_EMAIL,
        sit_targets_cache_ttl_seconds=600,
    )
    _override_settings(settings)

    first = client.get("/sit/impersonate", headers=_admin_headers())
    assert first.status_code == 200
    first_call_count = doubles.directory_cursor.execute.call_count
    assert first_call_count > 0

    second = client.get("/sit/impersonate", headers=_admin_headers())
    assert second.status_code == 200
    assert doubles.directory_cursor.execute.call_count == first_call_count  # no new query


UAT_SETTINGS = Settings(
    _env_file=None,
    app_env="uat",
    admin_emails=ADMIN_EMAIL,
    sit_impersonate=ADMIN_EMAIL,
)


def test_get_page_in_uat_warns_about_production_instead_of_claiming_staging(client, monkeypatch):
    """`app_env="uat"` means the picker is running on PRODUCTION (2026-09-06).

    The staging banner would then be actively false — it tells the operator the
    opposite of the truth at exactly the moment the warning matters most.
    """
    _install_live_directory(monkeypatch, _PEOPLE)
    _override_settings(UAT_SETTINGS)
    body = client.get("/sit/impersonate", headers=_admin_headers()).text

    assert "staging" not in body.lower()
    assert "ห้ามใช้งานจริง" not in body
    assert "UAT" in body
    assert "production" in body.lower()
    # the three things an operator must know before clicking a target here
    assert "ข้อมูลจริง" in body
    assert "อีเมลจริง" in body
    assert "ไม่ใช่ชื่อผู้ที่กดจริง" in body  # the audit trail records the TARGET


def test_get_page_in_staging_keeps_the_staging_banner(client, monkeypatch):
    """Pin the other branch, so a future edit cannot silently swap the copy."""
    _install_live_directory(monkeypatch, _PEOPLE)
    _override_settings(SIT_SETTINGS)
    body = client.get("/sit/impersonate", headers=_admin_headers()).text

    assert "staging (SIT)" in body
    assert "ห้ามใช้งานจริง" in body
    assert "UAT" not in body


def test_get_page_titles_and_heading_track_the_environment(client, monkeypatch):
    _install_live_directory(monkeypatch, _PEOPLE)
    _override_settings(UAT_SETTINGS)
    uat_body = client.get("/sit/impersonate", headers=_admin_headers()).text
    _install_live_directory(monkeypatch, _PEOPLE)
    _override_settings(SIT_SETTINGS)
    sit_body = client.get("/sit/impersonate", headers=_admin_headers()).text

    assert "<title>UAT Impersonation</title>" in uat_body
    assert "(UAT impersonation)" in uat_body
    assert "<title>SIT Impersonation</title>" in sit_body
    assert "(SIT impersonation)" in sit_body


def test_get_404_in_production(client, monkeypatch):
    mock_get_conn = MagicMock()
    monkeypatch.setattr("app.auth.get_fabric_conn", mock_get_conn)
    prod_settings = Settings(
        _env_file=None,
        app_env="production",
        admin_emails=ADMIN_EMAIL,
        sit_impersonate=ADMIN_EMAIL,
    )
    _override_settings(prod_settings)
    response = client.get("/sit/impersonate", headers=_admin_headers())
    assert response.status_code == 404
    mock_get_conn.assert_not_called()  # guard fails before any DB touch


def test_get_404_for_non_admin_caller(client, monkeypatch):
    mock_get_conn = MagicMock()
    monkeypatch.setattr("app.auth.get_fabric_conn", mock_get_conn)
    _override_settings(SIT_SETTINGS)
    response = client.get("/sit/impersonate", headers=_admin_headers("somchai.j@chememan.com"))
    assert response.status_code == 404
    mock_get_conn.assert_not_called()


def test_get_404_for_a_different_admin_not_the_configured_from_email(client, monkeypatch):
    """Fix 2 (2026-08-18 gate): the router gate is exactly as strict as the
    rewrite gate — a DIFFERENT admin than the configured from_email is
    refused too."""
    monkeypatch.setattr("app.auth.get_fabric_conn", MagicMock())
    settings = Settings(
        _env_file=None,
        app_env="local",
        admin_emails=f"{ADMIN_EMAIL},{SECOND_ADMIN_EMAIL}",
        sit_impersonate=ADMIN_EMAIL,
    )
    _override_settings(settings)
    response = client.get("/sit/impersonate", headers=_admin_headers(SECOND_ADMIN_EMAIL))
    assert response.status_code == 404


def test_get_404_when_sit_impersonate_unset(client, monkeypatch):
    monkeypatch.setattr("app.auth.get_fabric_conn", MagicMock())
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


def test_post_200_sets_cookie_for_a_valid_target(client, monkeypatch):
    _install_live_directory(monkeypatch, _PEOPLE)
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


def test_post_case_insensitive_target_match(client, monkeypatch):
    _install_live_directory(monkeypatch, _PEOPLE)
    _override_settings(SIT_SETTINGS)
    response = client.post(
        "/sit/impersonate", data={"as": TARGET_2.upper()}, headers=_admin_headers()
    )
    assert response.status_code == 200
    assert response.json() == {"impersonating": TARGET_2}


def test_post_clears_cookie_when_as_is_empty(client, monkeypatch):
    _install_live_directory(monkeypatch, _PEOPLE)
    _override_settings(SIT_SETTINGS)
    response = client.post("/sit/impersonate", data={"as": ""}, headers=_admin_headers())
    assert response.status_code == 200
    assert response.json() == {"impersonating": None}
    assert SIT_COOKIE_NAME in response.headers.get("set-cookie", "")


def test_post_clears_cookie_when_as_field_is_absent(client, monkeypatch):
    _install_live_directory(monkeypatch, _PEOPLE)
    _override_settings(SIT_SETTINGS)
    response = client.post("/sit/impersonate", data={}, headers=_admin_headers())
    assert response.status_code == 200
    assert response.json() == {"impersonating": None}


def test_post_400_for_off_allowlist_target_leaves_cookie_untouched(client, monkeypatch):
    _install_live_directory(monkeypatch, _PEOPLE)
    _override_settings(SIT_SETTINGS)
    response = client.post(
        "/sit/impersonate", data={"as": "nobody@chememan.com"}, headers=_admin_headers()
    )
    assert response.status_code == 400
    assert "set-cookie" not in response.headers


def test_post_400_for_a_target_removed_from_the_live_set(client, monkeypatch):
    """An old hand-typed target (e.g. `pornthipp@chememan.com`, dropped by
    ADR-0031) must be refused exactly like any other unknown target."""
    _install_live_directory(monkeypatch, _PEOPLE)
    _override_settings(SIT_SETTINGS)
    response = client.post(
        "/sit/impersonate", data={"as": "pornthipp@chememan.com"}, headers=_admin_headers()
    )
    assert response.status_code == 400
    assert "set-cookie" not in response.headers


def test_post_503_when_live_target_set_query_fails(client, monkeypatch):
    monkeypatch.setattr(
        "app.auth.get_fabric_conn", MagicMock(side_effect=pyodbc.Error("connection refused"))
    )
    _override_settings(SIT_SETTINGS)
    response = client.post("/sit/impersonate", data={"as": TARGET_1}, headers=_admin_headers())
    assert response.status_code == 503
    assert "set-cookie" not in response.headers


def test_post_404_in_production(client, monkeypatch):
    monkeypatch.setattr("app.auth.get_fabric_conn", MagicMock())
    prod_settings = Settings(
        _env_file=None,
        app_env="production",
        admin_emails=ADMIN_EMAIL,
        sit_impersonate=ADMIN_EMAIL,
    )
    _override_settings(prod_settings)
    response = client.post("/sit/impersonate", data={"as": TARGET_1}, headers=_admin_headers())
    assert response.status_code == 404


def test_post_404_for_non_admin_caller(client, monkeypatch):
    monkeypatch.setattr("app.auth.get_fabric_conn", MagicMock())
    _override_settings(SIT_SETTINGS)
    response = client.post(
        "/sit/impersonate", data={"as": TARGET_1}, headers=_admin_headers("somchai.j@chememan.com")
    )
    assert response.status_code == 404


def test_post_404_when_sit_impersonate_unset(client, monkeypatch):
    monkeypatch.setattr("app.auth.get_fabric_conn", MagicMock())
    no_alias_settings = Settings(_env_file=None, app_env="local", admin_emails=ADMIN_EMAIL)
    _override_settings(no_alias_settings)
    response = client.post("/sit/impersonate", data={"as": TARGET_1}, headers=_admin_headers())
    assert response.status_code == 404


def test_post_401_without_auth_header(client):
    _override_settings(SIT_SETTINGS)
    response = client.post("/sit/impersonate", data={"as": TARGET_1})
    assert response.status_code == 401


# --- CSRF: same-origin check on POST (2026-08-18 gate fix 1) --------------


def test_post_cross_origin_rejected(client, monkeypatch):
    _install_live_directory(monkeypatch, _PEOPLE)
    _override_settings(SIT_SETTINGS)
    response = client.post(
        "/sit/impersonate",
        data={"as": TARGET_1},
        headers={**_admin_headers(), "origin": "https://evil.example.com"},
    )
    assert response.status_code == 403
    assert "set-cookie" not in response.headers


def test_post_same_origin_accepted(client, monkeypatch):
    """A same-origin Origin header (matching the request's own scheme+host)
    must NOT be rejected."""
    _install_live_directory(monkeypatch, _PEOPLE)
    _override_settings(SIT_SETTINGS)
    response = client.post(
        "/sit/impersonate",
        data={"as": TARGET_1},
        headers={**_admin_headers(), "origin": "http://testserver"},
    )
    assert response.status_code == 200
    assert response.json() == {"impersonating": TARGET_1}


def test_post_missing_origin_is_allowed(client, monkeypatch):
    """Do NOT reject on a missing Origin — that would break legitimate
    same-origin form posts from clients that omit the header."""
    _install_live_directory(monkeypatch, _PEOPLE)
    _override_settings(SIT_SETTINGS)
    response = client.post("/sit/impersonate", data={"as": TARGET_1}, headers=_admin_headers())
    assert response.status_code == 200
    assert response.json() == {"impersonating": TARGET_1}


def test_get_never_answers_with_a_403_csrf_style_rejection(client, monkeypatch):
    """The CSRF check only applies to the mutating POST — GET must never be
    refused for an Origin/CSRF reason (it has no side effects to protect)."""
    _install_live_directory(monkeypatch, _PEOPLE)
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


def test_post_same_origin_accepted_via_configured_app_base_url(client, monkeypatch):
    """Regression test for the exact Container Apps TLS-termination bug: a
    genuine browser POST arrives with `Origin: https://<host>`, but the
    request itself is seen as plain http (simulated here — TestClient
    always sends plain http, matching the real topology where uvicorn never
    sees TLS). Must be accepted when Origin matches `settings.app_base_url`,
    not just the request-derived scheme+host."""
    _install_live_directory(monkeypatch, _PEOPLE)
    settings = Settings(
        _env_file=None,
        app_env="local",
        admin_emails=ADMIN_EMAIL,
        sit_impersonate=ADMIN_EMAIL,
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


def test_post_cross_origin_still_rejected_with_app_base_url_configured(client, monkeypatch):
    _install_live_directory(monkeypatch, _PEOPLE)
    settings = Settings(
        _env_file=None,
        app_env="local",
        admin_emails=ADMIN_EMAIL,
        sit_impersonate=ADMIN_EMAIL,
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


def test_post_blank_app_base_url_falls_back_to_request_derived_origin(client, monkeypatch):
    """When `app_base_url` is blank, the same-origin check must fall back
    to comparing against the request's own scheme+host — the pre-fix
    behaviour, preserved on purpose (local dev has no TLS-terminating edge
    proxy either)."""
    _install_live_directory(monkeypatch, _PEOPLE)
    settings = Settings(
        _env_file=None,
        app_env="local",
        admin_emails=ADMIN_EMAIL,
        sit_impersonate=ADMIN_EMAIL,
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


def test_post_blank_app_base_url_still_rejects_cross_origin(client, monkeypatch):
    _install_live_directory(monkeypatch, _PEOPLE)
    settings = Settings(
        _env_file=None,
        app_env="local",
        admin_emails=ADMIN_EMAIL,
        sit_impersonate=ADMIN_EMAIL,
        app_base_url="",
    )
    _override_settings(settings)
    response = client.post(
        "/sit/impersonate",
        data={"as": TARGET_1},
        headers={**_admin_headers(), "origin": "https://evil.example.com"},
    )
    assert response.status_code == 403
