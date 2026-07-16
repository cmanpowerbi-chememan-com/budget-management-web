"""Unit tests for GET /budget/gl-accounts + GET /scope/departments — DB
always mocked, no live connection."""
from unittest.mock import MagicMock, patch

from app.auth import get_current_user_email
from app.main import app
from app.rls import Scope


def _override_auth(email: str) -> None:
    app.dependency_overrides[get_current_user_email] = lambda: email


# ---------------------------------------------------------------------------
# GET /budget/gl-accounts
# ---------------------------------------------------------------------------

def test_gl_accounts_401_without_auth_header(client):
    response = client.get("/budget/gl-accounts")
    assert response.status_code == 401


def test_gl_accounts_returns_list(client):
    _override_auth("user@chememan.com")
    fake_rows = [{"gl_code": "6211800030", "gl_group": "Office expenses", "gl_name": "x", "is_special": False}]
    with patch("app.routers.reference.get_fabric_conn") as mock_fabric, patch(
        "app.routers.reference.fetch_gl_accounts", return_value=fake_rows
    ):
        mock_fabric.return_value.__enter__.return_value = MagicMock()
        response = client.get("/budget/gl-accounts")

    assert response.status_code == 200
    assert response.json() == fake_rows


def test_gl_accounts_502_on_db_error(client):
    import pyodbc

    _override_auth("user@chememan.com")
    with patch("app.routers.reference.get_fabric_conn") as mock_fabric, patch(
        "app.routers.reference.fetch_gl_accounts", side_effect=pyodbc.Error("boom")
    ):
        mock_fabric.return_value.__enter__.return_value = MagicMock()
        response = client.get("/budget/gl-accounts")

    assert response.status_code == 502


# ---------------------------------------------------------------------------
# GET /scope/departments
# ---------------------------------------------------------------------------

def test_departments_401_without_auth_header(client):
    response = client.get("/scope/departments")
    assert response.status_code == 401


def test_departments_non_admin_passes_see_cost_centers(client):
    _override_auth("filler@chememan.com")
    fake_scope = Scope(
        email="filler@chememan.com", is_admin=False, role="filler",
        fill_cost_centers=["CC1"], see_cost_centers=["CC1", "CC2"],
    )
    with patch("app.routers.reference.get_fabric_conn") as mock_fabric, patch(
        "app.routers.reference.resolve_scope", return_value=fake_scope
    ), patch("app.routers.reference.fetch_departments", return_value=[]) as mock_fetch:
        mock_fabric.return_value.__enter__.return_value = MagicMock()
        response = client.get("/scope/departments")

    assert response.status_code == 200
    args, _ = mock_fetch.call_args
    assert sorted(args[1]) == ["CC1", "CC2"]


def test_departments_admin_view_enabled_passes_none_for_admin_wide(client):
    _override_auth("admin@chememan.com")
    fake_scope = Scope(email="admin@chememan.com", is_admin=True, role="admin", fill_cost_centers=[], see_cost_centers=[])
    with patch("app.routers.reference.get_fabric_conn") as mock_fabric, patch(
        "app.routers.reference.resolve_scope", return_value=fake_scope
    ), patch("app.routers.reference.fetch_departments", return_value=[]) as mock_fetch:
        mock_fabric.return_value.__enter__.return_value = MagicMock()
        response = client.get("/scope/departments?admin_view_enabled=true")

    assert response.status_code == 200
    args, _ = mock_fetch.call_args
    assert args[1] is None


def test_departments_non_admin_admin_view_enabled_true_does_not_widen(client):
    """Never-cut: a non-admin passing admin_view_enabled=True must still get
    their own See-scope list, never None (admin-wide)."""
    _override_auth("user@chememan.com")
    fake_scope = Scope(email="user@chememan.com", is_admin=False, role="filler", fill_cost_centers=["CC1"], see_cost_centers=["CC1"])
    with patch("app.routers.reference.get_fabric_conn") as mock_fabric, patch(
        "app.routers.reference.resolve_scope", return_value=fake_scope
    ), patch("app.routers.reference.fetch_departments", return_value=[]) as mock_fetch:
        mock_fabric.return_value.__enter__.return_value = MagicMock()
        response = client.get("/scope/departments?admin_view_enabled=true")

    assert response.status_code == 200
    args, _ = mock_fetch.call_args
    assert args[1] == ["CC1"]


def test_departments_502_on_db_error(client):
    import pyodbc

    _override_auth("user@chememan.com")
    fake_scope = Scope(email="user@chememan.com", is_admin=False, role="filler", fill_cost_centers=[], see_cost_centers=["CC1"])
    with patch("app.routers.reference.get_fabric_conn") as mock_fabric, patch(
        "app.routers.reference.resolve_scope", return_value=fake_scope
    ), patch("app.routers.reference.fetch_departments", side_effect=pyodbc.Error("boom")):
        mock_fabric.return_value.__enter__.return_value = MagicMock()
        response = client.get("/scope/departments")

    assert response.status_code == 502


def test_departments_db_error_during_scope_resolution_returns_502(client):
    """A pyodbc.Error inside `resolve_scope` used to run outside the
    try/except (HTTP 500) — a Fabric SQL failure on this read must be 502."""
    import pyodbc

    _override_auth("user@chememan.com")
    with patch("app.routers.reference.get_fabric_conn") as mock_fabric, patch(
        "app.routers.reference.resolve_scope", side_effect=pyodbc.Error("08S01", "boom")
    ):
        mock_fabric.return_value.__enter__.return_value = MagicMock()
        response = client.get("/scope/departments")

    assert response.status_code == 502
