"""Unit tests for jobs.send_reminders — A12 automation D. DB always mocked;
`app.notifications.notify_reminder` always monkeypatched (no real Graph
call in any test)."""
from datetime import date
from unittest.mock import MagicMock, patch

from jobs.send_reminders import _find_still_not_submitted_departments, _group_by_filler, run


def test_reminder_date_not_reached_does_nothing():
    conn = MagicMock()
    with patch("jobs.send_reminders.get_fabric_conn") as mock_conn, patch(
        "jobs.send_reminders._reminder_date_reached", return_value=False
    ), patch("jobs.send_reminders.notifications.notify_reminder") as mock_notify:
        mock_conn.return_value.__enter__.return_value = conn
        result = run(fiscal_year=2027, dry_run=False, notifications_dry_run=True)
    assert result == 0
    mock_notify.assert_not_called()


def test_find_still_not_submitted_departments_parses_rows():
    conn = MagicMock()
    conn.cursor.return_value.fetchall.return_value = [("Accounting",), ("IT",)]
    result = _find_still_not_submitted_departments(conn, 2027)
    assert result == ["Accounting", "IT"]


def test_group_by_filler_inverts_department_to_filler_map():
    conn = MagicMock()
    conn.cursor.return_value.fetchall.side_effect = [
        [("alice@chememan.com",), ("bob@chememan.com",)],  # Accounting's fillers
        [("alice@chememan.com",)],                          # IT's fillers
    ]
    result = _group_by_filler(conn, ["Accounting", "IT"])
    assert result == {
        "alice@chememan.com": ["Accounting", "IT"],
        "bob@chememan.com": ["Accounting"],
    }


def test_dry_run_lists_fillers_without_sending():
    conn = MagicMock()
    with patch("jobs.send_reminders.get_fabric_conn") as mock_conn, patch(
        "jobs.send_reminders._reminder_date_reached", return_value=True
    ), patch(
        "jobs.send_reminders._find_still_not_submitted_departments", return_value=["Accounting"]
    ), patch(
        "jobs.send_reminders._group_by_filler", return_value={"alice@chememan.com": ["Accounting"]}
    ), patch("jobs.send_reminders.notifications.notify_reminder") as mock_notify:
        mock_conn.return_value.__enter__.return_value = conn
        result = run(fiscal_year=2027, dry_run=True, notifications_dry_run=True)
    assert result == 1
    mock_notify.assert_not_called()


def test_execute_sends_one_grouped_email_per_filler():
    conn = MagicMock()
    with patch("jobs.send_reminders.get_fabric_conn") as mock_conn, patch(
        "jobs.send_reminders._reminder_date_reached", return_value=True
    ), patch(
        "jobs.send_reminders._find_still_not_submitted_departments", return_value=["Accounting", "IT"]
    ), patch(
        "jobs.send_reminders._group_by_filler",
        return_value={"alice@chememan.com": ["Accounting", "IT"], "bob@chememan.com": ["Accounting"]},
    ), patch("jobs.send_reminders.notifications.notify_reminder") as mock_notify:
        mock_conn.return_value.__enter__.return_value = conn
        result = run(fiscal_year=2027, dry_run=False, notifications_dry_run=True)

    assert result == 2
    assert mock_notify.call_count == 2
    alice_call = next(c for c in mock_notify.call_args_list if c.args[0] == "alice@chememan.com")
    assert alice_call.args[1] == [("Accounting", 2027), ("IT", 2027)]


def test_no_departments_found_does_nothing():
    conn = MagicMock()
    with patch("jobs.send_reminders.get_fabric_conn") as mock_conn, patch(
        "jobs.send_reminders._reminder_date_reached", return_value=True
    ), patch("jobs.send_reminders._find_still_not_submitted_departments", return_value=[]), patch(
        "jobs.send_reminders.notifications.notify_reminder"
    ) as mock_notify:
        mock_conn.return_value.__enter__.return_value = conn
        result = run(fiscal_year=2027, dry_run=False, notifications_dry_run=True)
    assert result == 0
    mock_notify.assert_not_called()


def test_one_filler_failure_does_not_block_the_rest():
    conn = MagicMock()
    with patch("jobs.send_reminders.get_fabric_conn") as mock_conn, patch(
        "jobs.send_reminders._reminder_date_reached", return_value=True
    ), patch(
        "jobs.send_reminders._find_still_not_submitted_departments", return_value=["Accounting"]
    ), patch(
        "jobs.send_reminders._group_by_filler",
        return_value={"alice@chememan.com": ["Accounting"], "bob@chememan.com": ["Accounting"]},
    ), patch(
        "jobs.send_reminders.notifications.notify_reminder", side_effect=[RuntimeError("graph down"), MagicMock()]
    ):
        mock_conn.return_value.__enter__.return_value = conn
        result = run(fiscal_year=2027, dry_run=False, notifications_dry_run=True)
    assert result == 1
