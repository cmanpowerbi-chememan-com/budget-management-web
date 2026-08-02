"""Unit tests for app.config — env-driven settings, no live DB."""
import logging

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


def test_notifications_dry_run_defaults_true():
    """Never-cut safety default (A12) — real sends require an explicit,
    deliberate config flip, never the out-of-the-box value."""
    settings = Settings(_env_file=None)
    assert settings.notifications_dry_run is True


def test_app_base_url_has_a_placeholder_default():
    settings = Settings(_env_file=None)
    assert settings.app_base_url == "https://budget.chememan.com"


def test_production_with_placeholder_base_url_warns_loudly(caplog):
    """Misconfiguration guard: production + still-default app_base_url must
    log a warning at settings load (never crash) so a forgotten
    APP_BASE_URL override for a real deploy does not go unnoticed."""
    with caplog.at_level(logging.WARNING, logger="app.config"):
        Settings(_env_file=None, app_env="production")
    assert any("app_base_url" in record.message for record in caplog.records)


def test_local_with_placeholder_base_url_does_not_warn(caplog):
    with caplog.at_level(logging.WARNING, logger="app.config"):
        Settings(_env_file=None, app_env="local")
    assert not any("app_base_url" in record.message for record in caplog.records)


def test_attachments_settings_default_to_the_confirmed_sharepoint_location():
    """A10 (R1, spec §4b) — the site/library/root-folder are confirmed values
    (2026-07-13), not a guess, so they ship as real defaults; still
    overridable via env for ops to correct without a code change."""
    settings = Settings(_env_file=None)
    assert settings.attachments_site_hostname == "chememan.sharepoint.com"
    assert settings.attachments_site_name == "CMANDWPRD"
    assert settings.attachments_library_name == "Budgeting and Management"
    assert settings.attachments_root_folder == "เอกสาร ฝ่าย"


def test_gl_edit_by_enabled_defaults_false():
    """Never-cut safety default (GL edit_by lock design v2): must be an
    explicit, deliberate flip, never the out-of-the-box value."""
    settings = Settings(_env_file=None)
    assert settings.gl_edit_by_enabled is False


def test_log_level_defaults_to_info():
    settings = Settings(_env_file=None)
    assert settings.log_level == "INFO"


def test_log_level_reads_from_env(monkeypatch):
    """LOG_LEVEL override (see app/logging_config.py) — e.g. WARNING to
    quiet a deploy down, or DEBUG for a live debug session."""
    monkeypatch.setenv("LOG_LEVEL", "WARNING")
    settings = Settings(_env_file=None)
    assert settings.log_level == "WARNING"


def test_get_settings_reads_from_environment(monkeypatch):
    monkeypatch.setenv("APP_ENV", "local")
    monkeypatch.setenv("FABRIC_SQL_SERVER", "example.database.fabric.microsoft.com")
    get_settings.cache_clear()
    settings = get_settings()
    assert settings.app_env == "local"
    assert settings.fabric_sql_server == "example.database.fabric.microsoft.com"
    get_settings.cache_clear()
