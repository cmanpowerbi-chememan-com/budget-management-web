"""Unit tests for jobs.auto_submit — A11 scheduled job. DB always mocked
(one shared `conn.cursor.return_value` cursor, matching the app-level test
convention); `app.notifications.notify_turn` is always monkeypatched so no
test can trigger a real Graph call.
"""
from unittest.mock import MagicMock, patch

import pytest

from jobs.auto_submit import _find_true_draft_departments, run


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
