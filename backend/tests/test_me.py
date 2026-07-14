"""Unit tests for GET /me — auth smoke test."""
from app.config import Settings, get_settings
from app.main import app


def test_me_returns_email_and_app_env_with_valid_header(client):
    response = client.get(
        "/me", headers={"x-ms-client-principal-name": "somchai.j@chememan.com"}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["email"] == "somchai.j@chememan.com"
    assert "app_env" in body


def test_me_401_without_header_in_production_mode(client):
    app.dependency_overrides[get_settings] = lambda: Settings(
        _env_file=None, app_env="production"
    )
    response = client.get("/me")
    assert response.status_code == 401


def test_me_dev_override_in_local_mode(client):
    app.dependency_overrides[get_settings] = lambda: Settings(
        _env_file=None, app_env="local", dev_auth_email="dev@chememan.com"
    )
    response = client.get("/me")
    assert response.status_code == 200
    body = response.json()
    assert body["email"] == "dev@chememan.com"
    assert body["app_env"] == "local"
