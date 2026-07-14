"""Unit tests for app.auth — Easy Auth header extraction + DEV override.

No live DB, no live Entra ID. Calls the dependency function directly.
"""
import pytest
from fastapi import HTTPException

from app.auth import get_current_user_email
from app.config import Settings


PROD_SETTINGS = Settings(_env_file=None, app_env="production")
LOCAL_SETTINGS = Settings(_env_file=None, app_env="local", dev_auth_email="dev@chememan.com")
LOCAL_SETTINGS_NO_OVERRIDE = Settings(_env_file=None, app_env="local")


def test_valid_header_returns_email():
    email = get_current_user_email(
        x_ms_client_principal_name="somchai.j@chememan.com", settings=PROD_SETTINGS
    )
    assert email == "somchai.j@chememan.com"


def test_missing_header_in_production_raises_401():
    with pytest.raises(HTTPException) as exc_info:
        get_current_user_email(x_ms_client_principal_name=None, settings=PROD_SETTINGS)
    assert exc_info.value.status_code == 401


def test_blank_header_treated_as_missing_raises_401():
    """Malformed header (blank/whitespace-only) must not silently authenticate."""
    with pytest.raises(HTTPException) as exc_info:
        get_current_user_email(x_ms_client_principal_name="   ", settings=PROD_SETTINGS)
    assert exc_info.value.status_code == 401


def test_dev_override_used_when_header_absent_and_local():
    email = get_current_user_email(x_ms_client_principal_name=None, settings=LOCAL_SETTINGS)
    assert email == "dev@chememan.com"


def test_dev_override_ignored_when_not_local_even_if_configured():
    """DEV_AUTH_EMAIL must never leak into a non-local environment."""
    settings_with_leak = Settings(
        _env_file=None, app_env="production", dev_auth_email="dev@chememan.com"
    )
    with pytest.raises(HTTPException) as exc_info:
        get_current_user_email(x_ms_client_principal_name=None, settings=settings_with_leak)
    assert exc_info.value.status_code == 401


def test_local_without_dev_auth_email_still_401():
    with pytest.raises(HTTPException) as exc_info:
        get_current_user_email(
            x_ms_client_principal_name=None, settings=LOCAL_SETTINGS_NO_OVERRIDE
        )
    assert exc_info.value.status_code == 401


def test_real_header_takes_priority_over_dev_override():
    email = get_current_user_email(
        x_ms_client_principal_name="real.user@chememan.com", settings=LOCAL_SETTINGS
    )
    assert email == "real.user@chememan.com"
