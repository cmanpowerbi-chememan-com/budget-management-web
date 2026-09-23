"""Unit tests for app.auth — Easy Auth header extraction + DEV override.

No live DB, no live Entra ID. Calls the dependency function directly. SIT
impersonation tests that need a target set mock `app.auth.get_fabric_conn`
(see `_mock_live_targets`) — no live connection is ever opened.
"""
import logging
from unittest.mock import MagicMock, patch

import pyodbc
import pytest
from fastapi import HTTPException

from app.auth import (
    _apply_sit_impersonation,
    _parse_sit_from_email,
    _select_sit_target,
    clear_sit_targets_cache,
    get_current_user_email,
    live_sit_targets,
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


# --- Permanent production impersonation (ADR-0031, 2026-09-23) ------------
# Supersedes the 2026-08-10/08-17 staging-only design. Two changes:
#
# 1. `SIT_IMPERSONATE` now names ONLY the from-side (who may impersonate).
#    The live prd value still has a trailing ":target1,target2,..." for
#    backward compatibility — everything after the first ':' is IGNORED,
#    no env edit required on deploy (`_parse_sit_from_email`).
# 2. WHO may be impersonated is read live from the DB and TTL-cached
#    (`live_sit_targets`) — every distinct Filler email in
#    `dbo.cc_filler_map` UNION each Filler's
#    `dbo.v_employee_budget_01.manager_email`. Default with no/blank/stale
#    cookie is now the CALLER'S OWN email, never `targets[0]` — jakkaritw is
#    not himself in the live set. DB failures fail CLOSED (self, a WARNING,
#    never an exception) and are never cached.
#
# `app_env != "production"` stays the hard guard; prd deliberately runs
# `app_env=uat`, which is why impersonation is live there by design.

ADMIN_EMAIL = "jakkaritw@chememan.com"
TARGET_1 = "nipapornt@chememan.com"
TARGET_2 = "warapornt@chememan.com"

SIT_SETTINGS = Settings(
    _env_file=None,
    app_env="local",
    admin_emails=ADMIN_EMAIL,
    sit_impersonate=ADMIN_EMAIL,
)


def _mock_live_targets(monkeypatch, emails):
    """Patches `app.auth.get_fabric_conn` so `live_sit_targets` sees `emails`
    without ever opening a real connection. Returns the mock cursor so tests
    can assert on `execute`/`fetchall` call counts."""
    mock_cursor = MagicMock()
    mock_cursor.fetchall.return_value = [(e,) for e in emails]
    mock_conn = MagicMock()
    mock_conn.cursor.return_value = mock_cursor
    mock_ctx = MagicMock()
    mock_ctx.__enter__.return_value = mock_conn
    mock_ctx.__exit__.return_value = False
    monkeypatch.setattr("app.auth.get_fabric_conn", lambda settings=None: mock_ctx)
    return mock_cursor


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (ADMIN_EMAIL, ADMIN_EMAIL),  # bare email, no colon at all — NEW, now valid
        (f"{ADMIN_EMAIL}:{TARGET_1},{TARGET_2}", ADMIN_EMAIL),  # legacy grammar, right side ignored
        (f"{ADMIN_EMAIL}:", ADMIN_EMAIL),  # trailing colon, empty right side
        (f"  {ADMIN_EMAIL}  :{TARGET_1}", ADMIN_EMAIL),  # whitespace around from-side
        ("", None),
        ("   ", None),
        (f":{TARGET_1}", None),  # empty from-side
        (f"   :{TARGET_1}", None),  # whitespace-only from-side
    ],
)
def test_parse_sit_from_email(raw, expected):
    assert _parse_sit_from_email(raw) == expected


def test_sit_impersonation_no_cookie_defaults_to_self_and_never_touches_db(monkeypatch):
    mock_cursor = _mock_live_targets(monkeypatch, [TARGET_1, TARGET_2])
    email = get_current_user_email(
        x_ms_client_principal_name=ADMIN_EMAIL, settings=SIT_SETTINGS, sit_as=None
    )
    assert email == ADMIN_EMAIL
    mock_cursor.execute.assert_not_called()


def test_sit_impersonation_blank_cookie_defaults_to_self(monkeypatch):
    _mock_live_targets(monkeypatch, [TARGET_1, TARGET_2])
    email = get_current_user_email(
        x_ms_client_principal_name=ADMIN_EMAIL, settings=SIT_SETTINGS, sit_as="   "
    )
    assert email == ADMIN_EMAIL


def test_sit_impersonation_cookie_in_live_set_selects_target(monkeypatch):
    _mock_live_targets(monkeypatch, [TARGET_1, TARGET_2])
    email = get_current_user_email(
        x_ms_client_principal_name=ADMIN_EMAIL, settings=SIT_SETTINGS, sit_as=TARGET_2
    )
    assert email == TARGET_2


def test_sit_impersonation_cookie_case_insensitive_match(monkeypatch):
    _mock_live_targets(monkeypatch, [TARGET_1, TARGET_2])
    email = get_current_user_email(
        x_ms_client_principal_name=ADMIN_EMAIL, settings=SIT_SETTINGS, sit_as=TARGET_2.upper()
    )
    assert email == TARGET_2


def test_sit_impersonation_stale_cookie_falls_back_to_self_and_warns(caplog, monkeypatch):
    """A cookie naming someone dropped from the live set (e.g. removed from
    `cc_filler_map`) must fall back to self, not raise, and log a warning."""
    _mock_live_targets(monkeypatch, [TARGET_1, TARGET_2])
    with caplog.at_level(logging.WARNING, logger="app.auth"):
        email = get_current_user_email(
            x_ms_client_principal_name=ADMIN_EMAIL,
            settings=SIT_SETTINGS,
            sit_as="pornthipp@chememan.com",  # was in the old hand-typed list, dropped by ADR-0031
        )
    assert email == ADMIN_EMAIL
    assert any("sit_as" in record.message for record in caplog.records)


def test_sit_impersonation_case_insensitive_match_on_header(monkeypatch):
    _mock_live_targets(monkeypatch, [TARGET_1])
    email = get_current_user_email(
        x_ms_client_principal_name=ADMIN_EMAIL.upper(), settings=SIT_SETTINGS, sit_as=TARGET_1
    )
    assert email == TARGET_1


def test_sit_impersonation_non_matching_header_passthrough():
    email = get_current_user_email(
        x_ms_client_principal_name="somchai.j@chememan.com", settings=SIT_SETTINGS
    )
    assert email == "somchai.j@chememan.com"


def test_sit_impersonation_hard_guard_production_passthrough(monkeypatch):
    """HARD PRD guard: app_env=production must keep the real identity even when
    the caller is an admin, SIT_IMPERSONATE is set, AND a cookie is present."""
    mock_cursor = _mock_live_targets(monkeypatch, [TARGET_1])
    settings_prod = Settings(
        _env_file=None,
        app_env="production",
        admin_emails=ADMIN_EMAIL,
        sit_impersonate=ADMIN_EMAIL,
    )
    email = get_current_user_email(
        x_ms_client_principal_name=ADMIN_EMAIL, settings=settings_prod, sit_as=TARGET_1
    )
    assert email == ADMIN_EMAIL
    mock_cursor.execute.assert_not_called()  # guard fails before any DB touch


def test_sit_impersonation_non_admin_caller_passthrough_even_with_everything_set(monkeypatch):
    """A caller who is NOT in admin_emails_set must never be rewritten, even
    with a matching SIT_IMPERSONATE from_email and a non-production app_env
    — and the guard must fail before ever touching the DB."""
    mock_cursor = _mock_live_targets(monkeypatch, ["target@chememan.com"])
    settings_non_admin = Settings(
        _env_file=None,
        app_env="local",
        admin_emails="",  # only the shared reporting mailbox is admin by default
        sit_impersonate="somchai.j@chememan.com",
    )
    email = get_current_user_email(
        x_ms_client_principal_name="somchai.j@chememan.com",
        settings=settings_non_admin,
        sit_as="target@chememan.com",
    )
    assert email == "somchai.j@chememan.com"
    mock_cursor.execute.assert_not_called()


def test_sit_impersonation_default_empty_is_passthrough():
    email = get_current_user_email(
        x_ms_client_principal_name=ADMIN_EMAIL, settings=PROD_SETTINGS
    )
    assert email == ADMIN_EMAIL


def test_sit_impersonation_blank_sit_impersonate_passthrough_no_crash(monkeypatch):
    _mock_live_targets(monkeypatch, [TARGET_1])
    settings_blank = Settings(
        _env_file=None,
        app_env="local",
        admin_emails=ADMIN_EMAIL,
        sit_impersonate="",
    )
    email = get_current_user_email(
        x_ms_client_principal_name=ADMIN_EMAIL, settings=settings_blank, sit_as=TARGET_1
    )
    assert email == ADMIN_EMAIL


def test_sit_impersonation_never_manufactures_identity_without_header():
    """The alias only ever rewrites an ALREADY-resolved header identity — it
    must never manufacture a login on its own (dev override / 401 untouched)."""
    with pytest.raises(HTTPException) as exc_info:
        get_current_user_email(x_ms_client_principal_name=None, settings=SIT_SETTINGS)
    assert exc_info.value.status_code == 401


def test_sit_impersonation_db_error_falls_back_to_self_never_raises_and_not_cached(
    caplog, monkeypatch
):
    """Fail-closed contract (ADR-0031 item 5): a Fabric hiccup while loading
    the live target set must never raise out of the identity dependency —
    the caller keeps their own identity — and the failure is never cached,
    so the very next request can recover the moment the DB is healthy again."""
    calls = {"n": 0}

    def flaky_get_conn(settings=None):
        calls["n"] += 1
        if calls["n"] == 1:
            raise pyodbc.Error("connection refused")
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = [(TARGET_1,)]
        mock_conn = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        ctx = MagicMock()
        ctx.__enter__.return_value = mock_conn
        ctx.__exit__.return_value = False
        return ctx

    monkeypatch.setattr("app.auth.get_fabric_conn", flaky_get_conn)

    with caplog.at_level(logging.WARNING, logger="app.auth"):
        email = get_current_user_email(
            x_ms_client_principal_name=ADMIN_EMAIL, settings=SIT_SETTINGS, sit_as=TARGET_1
        )
    assert email == ADMIN_EMAIL
    assert any("SIT impersonation target" in record.message for record in caplog.records)

    # Second call, DB now healthy — proves the first failure was NOT cached.
    email2 = get_current_user_email(
        x_ms_client_principal_name=ADMIN_EMAIL, settings=SIT_SETTINGS, sit_as=TARGET_1
    )
    assert email2 == TARGET_1


def test_sit_impersonation_non_pyodbc_exception_also_falls_back_to_self(caplog, monkeypatch):
    """The connection also does an msal token acquisition
    (`app.db._acquire_access_token`) BEFORE pyodbc is ever involved — a
    network failure there raises whatever msal/requests raises, not a
    `pyodbc.Error`. `_live_sit_targets_fail_closed` must catch that too
    (gate finding, 2026-09-23): a narrower `except pyodbc.Error` would 500
    every jakkaritw request while a `sit_as` cookie is set."""
    monkeypatch.setattr(
        "app.auth.get_fabric_conn", MagicMock(side_effect=RuntimeError("msal token acquisition failed"))
    )
    with caplog.at_level(logging.WARNING, logger="app.auth"):
        email = get_current_user_email(
            x_ms_client_principal_name=ADMIN_EMAIL, settings=SIT_SETTINGS, sit_as=TARGET_1
        )
    assert email == ADMIN_EMAIL
    assert any("SIT impersonation target" in record.message for record in caplog.records)


def test_live_sit_targets_cache_hit_avoids_a_second_query(monkeypatch):
    mock_cursor = _mock_live_targets(monkeypatch, [TARGET_1, TARGET_2])
    settings = Settings(
        _env_file=None,
        app_env="local",
        admin_emails=ADMIN_EMAIL,
        sit_impersonate=ADMIN_EMAIL,
        sit_targets_cache_ttl_seconds=600,
    )
    first = live_sit_targets(settings)
    second = live_sit_targets(settings)
    assert first == second == frozenset({TARGET_1, TARGET_2})
    mock_cursor.execute.assert_called_once()


def test_clear_sit_targets_cache_forces_a_fresh_query(monkeypatch):
    mock_cursor = _mock_live_targets(monkeypatch, [TARGET_1])
    settings = Settings(_env_file=None, sit_targets_cache_ttl_seconds=600)
    live_sit_targets(settings)
    clear_sit_targets_cache()
    live_sit_targets(settings)
    assert mock_cursor.execute.call_count == 2


# --- Router/rewrite-gate agreement (kept from the pre-ADR-0031 suite) -----

SECOND_ADMIN_EMAIL = "piyadad@chememan.com"  # a real configured admin, NOT the from_email


def test_non_from_email_admin_passthrough_even_with_sit_as_cookie_present(monkeypatch):
    """A DIFFERENT admin's real login must never be rewritten, even if a
    sit_as cookie happens to be present in their browser (e.g. shared
    staging machine) — and the guard must fail before ever touching the DB."""
    mock_cursor = _mock_live_targets(monkeypatch, [TARGET_1, TARGET_2])
    settings = Settings(
        _env_file=None,
        app_env="local",
        admin_emails=f"{ADMIN_EMAIL},{SECOND_ADMIN_EMAIL}",
        sit_impersonate=ADMIN_EMAIL,
    )
    email = get_current_user_email(
        x_ms_client_principal_name=SECOND_ADMIN_EMAIL, settings=settings, sit_as=TARGET_2
    )
    assert email == SECOND_ADMIN_EMAIL
    mock_cursor.execute.assert_not_called()


@pytest.mark.parametrize(
    ("caller_email", "expect_eligible"),
    [
        (ADMIN_EMAIL, True),  # the configured from_email, also an admin
        (SECOND_ADMIN_EMAIL, False),  # a DIFFERENT configured admin
        ("somchai.j@chememan.com", False),  # not an admin at all
    ],
)
def test_sit_targets_for_narrowed_to_the_configured_from_email(
    caller_email, expect_eligible, monkeypatch
):
    _mock_live_targets(monkeypatch, [TARGET_1, TARGET_2])
    settings = Settings(
        _env_file=None,
        app_env="local",
        admin_emails=f"{ADMIN_EMAIL},{SECOND_ADMIN_EMAIL}",
        sit_impersonate=ADMIN_EMAIL,
    )
    assert (sit_targets_for(caller_email, settings) is not None) == expect_eligible


def test_sit_targets_for_returns_the_sorted_live_set(monkeypatch):
    _mock_live_targets(monkeypatch, [TARGET_2, TARGET_1])  # deliberately unsorted
    settings = Settings(
        _env_file=None, app_env="local", admin_emails=ADMIN_EMAIL, sit_impersonate=ADMIN_EMAIL
    )
    assert sit_targets_for(ADMIN_EMAIL, settings) == sorted([TARGET_1, TARGET_2])


@pytest.mark.parametrize("caller_email", [ADMIN_EMAIL, SECOND_ADMIN_EMAIL, "somchai.j@chememan.com"])
def test_router_gate_and_rewrite_gate_never_disagree(caller_email, monkeypatch):
    """Regression guard for the exact asymmetry the 2026-08-18 gate flagged:
    whatever `sit_targets_for` (router gate) allows must be EXACTLY what
    `_apply_sit_impersonation` (rewrite gate) would actually rewrite (with a
    cookie naming a live target present) — never looser, never stricter."""
    _mock_live_targets(monkeypatch, [TARGET_1, TARGET_2])
    settings = Settings(
        _env_file=None,
        app_env="local",
        admin_emails=f"{ADMIN_EMAIL},{SECOND_ADMIN_EMAIL}",
        sit_impersonate=ADMIN_EMAIL,
    )
    router_allows = sit_targets_for(caller_email, settings) is not None
    rewrite_happens = (
        _apply_sit_impersonation(caller_email, settings, cookie_target=TARGET_1) != caller_email
    )
    assert router_allows == rewrite_happens


# --- Fix 1 support (2026-08-18 gate item 4): pathological `sit_as` cookie
# values must fall back to self, never raise, never grant an out-of-set
# identity.

@pytest.mark.parametrize(
    "pathological_value",
    [
        "a" * 10000 + "@chememan.com",  # very long
        "nipapornt@chememan.com\r\nSet-Cookie: evil=1",  # embedded CR/LF
        "ผู้ทดสอบ🙂@chememan.com",  # non-ASCII / unicode
    ],
)
def test_select_sit_target_pathological_cookie_falls_back_safely(pathological_value):
    result = _select_sit_target(
        [TARGET_1, TARGET_2], pathological_value, self_email=ADMIN_EMAIL
    )
    assert result == ADMIN_EMAIL  # the default — never raises, never the pathological value
