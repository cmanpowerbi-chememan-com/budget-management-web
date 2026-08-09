"""Unit tests for GET /scope — DB always mocked, no live connection."""
from unittest.mock import MagicMock, patch

from app.auth import get_current_user_email
from app.main import app
from app.rls import Scope


def _mock_conn(fill_rows: list[tuple], manager_add_rows: list[tuple]) -> MagicMock:
    cursor = MagicMock()
    cursor.fetchall.side_effect = [fill_rows, manager_add_rows]
    # ADR-0029 approver see-overlay: `resolve_scope` now also resolves the
    # caller's empcode (`resolve_submitter`'s `fetchone()`) to check for a
    # pending department. `None` = "not in the employee view" -> overlay
    # short-circuits with no further `fetchall()` calls, matching this
    # test's pre-ADR-0029 fixture (2 rows queried, nothing more).
    cursor.fetchone.return_value = None
    conn = MagicMock()
    conn.cursor.return_value = cursor
    return conn


def test_scope_returns_fill_and_see_for_authenticated_user(client):
    app.dependency_overrides[get_current_user_email] = lambda: "filler@chememan.com"
    mock_conn = _mock_conn(fill_rows=[("10CA013000",)], manager_add_rows=[])
    with patch("app.routers.scope.get_fabric_conn") as mock_get_conn:
        mock_get_conn.return_value.__enter__.return_value = mock_conn
        response = client.get("/scope")

    assert response.status_code == 200
    body = response.json()
    assert body["email"] == "filler@chememan.com"
    assert body["fill_cost_centers"] == ["10CA013000"]
    assert body["see_cost_centers"] == ["10CA013000"]
    assert body["role"] == "filler"
    assert body["is_admin"] is False


def test_scope_401_without_auth_header_in_production_mode(client):
    response = client.get("/scope")
    assert response.status_code == 401


def test_scope_db_error_during_resolve_returns_502_not_500(client):
    """A pyodbc.Error inside `resolve_scope` used to propagate uncaught
    (HTTP 500) — a Fabric SQL failure on this read must be a 502."""
    import pyodbc

    app.dependency_overrides[get_current_user_email] = lambda: "user@chememan.com"
    with patch("app.routers.scope.get_fabric_conn") as mock_get_conn, patch(
        "app.routers.scope.resolve_scope", side_effect=pyodbc.Error("08S01", "boom")
    ):
        mock_get_conn.return_value.__enter__.return_value = MagicMock()
        response = client.get("/scope")

    assert response.status_code == 502
    assert "boom" not in response.text


def test_scope_passes_admin_view_enabled_query_param_through_to_resolve_scope(client):
    app.dependency_overrides[get_current_user_email] = lambda: "admin@chememan.com"
    with patch("app.routers.scope.get_fabric_conn") as mock_get_conn, patch(
        "app.routers.scope.resolve_scope"
    ) as mock_resolve:
        mock_get_conn.return_value.__enter__.return_value = MagicMock()
        mock_resolve.return_value = Scope(
            email="admin@chememan.com",
            is_admin=True,
            role="admin",
            fill_cost_centers=[],
            see_cost_centers=[],
        )
        response = client.get("/scope?admin_view_enabled=true")

    assert response.status_code == 200
    _, kwargs = mock_resolve.call_args
    assert kwargs["admin_view_enabled"] is True


def test_scope_admin_view_enabled_defaults_to_false(client):
    app.dependency_overrides[get_current_user_email] = lambda: "user@chememan.com"
    with patch("app.routers.scope.get_fabric_conn") as mock_get_conn, patch(
        "app.routers.scope.resolve_scope"
    ) as mock_resolve:
        mock_get_conn.return_value.__enter__.return_value = MagicMock()
        mock_resolve.return_value = Scope(
            email="user@chememan.com",
            is_admin=False,
            role="none",
            fill_cost_centers=[],
            see_cost_centers=[],
        )
        response = client.get("/scope")

    assert response.status_code == 200
    _, kwargs = mock_resolve.call_args
    assert kwargs["admin_view_enabled"] is False
