"""Unit tests for app.logging_config — root logger setup so `app.*` log
records actually reach the container log, instead of being silently
dropped. Root cause: uvicorn only installs handlers on its OWN loggers
("uvicorn", "uvicorn.access") and sets `propagate=False` on both (verified
against the installed uvicorn's `LOGGING_CONFIG`) — it never touches the
root logger, which defaults to WARNING with no handler at all.

Assertions use plain `caplog` (never `caplog.set_level`/`at_level`, which
would override the very level this module is responsible for setting) —
verified empirically that a bare `caplog` fixture faithfully reflects the
root logger's actual configured level, so it exercises real behavior rather
than a re-declared expectation. `capsys`/`capfd` were tried first and
rejected: `app.main` (imported once by conftest.py at collection, before
any test's capture fixture exists) already calls `configure_logging` and
binds its handler to that original `sys.stdout` object, so per-test stream
swapping never observes the write — a stream-identity artifact of testing
here, not of the container.
"""
import logging

import pytest

from app.logging_config import configure_logging


@pytest.fixture(autouse=True)
def _restore_root_logger():
    """The root logger is a process-wide singleton — save/restore its
    handlers and level around every test here so this file never leaks
    logging state into the rest of the suite."""
    root = logging.getLogger()
    original_handlers = list(root.handlers)
    original_level = root.level
    yield
    root.handlers[:] = original_handlers
    root.setLevel(original_level)


def test_configure_logging_lets_info_records_through(caplog):
    configure_logging("INFO")

    logging.getLogger("app.something").info("visible marker line")

    assert any("visible marker line" in r.message for r in caplog.records)


def test_configure_logging_twice_does_not_add_duplicate_handlers():
    """Duplicate handlers on the root logger would print every future line
    twice — assert the handler count is stable across repeated calls."""
    configure_logging("INFO")
    handler_count_after_first_call = len(logging.getLogger().handlers)

    configure_logging("INFO")

    assert len(logging.getLogger().handlers) == handler_count_after_first_call


def test_configure_logging_at_warning_suppresses_info_but_not_warning(caplog):
    """Stands in for the `LOG_LEVEL=WARNING` env override end to end: the
    env value flows into `Settings.log_level` (see test_config.py) and then
    here, into `configure_logging`."""
    configure_logging("WARNING")

    logging.getLogger("app.something").info("suppressed info marker")
    logging.getLogger("app.something").warning("surfaced warning marker")

    messages = [r.message for r in caplog.records]
    assert "suppressed info marker" not in messages
    assert "surfaced warning marker" in messages
