"""Unit tests for GET /health — DB always mocked, no live connection."""
from unittest.mock import MagicMock, patch

import pyodbc

from app.config import Settings, get_settings
from app.main import app


def test_health_shallow_returns_200_without_touching_db(client):
    with patch("app.routers.health.get_fabric_conn") as mock_get_conn:
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}
        mock_get_conn.assert_not_called()


def test_health_deep_success_reports_db_ok(client):
    app.dependency_overrides[get_settings] = lambda: Settings(
        _env_file=None,
        fabric_sql_server="fabric-host",
        fabric_sql_database="fabric_sql_database",
        entra_client_id="id",
        entra_client_secret="secret",
    )
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_conn.cursor.return_value = mock_cursor
    with patch("app.routers.health.get_fabric_conn") as mock_get_conn:
        mock_get_conn.return_value.__enter__.return_value = mock_conn
        response = client.get("/health?deep=1")
        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "ok"
        assert body["db"] == "ok"


def test_health_deep_failure_reports_db_fail_without_leaking_secrets(client):
    app.dependency_overrides[get_settings] = lambda: Settings(
        _env_file=None,
        fabric_sql_server="fabric-host",
        fabric_sql_database="fabric_sql_database",
        entra_client_id="id",
        entra_client_secret="topsecret",
    )
    with patch("app.routers.health.get_fabric_conn") as mock_get_conn:
        mock_get_conn.side_effect = pyodbc.Error("connection refused")
        response = client.get("/health?deep=1")
        assert response.status_code == 200
        body = response.json()
        assert body["db"] == "fail"
        assert "topsecret" not in response.text


def test_health_deep_reports_db_fail_on_token_acquisition_failure(client):
    """`_acquire_access_token` (app.db) raises RuntimeError on token failure,
    not pyodbc.Error — deep=1 must still degrade to db:fail, not a 500."""
    app.dependency_overrides[get_settings] = lambda: Settings(
        _env_file=None,
        fabric_sql_server="fabric-host",
        fabric_sql_database="fabric_sql_database",
        entra_client_id="id",
        entra_client_secret="topsecret",
    )
    with patch("app.routers.health.get_fabric_conn") as mock_get_conn:
        mock_get_conn.side_effect = RuntimeError("msal token acquisition failed: invalid_client - bad secret")
        response = client.get("/health?deep=1")
        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "ok"
        assert body["db"] == "fail"
        assert "topsecret" not in response.text


def test_health_deep_reports_not_configured_when_env_missing(client):
    app.dependency_overrides[get_settings] = lambda: Settings(_env_file=None)
    response = client.get("/health?deep=1")
    assert response.status_code == 200
    assert response.json()["db"] == "not_configured"
