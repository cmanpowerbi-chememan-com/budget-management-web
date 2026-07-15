"""Unit tests for app.notifications — A12 Graph sendMail. No real HTTP ever:
`send_mail`'s only network calls (`_get_graph_token` / `_post_send_mail`) are
monkeypatched at the module level, matching the never-cut safety rule (no
test may send a real email). DB lookups are always a mocked pyodbc connection.
"""
from unittest.mock import MagicMock

import pytest

from app.config import Settings
from app.notifications import (
    NotificationError,
    build_deep_link,
    notify_reject,
    notify_reminder,
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
    assert "&year=2027" in link


def test_build_deep_link_uses_configured_base_url():
    link = build_deep_link("IT", 2028, settings=_settings(app_base_url="https://example.test/"))
    assert link == "https://example.test/?dept=IT&year=2028"


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


def test_notify_turn_no_email_found_skips_without_error(monkeypatch):
    conn = MagicMock()
    conn.cursor.return_value.fetchone.return_value = None
    monkeypatch.setattr("app.notifications.send_mail", lambda *a, **k: pytest.fail("must not be called"))

    result = notify_turn(
        conn, department="Accounting", fiscal_year=2027, approver_empcode="999-unknown",
        submitter_email="filler@chememan.com", dry_run=True, settings=_settings(),
    )
    assert result is None


# ---------------------------------------------------------------------------
# notify_reject — uses the frozen submitter_email directly, no DB lookup
# ---------------------------------------------------------------------------

def test_notify_reject_sends_to_submitter(monkeypatch):
    calls = []
    monkeypatch.setattr("app.notifications.send_mail", lambda *a, **k: calls.append((a, k)) or "SENTINEL")

    result = notify_reject(
        department="Accounting", fiscal_year=2027, submitter_email="filler@chememan.com",
        reason="numbers look wrong", dry_run=True, settings=_settings(),
    )

    assert result == "SENTINEL"
    (to_email, subject, body), kwargs = calls[0]
    assert to_email == "filler@chememan.com"
    assert "numbers look wrong" in body


def test_notify_reject_no_submitter_email_skips(monkeypatch):
    monkeypatch.setattr("app.notifications.send_mail", lambda *a, **k: pytest.fail("must not be called"))
    result = notify_reject(
        department="Accounting", fiscal_year=2027, submitter_email=None,
        reason="bad", dry_run=True, settings=_settings(),
    )
    assert result is None


# ---------------------------------------------------------------------------
# notify_reminder — grouped, one email per Filler, N department lines
# ---------------------------------------------------------------------------

def test_notify_reminder_lists_every_pending_department(monkeypatch):
    calls = []
    monkeypatch.setattr("app.notifications.send_mail", lambda *a, **k: calls.append((a, k)) or "SENTINEL")

    result = notify_reminder(
        "filler@chememan.com", [("Accounting", 2027), ("IT", 2027)], dry_run=True, settings=_settings(),
    )

    assert result == "SENTINEL"
    (to_email, subject, body), kwargs = calls[0]
    assert to_email == "filler@chememan.com"
    assert "Accounting" in body and "IT" in body


def test_notify_reminder_empty_list_skips(monkeypatch):
    monkeypatch.setattr("app.notifications.send_mail", lambda *a, **k: pytest.fail("must not be called"))
    result = notify_reminder("filler@chememan.com", [], dry_run=True, settings=_settings())
    assert result is None
