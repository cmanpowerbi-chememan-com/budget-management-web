"""Read-only preview of the pre-deadline reminder mail blast radius, BEFORE
jakkaritw decides whether to switch `jobs.send_reminders` Phase B on for a
fiscal year.

Why a plain dry run of the job cannot answer this: `jobs.send_reminders`
only ever looks at TODAY. `_run_deadline_reminders` returns 0 the instant
`today < reminder_date` -- for FY2027 (`reminder_date` 2026-09-30,
`deadline_date` 2026-10-15) any dry run before 30 September lists nobody,
which proves nothing about who WOULD be mailed once the window opens. This
script reuses the exact same eligibility rule but reports the WHOLE
upcoming window instead of only today, so the go-live decision can be made
now, two weeks early.

Eligibility (who is due, who is grouped how, who is cc'd, the per-person
7-day cadence, the per-run cap) is 100% delegated to `jobs.send_reminders` --
this file imports and calls its private helpers rather than re-implementing
any of that rule, so the preview can never drift from what the real job
would do. The only NEW logic here is reporting-only: projecting the send
DATES a fixed window+cadence implies, and classifying departments that
would NOT be mailed by reason (already submitted, already approved, no
Filler mapped, year not open) -- neither of which the job itself needs,
since it only ever asks "is this due right now", never "what does the
whole window look like".

SELECT ONLY. This script never opens a write transaction, never logs a
`budget.reminder_log` row, and never calls `app.notifications.send_mail`.

Run (from the repo root):
    python -X utf8 setup/preview_reminder_audience.py --fiscal-year 2027
"""
import argparse
import sys
from datetime import date, timedelta
from pathlib import Path
from typing import NamedTuple

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from app.approval import APPROVED, PENDING_APPROVER1, PENDING_APPROVER2, PENDING_APPROVER3  # noqa: E402
from app.config import get_settings  # noqa: E402
from app.db import get_fabric_conn  # noqa: E402
from app.deadline import bangkok_today  # noqa: E402
from jobs.common import configure_logging  # noqa: E402
from jobs.send_reminders import (  # noqa: E402
    DEADLINE_REMINDER_TYPE,
    PERSON_SENTINEL,
    _apply_cap,
    _deadline_window,
    _find_fillers,
    _find_still_not_submitted_departments,
    _last_sent_at,
    _naive,
    _resolve_approver1_cc_email,
    _resolve_interval_minutes,
)

MINUTES_PER_DAY = 24 * 60
_RULE_WIDTH = 78


class Recipient(NamedTuple):
    """One row of the preview: the mail `_run_deadline_reminders` would
    send this Filler, and the dates it would repeat on."""

    filler_email: str
    departments: list[str]
    cc_display: str
    dates: list[date]


# ---------------------------------------------------------------------------
# Pure helpers (unit tested in backend/tests/test_preview_reminder_audience.py)
# ---------------------------------------------------------------------------

def _interval_days(interval_minutes: int) -> int:
    """Whole-day cadence for a calendar-date projection. The real per-person
    gate (`_deadline_due`) compares at MINUTE granularity so a staging-only
    override of a few minutes can be tested without a 7-day wait (see
    `Settings.reminder_interval_minutes`) -- but a preview of calendar SEND
    DATES cannot show a fraction of a day, so this rounds to the nearest
    whole day and clamps to a minimum of 1."""
    return max(1, round(interval_minutes / MINUTES_PER_DAY))


def _project_send_dates(
    window_start: date,
    window_end: date,
    interval_days: int,
    last_sent_date: date | None = None,
) -> list[date]:
    """Dates within `[window_start, window_end]` (inclusive) this ONE
    recipient would be mailed, assuming nobody acts on any of their pending
    departments. Mirrors `_deadline_due`'s own gate: due immediately if
    never sent, otherwise not due again until `interval_days` after their
    OWN last send -- so a recipient already reminded once gets a later
    first date than the window's shared start. The `<=` end bound mirrors
    `_run_deadline_reminders`'s own stop condition (`today > deadline_date`
    stops it), which still allows a send exactly ON deadline_date."""
    first = window_start
    if last_sent_date is not None:
        first = max(first, last_sent_date + timedelta(days=interval_days))
    dates: list[date] = []
    current = first
    while current <= window_end:
        dates.append(current)
        current += timedelta(days=interval_days)
    return dates


def _resolve_cc_display(filler_email: str, cc_email: str | None) -> str:
    """Human-readable cc value for the report, mirroring
    `_run_deadline_reminders`'s own cc rule exactly (never cc the filler
    themselves) so the preview can never claim a cc the real mail would not
    actually carry."""
    if cc_email is None:
        return "(none -- approver1 e-mail could not be resolved)"
    if cc_email.lower() == filler_email.lower():
        return "(none -- resolved approver1 is the filler themselves, skipped)"
    return cc_email


def _classify_excluded_departments(
    all_departments: list[str],
    eligible_departments: list[str],
    status_by_department: dict[str, str],
    no_filler_departments: list[str],
) -> dict[str, list[str]]:
    """Buckets every department that would NOT be mailed, by reason -- the
    "who is NOT reminded" half, which the job itself never has to answer
    (it only ever asks "is this due", never "why isn't that one"). A
    department in `eligible_departments` (DRAFT, or REJECTED -- both count
    as eligible per `_find_still_not_submitted_departments`'s own `status
    <> REJECTED` rule) is never excluded here regardless of any stale
    approval_status row; `no_filler_departments` are eligible departments
    with zero mapped Fillers, computed by the caller via `_find_fillers`."""
    eligible = set(eligible_departments)
    buckets: dict[str, list[str]] = {
        "already submitted, awaiting approval": [],
        "already approved": [],
        "no Filler mapped": sorted(no_filler_departments),
        "unexpected status (needs review)": [],
    }
    for department in all_departments:
        if department in eligible:
            continue
        status = status_by_department.get(department)
        if status in (PENDING_APPROVER1, PENDING_APPROVER2, PENDING_APPROVER3):
            buckets["already submitted, awaiting approval"].append(department)
        elif status == APPROVED:
            buckets["already approved"].append(department)
        else:
            buckets["unexpected status (needs review)"].append(f"{department} (status={status!r})")
    return buckets


# ---------------------------------------------------------------------------
# Reporting-only DB reads -- classification detail the job never needs.
# The eligibility RULE (who is due) never lives here; it is always imported
# from jobs.send_reminders above.
# ---------------------------------------------------------------------------

def _fetch_all_departments(conn) -> list[str]:
    """Every department `dbo.cc_filler_map` knows about -- the same universe
    `_find_still_not_submitted_departments` draws from."""
    cursor = conn.cursor()
    try:
        cursor.execute(
            "SELECT DISTINCT department FROM dbo.cc_filler_map "
            "WHERE department IS NOT NULL ORDER BY department"
        )
        rows = cursor.fetchall()
    finally:
        cursor.close()
    return [row[0] for row in rows]


def _fetch_department_statuses(conn, fiscal_year: int) -> dict[str, str]:
    """department -> status for every `budget.approval_status` row this
    fiscal year. PK is `(department, fiscal_year)` -- one row per
    department per year, so this dict is never ambiguous."""
    cursor = conn.cursor()
    try:
        cursor.execute(
            "SELECT department, status FROM budget.approval_status WHERE fiscal_year = ?",
            fiscal_year,
        )
        rows = cursor.fetchall()
    finally:
        cursor.close()
    return {row[0]: row[1] for row in rows}


def _group_by_filler(conn, eligible_departments: list[str]) -> tuple[dict[str, list[str]], list[str]]:
    """Mirrors `_run_deadline_reminders`'s own `by_filler` grouping loop
    exactly (same `_find_fillers` call, same accumulation), so the
    recipient list can never drift from what the real job would build.
    Departments with zero mapped Fillers are returned separately -- the
    "no Filler mapped" exclusion reason, not silently dropped."""
    by_filler: dict[str, list[str]] = {}
    no_filler_departments: list[str] = []
    for department in eligible_departments:
        fillers = _find_fillers(conn, department)
        if not fillers:
            no_filler_departments.append(department)
            continue
        for filler_email in fillers:
            by_filler.setdefault(filler_email, []).append(department)
    return by_filler, no_filler_departments


def _build_recipients(
    conn,
    fiscal_year: int,
    by_filler: dict[str, list[str]],
    window_start: date,
    window_end: date,
    interval_days: int,
) -> tuple[list[Recipient], int]:
    """One `Recipient` per Filler in `by_filler` who still has >=1
    projected send date, sorted by e-mail. `last_sent_at` (reused from
    jobs.send_reminders) makes this correct whether the window has not
    opened yet (everyone's `last_sent` is None) or the preview is re-run
    mid-window (some already have one logged send). A Filler whose OWN
    cadence already clears the rest of the window is counted in
    `already_clear`, not listed -- they would receive no further mail."""
    recipients: list[Recipient] = []
    already_clear = 0
    for filler_email in sorted(by_filler):
        departments = sorted(by_filler[filler_email])
        last_sent = _last_sent_at(conn, DEADLINE_REMINDER_TYPE, PERSON_SENTINEL, fiscal_year, filler_email)
        last_sent_date = _naive(last_sent).date() if last_sent is not None else None
        dates = _project_send_dates(window_start, window_end, interval_days, last_sent_date)
        if not dates:
            already_clear += 1
            continue
        cc_email = _resolve_approver1_cc_email(conn, filler_email)
        recipients.append(Recipient(filler_email, departments, _resolve_cc_display(filler_email, cc_email), dates))
    return recipients, already_clear


# ---------------------------------------------------------------------------
# Printing
# ---------------------------------------------------------------------------

def _print_header(
    fiscal_year: int, today: date, reminder_date: date, deadline_date: date,
    interval_minutes: int, interval_days: int, max_sends: int, send_delay_seconds: float,
) -> None:
    print("=" * _RULE_WIDTH)
    print(f" Deadline-reminder audience preview -- fiscal year {fiscal_year}")
    print(" READ-ONLY: reuses jobs.send_reminders' own eligibility rules.")
    print("=" * _RULE_WIDTH)
    print(f"Today (Asia/Bangkok)   : {today.isoformat()}")
    print(
        f"Configured window      : reminder_date={reminder_date.isoformat()} "
        f".. deadline_date={deadline_date.isoformat()}  (dbo.submission_deadline)"
    )
    print(
        f"Per-person cadence     : every {interval_days} day(s) "
        f"(Settings.reminder_interval_minutes={interval_minutes})"
    )
    print(
        f"Per-run cap / pacing   : {max_sends} per run / {send_delay_seconds}s between sends "
        f"(Settings.reminder_max_sends_per_run / reminder_send_delay_seconds)"
    )
    if today < reminder_date:
        print(
            "NOTE: today is BEFORE the window opens -- a plain dry run of the real job would list "
            "NOBODY right now. Everything below is PROJECTED for the whole window, assuming nobody "
            "submits or gets approved between now and then, and nobody acts on a reminder once sent."
        )
    elif today > deadline_date:
        print(
            "NOTE: today is AFTER the window closed -- the real job would send nothing further this "
            "year. This shows what the full schedule would have looked like."
        )
    else:
        print("NOTE: today is INSIDE the window -- any date below already passed would already have been sent.")
    print()


def _print_recipients(recipients: list[Recipient], already_clear: int) -> None:
    print("-" * _RULE_WIDTH)
    print(f"Recipients -- {len(recipients)} Filler(s) would be mailed")
    print("-" * _RULE_WIDTH)
    if not recipients:
        print("(none -- see the exclusions below for why)")
    for r in recipients:
        dates_display = ", ".join(d.isoformat() for d in r.dates)
        print(f"* {r.filler_email}")
        print(f"    departments : {', '.join(r.departments)}")
        print(f"    cc approver : {r.cc_display}")
        print(
            f"    send dates  : {dates_display}  "
            f"({len(r.dates)} mail(s); assumes no action is taken on any listed department)"
        )
    if already_clear:
        print(
            f"\n({already_clear} additional Filler(s) already have a reminder logged recently enough that "
            "their own cadence clears before the window ends -- 0 further mails, not counted above)"
        )
    print()


def _print_exclusions(buckets: dict[str, list[str]]) -> None:
    print("-" * _RULE_WIDTH)
    total_excluded = sum(len(v) for v in buckets.values())
    print(f"Departments that would NOT be mailed -- {total_excluded} department(s), by reason")
    print("-" * _RULE_WIDTH)
    for reason in ("already submitted, awaiting approval", "already approved", "no Filler mapped"):
        depts = buckets[reason]
        print(f"{reason} ({len(depts)}):")
        print(f"    {', '.join(depts) if depts else '(none)'}")
    unexpected = buckets["unexpected status (needs review)"]
    if unexpected:
        print(f"UNEXPECTED status, needs review ({len(unexpected)}):")
        print(f"    {', '.join(unexpected)}")
    print()


def _print_control_totals(
    recipients: list[Recipient], fiscal_year: int, max_sends: int, send_delay_seconds: float,
) -> None:
    print("-" * _RULE_WIDTH)
    print("Control totals")
    print("-" * _RULE_WIDTH)
    print(f"Recipients             : {len(recipients)}")
    total_mails = sum(len(r.dates) for r in recipients)
    print(f"Total mails in window   : {total_mails}")
    if not recipients:
        print()
        return

    by_date: dict[date, list[str]] = {}
    for r in recipients:
        for d in r.dates:
            by_date.setdefault(d, []).append(r.filler_email)

    largest_date = max(by_date, key=lambda d: len(by_date[d]))
    print(f"Largest single day      : {len(by_date[largest_date])} mail(s) on {largest_date.isoformat()}")
    print()
    print("Per-date volume vs the per-run cap and pacing:")
    for d in sorted(by_date):
        due_this_day = by_date[d]
        to_send, capped = _apply_cap(due_this_day, max_sends, DEADLINE_REMINDER_TYPE, fiscal_year)
        pacing_minutes = ((len(to_send) - 1) * send_delay_seconds) / 60 if to_send else 0.0
        if capped:
            print(
                f"  {d.isoformat()}: {len(due_this_day)} mail(s) due -> EXCEEDS the {max_sends}-per-run cap: "
                f"{len(to_send)} would send, {capped} would be skipped that day "
                "(not logged -- they stay due and are swept up on a later run)"
            )
        else:
            print(
                f"  {d.isoformat()}: {len(due_this_day)} mail(s) -> under the {max_sends}-per-run cap "
                f"(~{pacing_minutes:.1f} min at {send_delay_seconds}s pacing)"
            )
    print()


def _print_footer() -> None:
    print("=" * _RULE_WIDTH)
    print("ZERO writes performed. ZERO mail sent. This is a read-only preview.")
    print("=" * _RULE_WIDTH)


def _print_year_not_open(fiscal_year: int) -> None:
    print("=" * _RULE_WIDTH)
    print(f" Deadline-reminder audience preview -- fiscal year {fiscal_year}")
    print("=" * _RULE_WIDTH)
    print(
        f"dbo.submission_deadline has no row for fiscal_year={fiscal_year} (or its reminder_date "
        "is blank) -- deadline reminders are OFF for this year (YEAR NOT OPEN for deadline "
        "reminders). jobs.send_reminders would compute nothing either; there is no window to preview."
    )
    print("Recipients: 0. Total mails: 0.")
    _print_footer()


def _print_open_ended_window(fiscal_year: int, reminder_date: date) -> None:
    print("=" * _RULE_WIDTH)
    print(f" Deadline-reminder audience preview -- fiscal year {fiscal_year}")
    print("=" * _RULE_WIDTH)
    print(
        f"dbo.submission_deadline has reminder_date={reminder_date.isoformat()} but no deadline_date "
        f"for fiscal_year={fiscal_year} -- the window has no configured end, so a finite send "
        "schedule cannot be projected. Set deadline_date first."
    )
    print("Recipients: 0. Total mails: 0.")
    _print_footer()


# ---------------------------------------------------------------------------
# entry point
# ---------------------------------------------------------------------------

def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Read-only preview of the whole upcoming deadline-reminder window: who would be "
            "mailed, how many mails each person gets, on which dates, and who is deliberately "
            "excluded and why. Reuses jobs.send_reminders' own eligibility rules -- SELECT ONLY, "
            "never writes, never sends mail."
        )
    )
    parser.add_argument(
        "--fiscal-year", type=int, required=True,
        help="the planning year to preview (no auto-detect -- same rule the jobs follow)",
    )
    return parser.parse_args()


def main() -> int:
    configure_logging()
    args = _parse_args()
    fiscal_year = args.fiscal_year
    settings = get_settings()

    with get_fabric_conn(settings) as conn:
        window = _deadline_window(conn, fiscal_year)
        if window is None:
            _print_year_not_open(fiscal_year)
            return 0
        reminder_date, deadline_date = window
        if deadline_date is None:
            _print_open_ended_window(fiscal_year, reminder_date)
            return 0

        interval_minutes = _resolve_interval_minutes(None)
        interval_days = _interval_days(interval_minutes)
        today = bangkok_today()
        _print_header(
            fiscal_year, today, reminder_date, deadline_date, interval_minutes, interval_days,
            settings.reminder_max_sends_per_run, settings.reminder_send_delay_seconds,
        )

        eligible_departments = _find_still_not_submitted_departments(conn, fiscal_year)
        by_filler, no_filler_departments = _group_by_filler(conn, eligible_departments)
        recipients, already_clear = _build_recipients(
            conn, fiscal_year, by_filler, reminder_date, deadline_date, interval_days,
        )
        _print_recipients(recipients, already_clear)

        all_departments = _fetch_all_departments(conn)
        status_by_department = _fetch_department_statuses(conn, fiscal_year)
        buckets = _classify_excluded_departments(
            all_departments, eligible_departments, status_by_department, no_filler_departments,
        )
        _print_exclusions(buckets)

        _print_control_totals(
            recipients, fiscal_year, settings.reminder_max_sends_per_run, settings.reminder_send_delay_seconds,
        )
        _print_footer()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
