"""Unit tests for app.config — env-driven settings, no live DB."""
from app.config import Settings, get_settings


def test_default_app_env_is_production_fail_closed(monkeypatch):
    """Missing APP_ENV must default to production (fail-closed), never local."""
    monkeypatch.delenv("APP_ENV", raising=False)
    settings = Settings(_env_file=None)
    assert settings.app_env == "production"
    assert settings.is_local is False


def test_app_env_local_sets_is_local_true():
    settings = Settings(_env_file=None, app_env="local")
    assert settings.is_local is True


def test_app_env_is_case_insensitive_for_is_local():
    settings = Settings(_env_file=None, app_env="Local")
    assert settings.is_local is True


def test_fabric_and_gold_fields_default_to_none():
    settings = Settings(_env_file=None)
    assert settings.fabric_sql_server is None
    assert settings.fabric_sql_database is None
    assert settings.gold_sql_server is None
    assert settings.gold_sql_database is None


def test_dev_auth_email_defaults_to_none():
    settings = Settings(_env_file=None)
    assert settings.dev_auth_email is None


def test_admin_emails_defaults_to_empty_set():
    settings = Settings(_env_file=None)
    assert settings.admin_emails_set == set()


def test_admin_emails_parses_comma_separated_lowercased_and_trimmed():
    settings = Settings(_env_file=None, admin_emails=" Jakkaritw@Chememan.com, nipapornt@chememan.com ,,")
    assert settings.admin_emails_set == {"jakkaritw@chememan.com", "nipapornt@chememan.com"}


def test_get_settings_reads_from_environment(monkeypatch):
    monkeypatch.setenv("APP_ENV", "local")
    monkeypatch.setenv("FABRIC_SQL_SERVER", "example.database.fabric.microsoft.com")
    get_settings.cache_clear()
    settings = get_settings()
    assert settings.app_env == "local"
    assert settings.fabric_sql_server == "example.database.fabric.microsoft.com"
    get_settings.cache_clear()
