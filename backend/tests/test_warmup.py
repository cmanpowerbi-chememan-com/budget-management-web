"""Unit tests for the startup warmup path (app.main) — Fix 3: connection-pool
+ SAP-cache warmup at startup. Perf fix: live-measured on PRD, the FIRST
request in each worker process pays fabric conn open 2.86s + gold conn open
2.01s (vs 0.70s / 1.45s warm) plus the uncached SAP reads; warming at startup
moves that cost off the first real user. Must never block startup (runs on a
daemon thread) or crash it (any exception is only logged).

Calls `main._run_warmup` / `main._start_warmup_if_enabled` directly rather
than going through `TestClient(app)`'s lifespan, so these stay fast and
deterministic (conftest's hermetic fixture already forces
`WARMUP_ENABLED=false` for the `client` fixture — see conftest.py).
"""
from datetime import date
from unittest.mock import MagicMock

import pyodbc
import pytest

from app import main


def test_warmup_disabled_touches_nothing(monkeypatch):
    """warmup_enabled=False -> no connection factory call at all."""
    monkeypatch.setattr(main, "get_settings", lambda: MagicMock(warmup_enabled=False))
    fabric_mock = MagicMock()
    gold_mock = MagicMock()
    monkeypatch.setattr(main, "get_fabric_conn", fabric_mock)
    monkeypatch.setattr(main, "get_gold_conn", gold_mock)

    main._start_warmup_if_enabled()

    fabric_mock.assert_not_called()
    gold_mock.assert_not_called()


@pytest.mark.parametrize("db_error", [pyodbc.Error("connection refused"), Exception("boom")])
def test_warmup_never_raises_when_db_unreachable(monkeypatch, db_error):
    monkeypatch.setattr(main, "get_fabric_conn", MagicMock(side_effect=db_error))
    monkeypatch.setattr(main, "get_gold_conn", MagicMock())

    main._run_warmup()  # must return normally, never propagate


def test_warmup_happy_path_opens_conns_and_primes_both_sap_caches(monkeypatch):
    fabric_mock = MagicMock()
    gold_mock = MagicMock()
    actuals_mock = MagicMock()
    coverage_mock = MagicMock()
    monkeypatch.setattr(main, "get_fabric_conn", fabric_mock)
    monkeypatch.setattr(main, "get_gold_conn", gold_mock)
    monkeypatch.setattr(main, "fetch_sap_actuals_cached", actuals_mock)
    monkeypatch.setattr(main, "resolve_sap_coverage_cached", coverage_mock)

    main._run_warmup()

    # ADR-0020 amendment 2026-08-11: fetch_sap_actuals_cached now also needs
    # fabric_conn (dbo.hide_document read), so fabric_conn is opened twice —
    # once for pool warm-up alone, once alongside gold_conn for cache
    # priming — same tolerant-count pattern already used for gold_mock.
    assert fabric_mock.call_count >= 1
    assert gold_mock.call_count >= 1

    board_year = date.today().year
    actuals_mock.assert_called_once()
    coverage_mock.assert_called_once()
    assert actuals_mock.call_args.kwargs.get("fiscal_year") == board_year
    assert coverage_mock.call_args.kwargs.get("fiscal_year") == board_year


def test_startup_spawns_daemon_thread_not_inline(monkeypatch):
    """Startup must not block: the entrypoint spawns a thread rather than
    running the warmup body on the calling thread."""
    monkeypatch.setattr(main, "get_settings", lambda: MagicMock(warmup_enabled=True))
    run_warmup_mock = MagicMock()
    monkeypatch.setattr(main, "_run_warmup", run_warmup_mock)

    started_threads = []

    class _FakeThread:
        def __init__(self, target=None, daemon=None):
            self.target = target
            self.daemon = daemon
            self.started = False
            started_threads.append(self)

        def start(self):
            self.started = True  # deliberately does NOT call self.target

    monkeypatch.setattr(main.threading, "Thread", _FakeThread)

    main._start_warmup_if_enabled()

    assert len(started_threads) == 1
    assert started_threads[0].daemon is True
    assert started_threads[0].started is True
    run_warmup_mock.assert_not_called()  # real work never ran on the calling thread
