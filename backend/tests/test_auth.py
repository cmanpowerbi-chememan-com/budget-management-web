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


# --- SIT impersonation alias (staging test aid) ---------------------------
# jakkaritw has no row in dbo.v_employee_budget_01 and cannot be an approver,
# but real Easy Auth on staging cannot be header-spoofed. SIT_IMPERSONATE
# rewrites his resolved identity to a real approver's email, AFTER the
# header is trusted, so RLS/approval/notifications see the impersonated
# person exactly like the old spoof-header technique — just behind real
# login. Guarded by THREE conditions (all required): app_env != production
# (the hard PRD guard), a non-blank notifications_environment_label, and the
# alias itself — so a copy-pasted env var can never activate on PRD.
#
# stg runs APP_ENV=local (verified 2026-08-10), so the "applies" cases below
# use app_env="local" to mirror the real staging environment.

SIT_SETTINGS = Settings(
    _env_file=None,
    app_env="local",
    sit_impersonate="jakkaritw@chememan.com:pornthipp@chememan.com",
    notifications_environment_label="ทดสอบ on stg server",
)


def test_sit_impersonation_alias_applies_on_match():
    email = get_current_user_email(
        x_ms_client_principal_name="jakkaritw@chememan.com", settings=SIT_SETTINGS
    )
    assert email == "pornthipp@chememan.com"


def test_sit_impersonation_case_insensitive_match():
    email = get_current_user_email(
        x_ms_client_principal_name="JAKKARITW@Chememan.com", settings=SIT_SETTINGS
    )
    assert email == "pornthipp@chememan.com"


def test_sit_impersonation_non_matching_header_passthrough():
    email = get_current_user_email(
        x_ms_client_principal_name="somchai.j@chememan.com", settings=SIT_SETTINGS
    )
    assert email == "somchai.j@chememan.com"


def test_sit_impersonation_hard_guard_production_passthrough():
    """HARD PRD guard: app_env=production must keep the real identity even when
    BOTH the alias AND the environment label are set — the copy-pasted-env
    disaster case. This is the primary defense the security review asked for."""
    settings_prod = Settings(
        _env_file=None,
        app_env="production",
        sit_impersonate="jakkaritw@chememan.com:pornthipp@chememan.com",
        notifications_environment_label="ทดสอบ on stg server",
    )
    email = get_current_user_email(
        x_ms_client_principal_name="jakkaritw@chememan.com", settings=settings_prod
    )
    assert email == "jakkaritw@chememan.com"


def test_sit_impersonation_ignored_when_environment_label_blank():
    """Second guard: SIT_IMPERSONATE alone (no environment label set) must
    never activate, even in a non-production env."""
    settings_no_label = Settings(
        _env_file=None,
        app_env="local",
        sit_impersonate="jakkaritw@chememan.com:pornthipp@chememan.com",
        notifications_environment_label="",
    )
    email = get_current_user_email(
        x_ms_client_principal_name="jakkaritw@chememan.com", settings=settings_no_label
    )
    assert email == "jakkaritw@chememan.com"


def test_sit_impersonation_default_empty_is_passthrough():
    email = get_current_user_email(
        x_ms_client_principal_name="jakkaritw@chememan.com", settings=PROD_SETTINGS
    )
    assert email == "jakkaritw@chememan.com"


@pytest.mark.parametrize(
    "raw_value",
    [
        "jakkaritw@chememan.com",  # no colon at all
        ":pornthipp@chememan.com",  # empty from-side
        "jakkaritw@chememan.com:",  # empty to-side
    ],
)
def test_sit_impersonation_malformed_values_passthrough_no_crash(raw_value):
    settings_malformed = Settings(
        _env_file=None,
        app_env="local",
        sit_impersonate=raw_value,
        notifications_environment_label="ทดสอบ on stg server",
    )
    email = get_current_user_email(
        x_ms_client_principal_name="jakkaritw@chememan.com", settings=settings_malformed
    )
    assert email == "jakkaritw@chememan.com"


def test_sit_impersonation_never_manufactures_identity_without_header():
    """The alias only ever rewrites an ALREADY-resolved header identity — it
    must never manufacture a login on its own (dev override / 401 untouched)."""
    with pytest.raises(HTTPException) as exc_info:
        get_current_user_email(x_ms_client_principal_name=None, settings=SIT_SETTINGS)
    assert exc_info.value.status_code == 401
