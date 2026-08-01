"""Unit tests for jobs.common — shared CLI/safety scaffolding for the A11
scheduled job (auto_submit) and the A12 reminder job.
"""
import argparse

from jobs.common import add_common_args, is_dry_run


def _parse(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    add_common_args(parser)
    return parser.parse_args(argv)


def test_fiscal_year_is_required():
    import pytest

    with pytest.raises(SystemExit):
        _parse([])


def test_default_is_dry_run_true_with_no_execute_flag(monkeypatch):
    monkeypatch.delenv("DRY_RUN", raising=False)
    args = _parse(["--fiscal-year", "2027"])
    assert is_dry_run(args) is True


def test_execute_flag_alone_is_not_enough_when_env_dry_run_defaults_true(monkeypatch):
    """Never-cut belt-and-braces: DRY_RUN env defaults 'true' even if
    --execute is passed — both must agree to actually write."""
    monkeypatch.delenv("DRY_RUN", raising=False)
    args = _parse(["--fiscal-year", "2027", "--execute"])
    assert is_dry_run(args) is True


def test_execute_flag_plus_explicit_dry_run_false_env_actually_executes(monkeypatch):
    monkeypatch.setenv("DRY_RUN", "false")
    args = _parse(["--fiscal-year", "2027", "--execute"])
    assert is_dry_run(args) is False


def test_no_execute_flag_stays_dry_run_even_if_env_dry_run_false(monkeypatch):
    monkeypatch.setenv("DRY_RUN", "false")
    args = _parse(["--fiscal-year", "2027"])
    assert is_dry_run(args) is True
