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
    notify_turn,
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
    assert send_kwargs["headers"]["Authorization"] == "Bearer tok-123"
    assert send_kwargs["json"]["message"]["toRecipients"][0]["emailAddress"]["address"] == "someone@chememan.com"


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

    # posts = [token1, sendMail1, token2, sendMail2]
    assert "ccRecipients" not in posts[1][1]["json"]["message"]
    assert "ccRecipients" not in posts[3][1]["json"]["message"]


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
# notify_deadline_reminder — ONE email per (department, filler), 2026-07-31
# revamp replacing the grouped per-filler notify_reminder
# ---------------------------------------------------------------------------

def test_notify_deadline_reminder_single_department_with_cc_and_link(monkeypatch):
    calls = []
    monkeypatch.setattr("app.notifications.send_mail", lambda *a, **k: calls.append((a, k)) or "SENTINEL")

    result = notify_deadline_reminder(
        "filler@chememan.com", "Accounting", 2027, date(2026, 8, 31),
        cc_emails=["vp@chememan.com"], dry_run=True, settings=_settings(),
    )

    assert result == "SENTINEL"
    (to_email, subject, body), kwargs = calls[0]
    assert to_email == "filler@chememan.com"
    assert kwargs["cc"] == ["vp@chememan.com"]
    assert "Accounting" in subject
    link = build_deep_link("Accounting", 2027, settings=_settings())
    assert link in body  # deep link carries THIS department + label year (ADR-0016)
    assert "2027" in body and "Year 2026" in body
    assert "2026" in body  # closing date rendered


def test_notify_deadline_reminder_no_filler_email_skips(monkeypatch):
    monkeypatch.setattr("app.notifications.send_mail", lambda *a, **k: pytest.fail("must not be called"))
    result = notify_deadline_reminder(
        "", "Accounting", 2027, date(2026, 8, 31), cc_emails=[], dry_run=True, settings=_settings(),
    )
    assert result is None
