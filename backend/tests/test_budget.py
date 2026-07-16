"""Unit tests for GET /budget — DB always mocked, no live connection."""
from unittest.mock import MagicMock, patch

import pyodbc

from app.auth import get_current_user_email
from app.main import app
from app.read_model import BudgetRow
from app.rls import Scope
from app.sap import SapActualsFetchError

_GENERIC_502_DETAIL = "SAP actuals unavailable, please try again later"


def _override_auth(email: str) -> None:
    app.dependency_overrides[get_current_user_email] = lambda: email


def test_budget_401_without_auth_header(client):
    response = client.get("/budget?year=2027")
    assert response.status_code == 401


def test_budget_422_when_year_missing(client):
    _override_auth("user@chememan.com")
    response = client.get("/budget")
    assert response.status_code == 422


def test_budget_returns_merged_rows_for_authenticated_user(client):
    _override_auth("filler@chememan.com")
    fake_scope = Scope(
        email="filler@chememan.com", is_admin=False, role="filler",
        fill_cost_centers=["CC1"], see_cost_centers=["CC1"],
    )
    fake_rows = [BudgetRow(cost_center="CC1", gl_account="GL1", editable=True)]
    with patch("app.routers.budget.get_fabric_conn") as mock_fabric, patch(
        "app.routers.budget.get_gold_conn"
    ) as mock_gold, patch("app.routers.budget.resolve_scope", return_value=fake_scope), patch(
        "app.routers.budget.get_budget_grid", return_value=fake_rows
    ) as mock_grid:
        mock_fabric.return_value.__enter__.return_value = MagicMock()
        mock_gold.return_value.__enter__.return_value = MagicMock()
        response = client.get("/budget?year=2027")

    assert response.status_code == 200
    body = response.json()
    assert body[0]["cost_center"] == "CC1"
    assert body[0]["editable"] is True
    _, kwargs = mock_grid.call_args
    assert kwargs["planning_year"] == 2027


def test_budget_passes_admin_view_enabled_and_filters_through(client):
    _override_auth("admin@chememan.com")
    fake_scope = Scope(email="admin@chememan.com", is_admin=True, role="admin", fill_cost_centers=[], see_cost_centers=[])
    with patch("app.routers.budget.get_fabric_conn") as mock_fabric, patch(
        "app.routers.budget.get_gold_conn"
    ) as mock_gold, patch("app.routers.budget.resolve_scope", return_value=fake_scope), patch(
        "app.routers.budget.get_budget_grid", return_value=[]
    ) as mock_grid:
        mock_fabric.return_value.__enter__.return_value = MagicMock()
        mock_gold.return_value.__enter__.return_value = MagicMock()
        response = client.get(
            "/budget?year=2027&admin_view_enabled=true&cost_center=CC1&department=%E0%B8%9D%E0%B9%88%E0%B8%B2%E0%B8%A2A"
        )

    assert response.status_code == 200
    _, kwargs = mock_grid.call_args
    assert kwargs["admin_view_enabled"] is True
    assert kwargs["cost_center_filter"] == "CC1"
    assert kwargs["department_filter"] == "ฝ่ายA"


def test_budget_admin_view_enabled_defaults_to_false(client):
    _override_auth("user@chememan.com")
    fake_scope = Scope(email="user@chememan.com", is_admin=False, role="filler", fill_cost_centers=[], see_cost_centers=[])
    with patch("app.routers.budget.get_fabric_conn") as mock_fabric, patch(
        "app.routers.budget.get_gold_conn"
    ) as mock_gold, patch("app.routers.budget.resolve_scope", return_value=fake_scope), patch(
        "app.routers.budget.get_budget_grid", return_value=[]
    ) as mock_grid:
        mock_fabric.return_value.__enter__.return_value = MagicMock()
        mock_gold.return_value.__enter__.return_value = MagicMock()
        response = client.get("/budget?year=2027")

    assert response.status_code == 200
    _, kwargs = mock_grid.call_args
    assert kwargs["admin_view_enabled"] is False


def test_budget_sap_failure_returns_502_not_a_silent_empty_grid(client):
    """Never-cut: a failed SAP read-through must be a loud error, never a
    200 with an empty/partial grid. The raw exception message must NOT leak
    to the client (gate finding #2) — only a generic detail, matching the
    `health.py` pattern ("never leaks connection details")."""
    _override_auth("filler@chememan.com")
    fake_scope = Scope(email="filler@chememan.com", is_admin=False, role="filler", fill_cost_centers=["CC1"], see_cost_centers=["CC1"])
    with patch("app.routers.budget.get_fabric_conn") as mock_fabric, patch(
        "app.routers.budget.get_gold_conn"
    ) as mock_gold, patch("app.routers.budget.resolve_scope", return_value=fake_scope), patch(
        "app.routers.budget.get_budget_grid", side_effect=SapActualsFetchError("DW unreachable, grant revoked")
    ):
        mock_fabric.return_value.__enter__.return_value = MagicMock()
        mock_gold.return_value.__enter__.return_value = MagicMock()
        response = client.get("/budget?year=2027")

    assert response.status_code == 502
    body = response.json()
    assert body["detail"] == _GENERIC_502_DETAIL
    assert "DW unreachable" not in response.text
    assert "grant revoked" not in response.text


def test_budget_db_error_during_scope_resolution_returns_502_not_500(client):
    """`resolve_scope` used to run OUTSIDE the try/except — a pyodbc.Error
    while resolving RLS scope propagated uncaught (HTTP 500), violating the
    read-path contract that any Fabric SQL failure on this read is a 502."""
    _override_auth("filler@chememan.com")
    with patch("app.routers.budget.get_fabric_conn") as mock_fabric, patch(
        "app.routers.budget.resolve_scope",
        side_effect=pyodbc.Error("08S01", "connection reset during scope resolution"),
    ):
        mock_fabric.return_value.__enter__.return_value = MagicMock()
        response = client.get("/budget?year=2027")

    assert response.status_code == 502
    assert response.json()["detail"] == _GENERIC_502_DETAIL
    assert "connection reset" not in response.text


def test_budget_raw_pyodbc_error_also_returns_502_generic_detail(client):
    """A raw `pyodbc.Error` (not wrapped in `SapActualsFetchError`) reaching
    the handler — e.g. a connection drop inside the local board/pending
    join — must also surface as a loud 502 with the same generic detail,
    never a silent empty grid and never the raw driver message."""
    _override_auth("filler@chememan.com")
    fake_scope = Scope(email="filler@chememan.com", is_admin=False, role="filler", fill_cost_centers=["CC1"], see_cost_centers=["CC1"])
    with patch("app.routers.budget.get_fabric_conn") as mock_fabric, patch(
        "app.routers.budget.get_gold_conn"
    ) as mock_gold, patch("app.routers.budget.resolve_scope", return_value=fake_scope), patch(
        "app.routers.budget.get_budget_grid",
        side_effect=pyodbc.Error("08S01", "connection reset by peer"),
    ):
        mock_fabric.return_value.__enter__.return_value = MagicMock()
        mock_gold.return_value.__enter__.return_value = MagicMock()
        response = client.get("/budget?year=2027")

    assert response.status_code == 502
    body = response.json()
    assert body["detail"] == _GENERIC_502_DETAIL
    assert "connection reset by peer" not in response.text
