"""Unit tests for GET /budget/detail + GET /budget/trip (A9 gap-fill router).
DB always mocked, no live connection (same convention as test_reference_router.py)."""
from unittest.mock import MagicMock, patch

from app.auth import get_current_user_email
from app.main import app
from app.rls import Scope


def _override_auth(email: str) -> None:
    app.dependency_overrides[get_current_user_email] = lambda: email


def _scope(**overrides) -> Scope:
    defaults = dict(email="filler@chememan.com", is_admin=False, role="filler",
                     fill_cost_centers=["CC1"], see_cost_centers=["CC1"])
    defaults.update(overrides)
    return Scope(**defaults)


# ---------------------------------------------------------------------------
# GET /budget/detail
# ---------------------------------------------------------------------------

def test_get_detail_lines_401_without_auth(client):
    response = client.get("/budget/detail", params={"cost_center": "CC1", "gl_account": "GL1", "fiscal_year": 2027})
    assert response.status_code == 401


def test_get_detail_lines_returns_list(client):
    _override_auth("filler@chememan.com")
    fake_rows = [{
        "detail_id": 1, "cost_center": "CC1", "gl_account": "GL1", "fiscal_year": 2027,
        "trip_id": None, "gl_group": "Entertainment", "line_label": None,
        **{f"m{m:02d}": 0.0 for m in range(1, 13)},
        "total_year": 0.0, "meta_json": None, "updated_at": "2026-01-01T00:00:00",
    }]
    with patch("app.routers.subform.get_fabric_conn") as mock_conn, patch(
        "app.routers.subform.resolve_scope", return_value=_scope()
    ), patch("app.routers.subform.fetch_detail_lines", return_value=fake_rows):
        mock_conn.return_value.__enter__.return_value = MagicMock()
        response = client.get("/budget/detail", params={"cost_center": "CC1", "gl_account": "GL1", "fiscal_year": 2027})

    assert response.status_code == 200
    assert response.json()[0]["detail_id"] == 1


def test_get_detail_lines_403_out_of_see_scope(client):
    _override_auth("outsider@chememan.com")
    with patch("app.routers.subform.get_fabric_conn") as mock_conn, patch(
        "app.routers.subform.resolve_scope", return_value=_scope(fill_cost_centers=[], see_cost_centers=[])
    ):
        mock_conn.return_value.__enter__.return_value = MagicMock()
        response = client.get("/budget/detail", params={"cost_center": "CC1", "gl_account": "GL1", "fiscal_year": 2027})

    assert response.status_code == 403


def test_get_detail_lines_admin_bypasses_scope(client):
    _override_auth("admin@chememan.com")
    with patch("app.routers.subform.get_fabric_conn") as mock_conn, patch(
        "app.routers.subform.resolve_scope", return_value=_scope(email="admin@chememan.com", is_admin=True, role="admin", fill_cost_centers=[], see_cost_centers=[])
    ), patch("app.routers.subform.fetch_detail_lines", return_value=[]):
        mock_conn.return_value.__enter__.return_value = MagicMock()
        response = client.get("/budget/detail", params={"cost_center": "CC1", "gl_account": "GL1", "fiscal_year": 2027})

    assert response.status_code == 200


def test_get_detail_lines_502_on_db_error(client):
    import pyodbc

    _override_auth("filler@chememan.com")
    with patch("app.routers.subform.get_fabric_conn") as mock_conn, patch(
        "app.routers.subform.resolve_scope", return_value=_scope()
    ), patch("app.routers.subform.fetch_detail_lines", side_effect=pyodbc.Error("boom")):
        mock_conn.return_value.__enter__.return_value = MagicMock()
        response = client.get("/budget/detail", params={"cost_center": "CC1", "gl_account": "GL1", "fiscal_year": 2027})

    assert response.status_code == 502


# ---------------------------------------------------------------------------
# GET /budget/trip
# ---------------------------------------------------------------------------

def test_get_trips_401_without_auth(client):
    response = client.get("/budget/trip", params={"cost_center": "CC1", "fiscal_year": 2027})
    assert response.status_code == 401


def test_get_trips_returns_list(client):
    _override_auth("filler@chememan.com")
    fake_rows = [{
        "trip_id": 10, "cost_center": "CC1", "fiscal_year": 2027, "traveler_empcode": "E1",
        "traveler_name": "สมชาย", "position": "Supervisor", "destination": "Japan",
        "country_group": 2, "days": 5, "travel_months": ["02", "03"], "purpose": None, "side": "COST",
        "updated_at": "2026-01-01T00:00:00", "per_diem_months": {f"m{m:02d}": 0.0 for m in range(1, 13)},
        "per_diem_error": None,
    }]
    with patch("app.routers.subform.get_fabric_conn") as mock_conn, patch(
        "app.routers.subform.resolve_scope", return_value=_scope()
    ), patch("app.routers.subform.fetch_trips", return_value=fake_rows):
        mock_conn.return_value.__enter__.return_value = MagicMock()
        response = client.get("/budget/trip", params={"cost_center": "CC1", "fiscal_year": 2027})

    assert response.status_code == 200
    assert response.json()[0]["trip_id"] == 10


def test_get_trips_403_out_of_see_scope(client):
    _override_auth("outsider@chememan.com")
    with patch("app.routers.subform.get_fabric_conn") as mock_conn, patch(
        "app.routers.subform.resolve_scope", return_value=_scope(fill_cost_centers=[], see_cost_centers=[])
    ):
        mock_conn.return_value.__enter__.return_value = MagicMock()
        response = client.get("/budget/trip", params={"cost_center": "CC1", "fiscal_year": 2027})

    assert response.status_code == 403


def test_get_trips_502_on_db_error(client):
    import pyodbc

    _override_auth("filler@chememan.com")
    with patch("app.routers.subform.get_fabric_conn") as mock_conn, patch(
        "app.routers.subform.resolve_scope", return_value=_scope()
    ), patch("app.routers.subform.fetch_trips", side_effect=pyodbc.Error("boom")):
        mock_conn.return_value.__enter__.return_value = MagicMock()
        response = client.get("/budget/trip", params={"cost_center": "CC1", "fiscal_year": 2027})

    assert response.status_code == 502
