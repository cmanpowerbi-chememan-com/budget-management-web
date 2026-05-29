"""Unit tests for Orgcode & Cost Center Mapping handlers (module 0007).

All external dependencies (authenticate, fetchall, fetchall_lakehouse,
execute, exists, pyodbc.IntegrityError) are patched per-test so these
tests run with NO real credentials, NO network, NO database.

Run from 04tests/:
    pytest test_orgcode_cc_handlers.py -v
"""
import json
from unittest.mock import patch, MagicMock, call
import pytest
import pyodbc  # real pyodbc is installed — we patch individual functions


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

ADMIN_CLAIMS = {"sub": "test-uuid", "email": "admin@chememan.com"}


@pytest.fixture
def admin_claims():
    return ADMIN_CLAIMS


@pytest.fixture
def make_request():
    """Factory: returns a MagicMock HttpRequest-like object."""
    def _factory(body=None, method="GET", route_params=None):
        req = MagicMock()
        req.get_json.return_value = body if body is not None else {}
        req.headers = {"x-ms-client-principal-name": "admin@chememan.com"}
        req.method = method
        req.route_params = route_params or {}
        return req
    return _factory


# ---------------------------------------------------------------------------
# list_handler
# ---------------------------------------------------------------------------

class TestListHandler:

    @patch("handlers_orgcode_cc.list_handler.fetchall")
    @patch("handlers_orgcode_cc.list_handler.authenticate")
    def test_happy_path_returns_correct_keys(
        self, mock_auth, mock_fetchall, make_request, admin_claims
    ):
        """Happy path: returns JSON list with id, cost_center, orgcode, orgcode_name."""
        from handlers_orgcode_cc import list_handler
        mock_auth.return_value = admin_claims
        mock_fetchall.return_value = [
            {
                "id": 1,
                "cost_center": "10CS000000",
                "orgcode": "1120000",
                "orgcode_name": "Corporate Strategy",
            }
        ]

        res = list_handler.handle(make_request(method="GET"))

        assert res.status_code == 200
        body = json.loads(res.get_body())
        assert isinstance(body, list)
        assert len(body) == 1
        row = body[0]
        # Assert all expected keys are present and NOT NULL
        assert row["id"] is not None, "id must not be null"
        assert row["cost_center"] is not None, "cost_center must not be null"
        assert row["orgcode"] is not None, "orgcode must not be null"
        assert "orgcode_name" in row, "orgcode_name key must be present"
        assert row["cost_center"] == "10CS000000"
        assert row["orgcode"] == "1120000"
        assert row["orgcode_name"] == "Corporate Strategy"

    @patch("handlers_orgcode_cc.list_handler.authenticate")
    def test_unauthenticated_returns_401(self, mock_auth, make_request):
        """Unauthenticated request: returns 401."""
        from handlers_orgcode_cc import list_handler
        from auth import AuthError
        mock_auth.side_effect = AuthError(401, "Not authenticated")

        res = list_handler.handle(make_request())

        assert res.status_code == 401
        body = json.loads(res.get_body())
        assert "error" in body

    @patch("handlers_orgcode_cc.list_handler.fetchall")
    @patch("handlers_orgcode_cc.list_handler.authenticate")
    def test_empty_table_returns_empty_list(
        self, mock_auth, mock_fetchall, make_request, admin_claims
    ):
        """Edge case: no rows in table returns empty JSON array."""
        from handlers_orgcode_cc import list_handler
        mock_auth.return_value = admin_claims
        mock_fetchall.return_value = []

        res = list_handler.handle(make_request(method="GET"))

        assert res.status_code == 200
        body = json.loads(res.get_body())
        assert body == []

    @patch("handlers_orgcode_cc.list_handler.fetchall")
    @patch("handlers_orgcode_cc.list_handler.authenticate")
    def test_row_with_no_orgcode_name_uses_empty_string(
        self, mock_auth, mock_fetchall, make_request, admin_claims
    ):
        """Edge case: orgcode_name is '' (COALESCE) not None — silent NULL would
        cause frontend keying to break.  Value must be the empty string."""
        from handlers_orgcode_cc import list_handler
        mock_auth.return_value = admin_claims
        mock_fetchall.return_value = [
            {"id": 2, "cost_center": "10IT010000", "orgcode": "9999999", "orgcode_name": ""}
        ]

        res = list_handler.handle(make_request(method="GET"))

        body = json.loads(res.get_body())
        assert body[0]["orgcode_name"] == "", (
            "orgcode_name must be empty string (COALESCE), not None"
        )


# ---------------------------------------------------------------------------
# save_handler
# ---------------------------------------------------------------------------

class TestSaveHandler:

    @patch("handlers_orgcode_cc.save_handler.execute")
    @patch("handlers_orgcode_cc.save_handler.exists")
    @patch("handlers_orgcode_cc.save_handler.authenticate")
    def test_happy_path_insert_returns_200_success(
        self, mock_auth, mock_exists, mock_execute, make_request, admin_claims
    ):
        """Happy path: new pair → INSERT → 200 {status: success}."""
        from handlers_orgcode_cc import save_handler
        mock_auth.return_value = admin_claims
        mock_exists.return_value = False
        mock_execute.return_value = None

        req = make_request(
            body={"cost_center": "10CS000000", "orgcode": "1120000"},
            method="POST",
        )
        res = save_handler.handle(req)

        assert res.status_code == 200
        body = json.loads(res.get_body())
        assert body["status"] == "success", (
            f"Expected status=success, got: {body}"
        )
        mock_execute.assert_called_once()

    @patch("handlers_orgcode_cc.save_handler.exists")
    @patch("handlers_orgcode_cc.save_handler.authenticate")
    def test_duplicate_exists_check_returns_409_with_duplicate_key_code(
        self, mock_auth, mock_exists, make_request, admin_claims
    ):
        """Duplicate: exists() returns True → 409 with DUPLICATE_KEY code."""
        from handlers_orgcode_cc import save_handler
        mock_auth.return_value = admin_claims
        mock_exists.return_value = True

        req = make_request(
            body={"cost_center": "10CS000000", "orgcode": "1120000"},
            method="POST",
        )
        res = save_handler.handle(req)

        assert res.status_code == 409
        body = json.loads(res.get_body())
        assert body.get("code") == "DUPLICATE_KEY", (
            f"Expected code=DUPLICATE_KEY, got: {body}"
        )

    @patch("handlers_orgcode_cc.save_handler.execute")
    @patch("handlers_orgcode_cc.save_handler.exists")
    @patch("handlers_orgcode_cc.save_handler.authenticate")
    def test_integrity_error_on_insert_toctou_race(
        self, mock_auth, mock_exists, mock_execute, make_request, admin_claims
    ):
        """TOCTOU race: exists()=False but INSERT raises IntegrityError.

        BUG REPORT: save_handler catches IntegrityError in a bare `except Exception`
        block that returns 500.  The correct response is 409 (duplicate detected at
        DB level).  This test DOCUMENTS the regression — it will FAIL until the
        production handler is fixed to catch pyodbc.IntegrityError and return 409.

        Root cause (file: handlers_orgcode_cc/save_handler.py line 41-51):
            except Exception as e:
                return func.HttpResponse(..., status_code=500, ...)
        The handler has no specific branch for pyodbc.IntegrityError, so a race
        between the exists() pre-check and the INSERT yields 500 instead of 409.
        """
        from handlers_orgcode_cc import save_handler
        mock_auth.return_value = admin_claims
        mock_exists.return_value = False  # pre-check passes
        mock_execute.side_effect = pyodbc.IntegrityError("UNIQUE constraint")

        req = make_request(
            body={"cost_center": "10CS000000", "orgcode": "1120000"},
            method="POST",
        )
        res = save_handler.handle(req)

        # EXPECTED correct behaviour: 409 (duplicate at DB level)
        # CURRENT behaviour: 500 (bare except returns 500)
        assert res.status_code == 409, (
            f"IntegrityError from INSERT must return 409, got {res.status_code}. "
            "Root cause: save_handler.py catches IntegrityError in the generic "
            "`except Exception` block and returns 500. Fix: add "
            "`except pyodbc.IntegrityError` before the generic except and return 409."
        )

    @patch("handlers_orgcode_cc.save_handler.authenticate")
    def test_missing_orgcode_in_payload_returns_400(
        self, mock_auth, make_request, admin_claims
    ):
        """Invalid payload: missing orgcode → 400."""
        from handlers_orgcode_cc import save_handler
        mock_auth.return_value = admin_claims

        req = make_request(
            body={"cost_center": "10CS000000"},  # orgcode missing
            method="POST",
        )
        res = save_handler.handle(req)

        assert res.status_code == 400
        body = json.loads(res.get_body())
        assert "error" in body

    @patch("handlers_orgcode_cc.save_handler.authenticate")
    def test_missing_cost_center_in_payload_returns_400(
        self, mock_auth, make_request, admin_claims
    ):
        """Invalid payload: missing cost_center → 400."""
        from handlers_orgcode_cc import save_handler
        mock_auth.return_value = admin_claims

        req = make_request(
            body={"orgcode": "1120000"},  # cost_center missing
            method="POST",
        )
        res = save_handler.handle(req)

        assert res.status_code == 400

    @patch("handlers_orgcode_cc.save_handler.authenticate")
    def test_empty_body_returns_400(
        self, mock_auth, make_request, admin_claims
    ):
        """Edge case: completely empty body → 400."""
        from handlers_orgcode_cc import save_handler
        mock_auth.return_value = admin_claims

        req = make_request(body={}, method="POST")
        res = save_handler.handle(req)

        assert res.status_code == 400

    @patch("handlers_orgcode_cc.save_handler.authenticate")
    def test_unauthenticated_returns_401(self, mock_auth, make_request):
        """Unauthenticated request: returns 401."""
        from handlers_orgcode_cc import save_handler
        from auth import AuthError
        mock_auth.side_effect = AuthError(401, "Not authenticated")

        req = make_request(
            body={"cost_center": "10CS000000", "orgcode": "1120000"},
            method="POST",
        )
        res = save_handler.handle(req)

        assert res.status_code == 401


# ---------------------------------------------------------------------------
# delete_handler
# ---------------------------------------------------------------------------

class TestDeleteHandler:

    @patch("handlers_orgcode_cc.delete_handler.execute")
    @patch("handlers_orgcode_cc.delete_handler.authenticate")
    def test_happy_path_returns_200_with_echoed_keys(
        self, mock_auth, mock_execute, make_request, admin_claims
    ):
        """Happy path: delete succeeds → 200 with cost_center and orgcode echoed back."""
        from handlers_orgcode_cc import delete_handler
        mock_auth.return_value = admin_claims
        mock_execute.return_value = None

        req = make_request(
            body={"cost_center": "10CS000000", "orgcode": "1120000"},
            method="DELETE",
        )
        res = delete_handler.handle(req)

        assert res.status_code == 200
        body = json.loads(res.get_body())
        # Keys must be present and NOT NULL
        assert body.get("cost_center") == "10CS000000", (
            f"cost_center not echoed: {body}"
        )
        assert body.get("orgcode") == "1120000", (
            f"orgcode not echoed: {body}"
        )
        mock_execute.assert_called_once()

    @patch("handlers_orgcode_cc.delete_handler.authenticate")
    def test_missing_orgcode_returns_400(self, mock_auth, make_request, admin_claims):
        """Invalid payload: missing orgcode → 400."""
        from handlers_orgcode_cc import delete_handler
        mock_auth.return_value = admin_claims

        req = make_request(
            body={"cost_center": "10CS000000"},  # orgcode missing
            method="DELETE",
        )
        res = delete_handler.handle(req)

        assert res.status_code == 400

    @patch("handlers_orgcode_cc.delete_handler.authenticate")
    def test_missing_cost_center_returns_400(
        self, mock_auth, make_request, admin_claims
    ):
        """Invalid payload: missing cost_center → 400."""
        from handlers_orgcode_cc import delete_handler
        mock_auth.return_value = admin_claims

        req = make_request(
            body={"orgcode": "1120000"},  # cost_center missing
            method="DELETE",
        )
        res = delete_handler.handle(req)

        assert res.status_code == 400

    @patch("handlers_orgcode_cc.delete_handler.authenticate")
    def test_unauthenticated_returns_401(self, mock_auth, make_request):
        """Unauthenticated request: returns 401."""
        from handlers_orgcode_cc import delete_handler
        from auth import AuthError
        mock_auth.side_effect = AuthError(401, "Not authenticated")

        req = make_request(
            body={"cost_center": "10CS000000", "orgcode": "1120000"},
            method="DELETE",
        )
        res = delete_handler.handle(req)

        assert res.status_code == 401


# ---------------------------------------------------------------------------
# reference_handler
# ---------------------------------------------------------------------------

class TestReferenceHandler:

    @patch("handlers_orgcode_cc.reference_handler.fetchall")
    @patch("handlers_orgcode_cc.reference_handler.authenticate")
    def test_orgcodes_ref_uses_fetchall_not_lakehouse(
        self, mock_auth, mock_fetchall, make_request, admin_claims
    ):
        """ref_name=orgcodes: fetchall (Fabric SQL) is called, not fetchall_lakehouse."""
        from handlers_orgcode_cc import reference_handler
        mock_auth.return_value = admin_claims
        mock_fetchall.return_value = [
            {"code": "1120000", "name": "Corporate Strategy"}
        ]

        req = make_request(route_params={"ref_name": "orgcodes"})
        res = reference_handler.handle(req)

        assert res.status_code == 200
        body = json.loads(res.get_body())
        assert isinstance(body, list)
        assert len(body) == 1
        assert body[0]["code"] == "1120000"
        assert body[0]["name"] is not None, "name must not be null"
        mock_fetchall.assert_called_once()

    @patch("handlers_orgcode_cc.reference_handler.fetchall_lakehouse")
    @patch("handlers_orgcode_cc.reference_handler.authenticate")
    def test_cost_centers_ref_uses_fetchall_lakehouse_not_fetchall(
        self, mock_auth, mock_fetchall_lakehouse, make_request, admin_claims
    ):
        """ref_name=cost-centers: fetchall_lakehouse (Lakehouse endpoint) is called,
        not fetchall (Fabric SQL)."""
        from handlers_orgcode_cc import reference_handler
        mock_auth.return_value = admin_claims
        mock_fetchall_lakehouse.return_value = [
            {"code": "10CS000000", "name": "Corporate Strategy Division"}
        ]

        req = make_request(route_params={"ref_name": "cost-centers"})
        res = reference_handler.handle(req)

        assert res.status_code == 200
        body = json.loads(res.get_body())
        assert isinstance(body, list)
        assert body[0]["code"] == "10CS000000"
        assert body[0]["name"] is not None, "name must not be null"
        mock_fetchall_lakehouse.assert_called_once()

    @patch("handlers_orgcode_cc.reference_handler.fetchall_lakehouse")
    @patch("handlers_orgcode_cc.reference_handler.fetchall")
    @patch("handlers_orgcode_cc.reference_handler.authenticate")
    def test_cost_centers_ref_does_not_call_fetchall(
        self, mock_auth, mock_fetchall, mock_fetchall_lakehouse,
        make_request, admin_claims
    ):
        """cost-centers must NOT call fetchall (Fabric SQL) — only Lakehouse."""
        from handlers_orgcode_cc import reference_handler
        mock_auth.return_value = admin_claims
        mock_fetchall_lakehouse.return_value = []

        req = make_request(route_params={"ref_name": "cost-centers"})
        reference_handler.handle(req)

        mock_fetchall.assert_not_called()

    @patch("handlers_orgcode_cc.reference_handler.fetchall")
    @patch("handlers_orgcode_cc.reference_handler.authenticate")
    def test_orgcodes_ref_does_not_call_fetchall_lakehouse(
        self, mock_auth, mock_fetchall, make_request, admin_claims
    ):
        """orgcodes must NOT call fetchall_lakehouse — only Fabric SQL."""
        from handlers_orgcode_cc import reference_handler
        mock_auth.return_value = admin_claims
        mock_fetchall.return_value = []

        with patch("handlers_orgcode_cc.reference_handler.fetchall_lakehouse") as mock_lh:
            req = make_request(route_params={"ref_name": "orgcodes"})
            reference_handler.handle(req)
            mock_lh.assert_not_called()

    @patch("handlers_orgcode_cc.reference_handler.authenticate")
    def test_unknown_ref_name_returns_404(self, mock_auth, make_request, admin_claims):
        """Unknown ref_name → 404."""
        from handlers_orgcode_cc import reference_handler
        mock_auth.return_value = admin_claims

        req = make_request(route_params={"ref_name": "nonexistent"})
        res = reference_handler.handle(req)

        assert res.status_code == 404
        body = json.loads(res.get_body())
        assert "error" in body

    @patch("handlers_orgcode_cc.reference_handler.authenticate")
    def test_missing_ref_name_returns_404(self, mock_auth, make_request, admin_claims):
        """Edge case: no route_params at all → 404 (ref_name = None)."""
        from handlers_orgcode_cc import reference_handler
        mock_auth.return_value = admin_claims

        req = make_request(route_params={})  # ref_name not present → .get() returns None
        res = reference_handler.handle(req)

        assert res.status_code == 404

    @patch("handlers_orgcode_cc.reference_handler.authenticate")
    def test_unauthenticated_returns_401(self, mock_auth, make_request):
        """Unauthenticated request: returns 401 before DB is touched."""
        from handlers_orgcode_cc import reference_handler
        from auth import AuthError
        mock_auth.side_effect = AuthError(401, "Not authenticated")

        req = make_request(route_params={"ref_name": "orgcodes"})
        res = reference_handler.handle(req)

        assert res.status_code == 401
