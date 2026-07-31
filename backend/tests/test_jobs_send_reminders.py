"""Unit tests for jobs.send_reminders — 2026-07-31 email-notify revamp:
Phase A (7-day turn reminders to the current approver of PENDING_* rows) +
Phase B (per-(department, filler) deadline reminders, replacing the old
grouped per-filler email). DB always mocked; `app.notifications.notify_*`
always monkeypatched (no real Graph call in any test)."""
from datetime import date, datetime, timedelta
from unittest.mock import MagicMock, patch

from app.approval import NIPAPORN_EMPCODE, PENDING_APPROVER1, PENDING_APPROVER2
from app.notifications import NotificationResult
from jobs.send_reminders import (
    DEADLINE_REMINDER_TYPE,
    TURN_REMINDER_TYPE,
    _deadline_due,
    _deadline_window,
    _find_fillers,
    _find_still_not_submitted_departments,
    _resolve_approver1_cc_email,
    _run_deadline_reminders,
    _run_turn_reminders,
    _turn_due,
    run,
)

NOW = datetime(2026, 7, 31, 12, 0, 0)
TODAY = NOW.date()


def _pending_row(
    department="Accounting", status=PENDING_APPROVER1, submitted_at=None,
    approver1_empcode="200", approver1_actioned_at=None, approver2_actioned_at=None,
    submitter_email="filler@chememan.com",
):
    """One budget.approval_status row dict, keyed like fetch_pending_rows."""
    return {
        "department": department,
        "fiscal_year": 2027,
        "status": status,
        "submitter_empcode": "100",
        "submitter_email": submitter_email,
        "submitted_at": submitted_at if submitted_at is not None else NOW - timedelta(days=8),
        "approver1_empcode": approver1_empcode,
        "approver1_actioned_at": approver1_actioned_at,
        "approver2_actioned_at": approver2_actioned_at,
        "approver3_actioned_at": None,
        "reject_reason": None,
        "_updated_at": NOW,
    }


# ---------------------------------------------------------------------------
# _turn_due — pure 7-day cadence logic (plan §3.3)
# ---------------------------------------------------------------------------

def test_turn_due_when_never_sent_and_turn_started_over_7_days_ago():
    assert _turn_due(NOW - timedelta(days=8), None, NOW) is True


def test_turn_not_due_when_turn_started_under_7_days_ago():
    assert _turn_due(NOW - timedelta(days=6), None, NOW) is False


def test_turn_due_at_exactly_7_days():
    assert _turn_due(NOW - timedelta(days=7), None, NOW) is True


def test_turn_not_due_when_reminded_less_than_7_days_ago():
    turn_start = NOW - timedelta(days=10)
    last_sent = NOW - timedelta(days=3)
    assert _turn_due(turn_start, last_sent, NOW) is False


def test_turn_due_again_when_last_reminder_7_days_ago():
    turn_start = NOW - timedelta(days=14)
    last_sent = NOW - timedelta(days=7)
    assert _turn_due(turn_start, last_sent, NOW) is True


def test_turn_last_sent_before_turn_start_counts_as_never_sent():
    """A log row from a PREVIOUS chain cycle (last_sent < turn_start) must
    not suppress the reminder — treat it as never sent (plan §3.3)."""
    # turn restarted 5 days ago; a 20-day-old log row is from the old cycle
    assert _turn_due(NOW - timedelta(days=5), NOW - timedelta(days=20), NOW) is False
    # same stale log row, but the new turn is already 9 days old -> due
    assert _turn_due(NOW - timedelta(days=9), NOW - timedelta(days=20), NOW) is True


# ---------------------------------------------------------------------------
# _deadline_due — pure 7-day cadence logic (plan §3.3)
# ---------------------------------------------------------------------------

def test_deadline_due_when_never_sent():
    assert _deadline_due(None, TODAY) is True


def test_deadline_not_due_when_sent_less_than_7_days_ago():
    assert _deadline_due(NOW - timedelta(days=6), TODAY) is False


def test_deadline_due_when_last_sent_7_days_ago():
    assert _deadline_due(NOW - timedelta(days=7), TODAY) is True


# ---------------------------------------------------------------------------
# Phase A — turn reminders
# ---------------------------------------------------------------------------

def _patch_turn_phase(notify_side_effect=None, notify_return=None):
    """Common patch stack for _run_turn_reminders tests."""
    return (
        patch("jobs.send_reminders.fetch_pending_rows"),
        patch("jobs.send_reminders._last_sent_at"),
        patch("jobs.send_reminders._log_reminder"),
        patch(
            "jobs.send_reminders.notifications.notify_turn",
            side_effect=notify_side_effect,
            return_value=notify_return if notify_side_effect is None else None,
        ),
    )


def test_turn_reminder_sent_when_due_and_logged():
    p_rows, p_last, p_log, p_notify = _patch_turn_phase(notify_return=MagicMock())
    with p_rows as m_rows, p_last as m_last, p_log as m_log, p_notify as m_notify:
        m_rows.return_value = [_pending_row(submitted_at=NOW - timedelta(days=8))]
        m_last.return_value = None
        sent = _run_turn_reminders(MagicMock(), 2027, dry_run=False, notifications_dry_run=True, now=NOW)

    assert sent == 1
    m_notify.assert_called_once()
    assert m_notify.call_args.kwargs["approver_empcode"] == "200"
    assert m_notify.call_args.kwargs["reminder"] is True
    assert m_notify.call_args.kwargs["days_pending"] == 8
    m_log.assert_called_once()
    assert m_log.call_args.args[1:4] == (TURN_REMINDER_TYPE, "Accounting", 2027)
    assert m_log.call_args.args[4] == "200"  # recipient = current approver empcode


def test_turn_reminder_not_sent_when_turn_too_young():
    p_rows, p_last, p_log, p_notify = _patch_turn_phase()
    with p_rows as m_rows, p_last as m_last, p_log as m_log, p_notify as m_notify:
        m_rows.return_value = [_pending_row(submitted_at=NOW - timedelta(days=3))]
        m_last.return_value = None
        sent = _run_turn_reminders(MagicMock(), 2027, dry_run=False, notifications_dry_run=True, now=NOW)

    assert sent == 0
    m_notify.assert_not_called()
    m_log.assert_not_called()


def test_turn_reminder_not_resent_when_reminded_recently():
    p_rows, p_last, p_log, p_notify = _patch_turn_phase()
    with p_rows as m_rows, p_last as m_last, p_log as m_log, p_notify as m_notify:
        m_rows.return_value = [_pending_row(submitted_at=NOW - timedelta(days=10))]
        m_last.return_value = NOW - timedelta(days=3)
        sent = _run_turn_reminders(MagicMock(), 2027, dry_run=False, notifications_dry_run=True, now=NOW)

    assert sent == 0
    m_notify.assert_not_called()
    m_log.assert_not_called()


def test_turn_reminder_skipped_when_no_current_approver():
    """PENDING_APPROVER1 row with a NULL frozen approver1 has no occupant to
    mail — skip loudly, never crash (plan §4.7 'ไม่มี current approver ข้าม')."""
    p_rows, p_last, p_log, p_notify = _patch_turn_phase()
    with p_rows as m_rows, p_last as m_last, p_log as m_log, p_notify as m_notify:
        m_rows.return_value = [_pending_row(approver1_empcode=None)]
        m_last.return_value = None
        sent = _run_turn_reminders(MagicMock(), 2027, dry_run=False, notifications_dry_run=True, now=NOW)

    assert sent == 0
    m_notify.assert_not_called()
    m_log.assert_not_called()


def test_turn_reminder_not_logged_when_email_unresolvable():
    """notify_turn returns None when the approver's email cannot be resolved
    — nothing was sent, so NOTHING may be logged (retry next run, plan §3.3)."""
    p_rows, p_last, p_log, p_notify = _patch_turn_phase(notify_return=None)
    with p_rows as m_rows, p_last as m_last, p_log as m_log, p_notify as m_notify:
        m_rows.return_value = [_pending_row()]
        m_last.return_value = None
        sent = _run_turn_reminders(MagicMock(), 2027, dry_run=False, notifications_dry_run=True, now=NOW)

    assert sent == 0
    m_notify.assert_called_once()
    m_log.assert_not_called()


def test_turn_reminder_not_logged_when_send_suppressed_by_notifications_dry_run():
    """A manual --execute BEFORE the go-live flip (NOTIFICATIONS_DRY_RUN=true)
    makes send_mail return sent=False — logging that as 'sent' would let a
    stale cadence row swallow the FIRST real reminder for up to 7 days after
    the flip (gate finding 2026-07-31): nothing really sent, nothing logged."""
    suppressed = NotificationResult(sent=False, to_email="vp@chememan.com", subject="s", dry_run=True, detail="dry_run")
    p_rows, p_last, p_log, p_notify = _patch_turn_phase(notify_return=suppressed)
    with p_rows as m_rows, p_last as m_last, p_log as m_log, p_notify as m_notify:
        m_rows.return_value = [_pending_row()]
        m_last.return_value = None
        sent = _run_turn_reminders(MagicMock(), 2027, dry_run=False, notifications_dry_run=True, now=NOW)

    assert sent == 0
    m_notify.assert_called_once()
    m_log.assert_not_called()


def test_turn_reminder_failure_isolates_per_department():
    p_rows, p_last, p_log, p_notify = _patch_turn_phase(
        notify_side_effect=[RuntimeError("graph down"), MagicMock()]
    )
    with p_rows as m_rows, p_last as m_last, p_log as m_log, p_notify as m_notify:
        m_rows.return_value = [_pending_row("Accounting"), _pending_row("IT", PENDING_APPROVER2, approver1_empcode=None)]
        m_last.return_value = None
        sent = _run_turn_reminders(MagicMock(), 2027, dry_run=False, notifications_dry_run=True, now=NOW)

    assert sent == 1  # IT still sent after Accounting blew up
    assert m_notify.call_count == 2
    m_log.assert_called_once()  # only the successful send is logged
    assert m_log.call_args.args[2] == "IT"


def test_turn_reminder_dry_run_sends_nothing_and_writes_no_log():
    p_rows, p_last, p_log, p_notify = _patch_turn_phase()
    with p_rows as m_rows, p_last as m_last, p_log as m_log, p_notify as m_notify:
        m_rows.return_value = [_pending_row()]
        m_last.return_value = None
        sent = _run_turn_reminders(MagicMock(), 2027, dry_run=True, notifications_dry_run=True, now=NOW)

    assert sent == 1  # would-be count
    m_notify.assert_not_called()
    m_log.assert_not_called()


# ---------------------------------------------------------------------------
# Phase B — deadline reminders (per-(department, filler), cc derived approver1)
# ---------------------------------------------------------------------------

def _patch_deadline_phase(window=(date(2026, 7, 1), date(2026, 8, 31)), notify_side_effect=None):
    return (
        patch("jobs.send_reminders._deadline_window", return_value=window),
        patch("jobs.send_reminders._find_still_not_submitted_departments"),
        patch("jobs.send_reminders._find_fillers"),
        patch("jobs.send_reminders._last_sent_at", return_value=None),
        patch("jobs.send_reminders._resolve_approver1_cc_email", return_value="vp@chememan.com"),
        patch("jobs.send_reminders._log_reminder"),
        patch("jobs.send_reminders.notifications.notify_deadline_reminder", side_effect=notify_side_effect),
    )


def test_deadline_one_email_per_department_even_for_same_filler():
    """The old grouped mail is gone: a filler with 2 pending departments gets
    2 SEPARATE emails, one deep link each (plan §1/§3.4)."""
    patches = _patch_deadline_phase()
    with patches[0], patches[1] as m_depts, patches[2] as m_fillers, patches[3], patches[4], \
            patches[5] as m_log, patches[6] as m_notify:
        m_notify.return_value = MagicMock()
        m_depts.return_value = ["Accounting", "IT"]
        m_fillers.side_effect = lambda conn, dept: {"Accounting": ["alice@chememan.com"], "IT": ["alice@chememan.com"]}[dept]
        sent = _run_deadline_reminders(MagicMock(), 2027, dry_run=False, notifications_dry_run=True, today=TODAY)

    assert sent == 2
    assert m_notify.call_count == 2
    departments = [c.args[1] for c in m_notify.call_args_list]
    assert departments == ["Accounting", "IT"]
    for c in m_notify.call_args_list:
        assert c.args[0] == "alice@chememan.com"  # To = the filler
        assert c.kwargs["cc_emails"] == ["vp@chememan.com"]  # cc = derived approver1
    assert m_log.call_count == 2
    assert {c.args[2] for c in m_log.call_args_list} == {"Accounting", "IT"}
    assert all(c.args[1] == DEADLINE_REMINDER_TYPE for c in m_log.call_args_list)


def test_deadline_not_logged_when_send_suppressed_by_notifications_dry_run():
    """Same suppression rule as Phase A (gate finding 2026-07-31): --execute
    with NOTIFICATIONS_DRY_RUN=true returns sent=False — nothing really sent,
    so the cadence row must NOT be written."""
    patches = _patch_deadline_phase()
    with patches[0], patches[1] as m_depts, patches[2] as m_fillers, patches[3], patches[4], \
            patches[5] as m_log, patches[6] as m_notify:
        m_notify.return_value = NotificationResult(sent=False, to_email="alice@chememan.com", subject="s", dry_run=True, detail="dry_run")
        m_depts.return_value = ["Accounting"]
        m_fillers.return_value = ["alice@chememan.com"]
        sent = _run_deadline_reminders(MagicMock(), 2027, dry_run=False, notifications_dry_run=True, today=TODAY)

    assert sent == 0
    m_notify.assert_called_once()
    m_log.assert_not_called()


def test_deadline_not_sent_before_reminder_date():
    patches = _patch_deadline_phase(window=(TODAY + timedelta(days=5), TODAY + timedelta(days=30)))
    with patches[0], patches[1] as m_depts, patches[2], patches[3], patches[4], patches[5], patches[6] as m_notify:
        sent = _run_deadline_reminders(MagicMock(), 2027, dry_run=False, notifications_dry_run=True, today=TODAY)

    assert sent == 0
    m_depts.assert_not_called()
    m_notify.assert_not_called()


def test_deadline_not_sent_after_closing_date():
    patches = _patch_deadline_phase(window=(TODAY - timedelta(days=30), TODAY - timedelta(days=1)))
    with patches[0], patches[1] as m_depts, patches[2], patches[3], patches[4], patches[5], patches[6] as m_notify:
        sent = _run_deadline_reminders(MagicMock(), 2027, dry_run=False, notifications_dry_run=True, today=TODAY)

    assert sent == 0
    m_depts.assert_not_called()
    m_notify.assert_not_called()


def test_deadline_no_deadline_row_does_nothing():
    patches = _patch_deadline_phase(window=None)
    with patches[0], patches[1] as m_depts, patches[2], patches[3], patches[4], patches[5], patches[6] as m_notify:
        sent = _run_deadline_reminders(MagicMock(), 2027, dry_run=False, notifications_dry_run=True, today=TODAY)

    assert sent == 0
    m_depts.assert_not_called()
    m_notify.assert_not_called()


def test_deadline_not_resent_within_7_day_cadence():
    patches = _patch_deadline_phase()
    with patches[0], patches[1] as m_depts, patches[2] as m_fillers, \
            patches[3] as m_last, patches[4], patches[5] as m_log, patches[6] as m_notify:
        m_depts.return_value = ["Accounting"]
        m_fillers.return_value = ["alice@chememan.com"]
        m_last.return_value = NOW - timedelta(days=3)  # reminded 3 days ago
        sent = _run_deadline_reminders(MagicMock(), 2027, dry_run=False, notifications_dry_run=True, today=TODAY)

    assert sent == 0
    m_notify.assert_not_called()
    m_log.assert_not_called()


def test_deadline_cc_falls_back_to_empty_when_unresolvable_or_same_as_filler():
    """cc lookup failing must never block the To send; cc == To is dropped."""
    patches = _patch_deadline_phase()
    with patches[0], patches[1] as m_depts, patches[2] as m_fillers, patches[3], \
            patches[4] as m_cc, patches[5], patches[6] as m_notify:
        m_notify.return_value = MagicMock()
        m_depts.return_value = ["Accounting", "IT"]
        m_fillers.side_effect = lambda conn, dept: ["alice@chememan.com"]
        m_cc.side_effect = [None, "alice@chememan.com"]  # lookup failed / cc == To
        sent = _run_deadline_reminders(MagicMock(), 2027, dry_run=False, notifications_dry_run=True, today=TODAY)

    assert sent == 2
    assert m_notify.call_args_list[0].kwargs["cc_emails"] == []
    assert m_notify.call_args_list[1].kwargs["cc_emails"] == []


def test_deadline_failure_isolates_per_department():
    patches = _patch_deadline_phase(notify_side_effect=[RuntimeError("graph down"), MagicMock()])
    with patches[0], patches[1] as m_depts, patches[2] as m_fillers, patches[3], patches[4], \
            patches[5] as m_log, patches[6] as m_notify:
        m_depts.return_value = ["Accounting", "IT"]
        m_fillers.side_effect = lambda conn, dept: ["alice@chememan.com"]
        sent = _run_deadline_reminders(MagicMock(), 2027, dry_run=False, notifications_dry_run=True, today=TODAY)

    assert sent == 1
    assert m_notify.call_count == 2
    m_log.assert_called_once()
    assert m_log.call_args.args[2] == "IT"


def test_deadline_dry_run_sends_nothing_and_writes_no_log():
    patches = _patch_deadline_phase()
    with patches[0], patches[1] as m_depts, patches[2] as m_fillers, patches[3], patches[4], \
            patches[5] as m_log, patches[6] as m_notify:
        m_depts.return_value = ["Accounting"]
        m_fillers.return_value = ["alice@chememan.com"]
        sent = _run_deadline_reminders(MagicMock(), 2027, dry_run=True, notifications_dry_run=True, today=TODAY)

    assert sent == 1  # would-be count
    m_notify.assert_not_called()
    m_log.assert_not_called()


# ---------------------------------------------------------------------------
# approver1 cc derivation — manager rule, fallback Nipaporn (plan §1 locked)
# ---------------------------------------------------------------------------

def test_resolve_approver1_cc_uses_fillers_manager():
    conn = MagicMock()
    with patch("jobs.send_reminders.resolve_submitter", return_value=("100", "M200")) as m_resolve, patch(
        "jobs.send_reminders.lookup_email_by_empcode", return_value="vp@chememan.com"
    ) as m_lookup:
        result = _resolve_approver1_cc_email(conn, "alice@chememan.com")

    assert result == "vp@chememan.com"
    m_resolve.assert_called_once_with(conn, "alice@chememan.com")
    m_lookup.assert_called_once_with(conn, "M200")


def test_resolve_approver1_cc_falls_back_to_nipaporn():
    conn = MagicMock()
    with patch("jobs.send_reminders.resolve_submitter", return_value=(None, None)), patch(
        "jobs.send_reminders.lookup_email_by_empcode", return_value="nipaporn@chememan.com"
    ) as m_lookup:
        result = _resolve_approver1_cc_email(conn, "ghost@chememan.com")

    assert result == "nipaporn@chememan.com"
    m_lookup.assert_called_once_with(conn, NIPAPORN_EMPCODE)


# ---------------------------------------------------------------------------
# discovery helpers / window parsing
# ---------------------------------------------------------------------------

def test_find_still_not_submitted_departments_scope_is_draft_or_rejected():
    """Scope lock (plan §1): only departments with NO approval_status row
    (DRAFT) or a REJECTED row — PENDING_*/APPROVED belong to turn reminders."""
    conn = MagicMock()
    conn.cursor.return_value.fetchall.return_value = [("Accounting",), ("IT",)]
    result = _find_still_not_submitted_departments(conn, 2027)

    assert result == ["Accounting", "IT"]
    sql, *params = conn.cursor.return_value.execute.call_args.args
    assert "approval_status" in sql
    assert params == [2027, "REJECTED"]  # rows with any other status excluded


def test_find_fillers_parses_rows():
    conn = MagicMock()
    conn.cursor.return_value.fetchall.return_value = [("alice@chememan.com",), ("bob@chememan.com",)]
    assert _find_fillers(conn, "Accounting") == ["alice@chememan.com", "bob@chememan.com"]


def test_deadline_window_parses_reminder_and_closing_date():
    conn = MagicMock()
    conn.cursor.return_value.fetchone.return_value = (date(2026, 7, 1), date(2026, 8, 31))
    assert _deadline_window(conn, 2027) == (date(2026, 7, 1), date(2026, 8, 31))


def test_deadline_window_none_when_no_row_or_no_reminder_date():
    conn = MagicMock()
    conn.cursor.return_value.fetchone.return_value = None
    assert _deadline_window(conn, 2027) is None
    conn.cursor.return_value.fetchone.return_value = (None, date(2026, 8, 31))
    assert _deadline_window(conn, 2027) is None


# ---------------------------------------------------------------------------
# run() — both phases, one return total
# ---------------------------------------------------------------------------

def test_run_combines_both_phases():
    conn = MagicMock()
    with patch("jobs.send_reminders.get_fabric_conn") as mock_conn, patch(
        "jobs.send_reminders._run_turn_reminders", return_value=2
    ), patch("jobs.send_reminders._run_deadline_reminders", return_value=3):
        mock_conn.return_value.__enter__.return_value = conn
        result = run(fiscal_year=2027, dry_run=True, notifications_dry_run=True, now=NOW)
    assert result == 5


def test_run_nothing_due_returns_zero():
    conn = MagicMock()
    with patch("jobs.send_reminders.get_fabric_conn") as mock_conn, patch(
        "jobs.send_reminders.fetch_pending_rows", return_value=[]
    ), patch("jobs.send_reminders._deadline_window", return_value=None):
        mock_conn.return_value.__enter__.return_value = conn
        result = run(fiscal_year=2027, dry_run=False, notifications_dry_run=True, now=NOW)
    assert result == 0
