"""E2E test: invoke hide-document handlers against the real Fabric SQL DB.

Bypasses the Azure Function runtime — calls handler.handle(req) directly with
a mocked HttpRequest. Tests the full CRUD cycle:
  1. list (empty initially)
  2. save (new triple)
  3. list (shows it)
  4. save (duplicate — expect 409)
  5. delete
  6. list (empty again)
  7. delete same triple again (expect deleted=0)

Run from this directory:
    python test_hide_doc_e2e.py
"""
import sys
import io
import os
import json
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

# Load env
from dotenv import load_dotenv
HERE = Path(__file__).resolve().parent
load_dotenv(HERE.parents[3] / ".env")
for v in ("FABRIC_SQL_SERVER", "FABRIC_SQL_DATABASE",
          "FABRIC_LAKEHOUSE_SERVER", "FABRIC_LAKEHOUSE_DATABASE",
          "ENTRA_CLIENT_ID", "ENTRA_CLIENT_SECRET"):
    if v in os.environ:
        os.environ[v] = os.environ[v].strip("'\"")
# 0003 db.py reads AAD_CLIENT_ID/AAD_CLIENT_SECRET
os.environ["AAD_CLIENT_ID"]     = os.environ["ENTRA_CLIENT_ID"]
os.environ["AAD_CLIENT_SECRET"] = os.environ["ENTRA_CLIENT_SECRET"]
# Allow our test user through auth
os.environ.setdefault("ADMIN_EMAILS", "test@example.com")

BACKEND = HERE.parents[1] / "02backend"
sys.path.insert(0, str(BACKEND))

from modules.hide_document import list_handler, save_handler, delete_handler  # noqa: E402


class MockReq:
    def __init__(self, body=None):
        self.headers = {"x-ms-client-principal-name": "test@example.com"}
        self._body = body

    def get_json(self):
        return self._body


def parse(resp):
    return resp.status_code, json.loads(resp.get_body())


TEST_DOC = "9999999998"   # safe sentinel — unlikely to collide
TEST_YEAR = 2026
TEST_MONTH = 1

passes, fails = 0, 0


def check(name, cond, detail=""):
    global passes, fails
    print(f"  [{'PASS' if cond else 'FAIL'}] {name}  {detail}")
    if cond: passes += 1
    else:    fails += 1


def main():
    print("=" * 60)
    print("E2E: hide-document handlers vs real Fabric SQL DB")
    print("=" * 60)

    # Clean slate — remove sentinel if it exists from a prior failed run
    delete_handler.handle(MockReq({"doc_num": TEST_DOC, "fiscal_year": TEST_YEAR, "fiscal_month": TEST_MONTH}))

    # 1. List initially (should not contain TEST_DOC)
    print("\n── 1. List (initial) ──")
    code, body = parse(list_handler.handle(MockReq()))
    initial_count = len(body)
    has_test = any(r["doc_num"] == TEST_DOC for r in body)
    check("GET /list returns 200", code == 200, f"status={code}")
    check("Sentinel doc NOT in initial list", not has_test, f"initial_count={initial_count}")

    # 2. Save new triple
    print("\n── 2. Save new triple ──")
    code, body = parse(save_handler.handle(MockReq({
        "doc_num": TEST_DOC, "fiscal_year": TEST_YEAR, "fiscal_month": TEST_MONTH
    })))
    check("POST /save returns 200", code == 200, f"status={code} body={body}")
    check("response status=success", body.get("status") == "success")
    check("response.period correct", body.get("period") == "2026-01")

    # 3. List shows it
    print("\n── 3. List (after save) ──")
    code, body = parse(list_handler.handle(MockReq()))
    has_test = any(r["doc_num"] == TEST_DOC and r["fiscal_year"] == TEST_YEAR and r["fiscal_month"] == TEST_MONTH for r in body)
    check("Saved doc appears in list", has_test, f"count={len(body)}")
    if has_test:
        for r in body:
            if r["doc_num"] == TEST_DOC:
                check("period field computed", r.get("period") == "2026-01", f"got={r.get('period')}")

    # 4. Save duplicate → 409
    print("\n── 4. Save duplicate ──")
    code, body = parse(save_handler.handle(MockReq({
        "doc_num": TEST_DOC, "fiscal_year": TEST_YEAR, "fiscal_month": TEST_MONTH
    })))
    check("Duplicate save returns 409", code == 409, f"status={code}")
    check("response.code = DUPLICATE_KEY", body.get("code") == "DUPLICATE_KEY")

    # 5. Save with invalid payload
    print("\n── 5. Invalid payload ──")
    code, body = parse(save_handler.handle(MockReq({
        "doc_num": "abc", "fiscal_year": 2026, "fiscal_month": 1
    })))
    check("doc_num='abc' returns 400", code == 400, f"status={code}")
    code, body = parse(save_handler.handle(MockReq({
        "doc_num": TEST_DOC, "fiscal_year": 1999, "fiscal_month": 1
    })))
    check("fiscal_year=1999 returns 400", code == 400, f"status={code}")
    code, body = parse(save_handler.handle(MockReq({
        "doc_num": TEST_DOC, "fiscal_year": 2026, "fiscal_month": 13
    })))
    check("fiscal_month=13 returns 400", code == 400, f"status={code}")

    # 6. Delete
    print("\n── 6. Delete ──")
    code, body = parse(delete_handler.handle(MockReq({
        "doc_num": TEST_DOC, "fiscal_year": TEST_YEAR, "fiscal_month": TEST_MONTH
    })))
    check("DELETE returns 200", code == 200, f"status={code}")
    check("response.deleted == 1", body.get("deleted") == 1, f"deleted={body.get('deleted')}")

    # 7. List again — sentinel gone
    print("\n── 7. List (after delete) ──")
    code, body = parse(list_handler.handle(MockReq()))
    has_test = any(r["doc_num"] == TEST_DOC for r in body)
    check("Sentinel removed from list", not has_test, f"count={len(body)}")

    # 8. Re-delete (ghost) → deleted=0
    print("\n── 8. Re-delete (ghost) ──")
    code, body = parse(delete_handler.handle(MockReq({
        "doc_num": TEST_DOC, "fiscal_year": TEST_YEAR, "fiscal_month": TEST_MONTH
    })))
    check("Ghost delete returns 200", code == 200, f"status={code}")
    check("Ghost delete deleted=0", body.get("deleted") == 0, f"deleted={body.get('deleted')}")

    print()
    print(f"=== {passes}/{passes + fails} checks passed ===")
    return 0 if fails == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
