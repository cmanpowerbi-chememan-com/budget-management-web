"""`--scheduled` daily-window decision in jobs.officer_review: a scheduled run
proceeds on Bangkok Friday, or on any day up to and including the planning
year's submission deadline; otherwise it exits 0 without build/publish/mail."""
import sys
from contextlib import contextmanager
from datetime import date
from unittest.mock import MagicMock

import pytest

from jobs import officer_review

FRIDAY = date(2026, 10, 23)
THURSDAY = date(2026, 10, 22)


@pytest.fixture
def harness(monkeypatch):
    h = MagicMock()
    h.deadline = date(2026, 10, 30)
    h.deadline_error = None
    h.today = THURSDAY

    def fake_get_deadline(conn, fy):
        h.deadline_reads(fy)
        if h.deadline_error:
            raise h.deadline_error
        return h.deadline

    @contextmanager
    def fake_conn(settings=None):
        yield object()

    monkeypatch.setattr(officer_review, "configure_logging", lambda: None)
    monkeypatch.setattr(officer_review, "install_email_redaction", lambda: None)
    monkeypatch.setattr(officer_review, "_quiet_httpx_logger", lambda: None)
    monkeypatch.setattr(officer_review, "get_settings", lambda: object())
    monkeypatch.setattr(officer_review, "_today", lambda: h.today)
    monkeypatch.setattr(officer_review, "get_deadline_date", fake_get_deadline)
    monkeypatch.setattr(officer_review, "get_fabric_conn", fake_conn)
    monkeypatch.setattr(officer_review, "run_build", lambda **kw: (h.build(**kw), 0)[1])
    monkeypatch.setattr(officer_review, "run_probe", lambda s: (h.probe(), 0)[1])
    return h


def _run(monkeypatch, *extra):
    monkeypatch.setattr(sys, "argv", ["officer_review", "--fiscal-year", "2027", *extra])
    return officer_review.main()


def test_friday_proceeds_without_deadline_read(harness, monkeypatch, caplog):
    harness.today = FRIDAY
    caplog.set_level("INFO")
    assert _run(monkeypatch, "--scheduled") == 0
    harness.build.assert_called_once()
    harness.deadline_reads.assert_not_called()
    assert "WINDOW: proceed" in caplog.text


@pytest.mark.parametrize("deadline", [date(2026, 10, 22), date(2026, 10, 23)])
def test_thursday_up_to_deadline_inclusive_proceeds(harness, monkeypatch, caplog, deadline):
    harness.deadline = deadline
    caplog.set_level("INFO")
    assert _run(monkeypatch, "--scheduled") == 0
    harness.build.assert_called_once()
    harness.deadline_reads.assert_called_once_with(2027)
    assert "WINDOW: proceed" in caplog.text


def test_day_after_deadline_skips(harness, monkeypatch, caplog):
    harness.deadline = date(2026, 10, 21)
    caplog.set_level("INFO")
    assert _run(monkeypatch, "--scheduled") == 0
    harness.build.assert_not_called()
    assert "WINDOW: skip" in caplog.text


def test_no_deadline_row_skips(harness, monkeypatch, caplog):
    harness.deadline = None
    caplog.set_level("INFO")
    assert _run(monkeypatch, "--scheduled") == 0
    harness.build.assert_not_called()
    assert "WINDOW: skip" in caplog.text


def test_deadline_read_error_skips_with_warning(harness, monkeypatch, caplog):
    harness.deadline_error = RuntimeError("secret-host-detail")
    caplog.set_level("INFO")
    assert _run(monkeypatch, "--scheduled") == 0
    harness.build.assert_not_called()
    assert "could not read deadline (RuntimeError)" in caplog.text
    assert "secret-host-detail" not in caplog.text


def test_without_scheduled_never_reads_deadline(harness, monkeypatch):
    harness.deadline = date(2020, 1, 1)
    assert _run(monkeypatch) == 0
    harness.build.assert_called_once()
    harness.deadline_reads.assert_not_called()
