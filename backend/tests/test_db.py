"""Unit tests for app.db — connection factories, pyodbc fully mocked.

No live DB. Any test needing a real connection is marked integration
and skipped by default (per the master-tables pytest gotcha).
"""
from unittest.mock import MagicMock, patch

from app.config import Settings
from app.db import get_fabric_conn, get_gold_conn

FABRIC_SETTINGS = Settings(
    _env_file=None,
    fabric_sql_server="fabric-host.database.fabric.microsoft.com",
    fabric_sql_database="fabric_sql_database",
    gold_sql_server="gold-host.datawarehouse.fabric.microsoft.com",
    gold_sql_database="cman_dw_wh_gold",
    entra_client_id="client-id",
    entra_client_secret="client-secret",
)


def test_module_import_does_not_open_a_connection():
    """Connections must be lazy — never opened at import time."""
    with patch("app.db.pyodbc.connect") as mock_connect:
        import importlib

        import app.db as db_module

        importlib.reload(db_module)
        mock_connect.assert_not_called()


def test_get_fabric_conn_uses_odbc_driver_17_and_fabric_settings():
    with patch("app.db.pyodbc.connect") as mock_connect:
        mock_connect.return_value = MagicMock()
        with get_fabric_conn(FABRIC_SETTINGS):
            pass
        conn_str = mock_connect.call_args[0][0]
        assert "ODBC Driver 17 for SQL Server" in conn_str
        assert "ODBC Driver 18" not in conn_str
        assert "fabric-host.database.fabric.microsoft.com" in conn_str
        assert "fabric_sql_database" in conn_str
        assert "ActiveDirectoryServicePrincipal" in conn_str


def test_get_fabric_conn_closes_connection_after_use():
    with patch("app.db.pyodbc.connect") as mock_connect:
        mock_conn = MagicMock()
        mock_connect.return_value = mock_conn
        with get_fabric_conn(FABRIC_SETTINGS) as conn:
            assert conn is mock_conn
        mock_conn.close.assert_called_once()


def test_get_fabric_conn_closes_connection_even_on_error():
    with patch("app.db.pyodbc.connect") as mock_connect:
        mock_conn = MagicMock()
        mock_connect.return_value = mock_conn
        try:
            with get_fabric_conn(FABRIC_SETTINGS):
                raise ValueError("boom")
        except ValueError:
            pass
        mock_conn.close.assert_called_once()


def test_get_gold_conn_uses_gold_settings_not_fabric_settings():
    with patch("app.db.pyodbc.connect") as mock_connect:
        mock_connect.return_value = MagicMock()
        with get_gold_conn(FABRIC_SETTINGS):
            pass
        conn_str = mock_connect.call_args[0][0]
        assert "gold-host.datawarehouse.fabric.microsoft.com" in conn_str
        assert "cman_dw_wh_gold" in conn_str
