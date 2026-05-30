"""Pytest conftest — sys.path + env stubs before any test module loads.

auth.py and db.py read os.environ at module load time. These stubs prevent
KeyError during unit tests — the actual values are never used because
authenticate/execute/fetchall are mocked in every test.
"""
import os
import sys
from pathlib import Path

# Put the Function App backend on sys.path so tests can do
# `from modules.gl_group.save_handler import ...` etc.
# Conftest path: master-tables/tests/backend/conftest.py
# Backend path:  master-tables/02backend/
BACKEND = Path(__file__).resolve().parents[2] / "02backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

os.environ.setdefault("AAD_TENANT_ID",        "test-tenant-id")
os.environ.setdefault("AAD_AUDIENCE",         "test-audience")
os.environ.setdefault("FABRIC_SQL_SERVER",    "test-server")
os.environ.setdefault("FABRIC_SQL_DATABASE",  "test-database")
os.environ.setdefault("AAD_CLIENT_ID",           "test-client-id")
os.environ.setdefault("AAD_CLIENT_SECRET",       "test-secret")
os.environ.setdefault("FABRIC_LAKEHOUSE_SERVER",  "test-lakehouse-server")
os.environ.setdefault("FABRIC_LAKEHOUSE_DATABASE", "test-lakehouse-db")
os.environ.setdefault("ADMIN_EMAILS",             "admin@chememan.com")
