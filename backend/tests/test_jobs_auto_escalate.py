"""Unit tests for jobs.auto_escalate — A11 scheduled job. DB always mocked;
`app.notifications.notify_turn` is always monkeypatched (no real Graph call
in any test)."""
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

from app.approval import InvalidApprovalStateError
from jobs.auto_escalate import run


def _row(status="PENDING_APPROVER1", department="Accounting") -> dict:
    return {
        "department": department, "fiscal_year": 2027, "status": status,
        "submitter_empcode": "999", "submitter_email": "filler@chememan.com",
        "submitted_at": datetime(2027, 1, 1, tzinfo=timezone.utc),
        "approver1_empcode": "200", "approver1_actioned_at": None, "approver2_actioned_at": None,
        "approver3_actioned_at": None, "reject_reason": None, "rejected_by_empcode": None,
        "_updated_at": datetime(2027, 1, 1, tzinfo=timezone.utc),
    }


def test_no_pending_rows_does_nothing():
    conn = MagicMock()
    with patch("jobs.auto_escalate.get_fabric_conn") as mock_conn, patch(
        "jobs.auto_escalate.fetch_pending_rows", return_value=[]
    ):
        mock_conn.return_value.__enter__.return_value = conn
        result = run(fiscal_year=2027, dry_run=False, notifications_dry_run=True)
    assert result == 0


def test_non_stale_row_is_not_escalated():
    conn = MagicMock()
    with patch("jobs.auto_escalate.get_fabric_conn") as mock_conn, patch(
        "jobs.auto_escalate.fetch_pending_rows", return_value=[_row()]
    ), patch("jobs.auto_escalate.is_step_stale", return_value=False), patch(
        "jobs.auto_escalate.auto_escalate_step"
    ) as mock_escalate:
        mock_conn.return_value.__enter__.return_value = conn
        result = run(fiscal_year=2027, dry_run=False, notifications_dry_run=True)
    assert result == 0
    mock_escalate.assert_not_called()


def test_dry_run_lists_stale_rows_without_escalating():
    conn = MagicMock()
    with patch("jobs.auto_escalate.get_fabric_conn") as mock_conn, patch(
        "jobs.auto_escalate.fetch_pending_rows", return_value=[_row()]
    ), patch("jobs.auto_escalate.is_step_stale", return_value=True), patch(
        "jobs.auto_escalate.auto_escalate_step"
    ) as mock_escalate:
        mock_conn.return_value.__enter__.return_value = conn
        result = run(fiscal_year=2027, dry_run=True, notifications_dry_run=True)
    assert result == 1
    mock_escalate.assert_not_called()


def test_execute_escalates_stale_row_and_notifies():
    conn = MagicMock()
    fake_state = MagicMock(status="PENDING_APPROVER2", current_approver_empcode="101032")
    with patch("jobs.auto_escalate.get_fabric_conn") as mock_conn, patch(
        "jobs.auto_escalate.fetch_pending_rows", return_value=[_row()]
    ), patch("jobs.auto_escalate.is_step_stale", return_value=True), patch(
        "jobs.auto_escalate.auto_escalate_step", return_value=fake_state
    ) as mock_escalate, patch("jobs.auto_escalate.notifications.notify_turn") as mock_notify:
        mock_conn.return_value.__enter__.return_value = conn
        result = run(fiscal_year=2027, dry_run=False, notifications_dry_run=True)

    assert result == 1
    mock_escalate.assert_called_once()
    mock_notify.assert_called_once()
    assert mock_notify.call_args.kwargs["approver_empcode"] == "101032"


def test_final_step_row_is_skipped_not_treated_as_failure():
    """ADR-0006: a stuck FINAL step must not escalate to APPROVED —
    auto_escalate_step raises InvalidApprovalStateError for this, which the
    job must treat as a normal skip, not a logged failure."""
    conn = MagicMock()
    with patch("jobs.auto_escalate.get_fabric_conn") as mock_conn, patch(
        "jobs.auto_escalate.fetch_pending_rows", return_value=[_row(status="PENDING_APPROVER3")]
    ), patch("jobs.auto_escalate.is_step_stale", return_value=True), patch(
        "jobs.auto_escalate.auto_escalate_step",
        side_effect=InvalidApprovalStateError("already the final active position"),
    ):
        mock_conn.return_value.__enter__.return_value = conn
        result = run(fiscal_year=2027, dry_run=False, notifications_dry_run=True)
    assert result == 0
    conn.rollback.assert_not_called()  # not a failure -- no rollback needed


def test_one_row_failure_does_not_block_the_rest():
    conn = MagicMock()
    fake_state = MagicMock(status="PENDING_APPROVER2", current_approver_empcode="101032")
    rows = [_row(department="Accounting"), _row(department="IT")]
    with patch("jobs.auto_escalate.get_fabric_conn") as mock_conn, patch(
        "jobs.auto_escalate.fetch_pending_rows", return_value=rows
    ), patch("jobs.auto_escalate.is_step_stale", return_value=True), patch(
        "jobs.auto_escalate.auto_escalate_step", side_effect=[RuntimeError("boom"), fake_state]
    ), patch("jobs.auto_escalate.notifications.notify_turn"):
        mock_conn.return_value.__enter__.return_value = conn
        result = run(fiscal_year=2027, dry_run=False, notifications_dry_run=True)
    assert result == 1
    conn.rollback.assert_called_once()
