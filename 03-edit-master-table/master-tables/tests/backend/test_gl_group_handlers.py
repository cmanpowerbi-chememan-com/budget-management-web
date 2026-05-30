"""Unit tests for GL Group Master handlers.

Mocks pyodbc helpers + auth so tests run without Fabric.
Run: pytest tests/test_handlers.py
"""
import json
from unittest.mock import patch, MagicMock
import pytest


# ───────────────────────────────────────────────────────────
# Fixtures
# ───────────────────────────────────────────────────────────
@pytest.fixture
def admin_claims():
    return {
        "sub": "user-uuid-1",
        "email": "volks@chememan.com",
        "groups": ["master_table_admins"],
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
# save_handler tests
# ───────────────────────────────────────────────────────────
class TestSaveHandler:

    @patch("modules.gl_group.save_handler.execute")
    @patch("modules.gl_group.save_handler.find_group_id_by_name")
    @patch("modules.gl_group.save_handler.exists")
    @patch("modules.gl_group.save_handler.authenticate")
    def test_save_new_row_with_existing_group(
        self, mock_auth, mock_exists, mock_find, mock_execute,
        make_request, admin_claims
    ):
        from modules.gl_group import save_handler
        mock_auth.return_value = admin_claims
        mock_exists.return_value = False
        req = make_request({
            "gl_code": "5200016999",
            "group_id": "group-uuid-1",
            "is_edit_mode": False,
        })

        res = save_handler.handle(req)

        assert res.status_code == 200
        body = json.loads(res.get_body())
        assert body["status"] == "success"
        mock_execute.assert_called()

    @patch("modules.gl_group.save_handler.exists")
    @patch("modules.gl_group.save_handler.authenticate")
    def test_save_rejects_duplicate_when_not_editing(
        self, mock_auth, mock_exists, make_request, admin_claims
    ):
        """Fail Fast: locked decision #5"""
        from modules.gl_group import save_handler
        mock_auth.return_value = admin_claims
        mock_exists.return_value = True

        req = make_request({
            "gl_code": "5200016353",
            "group_id": "group-uuid-1",
            "is_edit_mode": False,
        })
        res = save_handler.handle(req)

        assert res.status_code == 409
        body = json.loads(res.get_body())
        assert body["code"] == "DUPLICATE_KEY"

    @patch("modules.gl_group.save_handler.execute")
    @patch("modules.gl_group.save_handler.find_group_id_by_name")
    @patch("modules.gl_group.save_handler.exists")
    @patch("modules.gl_group.save_handler.authenticate")
    def test_save_with_new_group_name_creates_dim_row(
        self, mock_auth, mock_exists, mock_find, mock_execute,
        make_request, admin_claims
    ):
        """create_on_save: new group_name → INSERT dim, then mapping"""
        from modules.gl_group import save_handler
        mock_auth.return_value = admin_claims
        mock_exists.return_value = False
        mock_find.return_value = None  # group name does NOT exist

        req = make_request({
            "gl_code": "5200016999",
            "group_name": "ค่าใหม่",
            "is_edit_mode": False,
        })
        res = save_handler.handle(req)

        assert res.status_code == 200
        # Two execute calls expected: dim INSERT + mapping MERGE
        assert mock_execute.call_count == 2

    @patch("modules.gl_group.save_handler.authenticate")
    def test_save_unauthorized_no_token(
        self, mock_auth, make_request
    ):
        from modules.gl_group import save_handler
        from auth import AuthError
        mock_auth.side_effect = AuthError(401, "Missing Authorization header")

        req = make_request({"gl_code": "5200016999", "group_id": "g1"})
        res = save_handler.handle(req)
        assert res.status_code == 401

    @patch("modules.gl_group.save_handler.authenticate")
    def test_save_forbidden_wrong_group(
        self, mock_auth, make_request
    ):
        from modules.gl_group import save_handler
        from auth import AuthError
        mock_auth.side_effect = AuthError(403, "Forbidden")

        req = make_request({"gl_code": "5200016999", "group_id": "g1"})
        res = save_handler.handle(req)
        assert res.status_code == 403

    @patch("modules.gl_group.save_handler.authenticate")
    def test_save_invalid_gl_code_format(
        self, mock_auth, make_request, admin_claims
    ):
        """Pydantic regex validation rejects non-digit gl_code"""
        from modules.gl_group import save_handler
        mock_auth.return_value = admin_claims

        req = make_request({
            "gl_code": "ABC123",  # not digits
            "group_id": "g1",
        })
        res = save_handler.handle(req)
        assert res.status_code == 400


# ───────────────────────────────────────────────────────────
# delete_handler tests
# ───────────────────────────────────────────────────────────
class TestDeleteHandler:

    @patch("modules.gl_group.delete_handler.execute")
    @patch("modules.gl_group.delete_handler.authenticate")
    def test_delete_happy_path(
        self, mock_auth, mock_execute, make_request, admin_claims
    ):
        from modules.gl_group import delete_handler
        mock_auth.return_value = admin_claims

        req = make_request({"gl_code": "5200016353"}, method="DELETE")
        res = delete_handler.handle(req)

        assert res.status_code == 200
        body = json.loads(res.get_body())
        assert body["status"] == "deleted"
        mock_execute.assert_called_once()

    @patch("modules.gl_group.delete_handler.authenticate")
    def test_delete_unauthorized(self, mock_auth, make_request):
        from modules.gl_group import delete_handler
        from auth import AuthError
        mock_auth.side_effect = AuthError(401, "missing")
        req = make_request({"gl_code": "5200016353"}, method="DELETE")
        res = delete_handler.handle(req)
        assert res.status_code == 401


# ───────────────────────────────────────────────────────────
# list_handler tests
# ───────────────────────────────────────────────────────────
class TestListHandler:

    @patch("modules.gl_group.list_handler.fetchall")
    @patch("modules.gl_group.list_handler.authenticate")
    def test_list_returns_joined_rows(
        self, mock_auth, mock_fetchall, make_request, admin_claims
    ):
        from modules.gl_group import list_handler
        mock_auth.return_value = admin_claims
        mock_fetchall.return_value = [
            {"gl_code": "5200016353", "group_id": "g1", "group_name": "office"}
        ]

        res = list_handler.handle(make_request(method="GET"))
        assert res.status_code == 200
        body = json.loads(res.get_body())
        assert len(body) == 1
        assert body[0]["gl_code"] == "5200016353"
