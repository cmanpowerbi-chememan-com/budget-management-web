"""Set dummy env vars before any module is imported.

auth.py and db.py read os.environ at module load time.
These stubs prevent KeyError during unit tests — the actual
values are never used because authenticate/execute/fetchall
are mocked in every test.
"""
import os

os.environ.setdefault("AAD_TENANT_ID",        "test-tenant-id")
os.environ.setdefault("AAD_AUDIENCE",         "test-audience")
os.environ.setdefault("FABRIC_SQL_SERVER",    "test-server")
os.environ.setdefault("FABRIC_SQL_DATABASE",  "test-database")
os.environ.setdefault("AAD_CLIENT_ID",           "test-client-id")
os.environ.setdefault("AAD_CLIENT_SECRET",       "test-secret")
os.environ.setdefault("FABRIC_LAKEHOUSE_SERVER",  "test-lakehouse-server")
os.environ.setdefault("FABRIC_LAKEHOUSE_DATABASE", "test-lakehouse-db")
os.environ.setdefault("ADMIN_EMAILS",             "admin@chememan.com")
