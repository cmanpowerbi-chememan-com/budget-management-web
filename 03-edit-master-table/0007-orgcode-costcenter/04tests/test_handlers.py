"""Unit tests for Orgcode-CostCenter Master handlers.

Critical test focus: COMPOSITE PK behavior.
- Duplicate check must use BOTH columns
- Delete must use BOTH columns in WHERE
- Same cost_center + different orgcode = NOT a duplicate
"""
import json
from unittest.mock import patch, MagicMock
import pytest


@pytest.fixture
def admin_claims():
    return {
        "sub": "user-uuid-1",
        "email": "volks@chememan.com",
        "groups": ["master-table-admins"],
    }


@pytest.fixture
def make_request():
    def _factory(body=None, headers=None, method="POST"):
        req = MagicMock()
        req.get_json.return_value = body or {}
        req.headers = headers or {"Authorization": "Bearer fake-token"}
        req.method = method
        return req
    return _factory


# ───────────────────────────────────────────────────────────
# save_handler — composite PK behavior
# ───────────────────────────────────────────────────────────
class TestSaveHandler:

    @patch("handlers.save_handler.spark")
    @patch("handlers.save_handler.exists")
    @patch("handlers.save_handler.authenticate")
    def test_save_new_pair_happy_path(
        self, mock_auth, mock_exists, mock_spark,
        make_request, admin_claims
    ):
        """Insert a new (cost_center, orgcode) pair."""
        from handlers import save_handler
        mock_auth.return_value = admin_claims
        mock_exists.return_value = False

        req = make_request({
            "cost_center": "10SP010000",
            "orgcode": "1110000",
            "is_edit_mode": False,
        })
        res = save_handler.handle(req)

        assert res.status_code == 200
        # Verify the existence check used BOTH PK columns
        mock_exists.assert_called_once()
        args, kwargs = mock_exists.call_args
        # args[1] is the where_clause, args[2] is params dict
        assert "cost_center" in args[1] and "orgcode" in args[1]
        assert "AND" in args[1].upper(), (
            "Composite PK check must use AND between columns"
        )

    @patch("handlers.save_handler.spark")
    @patch("handlers.save_handler.exists")
    @patch("handlers.save_handler.authenticate")
    def test_save_same_cc_different_orgcode_is_not_duplicate(
        self, mock_auth, mock_exists, mock_spark,
        make_request, admin_claims
    ):
        """CRITICAL: Same Cost Center with different Orgcode = NEW row.
        
        This is the core composite-key behavior. If skill v1 had been used
        (single PK), this would have been wrongly rejected as duplicate.
        """
        from handlers import save_handler
        mock_auth.return_value = admin_claims
        # exists() must check BOTH columns — if it does, this returns False
        # because (10SP010000, 1130000) does not yet exist even though
        # (10SP010000, 1110000) does.
        mock_exists.return_value = False

        req = make_request({
            "cost_center": "10SP010000",
            "orgcode": "1130000",  # Different orgcode, same CC
        })
        res = save_handler.handle(req)

        assert res.status_code == 200, (
            "Same CC with different orgcode should NOT be rejected"
        )

    @patch("handlers.save_handler.exists")
    @patch("handlers.save_handler.authenticate")
    def test_save_exact_same_pair_is_duplicate(
        self, mock_auth, mock_exists, make_request, admin_claims
    ):
        """Exact (cost_center, orgcode) pair already exists → 409."""
        from handlers import save_handler
        mock_auth.return_value = admin_claims
        mock_exists.return_value = True

        req = make_request({
            "cost_center": "10SP010000",
            "orgcode": "1110000",
        })
        res = save_handler.handle(req)

        assert res.status_code == 409
        body = json.loads(res.get_body())
        assert body["code"] == "DUPLICATE_KEY"

    @patch("handlers.save_handler.spark")
    @patch("handlers.save_handler.exists")
    @patch("handlers.save_handler.authenticate")
    def test_save_lowercase_cost_center_auto_uppercased(
        self, mock_auth, mock_exists, mock_spark,
        make_request, admin_claims
    ):
        """HTML regex says auto_transform: upper — model must enforce."""
        from handlers import save_handler
        mock_auth.return_value = admin_claims
        mock_exists.return_value = False

        req = make_request({
            "cost_center": "10sp010000",  # lowercase
            "orgcode": "1110000",
        })
        res = save_handler.handle(req)

        assert res.status_code == 200
        # The existence check params should contain UPPERCASE cost_center
        args, kwargs = mock_exists.call_args
        params_dict = args[2]
        assert params_dict["cost_center"] == "10SP010000"

    @patch("handlers.save_handler.authenticate")
    def test_save_invalid_cost_center_format(
        self, mock_auth, make_request, admin_claims
    ):
        """Cost Center with special chars (space, dash) → 400."""
        from handlers import save_handler
        mock_auth.return_value = admin_claims

        req = make_request({
            "cost_center": "10-SP-010",  # contains dash
            "orgcode": "1110000",
        })
        res = save_handler.handle(req)
        assert res.status_code == 400

    @patch("handlers.save_handler.authenticate")
    def test_save_missing_orgcode_rejected(
        self, mock_auth, make_request, admin_claims
    ):
        """Composite PK requires BOTH columns — missing orgcode → 400."""
        from handlers import save_handler
        mock_auth.return_value = admin_claims

        req = make_request({"cost_center": "10SP010000"})
        res = save_handler.handle(req)
        assert res.status_code == 400


# ───────────────────────────────────────────────────────────
# delete_handler — composite PK behavior
# ───────────────────────────────────────────────────────────
class TestDeleteHandler:

    @patch("handlers.delete_handler.spark")
    @patch("handlers.delete_handler.authenticate")
    def test_delete_uses_both_pk_columns(
        self, mock_auth, mock_spark, make_request, admin_claims
    ):
        """CRITICAL: DELETE must include BOTH PK columns in WHERE.
        
        Using only cost_center would delete ALL Orgcodes of that CC
        — catastrophic data loss bug.
        """
        from handlers import delete_handler
        mock_auth.return_value = admin_claims

        req = make_request(
            {"cost_center": "10SP010000", "orgcode": "1110000"},
            method="DELETE",
        )
        res = delete_handler.handle(req)

        assert res.status_code == 200
        # Inspect the SQL that was executed
        args, kwargs = mock_spark().sql.call_args
        sql = args[0]
        assert "cost_center" in sql and "orgcode" in sql
        assert "AND" in sql.upper(), "DELETE must use AND for composite PK"
        # Both parameters were passed
        assert kwargs.get("cost_center") == "10SP010000"
        assert kwargs.get("orgcode") == "1110000"

    @patch("handlers.delete_handler.authenticate")
    def test_delete_missing_orgcode_rejected(
        self, mock_auth, make_request, admin_claims
    ):
        from handlers import delete_handler
        mock_auth.return_value = admin_claims

        req = make_request({"cost_center": "10SP010000"}, method="DELETE")
        res = delete_handler.handle(req)
        assert res.status_code == 400

    @patch("handlers.delete_handler.authenticate")
    def test_delete_unauthorized(self, mock_auth, make_request):
        from handlers import delete_handler
        from auth import AuthError
        mock_auth.side_effect = AuthError(401, "missing")
        req = make_request({"cost_center": "X", "orgcode": "Y"}, method="DELETE")
        res = delete_handler.handle(req)
        assert res.status_code == 401


# ───────────────────────────────────────────────────────────
# list_handler — JOIN to reference table
# ───────────────────────────────────────────────────────────
class TestListHandler:

    @patch("handlers.list_handler.spark")
    @patch("handlers.list_handler.authenticate")
    def test_list_returns_joined_rows(
        self, mock_auth, mock_spark, make_request, admin_claims
    ):
        from handlers import list_handler
        mock_auth.return_value = admin_claims

        df = MagicMock()
        df.toJSON.return_value.collect.return_value = [
            '{"cost_center":"10SP010000","orgcode":"1110000","orgcode_name":"Sales BU"}'
        ]
        mock_spark().sql.return_value = df

        res = list_handler.handle(make_request(method="GET"))
        assert res.status_code == 200
        body = json.loads(res.get_body())
        assert body[0]["cost_center"] == "10SP010000"
        assert body[0]["orgcode_name"] == "Sales BU"

    @patch("handlers.list_handler.spark")
    @patch("handlers.list_handler.authenticate")
    def test_list_sql_includes_left_join_to_ref(
        self, mock_auth, mock_spark, make_request, admin_claims
    ):
        """list_handler must JOIN sap_orgcode_ref for display name."""
        from handlers import list_handler
        mock_auth.return_value = admin_claims
        df = MagicMock()
        df.toJSON.return_value.collect.return_value = []
        mock_spark().sql.return_value = df

        list_handler.handle(make_request(method="GET"))
        args, _ = mock_spark().sql.call_args
        sql = args[0].lower()
        assert "left join" in sql
        assert "sap_orgcode_ref" in sql
