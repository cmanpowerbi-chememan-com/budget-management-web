"""Security response headers — set by `app.main`'s `add_security_headers`
middleware on EVERY response: API routes (incl. errors), /health, and the
served SPA. Content-Security-Policy is deliberately absent for now (would
break the Vite/React SPA) — pinned by a test below so adding it later is an
explicit, tested change.
"""
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.main import add_security_headers
from app.static import mount_frontend

EXPECTED_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "SAMEORIGIN",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "Strict-Transport-Security": "max-age=31536000; includeSubDomains",
}


def _assert_all_security_headers(response) -> None:
    for name, value in EXPECTED_HEADERS.items():
        assert response.headers.get(name) == value, f"missing/wrong header: {name}"


def test_security_headers_on_health(client):
    response = client.get("/health")
    assert response.status_code == 200
    _assert_all_security_headers(response)


def test_security_headers_on_api_error_response(client):
    # "EVERY response" includes error responses — a 401 raised by the auth
    # dependency still passes back out through the middleware.
    response = client.get("/budget", params={"year": 2027})
    assert response.status_code == 401
    _assert_all_security_headers(response)


def test_security_headers_on_spa_route(tmp_path):
    """SPA fallback (index.html for a deep link) carries the headers too.

    Isolated test app with a controlled tmp dist, same convention as
    test_static.py — whether a real `frontend/dist` exists on this machine
    must not decide the outcome.
    """
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "index.html").write_text("<html>INDEX</html>", encoding="utf-8")

    test_app = FastAPI(title="test")
    test_app.middleware("http")(add_security_headers)
    mount_frontend(test_app, dist)
    spa_client = TestClient(test_app)

    response = spa_client.get("/some/deep-link")
    assert response.status_code == 200
    assert "INDEX" in response.text
    _assert_all_security_headers(response)


def test_no_content_security_policy_yet(client):
    """CSP deferred (would break the Vite/React SPA asset/inline loading) —
    lock the deferral in so a future CSP lands as a deliberate change."""
    response = client.get("/health")
    assert "Content-Security-Policy" not in response.headers
