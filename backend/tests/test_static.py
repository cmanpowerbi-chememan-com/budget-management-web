"""Unit tests for SPA static serving (A14 step 1).

Mounting the built frontend is a structural, import-time decision (Starlette
resolves routes in registration order once, at app construction) — so these
tests build isolated FastAPI test apps mirroring `app.main`'s router set and
call `mount_frontend` directly with a controlled `tmp_path`, rather than
depending on whether a real `frontend/out` happens to exist on this machine.
That keeps the "absent vs present" cases deterministic across environments.
"""
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.config import Settings, get_settings
from app.routers import approval, attachments, budget, budget_write, health, me, reference, scope, subform
from app.static import mount_frontend

ALL_ROUTERS = (health, me, scope, budget, budget_write, approval, reference, subform, attachments)


def _build_test_app() -> FastAPI:
    """Fresh FastAPI app with the same routers as app.main, unmounted.

    Settings are pinned to `_env_file=None`: these apps must be hermetic —
    with the documented local backend/.env (APP_ENV=local + DEV_AUTH_EMAIL)
    the real auth dependency would return the dev email and /budget would
    hit the LIVE DB instead of raising 401."""
    test_app = FastAPI(title="test")
    test_app.dependency_overrides[get_settings] = lambda: Settings(_env_file=None)
    for module in ALL_ROUTERS:
        test_app.include_router(module.router)
    return test_app


def test_static_dir_absent_no_mount_and_all_routes_fine(tmp_path):
    missing_dir = tmp_path / "does-not-exist"
    test_app = _build_test_app()

    mounted = mount_frontend(test_app, missing_dir)

    assert mounted is False
    # no catch-all/spa route or static mount was added
    assert not any(getattr(r, "path", None) == "/{full_path:path}" for r in test_app.router.routes)
    assert not any(getattr(r, "path", None) == "/assets" for r in test_app.router.routes)

    client = TestClient(test_app)
    resp = client.get("/openapi.json")
    assert resp.status_code == 200
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_static_dir_present_serves_asset_with_long_cache(tmp_path):
    dist = tmp_path / "dist"
    assets_dir = dist / "assets"
    assets_dir.mkdir(parents=True)
    (dist / "index.html").write_text("<html>INDEX</html>", encoding="utf-8")
    (assets_dir / "app-abc123.js").write_text("console.log('hi')", encoding="utf-8")

    test_app = _build_test_app()
    mounted = mount_frontend(test_app, dist)
    assert mounted is True

    client = TestClient(test_app)
    resp = client.get("/assets/app-abc123.js")
    assert resp.status_code == 200
    assert "console.log" in resp.text
    assert "max-age" in resp.headers.get("cache-control", "")


def test_static_dir_present_serves_next_asset_with_long_cache(tmp_path):
    dist = tmp_path / "dist"
    next_static_dir = dist / "_next" / "static"
    next_static_dir.mkdir(parents=True)
    (dist / "index.html").write_text("<html>INDEX</html>", encoding="utf-8")
    (next_static_dir / "app-abc123.js").write_text("console.log('hi')", encoding="utf-8")

    test_app = _build_test_app()
    mounted = mount_frontend(test_app, dist)
    assert mounted is True

    client = TestClient(test_app)
    resp = client.get("/_next/static/app-abc123.js")
    assert resp.status_code == 200
    assert "console.log" in resp.text
    assert "max-age" in resp.headers.get("cache-control", "")


def test_unknown_deep_link_path_falls_back_to_index_html_no_cache(tmp_path):
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "index.html").write_text("<html>INDEX</html>", encoding="utf-8")

    test_app = _build_test_app()
    mount_frontend(test_app, dist)
    client = TestClient(test_app)

    # simulates a hard reload on a client-side deep link, e.g. ?dept=&year=
    resp = client.get("/some/deep-link", params={"dept": "Finance", "year": "2027"})
    assert resp.status_code == 200
    assert "INDEX" in resp.text
    assert resp.headers.get("cache-control") == "no-cache"


def test_root_path_serves_index_html(tmp_path):
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "index.html").write_text("<html>INDEX</html>", encoding="utf-8")

    test_app = _build_test_app()
    mount_frontend(test_app, dist)
    client = TestClient(test_app)

    resp = client.get("/")
    assert resp.status_code == 200
    assert "INDEX" in resp.text


def test_missing_asset_with_extension_returns_404_not_index(tmp_path):
    """A broken/missing asset reference (has a file extension) must 404,
    never silently mask itself as an SPA deep link."""
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "index.html").write_text("<html>INDEX</html>", encoding="utf-8")

    test_app = _build_test_app()
    mount_frontend(test_app, dist)
    client = TestClient(test_app)

    resp = client.get("/favicon.ico")
    assert resp.status_code == 404
    assert "INDEX" not in resp.text


def test_budget_route_still_hits_api_not_spa_fallback(tmp_path):
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "index.html").write_text("<html>INDEX</html>", encoding="utf-8")

    test_app = _build_test_app()
    mount_frontend(test_app, dist)
    client = TestClient(test_app)

    # No auth header -> the real /budget route's own auth dependency raises
    # 401 (never reaches the SPA fallback / never 200s with HTML).
    resp = client.get("/budget", params={"year": 2027})
    assert resp.status_code == 401
    assert "INDEX" not in resp.text


def test_openapi_and_docs_paths_still_reserved_when_static_mounted(tmp_path):
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "index.html").write_text("<html>INDEX</html>", encoding="utf-8")

    test_app = _build_test_app()
    mount_frontend(test_app, dist)
    client = TestClient(test_app)

    resp = client.get("/openapi.json")
    assert resp.status_code == 200
    assert resp.json().get("openapi")

    resp = client.get("/docs")
    assert resp.status_code == 200
    assert "INDEX" not in resp.text


# --- Path traversal / arbitrary file read (CWE-22) -------------------------
#
# `spa_fallback` used to do `static_dir / full_path` and serve it with
# FileResponse without checking the resolved path stayed inside static_dir.
# A URL-encoded `..` (`%2e%2e`) is decoded by the ASGI layer before the app
# ever sees `full_path`, so `GET /%2e%2e/secret.txt` reached a file OUTSIDE
# the mounted static directory. These tests plant a secret file outside the
# static dir and prove none of the traversal encodings can read it: the
# response must always be a 404 or the SPA index.html, never the secret.

_SECRET_CONTENTS = "SECRET_CONTENTS_DO_NOT_LEAK"


def _build_traversal_app(tmp_path, dist_depth=1):
    """Build a mounted test app whose static dir sits `dist_depth` levels
    under tmp_path, with a secret file planted at tmp_path (outside the
    static dir) for traversal tests to try to reach."""
    dist = tmp_path
    for part in ["nested"] * (dist_depth - 1) + ["dist"]:
        dist = dist / part
    dist.mkdir(parents=True)
    (dist / "index.html").write_text("<html>INDEX</html>", encoding="utf-8")

    secret = tmp_path / "top-secret.txt"
    secret.write_text(_SECRET_CONTENTS, encoding="utf-8")

    test_app = _build_test_app()
    mount_frontend(test_app, dist)
    return TestClient(test_app), dist


def _assert_no_leak(resp):
    assert _SECRET_CONTENTS not in resp.text
    # Only two legitimate outcomes for an out-of-bounds path: 404, or the
    # SPA index.html fallback (extension-less-looking unknown path). Never
    # a bare 200 serving the escaped file's raw contents.
    assert resp.status_code == 404 or "INDEX" in resp.text


def test_path_traversal_encoded_dotdot_single_does_not_leak_secret(tmp_path):
    client, _ = _build_traversal_app(tmp_path)
    resp = client.get("/%2e%2e/top-secret.txt")
    _assert_no_leak(resp)


def test_path_traversal_encoded_dotdot_double_does_not_leak_secret(tmp_path):
    # dist is nested 2 levels deep here so the double `..` actually lands on
    # tmp_path (where the secret lives) instead of overshooting past it.
    client, _ = _build_traversal_app(tmp_path, dist_depth=2)
    resp = client.get("/%2e%2e%2f%2e%2e%2ftop-secret.txt")
    _assert_no_leak(resp)


def test_path_traversal_raw_dotdot_does_not_leak_secret(tmp_path):
    """A literal `../` may get collapsed client-side by httpx before the
    request is even sent (defence in depth from the HTTP client library) —
    kept anyway since the fix must not rely on that collapsing happening."""
    client, _ = _build_traversal_app(tmp_path)
    resp = client.get("/../top-secret.txt")
    _assert_no_leak(resp)


def test_path_traversal_deep_encoded_escape_does_not_leak_secret(tmp_path):
    """`..%2f..%2f..%2f`-style deep escape (the etc/passwd shape), from a
    static dir nested 3 levels deep, must still be contained."""
    client, _ = _build_traversal_app(tmp_path, dist_depth=3)
    resp = client.get("/%2e%2e%2f%2e%2e%2f%2e%2e%2ftop-secret.txt")
    _assert_no_leak(resp)


def test_path_traversal_backslash_variant_does_not_leak_secret(tmp_path):
    """Backslash-as-separator variant (Windows path-join quirk if the fix
    only sanitized `/`-separated segments instead of resolving the path)."""
    client, _ = _build_traversal_app(tmp_path)
    resp = client.get("/..%5Ctop-secret.txt")
    _assert_no_leak(resp)


def test_legit_extension_less_route_still_serves_index_after_fix(tmp_path):
    client, _ = _build_traversal_app(tmp_path)
    resp = client.get("/some/dept-view")
    assert resp.status_code == 200
    assert "INDEX" in resp.text


def test_real_asset_still_served_after_fix(tmp_path):
    client, dist = _build_traversal_app(tmp_path)
    (dist / "app-real123.js").write_text("console.log('real')", encoding="utf-8")
    resp = client.get("/app-real123.js")
    assert resp.status_code == 200
    assert "console.log" in resp.text
