"""Unit tests for jobs.send_reminders — §7 rework (plan/email-notify-revamp.md):
grouped reminders, ONE mail per PERSON (per approver for turn reminders, per
filler for deadline reminders), person-level 7-day cadence keyed on the '*'
sentinel, plus bulk-send hardening (pacing / cap / summary). DB always mocked;
`app.notifications.notify_*` always monkeypatched (no real Graph call, no real
sleep in any test)."""
import logging
from datetime import date, datetime, timedelta
from unittest.mock import ANY, MagicMock, patch

from app.approval import NIPAPORN_EMPCODE, PENDING_APPROVER1, PENDING_APPROVER2
from app.notifications import NotificationResult
from jobs.send_reminders import (
    DEADLINE_REMINDER_TYPE,
    PERSON_SENTINEL,
    TURN_REMINDER_TYPE,
    _deadline_due,
    _deadline_window,
    _find_fillers,
    _find_still_not_submitted_departments,
    _person_cadence_clear,
    _resolve_approver1_cc_email,
    _run_deadline_reminders,
    _run_turn_reminders,
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


def _ok_result():
    """What a successful notify_* returns, as the job consumes it."""
    return MagicMock(retries=0)


# ---------------------------------------------------------------------------
# _person_cadence_clear / _deadline_due — pure 7-day person-level cadence
# ---------------------------------------------------------------------------

def test_person_cadence_clear_when_never_sent():
    assert _person_cadence_clear(None, NOW) is True


def test_person_cadence_blocked_when_sent_less_than_7_days_ago():
    assert _person_cadence_clear(NOW - timedelta(days=6), NOW) is False


def test_person_cadence_clear_when_last_sent_7_days_ago():
    assert _person_cadence_clear(NOW - timedelta(days=7), NOW) is True


def test_deadline_due_when_never_sent():
    assert _deadline_due(None, TODAY) is True


def test_deadline_not_due_when_sent_less_than_7_days_ago():
    assert _deadline_due(NOW - timedelta(days=6), TODAY) is False


def test_deadline_due_when_last_sent_7_days_ago():
    assert _deadline_due(NOW - timedelta(days=7), TODAY) is True


# ---------------------------------------------------------------------------
# Phase A — turn reminders, grouped ONE mail per approver
# ---------------------------------------------------------------------------

def _patch_turn_phase(notify_side_effect=None):
    return (
        patch("jobs.send_reminders.fetch_pending_rows"),
        patch("jobs.send_reminders._last_sent_at", return_value=None),
        patch("jobs.send_reminders._log_reminder"),
        patch(
            "jobs.send_reminders.notifications.notify_turn_reminder",
            side_effect=notify_side_effect,
            return_value=None if notify_side_effect else _ok_result(),
        ),
    )


def test_turn_groups_all_pending_departments_into_one_mail_per_approver():
    """§7.1/§7.4.3: two rows waiting on the SAME approver -> ONE mail listing
    BOTH, including the one younger than 7 days ('ลิสต์ทุกฝ่ายที่รอเขาอยู่'
    — the 7-day gate is on the oldest item, the content is everything)."""
    p_rows, p_last, p_log, p_notify = _patch_turn_phase()
    with p_rows as m_rows, p_last as m_last, p_log as m_log, p_notify as m_notify:
        m_rows.return_value = [
            _pending_row("Accounting", submitted_at=NOW - timedelta(days=8)),
            _pending_row("IT", submitted_at=NOW - timedelta(days=2)),
        ]
        sent = _run_turn_reminders(MagicMock(), 2027, dry_run=False, notifications_dry_run=True, now=NOW)

    assert sent == 1
    m_notify.assert_called_once()
    assert m_notify.call_args.kwargs["approver_empcode"] == "200"
    items = m_notify.call_args.kwargs["items"]
    assert items == [("Accounting", 2027, 8), ("IT", 2027, 2)]  # young item rides along
    m_last.assert_called_once_with(ANY, TURN_REMINDER_TYPE, PERSON_SENTINEL, 2027, "200")
    m_log.assert_called_once()
    assert m_log.call_args.args[1:5] == (TURN_REMINDER_TYPE, PERSON_SENTINEL, 2027, "200")


def test_turn_not_due_when_all_items_younger_than_7_days():
    """The per-person gate needs at least ONE item aged >= 7 days."""
    p_rows, p_last, p_log, p_notify = _patch_turn_phase()
    with p_rows as m_rows, p_last as m_last, p_log as m_log, p_notify as m_notify:
        m_rows.return_value = [_pending_row(submitted_at=NOW - timedelta(days=3))]
        sent = _run_turn_reminders(MagicMock(), 2027, dry_run=False, notifications_dry_run=True, now=NOW)

    assert sent == 0
    m_notify.assert_not_called()
    m_log.assert_not_called()
    m_last.assert_not_called()


def test_turn_person_cadence_blocks_rerun_within_7_days():
    """§7.4.4: re-running <7d after the person's last reminder stays silent
    even though an item is old enough."""
    p_rows, p_last, p_log, p_notify = _patch_turn_phase()
    with p_rows as m_rows, p_last as m_last, p_log as m_log, p_notify as m_notify:
        m_rows.return_value = [_pending_row(submitted_at=NOW - timedelta(days=10))]
        m_last.return_value = NOW - timedelta(days=3)
        sent = _run_turn_reminders(MagicMock(), 2027, dry_run=False, notifications_dry_run=True, now=NOW)

    assert sent == 0
    m_notify.assert_not_called()
    m_log.assert_not_called()


def test_turn_person_cadence_resends_after_7_days():
    p_rows, p_last, p_log, p_notify = _patch_turn_phase()
    with p_rows as m_rows, p_last as m_last, p_log as m_log, p_notify as m_notify:
        m_rows.return_value = [_pending_row(submitted_at=NOW - timedelta(days=14))]
        m_last.return_value = NOW - timedelta(days=7)
        sent = _run_turn_reminders(MagicMock(), 2027, dry_run=False, notifications_dry_run=True, now=NOW)

    assert sent == 1
    m_notify.assert_called_once()
    m_log.assert_called_once()


def test_turn_reminder_still_due_at_day_120_no_upper_bound_no_cc():
    """D6 (ADR-0027): turn reminders repeat every 7 days FOREVER — no end
    date, no cap, no cc escalation after N rounds. A step stuck 120 days is
    still due once the person's 7-day cadence clears, its days-pending is
    shown as-is, and the mail stays To-only. Guards against anyone
    reintroducing a stop condition after the auto-escalation was retired."""
    p_rows, p_last, p_log, p_notify = _patch_turn_phase()
    with p_rows as m_rows, p_last as m_last, p_log as m_log, p_notify as m_notify:
        m_rows.return_value = [_pending_row(submitted_at=NOW - timedelta(days=120))]
        m_last.return_value = NOW - timedelta(days=7)  # last round went out 7 days ago
        sent = _run_turn_reminders(MagicMock(), 2027, dry_run=False, notifications_dry_run=True, now=NOW)

    assert sent == 1
    m_notify.assert_called_once()
    assert m_notify.call_args.kwargs["items"] == [("Accounting", 2027, 120)]
    assert "cc" not in m_notify.call_args.kwargs  # turn mails stay To-only, forever
    m_log.assert_called_once()


def test_turn_reminder_skipped_when_no_current_approver():
    p_rows, p_last, p_log, p_notify = _patch_turn_phase()
    with p_rows as m_rows, p_last as m_last, p_log as m_log, p_notify as m_notify:
        m_rows.return_value = [_pending_row(approver1_empcode=None)]
        sent = _run_turn_reminders(MagicMock(), 2027, dry_run=False, notifications_dry_run=True, now=NOW)

    assert sent == 0
    m_notify.assert_not_called()
    m_log.assert_not_called()


def test_turn_reminder_not_logged_when_email_unresolvable():
    """notify_turn_reminder returns None when the approver's email cannot be
    resolved — nothing was sent, so NOTHING may be logged (retry next run)."""
    p_rows, p_last, p_log, p_notify = _patch_turn_phase()
    with p_rows as m_rows, p_last as m_last, p_log as m_log, p_notify as m_notify:
        m_notify.side_effect = None
        m_notify.return_value = None
        m_rows.return_value = [_pending_row()]
        sent = _run_turn_reminders(MagicMock(), 2027, dry_run=False, notifications_dry_run=True, now=NOW)

    assert sent == 0
    m_notify.assert_called_once()
    m_log.assert_not_called()


def test_turn_reminder_not_logged_when_send_suppressed_by_notifications_dry_run():
    """A manual --execute BEFORE the go-live flip (NOTIFICATIONS_DRY_RUN=true)
    makes send_mail return sent=False — logging that would let a stale
    cadence row swallow the FIRST real reminder for up to 7 days after the
    flip (gate finding 2026-07-31, §7.4.10): nothing really sent, nothing
    logged. Restored after the §7 rework dropped the guard once."""
    p_rows, p_last, p_log, p_notify = _patch_turn_phase()
    with p_rows as m_rows, p_last as m_last, p_log as m_log, p_notify as m_notify:
        m_notify.side_effect = None
        m_notify.return_value = NotificationResult(sent=False, to_email="vp@chememan.com", subject="s", dry_run=True, detail="dry_run")
        m_rows.return_value = [_pending_row()]
        sent = _run_turn_reminders(MagicMock(), 2027, dry_run=False, notifications_dry_run=True, now=NOW)

    assert sent == 0
    m_notify.assert_called_once()
    m_log.assert_not_called()


def test_turn_reminder_failure_isolates_per_approver():
    p_rows, p_last, p_log, p_notify = _patch_turn_phase(
        notify_side_effect=[RuntimeError("graph down"), _ok_result()]
    )
    with p_rows as m_rows, p_last as m_last, p_log as m_log, p_notify as m_notify:
        m_rows.return_value = [
            _pending_row("Accounting", approver1_empcode="200"),
            _pending_row("IT", PENDING_APPROVER2, approver1_empcode=None),  # occupant = Nipaporn
        ]
        sent = _run_turn_reminders(MagicMock(), 2027, dry_run=False, notifications_dry_run=True, now=NOW)

    assert sent == 1  # Nipaporn's mail still sent after empcode-200's blew up
    assert m_notify.call_count == 2
    m_log.assert_called_once()  # only the successful send is logged
    assert m_log.call_args.args[4] == NIPAPORN_EMPCODE


def test_turn_reminder_dry_run_sends_nothing_and_writes_no_log():
    p_rows, p_last, p_log, p_notify = _patch_turn_phase()
    with p_rows as m_rows, p_last as m_last, p_log as m_log, p_notify as m_notify:
        m_rows.return_value = [_pending_row()]
        sent = _run_turn_reminders(MagicMock(), 2027, dry_run=True, notifications_dry_run=True, now=NOW)

    assert sent == 1  # would-be count
    m_notify.assert_not_called()
    m_log.assert_not_called()


def test_turn_pacing_sleeps_between_sends_not_after_last():
    """§7.4.9: N sends -> N-1 sleeps with the configured delay."""
    p_rows, p_last, p_log, p_notify = _patch_turn_phase()
    sleeps = []
    with p_rows as m_rows, p_last as m_last, p_log as m_log, p_notify as m_notify:
        m_notify.side_effect = [_ok_result(), _ok_result(), _ok_result()]
        m_rows.return_value = [
            _pending_row("A", approver1_empcode="201"),
            _pending_row("B", approver1_empcode="202"),
            _pending_row("C", approver1_empcode="203"),
        ]
        sent = _run_turn_reminders(
            MagicMock(), 2027, dry_run=False, notifications_dry_run=True, now=NOW,
            sleep=sleeps.append, send_delay_seconds=2.0,
        )

    assert sent == 3
    assert sleeps == [2.0, 2.0]  # 3 sends -> 2 sleeps


def test_turn_cap_limits_sends_and_reports_capped_loudly(caplog):
    """§7.3.4: over-cap persons are NOT sent and NOT logged; a 'capped N'
    line is logged loudly — never a silent cap."""
    p_rows, p_last, p_log, p_notify = _patch_turn_phase()
    with p_rows as m_rows, p_last as m_last, p_log as m_log, p_notify as m_notify, \
            caplog.at_level(logging.INFO, logger="jobs.send_reminders"):
        m_notify.side_effect = [_ok_result()]
        m_rows.return_value = [
            _pending_row("A", approver1_empcode="201"),
            _pending_row("B", approver1_empcode="202"),
        ]
        sent = _run_turn_reminders(
            MagicMock(), 2027, dry_run=False, notifications_dry_run=True, now=NOW,
            sleep=MagicMock(), max_sends=1,
        )

    assert sent == 1
    assert m_notify.call_count == 1
    assert m_log.call_count == 1  # the over-cap person got no reminder_log row
    assert "capped 1" in caplog.text


def test_turn_summary_line_reports_counts(caplog):
    """§7.3.5: one closing summary line per phase with all five counters."""
    p_rows, p_last, p_log, p_notify = _patch_turn_phase(
        notify_side_effect=[_ok_result(), RuntimeError("graph down")]
    )
    with p_rows as m_rows, p_last as m_last, p_log as m_log, p_notify as m_notify, \
            caplog.at_level(logging.INFO, logger="jobs.send_reminders"):
        m_rows.return_value = [
            _pending_row("A", approver1_empcode="201"),
            _pending_row("B", approver1_empcode="202"),
        ]
        sent = _run_turn_reminders(
            MagicMock(), 2027, dry_run=False, notifications_dry_run=True, now=NOW, sleep=MagicMock(),
        )

    assert sent == 1
    assert "attempted=2" in caplog.text
    assert "sent=1" in caplog.text
    assert "failed=1" in caplog.text
    assert "retried=0" in caplog.text
    assert "capped=0" in caplog.text


def test_turn_summary_counts_mail_that_needed_a_retry(caplog):
    """§7.3.5: a mail that succeeded only after a retry lands in `retried=1`
    (NotificationResult.retries > 0), not just in sent."""
    p_rows, p_last, p_log, p_notify = _patch_turn_phase()
    with p_rows as m_rows, p_last as m_last, p_log as m_log, p_notify as m_notify, \
            caplog.at_level(logging.INFO, logger="jobs.send_reminders"):
        m_notify.return_value = MagicMock(retries=1)
        m_rows.return_value = [_pending_row()]
        sent = _run_turn_reminders(
            MagicMock(), 2027, dry_run=False, notifications_dry_run=True, now=NOW, sleep=MagicMock(),
        )

    assert sent == 1
    assert "sent=1" in caplog.text
    assert "retried=1" in caplog.text


# ---------------------------------------------------------------------------
# Phase B — deadline reminders, grouped ONE mail per filler
# ---------------------------------------------------------------------------

def _patch_deadline_phase(window=(date(2026, 7, 1), date(2026, 8, 31)), notify_side_effect=None):
    return (
        patch("jobs.send_reminders._deadline_window", return_value=window),
        patch("jobs.send_reminders._find_still_not_submitted_departments"),
        patch("jobs.send_reminders._find_fillers"),
        patch("jobs.send_reminders._last_sent_at", return_value=None),
        patch("jobs.send_reminders._resolve_approver1_cc_email", return_value="vp@chememan.com"),
        patch("jobs.send_reminders._log_reminder"),
        patch(
            "jobs.send_reminders.notifications.notify_deadline_reminder",
            side_effect=notify_side_effect,
            return_value=None if notify_side_effect else _ok_result(),
        ),
    )


def test_deadline_groups_all_departments_into_one_mail_per_filler():
    """§7.1/§7.4.1: a filler with 2 pending departments gets ONE grouped mail
    (was: 2 separate mails before the §7 rework); cadence logged once, keyed
    on the '*' sentinel."""
    patches = _patch_deadline_phase()
    with patches[0], patches[1] as m_depts, patches[2] as m_fillers, patches[3] as m_last, \
            patches[4], patches[5] as m_log, patches[6] as m_notify:
        m_depts.return_value = ["Accounting", "IT"]
        m_fillers.side_effect = lambda conn, dept: ["alice@chememan.com"]
        sent = _run_deadline_reminders(MagicMock(), 2027, dry_run=False, notifications_dry_run=True, today=TODAY)

    assert sent == 1
    m_notify.assert_called_once()
    assert m_notify.call_args.args[0] == "alice@chememan.com"  # To = the filler
    assert m_notify.call_args.args[1] == ["Accounting", "IT"]  # ALL their departments, one mail
    assert m_notify.call_args.kwargs["cc_emails"] == ["vp@chememan.com"]  # ONE manager-derived cc
    m_last.assert_called_once_with(
        ANY, DEADLINE_REMINDER_TYPE, PERSON_SENTINEL, 2027, "alice@chememan.com"
    )
    m_log.assert_called_once()
    assert m_log.call_args.args[1:5] == (DEADLINE_REMINDER_TYPE, PERSON_SENTINEL, 2027, "alice@chememan.com")


def test_deadline_distinct_fillers_get_one_mail_each():
    patches = _patch_deadline_phase()
    with patches[0], patches[1] as m_depts, patches[2] as m_fillers, patches[3], patches[4], \
            patches[5] as m_log, patches[6] as m_notify:
        m_notify.side_effect = [_ok_result(), _ok_result()]
        m_depts.return_value = ["Accounting"]
        m_fillers.return_value = ["alice@chememan.com", "bob@chememan.com"]
        sent = _run_deadline_reminders(
            MagicMock(), 2027, dry_run=False, notifications_dry_run=True, today=TODAY, sleep=MagicMock(),
        )

    assert sent == 2
    assert m_notify.call_count == 2
    assert m_log.call_count == 2


def test_deadline_not_logged_when_send_suppressed_by_notifications_dry_run():
    """Same suppression rule as Phase A (gate finding 2026-07-31, §7.4.10):
    --execute with NOTIFICATIONS_DRY_RUN=true returns sent=False — nothing
    really sent, so the cadence row must NOT be written. Restored after the
    §7 rework dropped the guard once."""
    patches = _patch_deadline_phase()
    with patches[0], patches[1] as m_depts, patches[2] as m_fillers, patches[3], patches[4], \
            patches[5] as m_log, patches[6] as m_notify:
        m_notify.side_effect = None
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


def test_deadline_person_cadence_blocks_rerun_within_7_days():
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
        m_notify.side_effect = [_ok_result(), _ok_result()]
        m_depts.return_value = ["Accounting", "IT"]
        m_fillers.side_effect = lambda conn, dept: [["alice@chememan.com"], ["bob@chememan.com"]][dept == "IT"]
        m_cc.side_effect = [None, "bob@chememan.com"]  # lookup failed / cc == To (bob's own address)
        sent = _run_deadline_reminders(
            MagicMock(), 2027, dry_run=False, notifications_dry_run=True, today=TODAY, sleep=MagicMock(),
        )

    assert sent == 2
    assert m_notify.call_args_list[0].kwargs["cc_emails"] == []
    assert m_notify.call_args_list[1].kwargs["cc_emails"] == []


def test_deadline_failure_isolates_per_filler():
    patches = _patch_deadline_phase(notify_side_effect=[RuntimeError("graph down"), _ok_result()])
    with patches[0], patches[1] as m_depts, patches[2] as m_fillers, patches[3], patches[4], \
            patches[5] as m_log, patches[6] as m_notify:
        m_depts.return_value = ["Accounting"]
        m_fillers.return_value = ["alice@chememan.com", "bob@chememan.com"]
        sent = _run_deadline_reminders(
            MagicMock(), 2027, dry_run=False, notifications_dry_run=True, today=TODAY, sleep=MagicMock(),
        )

    assert sent == 1
    assert m_notify.call_count == 2
    m_log.assert_called_once()
    assert m_log.call_args.args[4] == "bob@chememan.com"


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


def test_deadline_cap_150_of_200_sends_and_reports_capped(caplog):
    """§7.4.8: 200 due fillers, cap 150 -> 150 sent, 50 NOT logged, and a
    loud 'capped 50' line."""
    patches = _patch_deadline_phase()
    fillers = [f"f{i:03d}@chememan.com" for i in range(200)]
    departments = [f"Dept{i:03d}" for i in range(200)]
    filler_of = dict(zip(departments, fillers))
    patches = _patch_deadline_phase()
    with patches[0], patches[1] as m_depts, patches[2] as m_fillers, patches[3], patches[4], \
            patches[5] as m_log, patches[6] as m_notify, \
            caplog.at_level(logging.INFO, logger="jobs.send_reminders"):
        m_notify.side_effect = [_ok_result() for _ in range(150)]
        m_depts.return_value = departments
        m_fillers.side_effect = lambda conn, dept: [filler_of[dept]]
        sent = _run_deadline_reminders(
            MagicMock(), 2027, dry_run=False, notifications_dry_run=True, today=TODAY,
            sleep=MagicMock(), max_sends=150,
        )

    assert sent == 150
    assert m_notify.call_count == 150
    assert m_log.call_count == 150  # the 50 over-cap fillers got no reminder_log row
    assert "capped 50" in caplog.text
    assert "attempted=150" in caplog.text  # summary line reports the round


# ---------------------------------------------------------------------------
# approver1 cc derivation — manager rule, fallback Nipaporn (unchanged §3 rule)
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
# discovery helpers / window parsing (unchanged from §3)
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


def test_deadline_window_parses_reminder_and_deadline_date():
    conn = MagicMock()
    conn.cursor.return_value.fetchone.return_value = (date(2026, 7, 1), date(2026, 8, 31))
    assert _deadline_window(conn, 2027) == (date(2026, 7, 1), date(2026, 8, 31))


def test_deadline_window_queries_the_real_schema_columns():
    """Regression for the 2026-07-31 cross-review catch (reverted once by the
    §7 rework, restored again): the LIVE dbo.submission_deadline stores the
    real closing DATE in `deadline_date`; the column named `closing_date` is
    an INT day-of-month input (31). The query must name `deadline_date` and
    must NOT name `closing_date` — a mocked row can never catch this because
    every mock returns a date for whichever column the code asks for."""
    conn = MagicMock()
    conn.cursor.return_value.fetchone.return_value = (date(2026, 10, 15), date(2026, 10, 31))
    _deadline_window(conn, 2027)
    sql = conn.cursor.return_value.execute.call_args.args[0]
    assert "deadline_date" in sql
    assert "closing_date" not in sql


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
