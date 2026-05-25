"""Unit tests for Hide Document Number handlers.

Critical test focus:
  - 3-column composite PK behavior (doc_num, fiscal_year, fiscal_month)
  - Range validation (year 2020-2099, month 1-12)
  - All 3 columns in dup-check AND delete WHERE
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
# save_handler — 3-column composite PK
# ───────────────────────────────────────────────────────────
class TestSaveHandler:

    @patch("handlers.save_handler.spark")
    @patch("handlers.save_handler.exists")
    @patch("handlers.save_handler.authenticate")
    def test_save_new_triple_happy_path(
        self, mock_auth, mock_exists, mock_spark,
        make_request, admin_claims
    ):
        """Insert a new (doc_num, year, month) triple."""
        from handlers import save_handler
        mock_auth.return_value = admin_claims
        mock_exists.return_value = False

        req = make_request({
            "doc_num": "5400005042",
            "fiscal_year": 2026,
            "fiscal_month": 1,
        })
        res = save_handler.handle(req)

        assert res.status_code == 200
        # Verify the existence check uses ALL 3 PK columns
        args, _ = mock_exists.call_args
        where_clause = args[1]
        params_dict = args[2]
        assert "doc_num"      in where_clause
        assert "fiscal_year"  in where_clause
        assert "fiscal_month" in where_clause
        assert where_clause.upper().count("AND") >= 2, (
            "3-column composite PK check must have at least 2 ANDs"
        )
        assert params_dict["doc_num"]      == "5400005042"
        assert params_dict["fiscal_year"]  == 2026
        assert params_dict["fiscal_month"] == 1

    @patch("handlers.save_handler.spark")
    @patch("handlers.save_handler.exists")
    @patch("handlers.save_handler.authenticate")
    def test_save_same_doc_different_period_is_not_duplicate(
        self, mock_auth, mock_exists, mock_spark,
        make_request, admin_claims
    ):
        """CRITICAL: Same doc_num in different period = NEW row.
        
        If only doc_num were checked, this would falsely 409.
        """
        from handlers import save_handler
        mock_auth.return_value = admin_claims
        mock_exists.return_value = False   # different period not yet present

        req = make_request({
            "doc_num": "5400005042",
            "fiscal_year": 2026,
            "fiscal_month": 2,  # February — different from existing January
        })
        res = save_handler.handle(req)
        assert res.status_code == 200

    @patch("handlers.save_handler.exists")
    @patch("handlers.save_handler.authenticate")
    def test_save_exact_same_triple_is_duplicate(
        self, mock_auth, mock_exists, make_request, admin_claims
    ):
        from handlers import save_handler
        mock_auth.return_value = admin_claims
        mock_exists.return_value = True

        req = make_request({
            "doc_num": "5400005042",
            "fiscal_year": 2026,
            "fiscal_month": 1,
        })
        res = save_handler.handle(req)

        assert res.status_code == 409
        body = json.loads(res.get_body())
        assert body["code"] == "DUPLICATE_KEY"

    @patch("handlers.save_handler.authenticate")
    def test_save_year_below_min_rejected(
        self, mock_auth, make_request, admin_claims
    ):
        """Pydantic ge=2020 rejects year < 2020."""
        from handlers import save_handler
        mock_auth.return_value = admin_claims

        req = make_request({
            "doc_num": "5400005042",
            "fiscal_year": 1999,  # below 2020
            "fiscal_month": 1,
        })
        res = save_handler.handle(req)
        assert res.status_code == 400

    @patch("handlers.save_handler.authenticate")
    def test_save_year_above_max_rejected(
        self, mock_auth, make_request, admin_claims
    ):
        from handlers import save_handler
        mock_auth.return_value = admin_claims

        req = make_request({
            "doc_num": "5400005042",
            "fiscal_year": 2100,  # above 2099
            "fiscal_month": 1,
        })
        res = save_handler.handle(req)
        assert res.status_code == 400

    @patch("handlers.save_handler.authenticate")
    def test_save_month_zero_rejected(
        self, mock_auth, make_request, admin_claims
    ):
        """month=0 is invalid (months are 1-indexed)."""
        from handlers import save_handler
        mock_auth.return_value = admin_claims

        req = make_request({
            "doc_num": "5400005042",
            "fiscal_year": 2026,
            "fiscal_month": 0,
        })
        res = save_handler.handle(req)
        assert res.status_code == 400

    @patch("handlers.save_handler.authenticate")
    def test_save_month_thirteen_rejected(
        self, mock_auth, make_request, admin_claims
    ):
        from handlers import save_handler
        mock_auth.return_value = admin_claims

        req = make_request({
            "doc_num": "5400005042",
            "fiscal_year": 2026,
            "fiscal_month": 13,
        })
        res = save_handler.handle(req)
        assert res.status_code == 400

    @patch("handlers.save_handler.authenticate")
    def test_save_missing_fiscal_month_rejected(
        self, mock_auth, make_request, admin_claims
    ):
        """Composite PK requires all 3 — missing month → 400."""
        from handlers import save_handler
        mock_auth.return_value = admin_claims

        req = make_request({
            "doc_num": "5400005042",
            "fiscal_year": 2026,
        })
        res = save_handler.handle(req)
        assert res.status_code == 400


# ───────────────────────────────────────────────────────────
# delete_handler — 3-column composite PK
# ───────────────────────────────────────────────────────────
class TestDeleteHandler:

    @patch("handlers.delete_handler.spark")
    @patch("handlers.delete_handler.authenticate")
    def test_delete_uses_all_three_pk_columns(
        self, mock_auth, mock_spark, make_request, admin_claims
    ):
        """⚠️ CATASTROPHIC if any PK column missing from WHERE."""
        from handlers import delete_handler
        mock_auth.return_value = admin_claims

        req = make_request(
            {"doc_num": "5400005042", "fiscal_year": 2026, "fiscal_month": 1},
            method="DELETE",
        )
        res = delete_handler.handle(req)

        assert res.status_code == 200
        args, kwargs = mock_spark().sql.call_args
        sql = args[0].lower()
        assert "doc_num" in sql
        assert "fiscal_year" in sql
        assert "fiscal_month" in sql
        assert sql.count("and") >= 2, (
            "3-column composite delete must have at least 2 ANDs"
        )

    @patch("handlers.delete_handler.authenticate")
    def test_delete_missing_period_rejected(
        self, mock_auth, make_request, admin_claims
    ):
        """Cannot delete with just doc_num (would be catastrophic)."""
        from handlers import delete_handler
        mock_auth.return_value = admin_claims

        req = make_request({"doc_num": "5400005042"}, method="DELETE")
        res = delete_handler.handle(req)
        assert res.status_code == 400


# ───────────────────────────────────────────────────────────
# list_handler — period computed in SQL
# ───────────────────────────────────────────────────────────
class TestListHandler:

    @patch("handlers.list_handler.spark")
    @patch("handlers.list_handler.authenticate")
    def test_list_sql_computes_period_string(
        self, mock_auth, mock_spark, make_request, admin_claims
    ):
        """SQL must include CONCAT/LPAD to build YYYY-MM string."""
        from handlers import list_handler
        mock_auth.return_value = admin_claims
        df = MagicMock()
        df.toJSON.return_value.collect.return_value = []
        mock_spark().sql.return_value = df

        list_handler.handle(make_request(method="GET"))
        args, _ = mock_spark().sql.call_args
        sql = args[0].upper()
        assert "CONCAT" in sql
        assert "LPAD" in sql
        assert "PERIOD" in sql
