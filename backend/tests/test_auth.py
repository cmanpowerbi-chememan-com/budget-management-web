"""Unit tests for app.auth — Easy Auth header extraction + DEV override.

No live DB, no live Entra ID. Calls the dependency function directly.
"""
import logging

import pytest
from fastapi import HTTPException

from app.auth import (
    _apply_sit_impersonation,
    _select_sit_target,
    get_current_user_email,
    sit_targets_for,
)
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
# rewrites his resolved identity to one of the configured target emails,
# AFTER the header is trusted, so RLS/approval/notifications see the
# impersonated person exactly like the old spoof-header technique — just
# behind real login.
#
# GUARD REDESIGN (2026-08-17): staging now removes
# NOTIFICATIONS_ENVIRONMENT_LABEL entirely so SIT mail looks byte-identical
# to production (no test banner/subject prefix) — see .claude/plan.md. That
# label can therefore no longer be this guard's condition 2. Replaced with
# an admin-caller check ("jakkarit แทน all admin" — jakkaritw, 2026-08-17):
# any of the 4 configured admins may use SIT impersonation, not only the
# literal `from_email` in SIT_IMPERSONATE. The three conditions, ALL
# required: (1) HARD app_env != "production" (unchanged, absolute, checked
# first); (2) NEW — the resolved caller email is in
# `settings.admin_emails_set`; (3) `sit_impersonate` set and well-formed.
#
# GRAMMAR (2026-08-17): extended from a single "from:to" pair to
# "from:target1[,target2,...]", staying backward compatible with the old
# single-target form. Default target = targets[0]; a `sit_as` cookie value
# matching one of the configured targets overrides the default for that
# browser session (see app.routers.sit); an unknown cookie value falls back
# to targets[0] and logs a warning.
#
# stg runs APP_ENV=local (verified 2026-08-10), so the "applies" cases below
# use app_env="local" to mirror the real staging environment.

ADMIN_EMAIL = "jakkaritw@chememan.com"
TARGET_1 = "nipapornt@chememan.com"
TARGET_2 = "warapornt@chememan.com"

SIT_SETTINGS = Settings(
    _env_file=None,
    app_env="local",
    admin_emails=ADMIN_EMAIL,
    sit_impersonate=f"{ADMIN_EMAIL}:{TARGET_1},{TARGET_2}",
)


def test_sit_impersonation_default_target_is_the_first_one_no_cookie():
    email = get_current_user_email(
        x_ms_client_principal_name=ADMIN_EMAIL, settings=SIT_SETTINGS, sit_as=None
    )
    assert email == TARGET_1


def test_sit_impersonation_cookie_selects_second_target():
    email = get_current_user_email(
        x_ms_client_principal_name=ADMIN_EMAIL, settings=SIT_SETTINGS, sit_as=TARGET_2
    )
    assert email == TARGET_2


def test_sit_impersonation_unknown_cookie_falls_back_to_default_and_warns(caplog):
    with caplog.at_level(logging.WARNING, logger="app.auth"):
        email = get_current_user_email(
            x_ms_client_principal_name=ADMIN_EMAIL,
            settings=SIT_SETTINGS,
            sit_as="nobody@chememan.com",
        )
    assert email == TARGET_1
    assert any("sit_as" in record.message for record in caplog.records)


def test_sit_impersonation_case_insensitive_match_on_header():
    email = get_current_user_email(
        x_ms_client_principal_name=ADMIN_EMAIL.upper(), settings=SIT_SETTINGS, sit_as=None
    )
    assert email == TARGET_1


def test_sit_impersonation_non_matching_header_passthrough():
    email = get_current_user_email(
        x_ms_client_principal_name="somchai.j@chememan.com", settings=SIT_SETTINGS
    )
    assert email == "somchai.j@chememan.com"


def test_sit_impersonation_hard_guard_production_passthrough():
    """HARD PRD guard: app_env=production must keep the real identity even when
    the caller is an admin AND the alias is set — the copy-pasted-env
    disaster case. This is the primary defense the security review asked for."""
    settings_prod = Settings(
        _env_file=None,
        app_env="production",
        admin_emails=ADMIN_EMAIL,
        sit_impersonate=f"{ADMIN_EMAIL}:{TARGET_1}",
    )
    email = get_current_user_email(
        x_ms_client_principal_name=ADMIN_EMAIL, settings=settings_prod
    )
    assert email == ADMIN_EMAIL


def test_sit_impersonation_non_admin_caller_passthrough_even_with_everything_set():
    """NEW condition 2: a caller who is NOT in admin_emails_set must never be
    rewritten, even with a matching SIT_IMPERSONATE from_email and a
    non-production app_env."""
    settings_non_admin = Settings(
        _env_file=None,
        app_env="local",
        admin_emails="",  # only the shared reporting mailbox is admin by default
        sit_impersonate="somchai.j@chememan.com:target@chememan.com",
    )
    email = get_current_user_email(
        x_ms_client_principal_name="somchai.j@chememan.com", settings=settings_non_admin
    )
    assert email == "somchai.j@chememan.com"


def test_sit_impersonation_blank_environment_label_no_longer_disables_it():
    """INVERTS the pre-2026-08-17 contract (was
    test_sit_impersonation_ignored_when_environment_label_blank): staging now
    removes NOTIFICATIONS_ENVIRONMENT_LABEL so SIT mail is byte-identical to
    production, so a blank label must NOT block impersonation any more —
    only admin-caller + non-prod + SIT_IMPERSONATE now gate it."""
    settings_no_label = Settings(
        _env_file=None,
        app_env="local",
        admin_emails=ADMIN_EMAIL,
        sit_impersonate=f"{ADMIN_EMAIL}:{TARGET_1}",
        notifications_environment_label="",
    )
    email = get_current_user_email(
        x_ms_client_principal_name=ADMIN_EMAIL, settings=settings_no_label, sit_as=None
    )
    assert email == TARGET_1


def test_sit_impersonation_default_empty_is_passthrough():
    email = get_current_user_email(
        x_ms_client_principal_name=ADMIN_EMAIL, settings=PROD_SETTINGS
    )
    assert email == ADMIN_EMAIL


@pytest.mark.parametrize(
    "raw_value",
    [
        ADMIN_EMAIL,  # no colon at all
        f":{TARGET_1}",  # empty from-side
        f"{ADMIN_EMAIL}:",  # empty to-side
    ],
)
def test_sit_impersonation_malformed_values_passthrough_no_crash(raw_value):
    settings_malformed = Settings(
        _env_file=None,
        app_env="local",
        admin_emails=ADMIN_EMAIL,
        sit_impersonate=raw_value,
    )
    email = get_current_user_email(
        x_ms_client_principal_name=ADMIN_EMAIL, settings=settings_malformed
    )
    assert email == ADMIN_EMAIL


def test_sit_impersonation_backward_compat_single_target_still_works():
    """The pre-multi-target grammar ("from:to", no comma) must keep working
    unchanged."""
    settings_single = Settings(
        _env_file=None,
        app_env="local",
        admin_emails=ADMIN_EMAIL,
        sit_impersonate=f"{ADMIN_EMAIL}:pornthipp@chememan.com",
    )
    email = get_current_user_email(
        x_ms_client_principal_name=ADMIN_EMAIL, settings=settings_single, sit_as=None
    )
    assert email == "pornthipp@chememan.com"


def test_sit_impersonation_never_manufactures_identity_without_header():
    """The alias only ever rewrites an ALREADY-resolved header identity — it
    must never manufacture a login on its own (dev override / 401 untouched)."""
    with pytest.raises(HTTPException) as exc_info:
        get_current_user_email(x_ms_client_principal_name=None, settings=SIT_SETTINGS)
    assert exc_info.value.status_code == 401


# --- Fix 2 (2026-08-18 gate): router gate narrowed to the configured
# from_email, matching the rewrite gate exactly — "any configured admin"
# was too loose; only the literal `SIT_IMPERSONATE` from_email may actually
# use impersonation, admin-ness is a necessary-but-not-sufficient condition.

SECOND_ADMIN_EMAIL = "piyadad@chememan.com"  # a real configured admin, NOT the from_email


def test_non_from_email_admin_passthrough_even_with_sit_as_cookie_present():
    """A DIFFERENT admin's real login must never be rewritten, even if a
    sit_as cookie happens to be present in their browser (e.g. shared
    staging machine)."""
    settings = Settings(
        _env_file=None,
        app_env="local",
        admin_emails=f"{ADMIN_EMAIL},{SECOND_ADMIN_EMAIL}",
        sit_impersonate=f"{ADMIN_EMAIL}:{TARGET_1},{TARGET_2}",
    )
    email = get_current_user_email(
        x_ms_client_principal_name=SECOND_ADMIN_EMAIL, settings=settings, sit_as=TARGET_2
    )
    assert email == SECOND_ADMIN_EMAIL


@pytest.mark.parametrize(
    ("caller_email", "expect_eligible"),
    [
        (ADMIN_EMAIL, True),  # the configured from_email, also an admin
        (SECOND_ADMIN_EMAIL, False),  # a DIFFERENT configured admin
        ("somchai.j@chememan.com", False),  # not an admin at all
    ],
)
def test_sit_targets_for_narrowed_to_the_configured_from_email(caller_email, expect_eligible):
    settings = Settings(
        _env_file=None,
        app_env="local",
        admin_emails=f"{ADMIN_EMAIL},{SECOND_ADMIN_EMAIL}",
        sit_impersonate=f"{ADMIN_EMAIL}:{TARGET_1},{TARGET_2}",
    )
    assert (sit_targets_for(caller_email, settings) is not None) == expect_eligible


@pytest.mark.parametrize("caller_email", [ADMIN_EMAIL, SECOND_ADMIN_EMAIL, "somchai.j@chememan.com"])
def test_router_gate_and_rewrite_gate_never_disagree(caller_email):
    """Regression guard for the exact asymmetry the 2026-08-18 gate flagged:
    whatever `sit_targets_for` (router gate) allows must be EXACTLY what
    `_apply_sit_impersonation` (rewrite gate) would actually rewrite — never
    looser, never stricter."""
    settings = Settings(
        _env_file=None,
        app_env="local",
        admin_emails=f"{ADMIN_EMAIL},{SECOND_ADMIN_EMAIL}",
        sit_impersonate=f"{ADMIN_EMAIL}:{TARGET_1},{TARGET_2}",
    )
    router_allows = sit_targets_for(caller_email, settings) is not None
    rewrite_happens = _apply_sit_impersonation(caller_email, settings) != caller_email
    assert router_allows == rewrite_happens


# --- Fix 1 support (2026-08-18 gate item 4): pathological `sit_as` cookie
# values must fall back to the default target, never raise, never grant an
# out-of-allowlist identity.

@pytest.mark.parametrize(
    "pathological_value",
    [
        "a" * 10000 + "@chememan.com",  # very long
        "nipapornt@chememan.com\r\nSet-Cookie: evil=1",  # embedded CR/LF
        "ผู้ทดสอบ🙂@chememan.com",  # non-ASCII / unicode
    ],
)
def test_select_sit_target_pathological_cookie_falls_back_safely(pathological_value):
    result = _select_sit_target([TARGET_1, TARGET_2], pathological_value)
    assert result == TARGET_1  # the default — never raises, never the pathological value
