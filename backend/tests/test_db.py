"""Unit tests for app.db — connection factories, pyodbc + msal fully mocked.

No live DB, no live AAD call. Any test needing a real connection is marked
integration and skipped by default (per the master-tables pytest gotcha).
"""
import struct
from unittest.mock import MagicMock, patch

import pytest

from app.config import Settings
from app.db import _pack_access_token, get_fabric_conn, get_gold_conn

_SQL_COPT_SS_ACCESS_TOKEN = 1256

FABRIC_SETTINGS = Settings(
    _env_file=None,
    fabric_sql_server="fabric-host.database.fabric.microsoft.com",
    fabric_sql_database="fabric_sql_database",
    gold_sql_server="gold-host.datawarehouse.fabric.microsoft.com",
    gold_sql_database="cman_dw_wh_gold",
    entra_client_id="client-id",
    entra_client_secret="client-secret",
    entra_tenant_id="tenant-id",
)


@pytest.fixture(autouse=True)
def _clear_msal_app_cache():
    """The module-level msal app cache (keyed by client_id) must not leak
    a mocked instance from one test into the next."""
    import app.db as db_module

    db_module._msal_apps.clear()
    yield
    db_module._msal_apps.clear()


def _mock_msal(token: str = "fake-access-token"):
    """Patch app.db.msal.ConfidentialClientApplication so token acquisition
    returns a fixed token without any network/AAD call."""
    patcher = patch("app.db.msal.ConfidentialClientApplication")
    mock_cls = patcher.start()
    mock_cls.return_value.acquire_token_for_client.return_value = {"access_token": token}
    return patcher, mock_cls


def test_module_import_does_not_open_a_connection():
    """Connections must be lazy — never opened at import time."""
    with patch("app.db.pyodbc.connect") as mock_connect:
        import importlib

        import app.db as db_module

        importlib.reload(db_module)
        mock_connect.assert_not_called()


def test_pack_access_token_packs_length_prefix_and_utf16le():
    """SQL_COPT_SS_ACCESS_TOKEN spec: 4-byte little-endian length prefix
    followed by the token as UTF-16-LE bytes, no null terminator."""
    packed = _pack_access_token("abc")
    raw = "abc".encode("utf-16-le")
    assert packed == struct.pack("<i", len(raw)) + raw
    assert packed == b"\x06\x00\x00\x00" + raw


def test_get_fabric_conn_uses_odbc_driver_17_and_fabric_settings():
    patcher, _ = _mock_msal()
    try:
        with patch("app.db.pyodbc.connect") as mock_connect:
            mock_connect.return_value = MagicMock()
            with get_fabric_conn(FABRIC_SETTINGS):
                pass
            conn_str = mock_connect.call_args[0][0]
            assert "ODBC Driver 17 for SQL Server" in conn_str
            assert "ODBC Driver 18" not in conn_str
            assert "fabric-host.database.fabric.microsoft.com" in conn_str
            assert "fabric_sql_database" in conn_str
    finally:
        patcher.stop()


def test_get_fabric_conn_conn_string_excludes_legacy_sql_auth():
    """Authentication=/UID=/PWD= must NOT appear once the token is injected
    via attrs_before — ODBC rejects the combination (module docstring)."""
    patcher, _ = _mock_msal()
    try:
        with patch("app.db.pyodbc.connect") as mock_connect:
            mock_connect.return_value = MagicMock()
            with get_fabric_conn(FABRIC_SETTINGS):
                pass
            conn_str = mock_connect.call_args[0][0]
            assert "Authentication=" not in conn_str
            assert "UID=" not in conn_str
            assert "PWD=" not in conn_str
    finally:
        patcher.stop()


def test_get_fabric_conn_injects_access_token_via_attrs_before():
    patcher, _ = _mock_msal(token="my-token")
    try:
        with patch("app.db.pyodbc.connect") as mock_connect:
            mock_connect.return_value = MagicMock()
            with get_fabric_conn(FABRIC_SETTINGS):
                pass
            _, kwargs = mock_connect.call_args
            assert kwargs["attrs_before"] == {_SQL_COPT_SS_ACCESS_TOKEN: _pack_access_token("my-token")}
            assert kwargs["timeout"] == 30
    finally:
        patcher.stop()


def test_get_fabric_conn_closes_connection_after_use():
    patcher, _ = _mock_msal()
    try:
        with patch("app.db.pyodbc.connect") as mock_connect:
            mock_conn = MagicMock()
            mock_connect.return_value = mock_conn
            with get_fabric_conn(FABRIC_SETTINGS) as conn:
                assert conn is mock_conn
            mock_conn.close.assert_called_once()
    finally:
        patcher.stop()


def test_get_fabric_conn_closes_connection_even_on_error():
    patcher, _ = _mock_msal()
    try:
        with patch("app.db.pyodbc.connect") as mock_connect:
            mock_conn = MagicMock()
            mock_connect.return_value = mock_conn
            try:
                with get_fabric_conn(FABRIC_SETTINGS):
                    raise ValueError("boom")
            except ValueError:
                pass
            mock_conn.close.assert_called_once()
    finally:
        patcher.stop()


def test_get_gold_conn_uses_gold_settings_not_fabric_settings():
    patcher, _ = _mock_msal()
    try:
        with patch("app.db.pyodbc.connect") as mock_connect:
            mock_connect.return_value = MagicMock()
            with get_gold_conn(FABRIC_SETTINGS):
                pass
            conn_str = mock_connect.call_args[0][0]
            assert "gold-host.datawarehouse.fabric.microsoft.com" in conn_str
            assert "cman_dw_wh_gold" in conn_str
    finally:
        patcher.stop()


def test_get_gold_conn_injects_access_token_via_attrs_before():
    patcher, _ = _mock_msal(token="gold-token")
    try:
        with patch("app.db.pyodbc.connect") as mock_connect:
            mock_connect.return_value = MagicMock()
            with get_gold_conn(FABRIC_SETTINGS):
                pass
            _, kwargs = mock_connect.call_args
            assert kwargs["attrs_before"] == {_SQL_COPT_SS_ACCESS_TOKEN: _pack_access_token("gold-token")}
            assert kwargs["timeout"] == 30
    finally:
        patcher.stop()


def test_token_acquisition_failure_raises_runtime_error_with_error_description():
    patcher = patch("app.db.msal.ConfidentialClientApplication")
    mock_cls = patcher.start()
    mock_cls.return_value.acquire_token_for_client.return_value = {
        "error": "invalid_client",
        "error_description": "AADSTS7000215: Invalid client secret provided.",
    }
    try:
        with patch("app.db.pyodbc.connect") as mock_connect:
            with pytest.raises(RuntimeError) as exc_info:
                with get_fabric_conn(FABRIC_SETTINGS):
                    pass
            mock_connect.assert_not_called()
        assert "invalid_client" in str(exc_info.value)
        assert "AADSTS7000215" in str(exc_info.value)
    finally:
        patcher.stop()


def test_msal_app_is_cached_across_connections():
    """Repeat calls must not rebuild ConfidentialClientApplication — msal's
    own cache (inside the instance) is what makes the token path fast."""
    patcher, mock_cls = _mock_msal()
    try:
        with patch("app.db.pyodbc.connect") as mock_connect:
            mock_connect.return_value = MagicMock()
            with get_fabric_conn(FABRIC_SETTINGS):
                pass
            with get_fabric_conn(FABRIC_SETTINGS):
                pass
        mock_cls.assert_called_once()
    finally:
        patcher.stop()


def test_msal_app_cache_keyed_by_tenant_and_client():
    """Same client_id under two different tenant_ids must NOT share a
    cached app instance — cache key is (tenant_id, client_id), not just
    client_id (a wrong tenant token would otherwise be silently reused)."""
    patcher, mock_cls = _mock_msal()
    try:
        settings_tenant_a = Settings(
            _env_file=None,
            fabric_sql_server="fabric-host.database.fabric.microsoft.com",
            fabric_sql_database="fabric_sql_database",
            entra_client_id="client-id",
            entra_client_secret="client-secret",
            entra_tenant_id="tenant-a",
        )
        settings_tenant_b = Settings(
            _env_file=None,
            fabric_sql_server="fabric-host.database.fabric.microsoft.com",
            fabric_sql_database="fabric_sql_database",
            entra_client_id="client-id",
            entra_client_secret="client-secret",
            entra_tenant_id="tenant-b",
        )
        with patch("app.db.pyodbc.connect") as mock_connect:
            mock_connect.return_value = MagicMock()
            with get_fabric_conn(settings_tenant_a):
                pass
            with get_fabric_conn(settings_tenant_b):
                pass
        assert mock_cls.call_count == 2
    finally:
        patcher.stop()
