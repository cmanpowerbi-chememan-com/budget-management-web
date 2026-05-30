"""Standalone test for validate_docs_handler.validate().

Bypasses Azure Function runtime — calls the pure validate() function directly,
which exercises the real pyodbc + Fabric Lakehouse query against gold_sap_gl_trans.

Run:
    cd 03-edit-master-table/0003-gl-group/02backend
    python test_validate_local.py
"""
import sys
import io
import os
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

# Make handler imports work when running this file directly
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE / "modules" / "hide_document"))

# Load .env from project root
try:
    from dotenv import load_dotenv
    # HERE = .../03-edit-master-table/0003-gl-group/02backend
    # parents[0]=0003-gl-group, [1]=03-edit-master-table, [2]=project-root
    PROJECT_ROOT = HERE.parents[2]
    env_path = PROJECT_ROOT / ".env"
    print(f"Loading env from: {env_path} (exists: {env_path.exists()})")
    load_dotenv(env_path)
except ImportError:
    print("⚠️  dotenv not installed — env vars must be set manually")

# Required vars
required = [
    "FABRIC_SQL_SERVER", "FABRIC_SQL_DATABASE",
    "FABRIC_LAKEHOUSE_SERVER", "FABRIC_LAKEHOUSE_DATABASE",
    "ENTRA_CLIENT_ID", "ENTRA_CLIENT_SECRET",
]
missing = [v for v in required if not os.environ.get(v)]
if missing:
    print(f"❌ Missing env vars: {missing}")
    sys.exit(1)

# Strip surrounding quotes that .env sometimes has
for v in required:
    os.environ[v] = os.environ[v].strip("'\"")

# 0003 db.py reads AAD_* env vars — alias from ENTRA_*
os.environ["AAD_CLIENT_ID"]     = os.environ["ENTRA_CLIENT_ID"]
os.environ["AAD_CLIENT_SECRET"] = os.environ["ENTRA_CLIENT_SECRET"]
# Allow the test "user" through auth.py if any handler is invoked
os.environ.setdefault("ADMIN_EMAILS", "test@example.com")

from modules.hide_document.validate_docs_handler import validate  # noqa: E402


def run(name: str, codes: list[str], expect_valid: list[str], expect_invalid_contains: list[str]) -> bool:
    print(f"\n── {name} ──")
    print(f"   input  : {codes}")
    try:
        result = validate(codes)
    except Exception as e:
        print(f"   ❌ EXCEPTION: {e}")
        return False
    print(f"   valid  : {result['valid']}")
    print(f"   invalid: {result['invalid']}")
    ok_valid   = set(result["valid"]) == set(expect_valid)
    ok_invalid = all(c in result["invalid"] for c in expect_invalid_contains)
    if ok_valid and ok_invalid:
        print(f"   ✅ PASS")
        return True
    if not ok_valid:
        print(f"   ❌ valid mismatch — expected {expect_valid}, got {result['valid']}")
    if not ok_invalid:
        print(f"   ❌ invalid missing — expected to contain {expect_invalid_contains}, got {result['invalid']}")
    return False


def main() -> int:
    print("=" * 60)
    print("Test: validate_docs_handler.validate()")
    print(f"Lakehouse Server: {os.environ['FABRIC_LAKEHOUSE_SERVER']}")
    print(f"Lakehouse DB    : {os.environ['FABRIC_LAKEHOUSE_DATABASE']}")
    print("=" * 60)

    # ── 1. Sanity: query 1 known + 1 obvious fake ──
    # We don't know which doc numbers really exist; first get any 3 real ones.
    print("\n── Probe: fetch 3 real doc numbers from dbo.gold_sap_gl_trans ──")
    try:
        # Use fetchall_lakehouse() not `with get_lakehouse_conn()` —
        # the cached thread-local conn would close on `with` exit.
        from db import fetchall_lakehouse
        rows = fetchall_lakehouse(
            "SELECT DISTINCT TOP 3 accounting_doc_number "
            "FROM dbo.gold_sap_gl_trans "
            "WHERE accounting_doc_number IS NOT NULL "
            "ORDER BY accounting_doc_number"
        )
        real = [r["accounting_doc_number"] for r in rows]
        print(f"   3 real codes: {real}")
        if not real:
            print("   ⚠️  Table is empty — cannot test 'valid' path")
            return 1
    except Exception as e:
        print(f"   ❌ Probe failed: {e}")
        return 1

    results = []
    results.append(run(
        "All real codes → all valid",
        codes=real,
        expect_valid=real,
        expect_invalid_contains=[],
    ))
    results.append(run(
        "Fake 10-digit code → invalid (format ok, not in DB)",
        codes=["9999999999"],
        expect_valid=[],
        expect_invalid_contains=["9999999999"],
    ))
    results.append(run(
        "Bad format → invalid (format check)",
        codes=["12345", "abcdefghij"],
        expect_valid=[],
        expect_invalid_contains=["12345", "abcdefghij"],
    ))
    results.append(run(
        "Mixed: 1 real + 1 fake + 1 bad-format → split correctly",
        codes=[real[0], "9999999999", "xyz"],
        expect_valid=[real[0]],
        expect_invalid_contains=["9999999999", "xyz"],
    ))
    results.append(run(
        "De-dup: same code twice → reported once",
        codes=[real[0], real[0]],
        expect_valid=[real[0]],
        expect_invalid_contains=[],
    ))

    print()
    passed = sum(results)
    total = len(results)
    print(f"=== {passed}/{total} tests passed ===")
    return 0 if passed == total else 1


if __name__ == "__main__":
    raise SystemExit(main())
