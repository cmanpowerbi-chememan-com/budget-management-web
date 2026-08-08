"""Unit tests for app.notifications — A12 Graph sendMail. No real HTTP ever:
`send_mail`'s only network calls (`_get_graph_token` / `_post_send_mail`) are
monkeypatched at the module level, matching the never-cut safety rule (no
test may send a real email). DB lookups are always a mocked pyodbc connection.
"""
from datetime import date
from unittest.mock import MagicMock

import pytest

from app.config import Settings
from app.notifications import (
    NotificationError,
    build_deep_link,
    notify_approved,
    notify_deadline_reminder,
    notify_reject,
    notify_step_overridden,
    notify_turn,
    notify_turn_reminder,
    send_mail,
)


def _settings(**overrides) -> Settings:
    defaults = dict(
        _env_file=None,
        entra_tenant_id="tenant-1",
        entra_client_id="client-1",
        entra_client_secret="secret-1",
        app_base_url="https://budget.chememan.com",
    )
    defaults.update(overrides)
    return Settings(**defaults)


@pytest.fixture(autouse=True)
def _reset_graph_token_cache():
    """The module-level Graph token cache (§7.3 bulk-send hardening) must
    never leak between tests — a cached token from one test would silently
    skip the token POST another test counts on."""
    from app import notifications

    notifications._reset_graph_token_cache()
    yield
    notifications._reset_graph_token_cache()


# ---------------------------------------------------------------------------
# build_deep_link
# ---------------------------------------------------------------------------

def test_build_deep_link_url_encodes_thai_and_slash():
    link = build_deep_link("บัญชี/การเงิน", 2027, settings=_settings())
    assert link.startswith("https://budget.chememan.com/?dept=")
    assert "%2F" in link  # the '/' inside the department name is encoded
    assert "&year=2026" in link  # URL carries the LABEL year (planning - 1)


def test_build_deep_link_uses_configured_base_url():
    link = build_deep_link("IT", 2028, settings=_settings(app_base_url="https://example.test/"))
    assert link == "https://example.test/?dept=IT&year=2027"  # label year = planning - 1


def test_build_deep_link_label_year_round_trips_with_frontend_parser():
    """Round-trip invariant with `frontend/src/filters/deepLink.ts`
    `parseYear`: this emits `year=<planning - 1>` (the label year); the
    frontend parser adds 1 back, returning the same planning year again."""
    for planning_year in (2025, 2027, 2030):
        link = build_deep_link("Accounting", planning_year, settings=_settings())
        assert f"&year={planning_year - 1}" in link


# ---------------------------------------------------------------------------
# send_mail — the one transport seam
# ---------------------------------------------------------------------------

def test_send_mail_dry_run_makes_zero_http_calls(monkeypatch):
    calls = []
    monkeypatch.setattr("app.notifications.httpx.post", lambda *a, **k: calls.append((a, k)))

    result = send_mail("someone@chememan.com", "subject", "<p>body</p>", dry_run=True, settings=_settings())

    assert result.sent is False
    assert result.dry_run is True
    assert calls == []  # zero HTTP calls in dry-run — never-cut


def test_send_mail_no_recipient_skips_without_error():
    result = send_mail("", "subject", "<p>body</p>", dry_run=True, settings=_settings())
    assert result.sent is False
    assert result.detail == "no recipient"


def test_send_mail_real_send_posts_token_then_sendmail(monkeypatch):
    posts = []

    def _fake_post(url, **kwargs):
        posts.append((url, kwargs))
        resp = MagicMock()
        if "oauth2" in url:
            resp.status_code = 200
            resp.json.return_value = {"access_token": "tok-123"}
        else:
            resp.status_code = 202
        return resp

    monkeypatch.setattr("app.notifications.httpx.post", _fake_post)

    result = send_mail("someone@chememan.com", "subject", "<p>body</p>", dry_run=False, settings=_settings())

    assert result.sent is True
    assert len(posts) == 2
    token_url, token_kwargs = posts[0]
    assert "oauth2/v2.0/token" in token_url
    assert token_kwargs["data"]["client_id"] == "client-1"
    send_url, send_kwargs = posts[1]
    assert "/sendMail" in send_url
    # The FROM mailbox is the settings value, not a hardcoded personal inbox
    # (2026-08-02: jakkaritw@ -> cmanpowerbi@, the shared reporting mailbox).
    assert "/users/cmanpowerbi@chememan.com/sendMail" in send_url
    assert send_kwargs["headers"]["Authorization"] == "Bearer tok-123"
    assert send_kwargs["json"]["message"]["toRecipients"][0]["emailAddress"]["address"] == "someone@chememan.com"


def test_send_mail_sender_mailbox_comes_from_settings(monkeypatch):
    """`notifications_sender_email` drives the sendMail URL, so the FROM
    mailbox can be re-pointed by env alone (no code change, no redeploy of
    a hardcoded constant)."""
    posts = []

    def _fake_post(url, **kwargs):
        posts.append(url)
        resp = MagicMock()
        if "oauth2" in url:
            resp.status_code = 200
            resp.json.return_value = {"access_token": "tok-123"}
        else:
            resp.status_code = 202
        return resp

    monkeypatch.setattr("app.notifications.httpx.post", _fake_post)

    send_mail(
        "someone@chememan.com", "subject", "<p>body</p>", dry_run=False,
        settings=_settings(notifications_sender_email="budget-noreply@chememan.com"),
    )

    assert "/users/budget-noreply@chememan.com/sendMail" in posts[1]


def test_send_mail_token_failure_raises_notification_error(monkeypatch):
    def _fake_post(url, **kwargs):
        resp = MagicMock()
        resp.status_code = 401
        resp.text = "invalid client"
        return resp

    monkeypatch.setattr("app.notifications.httpx.post", _fake_post)

    with pytest.raises(NotificationError):
        send_mail("someone@chememan.com", "subject", "<p>body</p>", dry_run=False, settings=_settings())


def test_send_mail_sendmail_failure_raises_notification_error(monkeypatch):
    def _fake_post(url, **kwargs):
        resp = MagicMock()
        if "oauth2" in url:
            resp.status_code = 200
            resp.json.return_value = {"access_token": "tok-123"}
        else:
            resp.status_code = 400
            resp.text = "bad request"
        return resp

    monkeypatch.setattr("app.notifications.httpx.post", _fake_post)

    with pytest.raises(NotificationError):
        send_mail("someone@chememan.com", "subject", "<p>body</p>", dry_run=False, settings=_settings())


def test_send_mail_includes_cc_recipients_when_cc_given(monkeypatch):
    """2026-07-31 revamp: `cc` lands in the Graph payload as ccRecipients."""
    posts = []

    def _fake_post(url, **kwargs):
        posts.append((url, kwargs))
        resp = MagicMock()
        if "oauth2" in url:
            resp.status_code = 200
            resp.json.return_value = {"access_token": "tok-123"}
        else:
            resp.status_code = 202
        return resp

    monkeypatch.setattr("app.notifications.httpx.post", _fake_post)

    result = send_mail(
        "someone@chememan.com", "subject", "<p>body</p>",
        cc=["vp@chememan.com", "boss@chememan.com"], dry_run=False, settings=_settings(),
    )

    assert result.sent is True
    message = posts[1][1]["json"]["message"]
    cc_addresses = [r["emailAddress"]["address"] for r in message["ccRecipients"]]
    assert cc_addresses == ["vp@chememan.com", "boss@chememan.com"]


def test_send_mail_omits_cc_recipients_key_when_no_cc(monkeypatch):
    """No cc -> the key must be ABSENT entirely (Graph treats an empty
    ccRecipients array differently from a missing one on some tenants)."""
    posts = []

    def _fake_post(url, **kwargs):
        posts.append((url, kwargs))
        resp = MagicMock()
        if "oauth2" in url:
            resp.status_code = 200
            resp.json.return_value = {"access_token": "tok-123"}
        else:
            resp.status_code = 202
        return resp

    monkeypatch.setattr("app.notifications.httpx.post", _fake_post)

    send_mail("someone@chememan.com", "subject", "<p>body</p>", cc=None, dry_run=False, settings=_settings())
    send_mail("someone@chememan.com", "subject", "<p>body</p>", cc=[], dry_run=False, settings=_settings())

    # posts = [token1, sendMail1, sendMail2] — the token is cached (§7.3.1),
    # so the second send has no token POST of its own.
    assert "ccRecipients" not in posts[1][1]["json"]["message"]
    assert "ccRecipients" not in posts[2][1]["json"]["message"]


# ---------------------------------------------------------------------------
# notify_turn — resolves an empcode to an email via dbo.v_employee_budget_01
# ---------------------------------------------------------------------------

def test_notify_turn_resolves_email_and_sends_dry_run(monkeypatch):
    conn = MagicMock()
    conn.cursor.return_value.fetchone.return_value = ("manager@chememan.com",)
    calls = []
    monkeypatch.setattr("app.notifications.send_mail", lambda *a, **k: calls.append((a, k)) or "SENTINEL")

    result = notify_turn(
        conn, department="Accounting", fiscal_year=2027, approver_empcode="200",
        submitter_email="filler@chememan.com", dry_run=True, settings=_settings(),
    )

    assert result == "SENTINEL"
    (to_email, subject, body), kwargs = calls[0]
    assert to_email == "manager@chememan.com"
    assert "Accounting" in subject or "Accounting" in body
    assert kwargs["dry_run"] is True


def test_notify_turn_subject_format_and_body_shows_both_years(monkeypatch):
    """Subject = status-first short form with the planning year only
    (2026-07-28 user-requested format). Body keeps the gate residual fix:
    recipient must see the SAME year the on-screen YearPicker shows
    (label = planning - 1), alongside the correct planning year, so the
    two never look contradictory."""
    conn = MagicMock()
    conn.cursor.return_value.fetchone.return_value = ("manager@chememan.com",)
    calls = []
    monkeypatch.setattr("app.notifications.send_mail", lambda *a, **k: calls.append((a, k)) or "SENTINEL")

    notify_turn(
        conn, department="Accounting", fiscal_year=2027, approver_empcode="200",
        submitter_email="filler@chememan.com", dry_run=True, settings=_settings(),
    )

    (to_email, subject, body), kwargs = calls[0]
    assert subject == "รอการอนุมัติ งบประมาณของฝ่าย Accounting ปีงบประมาณ 2027"
    assert "2027" in body
    assert "Year 2026" in body


def test_notify_turn_no_email_found_skips_without_error(monkeypatch):
    conn = MagicMock()
    conn.cursor.return_value.fetchone.return_value = None
    monkeypatch.setattr("app.notifications.send_mail", lambda *a, **k: pytest.fail("must not be called"))

    result = notify_turn(
        conn, department="Accounting", fiscal_year=2027, approver_empcode="999-unknown",
        submitter_email="filler@chememan.com", dry_run=True, settings=_settings(),
    )
    assert result is None


def test_notify_turn_reminder_mode_prefixes_subject_and_shows_days_pending(monkeypatch):
    """2026-07-31 revamp: reminder=True is the 7-day repeat nudge — subject
    prefixed '[เตือน]', body states how many days the turn has been pending."""
    conn = MagicMock()
    conn.cursor.return_value.fetchone.return_value = ("manager@chememan.com",)
    calls = []
    monkeypatch.setattr("app.notifications.send_mail", lambda *a, **k: calls.append((a, k)) or "SENTINEL")

    notify_turn(
        conn, department="Accounting", fiscal_year=2027, approver_empcode="200",
        submitter_email="filler@chememan.com", reminder=True, days_pending=9,
        dry_run=True, settings=_settings(),
    )

    (to_email, subject, body), kwargs = calls[0]
    assert to_email == "manager@chememan.com"
    assert subject.startswith("[เตือน]")
    assert "Accounting" in subject
    assert "9 วัน" in body


def test_notify_turn_default_mode_has_no_reminder_prefix(monkeypatch):
    """The initial landed-on-your-step mail stays unchanged (no [เตือน])."""
    conn = MagicMock()
    conn.cursor.return_value.fetchone.return_value = ("manager@chememan.com",)
    calls = []
    monkeypatch.setattr("app.notifications.send_mail", lambda *a, **k: calls.append((a, k)) or "SENTINEL")

    notify_turn(
        conn, department="Accounting", fiscal_year=2027, approver_empcode="200",
        submitter_email="filler@chememan.com", dry_run=True, settings=_settings(),
    )

    (_, subject, _), _ = calls[0]
    assert not subject.startswith("[เตือน]")


# ---------------------------------------------------------------------------
# notify_reject — uses the frozen submitter_email directly, no DB lookup
# ---------------------------------------------------------------------------

def test_notify_reject_sends_to_submitter(monkeypatch):
    calls = []
    monkeypatch.setattr("app.notifications.send_mail", lambda *a, **k: calls.append((a, k)) or "SENTINEL")

    result = notify_reject(
        MagicMock(), department="Accounting", fiscal_year=2027, submitter_email="filler@chememan.com",
        reason="numbers look wrong", approver1_empcode=None, dry_run=True, settings=_settings(),
    )

    assert result == "SENTINEL"
    (to_email, subject, body), kwargs = calls[0]
    assert to_email == "filler@chememan.com"
    assert "numbers look wrong" in body
    assert kwargs["cc"] is None  # no approver1 empcode -> no cc


def test_notify_reject_subject_format_and_body_shows_both_years(monkeypatch):
    calls = []
    monkeypatch.setattr("app.notifications.send_mail", lambda *a, **k: calls.append((a, k)) or "SENTINEL")

    notify_reject(
        MagicMock(), department="Accounting", fiscal_year=2027, submitter_email="filler@chememan.com",
        reason="numbers look wrong", approver1_empcode=None, dry_run=True, settings=_settings(),
    )

    (to_email, subject, body), kwargs = calls[0]
    assert subject == "ถูกตีกลับ งบประมาณของฝ่าย Accounting ปีงบประมาณ 2027"
    assert "2027" in body
    assert "Year 2026" in body


def test_notify_reject_no_submitter_email_skips(monkeypatch):
    monkeypatch.setattr("app.notifications.send_mail", lambda *a, **k: pytest.fail("must not be called"))
    result = notify_reject(
        MagicMock(), department="Accounting", fiscal_year=2027, submitter_email=None,
        reason="bad", approver1_empcode=None, dry_run=True, settings=_settings(),
    )
    assert result is None


def test_notify_reject_ccs_approver1_email(monkeypatch):
    """2026-07-31 revamp: reject (any layer) goes To the submitter, cc the
    frozen approver1's email (resolved via dbo.v_employee_budget_01)."""
    conn = MagicMock()
    conn.cursor.return_value.fetchone.return_value = ("vp@chememan.com",)
    calls = []
    monkeypatch.setattr("app.notifications.send_mail", lambda *a, **k: calls.append((a, k)) or "SENTINEL")

    notify_reject(
        conn, department="Accounting", fiscal_year=2027, submitter_email="filler@chememan.com",
        reason="bad", approver1_empcode="200", dry_run=True, settings=_settings(),
    )

    (to_email, subject, body), kwargs = calls[0]
    assert to_email == "filler@chememan.com"
    assert kwargs["cc"] == ["vp@chememan.com"]


def test_notify_reject_skips_cc_when_same_as_submitter(monkeypatch):
    """cc == To would duplicate the mail — skipped (plan §3.1)."""
    conn = MagicMock()
    conn.cursor.return_value.fetchone.return_value = ("filler@chememan.com",)
    calls = []
    monkeypatch.setattr("app.notifications.send_mail", lambda *a, **k: calls.append((a, k)) or "SENTINEL")

    notify_reject(
        conn, department="Accounting", fiscal_year=2027, submitter_email="filler@chememan.com",
        reason="bad", approver1_empcode="200", dry_run=True, settings=_settings(),
    )

    (to_email, subject, body), kwargs = calls[0]
    assert to_email == "filler@chememan.com"
    assert kwargs["cc"] is None


def test_notify_reject_still_sends_to_submitter_when_cc_lookup_fails(monkeypatch):
    """A broken cc lookup must NEVER block the main To send (plan §3.1)."""
    conn = MagicMock()
    conn.cursor.return_value.execute.side_effect = RuntimeError("db down")
    calls = []
    monkeypatch.setattr("app.notifications.send_mail", lambda *a, **k: calls.append((a, k)) or "SENTINEL")

    result = notify_reject(
        conn, department="Accounting", fiscal_year=2027, submitter_email="filler@chememan.com",
        reason="bad", approver1_empcode="200", dry_run=True, settings=_settings(),
    )

    assert result == "SENTINEL"
    (to_email, subject, body), kwargs = calls[0]
    assert to_email == "filler@chememan.com"
    assert kwargs["cc"] is None


# ---------------------------------------------------------------------------
# notify_approved — final-APPROVED confirmation, uses the frozen
# submitter_email directly, no DB lookup (same pattern as notify_reject)
# ---------------------------------------------------------------------------

def test_notify_approved_sends_to_submitter(monkeypatch):
    calls = []
    monkeypatch.setattr("app.notifications.send_mail", lambda *a, **k: calls.append((a, k)) or "SENTINEL")

    result = notify_approved(
        MagicMock(), department="Accounting", fiscal_year=2027, submitter_email="filler@chememan.com",
        approver1_empcode=None, dry_run=True, settings=_settings(),
    )

    assert result == "SENTINEL"
    (to_email, subject, body), kwargs = calls[0]
    assert to_email == "filler@chememan.com"
    assert subject == "ได้รับการอนุมัติ งบประมาณของฝ่าย Accounting ปีงบประมาณ 2027"
    link = build_deep_link("Accounting", 2027, settings=_settings())
    assert link in body
    assert kwargs["dry_run"] is True
    assert kwargs["cc"] is None


def test_notify_approved_body_shows_both_planning_and_label_year(monkeypatch):
    calls = []
    monkeypatch.setattr("app.notifications.send_mail", lambda *a, **k: calls.append((a, k)) or "SENTINEL")

    notify_approved(
        MagicMock(), department="Accounting", fiscal_year=2027, submitter_email="filler@chememan.com",
        approver1_empcode=None, dry_run=True, settings=_settings(),
    )

    (to_email, subject, body), kwargs = calls[0]
    assert "2027" in body
    assert "Year 2026" in body


def test_notify_approved_no_submitter_email_skips(monkeypatch):
    monkeypatch.setattr("app.notifications.send_mail", lambda *a, **k: pytest.fail("must not be called"))
    result = notify_approved(
        MagicMock(), department="Accounting", fiscal_year=2027, submitter_email=None,
        approver1_empcode=None, dry_run=True, settings=_settings(),
    )
    assert result is None


def test_notify_approved_dry_run_makes_zero_http_calls(monkeypatch):
    calls = []
    monkeypatch.setattr("app.notifications.httpx.post", lambda *a, **k: calls.append((a, k)))

    notify_approved(
        MagicMock(), department="Accounting", fiscal_year=2027, submitter_email="filler@chememan.com",
        approver1_empcode=None, dry_run=True, settings=_settings(),
    )

    assert calls == []  # zero HTTP calls in dry-run — never-cut


def test_notify_approved_ccs_approver1_email(monkeypatch):
    """2026-07-31 revamp: final approve goes To the submitter, cc the frozen
    approver1's email (resolved via dbo.v_employee_budget_01)."""
    conn = MagicMock()
    conn.cursor.return_value.fetchone.return_value = ("vp@chememan.com",)
    calls = []
    monkeypatch.setattr("app.notifications.send_mail", lambda *a, **k: calls.append((a, k)) or "SENTINEL")

    notify_approved(
        conn, department="Accounting", fiscal_year=2027, submitter_email="filler@chememan.com",
        approver1_empcode="200", dry_run=True, settings=_settings(),
    )

    (to_email, subject, body), kwargs = calls[0]
    assert to_email == "filler@chememan.com"
    assert kwargs["cc"] == ["vp@chememan.com"]


def test_notify_approved_skips_cc_when_same_as_submitter(monkeypatch):
    conn = MagicMock()
    conn.cursor.return_value.fetchone.return_value = ("Filler@chememan.com",)  # case-insensitive == To
    calls = []
    monkeypatch.setattr("app.notifications.send_mail", lambda *a, **k: calls.append((a, k)) or "SENTINEL")

    notify_approved(
        conn, department="Accounting", fiscal_year=2027, submitter_email="filler@chememan.com",
        approver1_empcode="200", dry_run=True, settings=_settings(),
    )

    (to_email, subject, body), kwargs = calls[0]
    assert kwargs["cc"] is None


def test_notify_approved_still_sends_to_submitter_when_cc_lookup_fails(monkeypatch):
    """A broken cc lookup must NEVER block the main To send (plan §3.1)."""
    conn = MagicMock()
    conn.cursor.return_value.execute.side_effect = RuntimeError("db down")
    calls = []
    monkeypatch.setattr("app.notifications.send_mail", lambda *a, **k: calls.append((a, k)) or "SENTINEL")

    result = notify_approved(
        conn, department="Accounting", fiscal_year=2027, submitter_email="filler@chememan.com",
        approver1_empcode="200", dry_run=True, settings=_settings(),
    )

    assert result == "SENTINEL"
    (to_email, subject, body), kwargs = calls[0]
    assert to_email == "filler@chememan.com"
    assert kwargs["cc"] is None


# ---------------------------------------------------------------------------
# notify_step_overridden — 6th notification (ADR-0027): To the frozen
# submitter, cc the SKIPPED position-1 approver (same skip rules as
# _resolve_approver1_cc), fired by the admin step-override
# ---------------------------------------------------------------------------

def test_notify_step_overridden_sends_to_submitter_ccs_skipped_approver(monkeypatch):
    conn = MagicMock()
    conn.cursor.return_value.fetchone.return_value = ("vp@chememan.com",)
    calls = []
    monkeypatch.setattr("app.notifications.send_mail", lambda *a, **k: calls.append((a, k)) or "SENTINEL")

    result = notify_step_overridden(
        conn, department="Accounting", fiscal_year=2027, submitter_email="filler@chememan.com",
        skipped_approver_empcode="200", admin_email="jakkaritw@chememan.com",
        dry_run=True, settings=_settings(),
    )

    assert result == "SENTINEL"
    (to_email, subject, _), kwargs = calls[0]
    assert to_email == "filler@chememan.com"
    assert subject == "ดำเนินการแทนผู้อนุมัติ งบประมาณของฝ่าย Accounting ปีงบประมาณ 2027"
    assert kwargs["cc"] == ["vp@chememan.com"]
    assert kwargs["dry_run"] is True


def test_notify_step_overridden_drops_cc_when_unresolvable_same_as_to_or_blank(monkeypatch):
    """Same cc skip rules as notify_reject/notify_approved: unresolvable,
    cc == To, or a blank empcode all drop the cc — never the To send."""
    calls = []
    monkeypatch.setattr("app.notifications.send_mail", lambda *a, **k: calls.append((a, k)) or "SENTINEL")

    conn = MagicMock()
    conn.cursor.return_value.fetchone.return_value = None  # lookup finds nothing
    result = notify_step_overridden(
        conn, department="Accounting", fiscal_year=2027, submitter_email="filler@chememan.com",
        skipped_approver_empcode="999-unknown", admin_email="jakkaritw@chememan.com",
        dry_run=True, settings=_settings(),
    )
    assert result == "SENTINEL"
    assert calls[0][1]["cc"] is None

    conn2 = MagicMock()
    conn2.cursor.return_value.fetchone.return_value = ("Filler@chememan.com",)  # case-insensitive == To
    notify_step_overridden(
        conn2, department="Accounting", fiscal_year=2027, submitter_email="filler@chememan.com",
        skipped_approver_empcode="200", admin_email="jakkaritw@chememan.com",
        dry_run=True, settings=_settings(),
    )
    assert calls[1][1]["cc"] is None

    notify_step_overridden(
        MagicMock(), department="Accounting", fiscal_year=2027, submitter_email="filler@chememan.com",
        skipped_approver_empcode=None, admin_email="jakkaritw@chememan.com",
        dry_run=True, settings=_settings(),
    )
    assert calls[2][1]["cc"] is None


def test_notify_step_overridden_still_sends_to_submitter_when_cc_lookup_fails(monkeypatch):
    """A broken cc lookup must NEVER block the main To send (same posture as
    the 2026-07-31 revamp cc rules)."""
    conn = MagicMock()
    conn.cursor.return_value.execute.side_effect = RuntimeError("db down")
    calls = []
    monkeypatch.setattr("app.notifications.send_mail", lambda *a, **k: calls.append((a, k)) or "SENTINEL")

    result = notify_step_overridden(
        conn, department="Accounting", fiscal_year=2027, submitter_email="filler@chememan.com",
        skipped_approver_empcode="200", admin_email="jakkaritw@chememan.com",
        dry_run=True, settings=_settings(),
    )

    assert result == "SENTINEL"
    (to_email, _, _), kwargs = calls[0]
    assert to_email == "filler@chememan.com"
    assert kwargs["cc"] is None


def test_notify_step_overridden_body_carries_department_year_both_names_and_link(monkeypatch):
    conn = MagicMock()
    conn.cursor.return_value.fetchone.return_value = ("vp@chememan.com",)
    calls = []
    monkeypatch.setattr("app.notifications.send_mail", lambda *a, **k: calls.append((a, k)) or "SENTINEL")

    notify_step_overridden(
        conn, department="Accounting", fiscal_year=2027, submitter_email="filler@chememan.com",
        skipped_approver_empcode="200", admin_email="jakkaritw@chememan.com",
        dry_run=True, settings=_settings(), new_current_approver_empcode="101032",
    )

    (_, _, body), _ = calls[0]
    assert "Accounting" in body
    assert "2027" in body and "Year 2026" in body  # planning + on-screen label year
    assert "vp@chememan.com" in body  # ผู้อนุมัติที่ถูกข้าม
    assert "jakkaritw@chememan.com" in body  # ผู้ดำเนินการแทน
    assert build_deep_link("Accounting", 2027, settings=_settings()) in body


def test_notify_step_overridden_still_sends_when_next_approver_lookup_fails(monkeypatch):
    """Review fix: `lookup_email_by_empcode` for the NEXT approver (feeds
    only the cosmetic สถานะปัจจุบัน body row) must NEVER prevent the To send
    -- same posture as the cc lookup. Bug 5 (2026-08-08): body degrades to
    the Thai placeholder, never the raw empcode."""
    conn = MagicMock()

    def _execute(sql, *args, **kwargs):
        # Calls 1-2 resolve the SKIPPED approver empcode "200" (cc, then the
        # independent display lookup for the same empcode) and succeed; call
        # 3 is the NEXT approver lookup (สถานะปัจจุบัน only) -- this one fails.
        if conn.cursor.return_value.execute.call_count > 2:
            raise RuntimeError("db down")

    conn.cursor.return_value.execute.side_effect = _execute
    conn.cursor.return_value.fetchone.return_value = ("vp@chememan.com",)
    calls = []
    monkeypatch.setattr("app.notifications.send_mail", lambda *a, **k: calls.append((a, k)) or "SENTINEL")

    result = notify_step_overridden(
        conn, department="Accounting", fiscal_year=2027, submitter_email="filler@chememan.com",
        skipped_approver_empcode="200", admin_email="jakkaritw@chememan.com",
        dry_run=True, settings=_settings(), new_current_approver_empcode="101032",
    )

    assert result == "SENTINEL"  # the To send still went out
    (to_email, _, body), kwargs = calls[0]
    assert to_email == "filler@chememan.com"
    assert kwargs["cc"] == ["vp@chememan.com"]  # cc lookup (first call) was unaffected
    assert "101032" not in body  # the raw empcode must never reach the body
    assert "(ไม่พบชื่อ)" in body  # degrades to the agreed Thai placeholder instead


def test_notify_step_overridden_unresolvable_skipped_approver_shows_placeholder_not_raw_code(monkeypatch):
    """Bug 5 (2026-08-07 production defect): a probe's fake empcode
    ('TESTPROBE') rendered verbatim in the delivered mail's ผู้อนุมัติที่ถูกข้าม
    row. The same fallback fires in production for a leaver or a mid-sync
    gap -- an unresolvable empcode must show the agreed Thai placeholder,
    and the raw code must not appear anywhere in the body (not merely
    alongside the placeholder)."""
    conn = MagicMock()
    conn.cursor.return_value.fetchone.return_value = None  # lookup finds no record
    calls = []
    monkeypatch.setattr("app.notifications.send_mail", lambda *a, **k: calls.append((a, k)) or "SENTINEL")

    notify_step_overridden(
        conn, department="Accounting", fiscal_year=2027, submitter_email="filler@chememan.com",
        skipped_approver_empcode="TESTPROBE", admin_email="jakkaritw@chememan.com",
        dry_run=True, settings=_settings(),
    )

    (_, _, body), _ = calls[0]
    assert "TESTPROBE" not in body
    assert "(ไม่พบชื่อ)" in body


def test_notify_step_overridden_resolved_skipped_approver_display_unchanged(monkeypatch):
    """Happy path regression: a resolved empcode renders exactly as before
    the fix -- the resolved email, never the placeholder."""
    conn = MagicMock()
    conn.cursor.return_value.fetchone.return_value = ("vp@chememan.com",)
    calls = []
    monkeypatch.setattr("app.notifications.send_mail", lambda *a, **k: calls.append((a, k)) or "SENTINEL")

    notify_step_overridden(
        conn, department="Accounting", fiscal_year=2027, submitter_email="filler@chememan.com",
        skipped_approver_empcode="200", admin_email="jakkaritw@chememan.com",
        dry_run=True, settings=_settings(),
    )

    (_, _, body), _ = calls[0]
    assert "vp@chememan.com" in body
    assert "(ไม่พบชื่อ)" not in body


def test_notify_step_overridden_no_submitter_email_skips(monkeypatch):
    monkeypatch.setattr("app.notifications.send_mail", lambda *a, **k: pytest.fail("must not be called"))
    result = notify_step_overridden(
        MagicMock(), department="Accounting", fiscal_year=2027, submitter_email=None,
        skipped_approver_empcode="200", admin_email="jakkaritw@chememan.com",
        dry_run=True, settings=_settings(),
    )
    assert result is None


# ---------------------------------------------------------------------------
# notify_deadline_reminder — §7 rework: ONE grouped email per FILLER, table
# of every still-not-submitted department with its own deep link per row
# ---------------------------------------------------------------------------

def test_notify_deadline_reminder_grouped_46_departments_one_mail(monkeypatch):
    """§7.4.1: a filler with 46 pending departments gets ONE mail whose body
    carries 46 rows and 46 per-department deep links; cc = one address."""
    departments = [f"Dept{i:02d}" for i in range(46)]
    calls = []
    monkeypatch.setattr("app.notifications.send_mail", lambda *a, **k: calls.append((a, k)) or "SENTINEL")

    result = notify_deadline_reminder(
        "filler@chememan.com", departments, 2027, date(2026, 8, 31),
        cc_emails=["vp@chememan.com"], dry_run=True, settings=_settings(),
    )

    assert result == "SENTINEL"
    assert len(calls) == 1
    (to_email, subject, body), kwargs = calls[0]
    assert to_email == "filler@chememan.com"
    assert kwargs["cc"] == ["vp@chememan.com"]
    for dept in departments:
        assert dept in body  # 46 rows
        assert build_deep_link(dept, 2027, settings=_settings()) in body  # 46 links


def test_notify_deadline_reminder_single_department_same_template(monkeypatch):
    """§7.4.2: a single-department filler gets the SAME grouped template —
    no special single-department branch."""
    calls = []
    monkeypatch.setattr("app.notifications.send_mail", lambda *a, **k: calls.append((a, k)) or "SENTINEL")

    result = notify_deadline_reminder(
        "filler@chememan.com", ["Accounting"], 2027, date(2026, 8, 31),
        cc_emails=["vp@chememan.com"], dry_run=True, settings=_settings(),
    )

    assert result == "SENTINEL"
    (to_email, subject, body), kwargs = calls[0]
    assert to_email == "filler@chememan.com"
    assert kwargs["cc"] == ["vp@chememan.com"]
    assert "Accounting" in body
    assert build_deep_link("Accounting", 2027, settings=_settings()) in body
    assert "2027" in body and "Year 2026" in body
    assert "2026" in body  # closing date rendered


def test_notify_deadline_reminder_no_filler_email_skips(monkeypatch):
    monkeypatch.setattr("app.notifications.send_mail", lambda *a, **k: pytest.fail("must not be called"))
    result = notify_deadline_reminder(
        "", ["Accounting"], 2027, date(2026, 8, 31), cc_emails=[], dry_run=True, settings=_settings(),
    )
    assert result is None


def test_notify_deadline_reminder_empty_department_list_skips(monkeypatch):
    monkeypatch.setattr("app.notifications.send_mail", lambda *a, **k: pytest.fail("must not be called"))
    result = notify_deadline_reminder(
        "filler@chememan.com", [], 2027, date(2026, 8, 31), cc_emails=[], dry_run=True, settings=_settings(),
    )
    assert result is None


# ---------------------------------------------------------------------------
# notify_turn_reminder — §7 rework: ONE grouped email per APPROVER, table of
# every department waiting on them with per-row days-pending
# ---------------------------------------------------------------------------

def test_notify_turn_reminder_groups_departments_with_days_pending(monkeypatch):
    """§7.4.3: an approver with N departments waiting gets ONE mail, N rows,
    each row carrying that department's own days-pending."""
    conn = MagicMock()
    conn.cursor.return_value.fetchone.return_value = ("manager@chememan.com",)
    calls = []
    monkeypatch.setattr("app.notifications.send_mail", lambda *a, **k: calls.append((a, k)) or "SENTINEL")

    result = notify_turn_reminder(
        conn, approver_empcode="200",
        items=[("Accounting", 2027, 9), ("IT", 2027, 3)],
        dry_run=True, settings=_settings(),
    )

    assert result == "SENTINEL"
    assert len(calls) == 1
    (to_email, subject, body), kwargs = calls[0]
    assert to_email == "manager@chememan.com"
    assert subject.startswith("[เตือน]")
    assert "Accounting" in body and "9 วัน" in body
    assert "IT" in body and "3 วัน" in body
    assert build_deep_link("Accounting", 2027, settings=_settings()) in body
    assert build_deep_link("IT", 2027, settings=_settings()) in body


def test_notify_turn_reminder_no_email_found_skips_without_error(monkeypatch):
    conn = MagicMock()
    conn.cursor.return_value.fetchone.return_value = None
    monkeypatch.setattr("app.notifications.send_mail", lambda *a, **k: pytest.fail("must not be called"))

    result = notify_turn_reminder(
        conn, approver_empcode="999-unknown", items=[("Accounting", 2027, 9)],
        dry_run=True, settings=_settings(),
    )
    assert result is None


# ---------------------------------------------------------------------------
# §7.3 bulk-send hardening — token cache, retry on 429/503/504
# ---------------------------------------------------------------------------

def test_send_mail_fetches_graph_token_once_for_n_sends(monkeypatch):
    """§7.4.5: the module-level token cache means N sends in one round cost
    ONE token request, not N."""
    token_calls = []
    monkeypatch.setattr(
        "app.notifications._get_graph_token",
        lambda settings: token_calls.append(1) or "tok-cached",
    )
    posts = []
    monkeypatch.setattr("app.notifications._post_send_mail", lambda *a, **k: posts.append(a) or 0)

    for i in range(3):
        result = send_mail(f"u{i}@chememan.com", "s", "<p>b</p>", dry_run=False, settings=_settings())
        assert result.sent is True

    assert len(token_calls) == 1
    assert len(posts) == 3


def test_send_mail_token_cache_refresh_after_expiry(monkeypatch):
    """Cache honors expiry: a token with <60s left is refreshed, never used stale."""
    token_calls = []
    monkeypatch.setattr(
        "app.notifications._get_graph_token",
        lambda settings: token_calls.append(1) or f"tok-{len(token_calls)}",
    )
    monkeypatch.setattr("app.notifications._post_send_mail", lambda *a, **k: 0)

    send_mail("u@chememan.com", "s", "<p>b</p>", dry_run=False, settings=_settings())
    assert len(token_calls) == 1
    # Force the cached token to be effectively expired (<60s remaining).
    from app import notifications

    notifications._token_cache["expires_at"] = 0.0
    send_mail("u@chememan.com", "s", "<p>b</p>", dry_run=False, settings=_settings())
    assert len(token_calls) == 2


def _retrying_post(responses, posts):
    """Build an httpx.post fake replaying `responses` (list of (status, headers)) in order."""
    it = iter(responses)

    def _fake_post(url, **kwargs):
        posts.append(url)
        status, headers = next(it)
        resp = MagicMock()
        resp.status_code = status
        resp.headers = headers
        resp.text = f"status {status}"
        resp.json.return_value = {"access_token": "tok-1"}
        return resp

    return _fake_post


def test_send_mail_retries_429_honoring_retry_after_header(monkeypatch):
    """§7.4.6: 429 + Retry-After: 5 -> sleep(5) then a successful retry."""
    monkeypatch.setattr("app.notifications._get_graph_token", lambda settings: "tok-1")
    posts = []
    monkeypatch.setattr(
        "app.notifications.httpx.post", _retrying_post([(429, {"Retry-After": "5"}), (202, {})], posts)
    )
    sleeps = []

    result = send_mail(
        "u@chememan.com", "s", "<p>b</p>", dry_run=False, settings=_settings(), sleep=sleeps.append
    )

    assert result.sent is True
    assert result.retries == 1
    assert sleeps == [5.0]
    assert len(posts) == 2  # one retry, no token refetch


def test_send_mail_retries_503_with_backoff_when_no_retry_after(monkeypatch):
    monkeypatch.setattr("app.notifications._get_graph_token", lambda settings: "tok-1")
    posts = []
    monkeypatch.setattr("app.notifications.httpx.post", _retrying_post([(503, {}), (202, {})], posts))
    sleeps = []

    result = send_mail(
        "u@chememan.com", "s", "<p>b</p>", dry_run=False, settings=_settings(), sleep=sleeps.append
    )

    assert result.sent is True
    assert sleeps == [2]  # first backoff step


def test_send_mail_429_three_times_raises_and_reports_attempts(monkeypatch):
    """§7.4.7: 429 on all 3 attempts (initial + 2 retries) -> NotificationError,
    the caller's per-recipient isolation treats it as failed."""
    monkeypatch.setattr("app.notifications._get_graph_token", lambda settings: "tok-1")
    posts = []
    monkeypatch.setattr(
        "app.notifications.httpx.post",
        _retrying_post([(429, {}), (429, {}), (429, {})], posts),
    )
    sleeps = []

    with pytest.raises(NotificationError):
        send_mail("u@chememan.com", "s", "<p>b</p>", dry_run=False, settings=_settings(), sleep=sleeps.append)

    assert len(posts) == 3  # exactly 3 attempts, no more
    assert sleeps == [2, 8]  # backoff steps between them


def test_send_mail_non_retryable_status_fails_immediately(monkeypatch):
    """A 400 is not transient — no retry, no sleep, fail at once."""
    monkeypatch.setattr("app.notifications._get_graph_token", lambda settings: "tok-1")
    posts = []
    monkeypatch.setattr("app.notifications.httpx.post", _retrying_post([(400, {})], posts))
    sleeps = []

    with pytest.raises(NotificationError):
        send_mail("u@chememan.com", "s", "<p>b</p>", dry_run=False, settings=_settings(), sleep=sleeps.append)

    assert len(posts) == 1
    assert sleeps == []
