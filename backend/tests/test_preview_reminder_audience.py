"""Unit tests for setup/preview_reminder_audience.py's pure helpers only:
date projection (window + per-person cadence) and the excluded-department
classification. The "who is due" eligibility rule itself is NOT re-tested
here -- the script imports and reuses jobs.send_reminders' own helpers
unmodified, and those already have full coverage in
test_jobs_send_reminders.py. No live DB, no mocked connection -- both
functions under test take plain values in and return plain values out.
"""
import sys
from datetime import date
from pathlib import Path

# setup/ is a sibling of backend/, not a package under it -- add the repo
# root to sys.path so `from setup import ...` resolves the same way
# backend/tests/tests_data_sync/conftest.py adds backend/ for `jobs`/`app`.
REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.approval import APPROVED, PENDING_APPROVER1, PENDING_APPROVER2, REJECTED  # noqa: E402
from setup.preview_reminder_audience import (  # noqa: E402
    _classify_excluded_departments,
    _interval_days,
    _project_send_dates,
    _resolve_cc_display,
)


# ---------------------------------------------------------------------------
# _interval_days -- Settings.reminder_interval_minutes (minutes) -> whole days
# ---------------------------------------------------------------------------

def test_interval_days_converts_the_production_default():
    assert _interval_days(10080) == 7  # 7 * 24 * 60, the real default


def test_interval_days_clamps_a_staging_override_to_at_least_one_day():
    # a SIT-aid override (a few minutes) can't produce a calendar date
    # cadence below one day
    assert _interval_days(2) == 1


def test_interval_days_rounds_to_the_nearest_whole_day():
    assert _interval_days(20160) == 14  # 14 days


# ---------------------------------------------------------------------------
# _project_send_dates -- per-recipient projected send dates within a window
# ---------------------------------------------------------------------------

def test_project_send_dates_fy2027_example():
    # the exact FY2027 window from dbo.submission_deadline (verified facts)
    dates = _project_send_dates(date(2026, 9, 30), date(2026, 10, 15), interval_days=7)
    assert dates == [date(2026, 9, 30), date(2026, 10, 7), date(2026, 10, 14)]


def test_project_send_dates_excludes_a_date_past_window_end():
    dates = _project_send_dates(date(2026, 9, 30), date(2026, 10, 6), interval_days=7)
    assert dates == [date(2026, 9, 30)]


def test_project_send_dates_includes_window_end_itself():
    # mirrors _run_deadline_reminders: only `today > deadline_date` stops
    # it, so a send exactly ON deadline_date is still allowed
    dates = _project_send_dates(date(2026, 10, 1), date(2026, 10, 8), interval_days=7)
    assert dates == [date(2026, 10, 1), date(2026, 10, 8)]


def test_project_send_dates_shifts_later_for_a_person_already_reminded():
    # last_sent_date 2026-10-01 -> THIS person's own cadence clears 7 days
    # after THEIR last send, not on the window's shared start date
    dates = _project_send_dates(
        date(2026, 9, 30), date(2026, 10, 15), interval_days=7, last_sent_date=date(2026, 10, 1),
    )
    assert dates == [date(2026, 10, 8), date(2026, 10, 15)]


def test_project_send_dates_empty_when_cadence_clears_after_window_end():
    dates = _project_send_dates(
        date(2026, 9, 30), date(2026, 10, 15), interval_days=7, last_sent_date=date(2026, 10, 14),
    )
    assert dates == []


def test_project_send_dates_empty_when_window_is_inverted():
    dates = _project_send_dates(date(2026, 10, 15), date(2026, 9, 30), interval_days=7)
    assert dates == []


# ---------------------------------------------------------------------------
# _classify_excluded_departments -- the "who is NOT mailed, and why" half
# ---------------------------------------------------------------------------

def test_classify_splits_submitted_approved_and_no_filler():
    buckets = _classify_excluded_departments(
        all_departments=["Finance", "HR", "IT", "Legal", "Ops"],
        eligible_departments=["Legal", "Ops"],
        status_by_department={"Finance": PENDING_APPROVER2, "HR": APPROVED, "IT": PENDING_APPROVER1},
        no_filler_departments=["Ops"],
    )
    assert buckets["already submitted, awaiting approval"] == ["Finance", "IT"]
    assert buckets["already approved"] == ["HR"]
    assert buckets["no Filler mapped"] == ["Ops"]
    assert buckets["unexpected status (needs review)"] == []


def test_classify_treats_rejected_as_eligible_not_excluded():
    # REJECTED departments are themselves part of the eligible set upstream
    # (jobs.send_reminders' own `status <> REJECTED` rule) -- a department
    # passed in as eligible must never show up in an excluded bucket
    # regardless of what its approval_status row says.
    buckets = _classify_excluded_departments(
        all_departments=["Finance"],
        eligible_departments=["Finance"],
        status_by_department={"Finance": REJECTED},
        no_filler_departments=[],
    )
    assert buckets["already submitted, awaiting approval"] == []
    assert buckets["already approved"] == []


def test_classify_flags_an_unexpected_status_instead_of_dropping_it():
    buckets = _classify_excluded_departments(
        all_departments=["Weird"],
        eligible_departments=[],
        status_by_department={"Weird": "SOME_FUTURE_STATUS"},
        no_filler_departments=[],
    )
    assert buckets["unexpected status (needs review)"] == ["Weird (status='SOME_FUTURE_STATUS')"]


def test_classify_no_filler_bucket_is_sorted():
    buckets = _classify_excluded_departments(
        all_departments=[],
        eligible_departments=["Z-dept", "A-dept"],
        status_by_department={},
        no_filler_departments=["Z-dept", "A-dept"],
    )
    assert buckets["no Filler mapped"] == ["A-dept", "Z-dept"]


# ---------------------------------------------------------------------------
# _resolve_cc_display -- mirrors _run_deadline_reminders' own cc == To skip
# ---------------------------------------------------------------------------

def test_resolve_cc_display_shows_the_resolved_approver():
    assert _resolve_cc_display("filler@chememan.com", "manager@chememan.com") == "manager@chememan.com"


def test_resolve_cc_display_flags_an_unresolvable_approver():
    assert "could not be resolved" in _resolve_cc_display("filler@chememan.com", None)


def test_resolve_cc_display_flags_cc_equal_to_recipient_case_insensitively():
    display = _resolve_cc_display("Filler@Chememan.com", "filler@chememan.com")
    assert "skipped" in display
