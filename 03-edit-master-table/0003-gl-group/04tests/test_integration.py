"""Integration tests — real Fabric SQL Database, no mocks.

Tests the full handler → db → Fabric SQL round-trip.
Auth is bypassed (authenticate returns a fixed admin claims dict).

Run from 04tests/:
    python -m pytest test_integration.py -v -s

Requirements: env vars set (FABRIC_SQL_SERVER, FABRIC_SQL_DATABASE,
              AAD_CLIENT_ID, AAD_CLIENT_SECRET are read by db.py)
"""
import json
import os
import pytest
from unittest.mock import patch, MagicMock

# Test GL code — unlikely to exist in real data; cleaned up after each test
TEST_GL_CODE = "9999999999"
TEST_GROUP_NAME = "__integ_test_group__"

ADMIN_CLAIMS = {
    "sub": "integ-test",
    "email": "test@chememan.com",
    "groups": ["master-table-admins"],
}


def make_req(body=None, method="GET"):
    req = MagicMock()
    req.get_json.return_value = body or {}
    req.headers = {"Authorization": "Bearer fake-token"}
    req.method = method
    return req


# ── helpers ──────────────────────────────────────────────────
def _delete_test_row():
    """Ensure no stale test row from a previous failed run."""
    from db import execute
    execute("DELETE FROM cfg_master.gl_group_mapping WHERE gl_code = ?", (TEST_GL_CODE,))


def _delete_test_group():
    from db import execute
    execute(
        "DELETE FROM cfg_master.gl_group_dim WHERE group_name = ?",
        (TEST_GROUP_NAME,),
    )


# ── fixtures ─────────────────────────────────────────────────
@pytest.fixture(autouse=True)
def cleanup():
    _delete_test_row()
    _delete_test_group()
    yield
    _delete_test_row()
    _delete_test_group()


# ── tests ────────────────────────────────────────────────────
class TestIntegration:

    @patch("handlers.list_handler.authenticate", return_value=ADMIN_CLAIMS)
    def test_list_returns_real_data(self, _):
        from handlers import list_handler
        res = list_handler.handle(make_req(method="GET"))
        assert res.status_code == 200
        rows = json.loads(res.get_body())
        assert isinstance(rows, list)
        assert len(rows) > 0, "Expected seeded GL group mappings in DB"
        assert all("gl_code" in r and "group_name" in r for r in rows)
        print(f"\n  list returned {len(rows)} rows, first: {rows[0]}")

    @patch("handlers.save_handler.authenticate", return_value=ADMIN_CLAIMS)
    def test_save_new_mapping_then_verify_in_list(self, _):
        from handlers import save_handler, list_handler
        from unittest.mock import patch as p2

        # Save with an existing group (Bank Charge)
        from db import find_group_id_by_name
        group_id = find_group_id_by_name("Bank Charge")
        assert group_id, "Bank Charge must exist in gl_group_dim (seeded)"

        req = make_req({"gl_code": TEST_GL_CODE, "group_id": group_id, "is_edit_mode": False})
        res = save_handler.handle(req)
        assert res.status_code == 200, f"Save failed: {res.get_body()}"
        body = json.loads(res.get_body())
        assert body["status"] == "success"
        print(f"\n  saved {TEST_GL_CODE} -> {group_id}")

        # Verify in list
        with p2("handlers.list_handler.authenticate", return_value=ADMIN_CLAIMS):
            list_res = list_handler.handle(make_req(method="GET"))
        rows = json.loads(list_res.get_body())
        assert any(r["gl_code"] == TEST_GL_CODE for r in rows), \
            f"{TEST_GL_CODE} not found in list after save"

    @patch("handlers.save_handler.authenticate", return_value=ADMIN_CLAIMS)
    def test_save_with_new_group_creates_dim_row(self, _):
        from handlers import save_handler
        from db import find_group_id_by_name

        req = make_req({
            "gl_code":    TEST_GL_CODE,
            "group_name": TEST_GROUP_NAME,
            "is_edit_mode": False,
        })
        res = save_handler.handle(req)
        assert res.status_code == 200, f"Save failed: {res.get_body()}"

        # group_name should now exist in dim
        gid = find_group_id_by_name(TEST_GROUP_NAME)
        assert gid is not None, "New dim row was not created"
        print(f"\n  new group '{TEST_GROUP_NAME}' created with id {gid}")

    @patch("handlers.save_handler.authenticate", return_value=ADMIN_CLAIMS)
    def test_duplicate_save_returns_409(self, _):
        from handlers import save_handler
        from db import find_group_id_by_name

        group_id = find_group_id_by_name("Bank Charge")
        payload = {"gl_code": TEST_GL_CODE, "group_id": group_id, "is_edit_mode": False}

        save_handler.handle(make_req(payload))           # first — OK
        res = save_handler.handle(make_req(payload))     # second — duplicate
        assert res.status_code == 409
        body = json.loads(res.get_body())
        assert body["code"] == "DUPLICATE_KEY"

    @patch("handlers.delete_handler.authenticate", return_value=ADMIN_CLAIMS)
    @patch("handlers.save_handler.authenticate",   return_value=ADMIN_CLAIMS)
    def test_delete_removes_row(self, _save, _del):
        from handlers import save_handler, delete_handler
        from db import find_group_id_by_name, exists

        group_id = find_group_id_by_name("Bank Charge")
        save_handler.handle(make_req(
            {"gl_code": TEST_GL_CODE, "group_id": group_id, "is_edit_mode": False}
        ))

        del_res = delete_handler.handle(make_req({"gl_code": TEST_GL_CODE}, method="DELETE"))
        assert del_res.status_code == 200
        body = json.loads(del_res.get_body())
        assert body["status"] == "deleted"

        still_exists = exists("cfg_master.gl_group_mapping", "gl_code = ?", (TEST_GL_CODE,))
        assert not still_exists, "Row still in DB after delete"
        print(f"\n  {TEST_GL_CODE} confirmed deleted from DB")
