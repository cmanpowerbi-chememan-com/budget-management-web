"""Unit tests for jobs.auto_submit — A11 scheduled job. DB always mocked
(one shared `conn.cursor.return_value` cursor, matching the app-level test
convention); `app.notifications.notify_turn` is always monkeypatched so no
test can trigger a real Graph call.
"""
from unittest.mock import MagicMock, patch

import pytest

from app.config import Settings
from jobs.auto_submit import _find_true_draft_departments, run


def _flag_on() -> Settings:
    """GL edit_by admin-only lock (design v2, ADR-0024) flag ON, for tests
    exercising that path — never mutates the process-wide cached
    get_settings()."""
    return Settings(_env_file=None, gl_edit_by_enabled=True)


def test_not_yet_post_deadline_does_nothing(monkeypatch):
    conn = MagicMock()
    with patch("jobs.auto_submit.get_fabric_conn") as mock_conn, patch(
        "jobs.auto_submit.is_post_deadline", return_value=False
    ), patch("jobs.auto_submit.auto_submit_department") as mock_submit:
        mock_conn.return_value.__enter__.return_value = conn
        result = run(fiscal_year=2027, dry_run=False, notifications_dry_run=True)

    assert result == 0
    mock_submit.assert_not_called()


def test_find_true_draft_departments_parses_rows():
    conn = MagicMock()
    conn.cursor.return_value.fetchall.return_value = [("Accounting", "editor@chememan.com"), ("IT", "other@chememan.com")]
    result = _find_true_draft_departments(conn, 2027)
    assert result == [("Accounting", "editor@chememan.com"), ("IT", "other@chememan.com")]


def test_find_true_draft_departments_no_exclusion_query_is_unchanged():
    """Default (no exclude_gl_codes, flag OFF): the query text carries no
    GL-exclusion clause at all — byte-identical to before ADR-0024's
    exclusion existed."""
    conn = MagicMock()
    conn.cursor.return_value.fetchall.return_value = []
    _find_true_draft_departments(conn, 2027)
    sql_text = conn.cursor.return_value.execute.call_args.args[0]
    assert "gl_account" not in sql_text
    assert conn.cursor.return_value.execute.call_args.args[1:] == (2027,)


def test_find_true_draft_departments_excludes_admin_gl_rows_from_both_subqueries():
    """GL edit_by admin-only lock (ADR-0024): the exclusion must reach BOTH
    the candidate row `p` and the correlated MAX(_updated_at) subquery `p2`
    — otherwise an admin-GL edit could still win the "most recent" pick even
    if the final SELECTed row itself were filtered."""
    conn = MagicMock()
    conn.cursor.return_value.fetchall.return_value = []
    _find_true_draft_departments(conn, 2027, exclude_gl_codes=frozenset({"GL1", "GL2"}))
    call = conn.cursor.return_value.execute.call_args
    sql_text = call.args[0]
    assert sql_text.count("gl_account NOT IN (?, ?)") == 2  # once for p, once for p2
    assert "p.gl_account NOT IN" in sql_text
    assert "p2.gl_account NOT IN" in sql_text
    params = call.args[1:]
    assert params[0] == 2027
    assert set(params[1:]) == {"GL1", "GL2"}  # fiscal_year + 2x(GL1,GL2), order-independent
    assert len(params) == 5  # fiscal_year + 2 codes (p) + 2 codes (p2)


def test_dry_run_lists_candidates_without_submitting():
    conn = MagicMock()
    conn.cursor.return_value.fetchall.return_value = [("Accounting", "editor@chememan.com")]
    with patch("jobs.auto_submit.get_fabric_conn") as mock_conn, patch(
        "jobs.auto_submit.is_post_deadline", return_value=True
    ), patch("jobs.auto_submit.auto_submit_department") as mock_submit:
        mock_conn.return_value.__enter__.return_value = conn
        result = run(fiscal_year=2027, dry_run=True, notifications_dry_run=True)

    assert result == 1
    mock_submit.assert_not_called()


def test_execute_submits_every_candidate_and_notifies():
    conn = MagicMock()
    conn.cursor.return_value.fetchall.return_value = [("Accounting", "editor@chememan.com")]
    fake_state = MagicMock(status="PENDING_APPROVER1", current_approver_empcode="200")

    with patch("jobs.auto_submit.get_fabric_conn") as mock_conn, patch(
        "jobs.auto_submit.is_post_deadline", return_value=True
    ), patch("jobs.auto_submit.auto_submit_department", return_value=fake_state) as mock_submit, patch(
        "jobs.auto_submit.notifications.notify_turn"
    ) as mock_notify:
        mock_conn.return_value.__enter__.return_value = conn
        result = run(fiscal_year=2027, dry_run=False, notifications_dry_run=True)

    assert result == 1
    mock_submit.assert_called_once_with(conn, "Accounting", 2027, "editor@chememan.com")
    mock_notify.assert_called_once()
    assert mock_notify.call_args.kwargs["approver_empcode"] == "200"


def test_one_department_failure_does_not_block_the_rest():
    conn = MagicMock()
    conn.cursor.return_value.fetchall.return_value = [
        ("Accounting", "editor1@chememan.com"),
        ("IT", "editor2@chememan.com"),
    ]
    fake_state = MagicMock(status="PENDING_APPROVER1", current_approver_empcode="200")

    with patch("jobs.auto_submit.get_fabric_conn") as mock_conn, patch(
        "jobs.auto_submit.is_post_deadline", return_value=True
    ), patch(
        "jobs.auto_submit.auto_submit_department", side_effect=[RuntimeError("boom"), fake_state]
    ), patch("jobs.auto_submit.notifications.notify_turn"):
        mock_conn.return_value.__enter__.return_value = conn
        result = run(fiscal_year=2027, dry_run=False, notifications_dry_run=True)

    assert result == 1  # only the 2nd department succeeded
    conn.rollback.assert_called_once()


def test_notify_failure_does_not_block_other_departments():
    conn = MagicMock()
    conn.cursor.return_value.fetchall.return_value = [("Accounting", "editor@chememan.com")]
    fake_state = MagicMock(status="PENDING_APPROVER1", current_approver_empcode="200")

    with patch("jobs.auto_submit.get_fabric_conn") as mock_conn, patch(
        "jobs.auto_submit.is_post_deadline", return_value=True
    ), patch("jobs.auto_submit.auto_submit_department", return_value=fake_state), patch(
        "jobs.auto_submit.notifications.notify_turn", side_effect=RuntimeError("graph down")
    ):
        mock_conn.return_value.__enter__.return_value = conn
        result = run(fiscal_year=2027, dry_run=False, notifications_dry_run=True)

    assert result == 1  # the submit itself still counts as successful


# ---------------------------------------------------------------------------
# run() — GL edit_by admin-only lock (design v2, ADR-0024) flag-gated
# exclusion, so approver1 is never resolved from an admin-GL editor.
# ---------------------------------------------------------------------------

def test_run_flag_off_never_fetches_admin_gl_codes():
    """Flag OFF (default): zero behavior change — the admin-GL set is never
    fetched, and the discovery query runs with no exclusion at all."""
    conn = MagicMock()
    conn.cursor.return_value.fetchall.return_value = []
    with patch("jobs.auto_submit.get_fabric_conn") as mock_conn, patch(
        "jobs.auto_submit.is_post_deadline", return_value=True
    ), patch("jobs.auto_submit.fetch_admin_gl_codes") as mock_fetch_codes:
        mock_conn.return_value.__enter__.return_value = conn
        run(fiscal_year=2027, dry_run=True, notifications_dry_run=True, settings=Settings(_env_file=None))

    mock_fetch_codes.assert_not_called()


def test_run_flag_on_fetches_admin_gl_codes_and_excludes_them_from_discovery():
    """Flag ON: the admin-GL set is fetched once and threaded into
    `_find_true_draft_departments` as `exclude_gl_codes`, so the "last
    editor" discovery can never resolve approver1 from someone who only
    touched a secret admin-GL row."""
    conn = MagicMock()
    conn.cursor.return_value.fetchall.return_value = []
    with patch("jobs.auto_submit.get_fabric_conn") as mock_conn, patch(
        "jobs.auto_submit.is_post_deadline", return_value=True
    ), patch(
        "jobs.auto_submit.fetch_admin_gl_codes", return_value=frozenset({"5211900030"})
    ) as mock_fetch_codes, patch(
        "jobs.auto_submit._find_true_draft_departments", return_value=[]
    ) as mock_discover:
        mock_conn.return_value.__enter__.return_value = conn
        run(fiscal_year=2027, dry_run=True, notifications_dry_run=True, settings=_flag_on())

    mock_fetch_codes.assert_called_once_with(conn)
    mock_discover.assert_called_once_with(conn, 2027, exclude_gl_codes=frozenset({"5211900030"}))
