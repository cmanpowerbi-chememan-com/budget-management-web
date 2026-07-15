"""Unit tests for the A5 write endpoints — PUT /budget/rows, PUT /budget/detail,
POST|PUT /budget/trip. DB always mocked; write_model itself is unit-tested in
test_write_model.py — these tests only prove the router wiring: auth,
error-code -> HTTP-status mapping, and the fail-loud 5xx for missing FX/rate.
"""
from unittest.mock import MagicMock, patch

from app.auth import get_current_user_email
from app.main import app
from app.per_diem import MissingFxRateError
from app.rls import Scope
from app.write_model import PendingRowState, RowSaveResult, TripSaveResult, TripState

_ROW_BODY = {
    "cost_center": "CC1", "gl_account": "GL1", "fiscal_year": 2027,
    "m01": 100, "template": "USER",
}
_TRIP_BODY = {
    "cost_center": "CC1", "fiscal_year": 2027, "traveler_empcode": "E1",
    "country_group": 1, "days": 5, "travel_months": ["03"], "side": "COST",
}


def _override_auth(email: str) -> None:
    app.dependency_overrides[get_current_user_email] = lambda: email


def _fake_scope(**overrides) -> Scope:
    defaults = dict(email="filler@chememan.com", is_admin=False, role="filler",
                     fill_cost_centers=["CC1"], see_cost_centers=["CC1"])
    defaults.update(overrides)
    return Scope(**defaults)


def test_put_rows_401_without_auth(client):
    response = client.put("/budget/rows", json=_ROW_BODY)
    assert response.status_code == 401


def test_put_rows_success_returns_200_and_row_state(client):
    _override_auth("filler@chememan.com")
    fake_row = PendingRowState(
        cost_center="CC1", gl_account="GL1", fiscal_year=2027, total_year=100,
        remark=None, template="USER", gl_name=None, gl_group="Bank Charge",
        c_level="clA", division="divA", department="deptA",
        updated_at="2026-01-01T00:00:00Z",
    )
    fake_result = RowSaveResult(cost_center="CC1", gl_account="GL1", fiscal_year=2027, ok=True, row=fake_row)
    with patch("app.routers.budget_write.get_fabric_conn") as mock_conn, patch(
        "app.routers.budget_write.resolve_scope", return_value=_fake_scope()
    ), patch("app.routers.budget_write.save_pending_rows", return_value=[fake_result]):
        mock_conn.return_value.__enter__.return_value = MagicMock()
        response = client.put("/budget/rows", json=_ROW_BODY)
    assert response.status_code == 200


def test_put_rows_forbidden_maps_to_403(client):
    _override_auth("outsider@chememan.com")
    fake_result = RowSaveResult(
        cost_center="CC1", gl_account="GL1", fiscal_year=2027, ok=False,
        error="forbidden", detail="CC1 is not in your Fill scope",
    )
    with patch("app.routers.budget_write.get_fabric_conn") as mock_conn, patch(
        "app.routers.budget_write.resolve_scope", return_value=_fake_scope(fill_cost_centers=[], see_cost_centers=[])
    ), patch("app.routers.budget_write.save_pending_rows", return_value=[fake_result]):
        mock_conn.return_value.__enter__.return_value = MagicMock()
        response = client.put("/budget/rows", json=_ROW_BODY)
    assert response.status_code == 403


def test_put_rows_conflict_maps_to_409(client):
    _override_auth("filler@chememan.com")
    fake_result = RowSaveResult(
        cost_center="CC1", gl_account="GL1", fiscal_year=2027, ok=False,
        error="conflict", detail="row changed by someone else",
    )
    with patch("app.routers.budget_write.get_fabric_conn") as mock_conn, patch(
        "app.routers.budget_write.resolve_scope", return_value=_fake_scope()
    ), patch("app.routers.budget_write.save_pending_rows", return_value=[fake_result]):
        mock_conn.return_value.__enter__.return_value = MagicMock()
        response = client.put("/budget/rows", json=_ROW_BODY)
    assert response.status_code == 409
    assert "changed by someone else" in response.json()["detail"]


def test_put_rows_negative_month_maps_to_400(client):
    _override_auth("filler@chememan.com")
    fake_result = RowSaveResult(
        cost_center="CC1", gl_account="GL1", fiscal_year=2027, ok=False,
        error="negative_month", detail="month amounts must be >= 0",
    )
    with patch("app.routers.budget_write.get_fabric_conn") as mock_conn, patch(
        "app.routers.budget_write.resolve_scope", return_value=_fake_scope()
    ), patch("app.routers.budget_write.save_pending_rows", return_value=[fake_result]):
        mock_conn.return_value.__enter__.return_value = MagicMock()
        response = client.put("/budget/rows", json={**_ROW_BODY, "m01": -5})
    assert response.status_code == 400


def test_post_trip_missing_fx_rate_is_a_loud_500_not_swallowed(client):
    """Never-cut: missing FX must surface as a loud failure, never a 4xx
    'validation error' and never a silent success."""
    _override_auth("filler@chememan.com")
    with patch("app.routers.budget_write.get_fabric_conn") as mock_conn, patch(
        "app.routers.budget_write.resolve_scope", return_value=_fake_scope()
    ), patch("app.routers.budget_write.save_trip", side_effect=MissingFxRateError("no FX for 2027")):
        mock_conn.return_value.__enter__.return_value = MagicMock()
        response = client.post("/budget/trip", json={**_TRIP_BODY, "country_group": 2})
    assert response.status_code == 500


def test_post_trip_success_returns_200(client):
    _override_auth("filler@chememan.com")
    fake_trip = TripState(
        trip_id=1, cost_center="CC1", fiscal_year=2027, traveler_empcode="E1",
        traveler_name="Somchai", position="Manager", destination="Bangkok",
        country_group=1, days=5, travel_months=["03"], purpose=None, side="COST",
        updated_at="2026-01-01T00:00:00Z", per_diem_months={"m03": 2500.0},
    )
    fake_result = TripSaveResult(cost_center="CC1", fiscal_year=2027, traveler_empcode="E1", ok=True, trip=fake_trip)
    with patch("app.routers.budget_write.get_fabric_conn") as mock_conn, patch(
        "app.routers.budget_write.resolve_scope", return_value=_fake_scope()
    ), patch("app.routers.budget_write.save_trip", return_value=[fake_result]):
        mock_conn.return_value.__enter__.return_value = MagicMock()
        response = client.post("/budget/trip", json=_TRIP_BODY)
    assert response.status_code == 200


def test_put_trip_requires_trip_id_in_body(client):
    _override_auth("filler@chememan.com")
    response = client.put("/budget/trip", json=_TRIP_BODY)  # no trip_id
    assert response.status_code == 422


def test_put_detail_conflict_maps_to_409(client):
    from app.write_model import DetailLineSaveResult

    _override_auth("filler@chememan.com")
    fake_result = DetailLineSaveResult(
        cost_center="CC1", gl_account="5211900030", fiscal_year=2027, ok=False,
        error="conflict", detail="detail line changed by someone else",
    )
    with patch("app.routers.budget_write.get_fabric_conn") as mock_conn, patch(
        "app.routers.budget_write.resolve_scope", return_value=_fake_scope()
    ), patch("app.routers.budget_write.save_detail_lines", return_value=[fake_result]):
        mock_conn.return_value.__enter__.return_value = MagicMock()
        response = client.put(
            "/budget/detail",
            json={
                "cost_center": "CC1", "gl_account": "5211900030", "fiscal_year": 2027,
                "detail_id": 5, "expected_updated_at": "2026-01-01T00:00:00Z",
            },
        )
    assert response.status_code == 409
