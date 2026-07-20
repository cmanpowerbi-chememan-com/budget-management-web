"""Connection-OPEN failure contract — every DB-backed endpoint returns 502
with a generic detail when opening the Fabric connection fails, whether the
failure is the ODBC driver (pyodbc.Error from pyodbc.connect) or msal token
acquisition (app.db._acquire_access_token). Never a 500, never driver/token
text in the response body.

Two failure modes per endpoint:

1. driver-open: the router-module's own `get_fabric_conn` import is patched
   to raise pyodbc.OperationalError the moment the `with` is entered —
   simulates HYT00 login timeout / capacity pause at connect time.
2. msal-open: `app.db.msal.ConfidentialClientApplication` is patched so
   acquire_token_for_client returns an AAD error dict, and the REAL
   `get_fabric_conn` runs — exercises the actual open path end-to-end
   (`_acquire_access_token` -> DbConnectionError -> router's pyodbc.Error
   handler). No network happens: token acquisition raises before
   pyodbc.connect is ever reached.
"""
from unittest.mock import patch

import pyodbc
import pytest

from app.auth import get_current_user_email
from app.main import app

_ROW_BODY = {
    "cost_center": "CC1", "gl_account": "GL1", "fiscal_year": 2027,
    "m01": 100, "template": "USER",
}
_DETAIL_BODY = {
    "cost_center": "CC1", "gl_account": "5211900030", "fiscal_year": 2027,
    "detail_id": 5, "expected_updated_at": "2026-01-01T00:00:00Z",
}
_TRIP_BODY = {
    "cost_center": "CC1", "fiscal_year": 2027, "traveler_empcode": "E1",
    "country_group": 1, "days": 5, "travel_months": ["03"], "side": "COST",
}
_SUBMIT_BODY = {"department": "ฝ่ายทดสอบ", "fiscal_year": 2027}

# (method, url, json body, module whose `get_fabric_conn` import to patch)
_ENDPOINTS = [
    pytest.param("GET", "/budget?year=2027", None, "app.routers.budget", id="GET /budget"),
    pytest.param("GET", "/scope", None, "app.routers.scope", id="GET /scope"),
    pytest.param(
        "GET", "/budget/detail?cost_center=CC1&gl_account=5211900030&fiscal_year=2027",
        None, "app.routers.subform", id="GET /budget/detail",
    ),
    pytest.param(
        "GET", "/budget/trip?cost_center=CC1&fiscal_year=2027",
        None, "app.routers.subform", id="GET /budget/trip",
    ),
    pytest.param("GET", "/budget/gl-accounts", None, "app.routers.reference", id="GET /budget/gl-accounts"),
    pytest.param("GET", "/scope/departments", None, "app.routers.reference", id="GET /scope/departments"),
    pytest.param("PUT", "/budget/rows", _ROW_BODY, "app.routers.budget_write", id="PUT /budget/rows"),
    pytest.param("PUT", "/budget/detail", _DETAIL_BODY, "app.routers.budget_write", id="PUT /budget/detail"),
    pytest.param("POST", "/budget/trip", _TRIP_BODY, "app.routers.budget_write", id="POST /budget/trip"),
    pytest.param(
        "DELETE", "/budget/rows?cost_center=X&gl_account=Y&fiscal_year=2026&expected_updated_at=2026-01-01T00:00:00Z",
        None, "app.routers.budget_write", id="DELETE /budget/rows",
    ),
    pytest.param(
        "DELETE", "/budget/detail?detail_id=5&expected_updated_at=2026-01-01T00:00:00Z",
        None, "app.routers.budget_write", id="DELETE /budget/detail",
    ),
    pytest.param(
        "DELETE", "/budget/trip?trip_id=5&expected_updated_at=2026-01-01T00:00:00Z",
        None, "app.routers.budget_write", id="DELETE /budget/trip",
    ),
    pytest.param("POST", "/approval/submit", _SUBMIT_BODY, "app.routers.approval", id="POST /approval/submit"),
    pytest.param(
        "GET", "/approval/status?department=X&fiscal_year=2027",
        None, "app.routers.approval", id="GET /approval/status",
    ),
    pytest.param(
        "GET", "/attachments?department=X&fiscal_year=2027",
        None, "app.routers.attachments", id="GET /attachments",
    ),
]

# Anything from the driver / AAD error surface that must NEVER reach a client.
_LEAK_MARKERS = ["HYT00", "AADSTS", "msal", "ODBC", "login timeout", "client secret", "invalid_client"]


@pytest.fixture(autouse=True)
def _clear_msal_app_cache():
    """Same isolation as test_db.py — the module-level msal app cache must
    not leak a mocked instance across tests."""
    import app.db as db_module

    db_module._msal_apps.clear()
    yield
    db_module._msal_apps.clear()


def _request(client, method: str, url: str, body):
    app.dependency_overrides[get_current_user_email] = lambda: "user@chememan.com"
    return client.request(method, url, json=body)


def _assert_502_generic(response):
    assert response.status_code == 502, f"expected 502, got {response.status_code}: {response.text}"
    for marker in _LEAK_MARKERS:
        assert marker.lower() not in response.text.lower(), f"leaked {marker!r}: {response.text}"


@pytest.mark.parametrize("method,url,body,module", _ENDPOINTS)
def test_driver_error_at_connection_open_returns_502(client, method, url, body, module):
    """pyodbc.Error raised at `with get_fabric_conn()` entry (driver-level
    connect failure) -> 502 generic, same as a query-time pyodbc.Error."""
    driver_error = pyodbc.OperationalError(
        "HYT00", "[HYT00] [Microsoft][ODBC Driver 17 for SQL Server] login timeout expired"
    )
    with patch(f"{module}.get_fabric_conn", side_effect=driver_error):
        response = _request(client, method, url, body)
    _assert_502_generic(response)


@pytest.mark.parametrize("method,url,body,module", _ENDPOINTS)
def test_msal_token_failure_at_connection_open_returns_502(client, method, url, body, module):
    """msal token acquisition fails at open (the REAL get_fabric_conn runs;
    only the msal layer is mocked to return an AAD error) -> 502 generic."""
    with patch("app.db.msal.ConfidentialClientApplication") as mock_cls, patch(
        "app.db.pyodbc.connect"
    ) as mock_connect:
        mock_cls.return_value.acquire_token_for_client.return_value = {
            "error": "invalid_client",
            "error_description": "AADSTS7000215: Invalid client secret provided.",
        }
        response = _request(client, method, url, body)
        # Token acquisition failed first — the driver must never be reached.
        mock_connect.assert_not_called()
    _assert_502_generic(response)
