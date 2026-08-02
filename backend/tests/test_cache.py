"""Unit tests for app.cache — the generic TTL cache backing the SAP gold-read
caching (perf fix, prod first-load 10-11s -> 2-3s). Pure/no DB: `loader()` is
a plain callable the tests control directly.
"""
from app.cache import TTLCache


def test_second_call_within_ttl_does_not_call_loader_again():
    calls = {"n": 0}

    def loader():
        calls["n"] += 1
        return "value"

    cache = TTLCache()
    assert cache.get_or_load("key", 600, loader) == "value"
    assert cache.get_or_load("key", 600, loader) == "value"
    assert calls["n"] == 1


def test_call_after_ttl_expiry_reloads(monkeypatch):
    calls = {"n": 0}
    fake_now = {"t": 1000.0}

    def loader():
        calls["n"] += 1
        return calls["n"]

    monkeypatch.setattr("app.cache.time.monotonic", lambda: fake_now["t"])

    cache = TTLCache()
    assert cache.get_or_load("key", 10, loader) == 1
    fake_now["t"] += 5  # still within TTL
    assert cache.get_or_load("key", 10, loader) == 1
    fake_now["t"] += 10  # now past TTL (>= 10s since the first load)
    assert cache.get_or_load("key", 10, loader) == 2
    assert calls["n"] == 2


def test_ttl_zero_disables_caching_every_call_queries():
    calls = {"n": 0}

    def loader():
        calls["n"] += 1
        return calls["n"]

    cache = TTLCache()
    assert cache.get_or_load("key", 0, loader) == 1
    assert cache.get_or_load("key", 0, loader) == 2
    assert cache.get_or_load("key", 0, loader) == 3
    assert calls["n"] == 3


def test_different_keys_do_not_collide():
    calls = {"n": 0}

    def loader():
        calls["n"] += 1
        return calls["n"]

    cache = TTLCache()
    assert cache.get_or_load(2026, 600, loader) == 1
    assert cache.get_or_load(2027, 600, loader) == 2
    # Each key still cached independently.
    assert cache.get_or_load(2026, 600, loader) == 1
    assert cache.get_or_load(2027, 600, loader) == 2
    assert calls["n"] == 2


def test_a_raised_exception_is_never_cached_next_call_reloads_and_succeeds():
    calls = {"n": 0}

    def flaky_loader():
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("DW unreachable")
        return "recovered"

    cache = TTLCache()
    try:
        cache.get_or_load("key", 600, flaky_loader)
        assert False, "expected RuntimeError to propagate"
    except RuntimeError:
        pass

    assert cache.get_or_load("key", 600, flaky_loader) == "recovered"
    assert calls["n"] == 2


def test_success_then_a_later_failure_after_expiry_raises_not_a_stale_hit(monkeypatch):
    """Never-cut (ADR-0020/0026): once the TTL has expired, a failed reload
    must raise straight to the caller — it must NOT fall back to serving the
    old (now stale) cached value."""
    fake_now = {"t": 0.0}
    calls = {"n": 0}

    def loader():
        calls["n"] += 1
        if calls["n"] == 1:
            return "first-success"
        raise RuntimeError("grant revoked")

    monkeypatch.setattr("app.cache.time.monotonic", lambda: fake_now["t"])

    cache = TTLCache()
    assert cache.get_or_load("key", 10, loader) == "first-success"
    fake_now["t"] += 20  # past TTL
    try:
        cache.get_or_load("key", 10, loader)
        assert False, "expected RuntimeError to propagate, not a stale hit"
    except RuntimeError:
        pass
    assert calls["n"] == 2


def test_clear_removes_all_entries_forcing_a_reload():
    calls = {"n": 0}

    def loader():
        calls["n"] += 1
        return calls["n"]

    cache = TTLCache()
    assert cache.get_or_load("key", 600, loader) == 1
    cache.clear()
    assert cache.get_or_load("key", 600, loader) == 2
    assert calls["n"] == 2
