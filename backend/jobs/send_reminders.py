"""A12 scheduled job (automation D) — reminder emails, §7 rework
(plan/email-notify-revamp.md §7, 2026-07-31): GROUPED one-mail-per-person
reminders + bulk-send hardening. TWO phases in ONE job (no new job created):

Phase A — TURN reminders: ONE mail per APPROVER listing every department
currently waiting on them (`notify_turn_reminder`), each row with that
department's days-pending. Due gate is per PERSON: they are due when ≥1 of
their pending items is ≥7 days old (turn_start from
`app.approval.current_turn_info`) AND their person-level cadence is clear
(never reminded, or last reminder ≥7 days ago). Reminders repeat every 7
days FOREVER until the approver acts (ADR-0027: no end date, no cap, no cc
escalation). The mail CONTENT is always ALL departments waiting
on them, including ones younger than 7 days (spec §7.1: "ลิสต์ทุกฝ่ายที่รอ
เขาอยู่") — the 7-day gate throttles the person, not the row.

Phase B — DEADLINE reminders: ONE mail per FILLER listing every
still-not-submitted department they Fill (NO approval_status row = DRAFT,
or status REJECTED — departments already in the chain are Phase A's job,
never both), each row with its own deep link. To the filler, cc the derived
approver1 (the filler's `manager_employee_code` from
`dbo.v_employee_budget_01`, fallback Nipaporn — the same rule
`app.approval.resolve_chain` freezes at submit time, ONE address).

Cadence bookkeeping lives in `budget.reminder_log` (db/ddl/budget_reminder_log.sql),
keyed per PERSON per year on the '*' department sentinel (the mail is no
longer about one department): ('turn','*',fy,empcode) /
('deadline','*',fy,filler_email). Accepted trade-off (§7.2, documented in
the DDL): cadence is per-person-per-year, so a department that newly goes
pending mid-week does NOT trigger a fresh mail immediately — it rides the
person's next 7-day round (event mails at submit/approve/reject still fire
instantly, so nobody misses work). Updated after each SUCCESSFUL send only;
a failed mail is never logged, so it is retried on the next run. Dry-run
never sends and never writes the log.

Bulk-send hardening (§7.3): the Graph token is fetched once per round
(module-level cache in app.notifications), transient 429/503/504 are
retried with Retry-After/backoff inside `send_mail`, the job PACES sends
(`reminder_send_delay_seconds`, injectable sleep) and CAPS each phase
(`reminder_max_sends_per_run`, 0 = unlimited — over-cap recipients are
skipped loudly via a "capped N" line and get no log row, so next run
reminds them), and each phase closes with ONE summary line:
attempted/sent/failed/retried/capped (`retried` = mails that needed ≥1
retry attempt). Per-recipient failure isolation + conn.rollback() unchanged.

Run (from `backend/`):
    python -m jobs.send_reminders --fiscal-year 2027            # dry-run preview (default)
    python -m jobs.send_reminders --fiscal-year 2027 --execute  # actually send

The old gate is unchanged: `--execute` + `DRY_RUN=false` (jobs/common.py,
untouched) + `Settings.notifications_dry_run` for the actual Graph send.
"""
import logging
import time
from datetime import date, datetime, timezone
from typing import Callable

from app import notifications
from app.approval import (
    NIPAPORN_EMPCODE,
    REJECTED,
    current_turn_info,
    fetch_pending_rows,
    resolve_submitter,
)
from app.config import get_settings
from app.db import get_fabric_conn
from app.deadline import bangkok_today
from app.notifications import lookup_email_by_empcode
from jobs.common import add_common_args, configure_logging, is_dry_run

logger = logging.getLogger("jobs.send_reminders")

TURN_REMINDER_TYPE = "turn"
DEADLINE_REMINDER_TYPE = "deadline"
REMINDER_INTERVAL_DAYS = 7
# §7.2: reminder mails are grouped per PERSON, so the reminder_log
# `department` column carries this sentinel instead of a real ฝ่าย.
PERSON_SENTINEL = "*"


# ---------------------------------------------------------------------------
# reminder_log bookkeeping (budget.reminder_log, plan §3.3 + §7.2)
# ---------------------------------------------------------------------------

def _last_sent_at(conn, reminder_type: str, department: str, fiscal_year: int, recipient: str) -> datetime | None:
    """MAX(sent_at) ever logged for this exact (type, department, year,
    recipient) — None when never reminded. Since §7.2 `department` is the
    '*' sentinel for both types (mails are per-person now), so a person's
    cadence follows THEM, not any single department."""
    cursor = conn.cursor()
    try:
        cursor.execute(
            "SELECT MAX(sent_at) FROM budget.reminder_log "
            "WHERE reminder_type = ? AND department = ? AND fiscal_year = ? AND recipient = ?",
            reminder_type, department, fiscal_year, recipient,
        )
        row = cursor.fetchone()
    finally:
        cursor.close()
    return row[0] if row else None


def _log_reminder(conn, reminder_type: str, department: str, fiscal_year: int, recipient: str, sent_at: datetime) -> None:
    """Upsert the cadence row AFTER a successful send only (callers never
    reach here on failure, cap, or dry-run — those recipients must be
    retried next run). UPDATE-first keeps the PK (reminder_type, department,
    fiscal_year, recipient) stable across repeats."""
    cursor = conn.cursor()
    try:
        cursor.execute(
            "UPDATE budget.reminder_log SET sent_at = ? "
            "WHERE reminder_type = ? AND department = ? AND fiscal_year = ? AND recipient = ?",
            sent_at, reminder_type, department, fiscal_year, recipient,
        )
        if cursor.rowcount == 0:
            cursor.execute(
                "INSERT INTO budget.reminder_log (reminder_type, department, fiscal_year, recipient, sent_at) "
                "VALUES (?, ?, ?, ?, ?)",
                reminder_type, department, fiscal_year, recipient, sent_at,
            )
    finally:
        cursor.close()
    conn.commit()


def _naive(dt: datetime) -> datetime:
    """Naive-UTC comparison (SQL Server DATETIME2 carries no offset; never
    crash on a tz mismatch, whether pyodbc returned tz-aware or naive)."""
    return dt.replace(tzinfo=None) if dt.tzinfo is not None else dt


def _person_cadence_clear(last_sent: datetime | None, now: datetime) -> bool:
    """§7 person-level 7-day cadence: clear when this PERSON was never
    reminded, or their last reminder went out >= 7 days ago. Replaces the
    per-(department, recipient) cadence of the first revamp — the reminder
    mail is grouped per person now, so the throttle is per person too."""
    if last_sent is None:
        return True
    return (_naive(now) - _naive(last_sent)).days >= REMINDER_INTERVAL_DAYS


def _deadline_due(last_sent: datetime | None, today: date) -> bool:
    """Deadline-phase person cadence (date-granularity twin of
    `_person_cadence_clear`): due when never sent, or the last send was
    >= 7 days ago. (The window check — reminder_date..closing_date —
    happens once per run in `_run_deadline_reminders`, not here.)"""
    if last_sent is None:
        return True
    return (today - _naive(last_sent).date()).days >= REMINDER_INTERVAL_DAYS


def _apply_cap(due: list, max_sends: int, phase: str, fiscal_year: int) -> tuple[list, int]:
    """§7.3.4 per-phase send cap (0 = unlimited). Over-cap recipients are
    NOT sent and NOT logged — never silently: a loud 'capped N' line is
    written so a partial round is always visible in the job log."""
    if not max_sends or len(due) <= max_sends:
        return due, 0
    capped = len(due) - max_sends
    logger.warning(
        "fiscal_year=%s phase=%s: %d recipient(s) due but cap is %d — capped %d (not sent, not logged; next run retries)",
        fiscal_year, phase, len(due), max_sends, capped,
    )
    return due[:max_sends], capped


# ---------------------------------------------------------------------------
# Phase A — turn reminders, ONE grouped mail per approver (PENDING_APPROVER1/2/3)
# ---------------------------------------------------------------------------

def _run_turn_reminders(
    conn, fiscal_year: int, dry_run: bool, notifications_dry_run: bool, now: datetime,
    *, sleep: Callable[[float], None] = time.sleep, send_delay_seconds: float = 2.0, max_sends: int = 150,
) -> int:
    rows = fetch_pending_rows(conn, fiscal_year)
    by_approver: dict[str, list[tuple[str, int]]] = {}  # empcode -> [(department, days_pending)]
    for row in rows:
        turn_start, approver_empcode = current_turn_info(row)
        if not approver_empcode:
            logger.warning(
                "department=%r status=%s has no current approver to remind — skipped",
                row["department"], row["status"],
            )
            continue
        days_pending = (_naive(now) - _naive(turn_start)).days
        by_approver.setdefault(approver_empcode, []).append((row["department"], days_pending))

    # Per-person due gate: >=1 item aged >=7d AND the person's own 7-day
    # cadence is clear. Content is always ALL their pending items (younger
    # ones ride along — see module docstring).
    due: list[tuple[str, list[tuple[str, int]]]] = []
    for approver_empcode, items in by_approver.items():
        if not any(days >= REMINDER_INTERVAL_DAYS for _, days in items):
            continue
        last_sent = _last_sent_at(conn, TURN_REMINDER_TYPE, PERSON_SENTINEL, fiscal_year, approver_empcode)
        if _person_cadence_clear(last_sent, now):
            due.append((approver_empcode, items))

    if not due:
        logger.info("fiscal_year=%s: 0 turn reminder(s) due", fiscal_year)
        return 0

    to_send, capped = _apply_cap(due, max_sends, TURN_REMINDER_TYPE, fiscal_year)

    if dry_run:
        for approver_empcode, items in to_send:
            logger.info(
                "[DRY-RUN] would send turn reminder approver=%s departments=%s",
                approver_empcode, [dept for dept, _ in items],
            )
        return len(to_send)

    attempted = sent = failed = retried = 0
    for i, (approver_empcode, items) in enumerate(to_send):
        if i:
            sleep(send_delay_seconds)  # §7.3.2 pacing: N sends -> N-1 sleeps
        attempted += 1
        try:
            result = notifications.notify_turn_reminder(
                conn, approver_empcode=approver_empcode,
                items=[(dept, fiscal_year, days) for dept, days in items],
                dry_run=notifications_dry_run,
            )
            if result is None or not result.sent:
                # Email unresolvable — or suppressed by NOTIFICATIONS_DRY_RUN
                # under a manual --execute BEFORE the go-live flip: nothing
                # REALLY sent, so nothing logged; the person stays due and the
                # first real send after the flip is never swallowed by a stale
                # cadence row (gate finding 2026-07-31).
                failed += 1
                continue
            _log_reminder(conn, TURN_REMINDER_TYPE, PERSON_SENTINEL, fiscal_year, approver_empcode, now)
            sent += 1
            if result.retries:
                retried += 1  # mails that needed >=1 retry attempt (§7.3.5)
        except Exception:
            conn.rollback()
            failed += 1
            logger.exception("turn reminder failed for approver=%r — continuing with next person", approver_empcode)

    logger.info(
        "fiscal_year=%s phase=turn summary: attempted=%d sent=%d failed=%d retried=%d capped=%d",
        fiscal_year, attempted, sent, failed, retried, capped,
    )
    return sent


# ---------------------------------------------------------------------------
# Phase B — deadline reminders, ONE grouped mail per filler (DRAFT / REJECTED)
# ---------------------------------------------------------------------------

def _deadline_window(conn, fiscal_year: int) -> tuple[date, date | None] | None:
    """`(reminder_date, deadline_date)` from `dbo.submission_deadline` — the
    existing, Nipaporn-maintained config row (plan §1: no new config). None
    when no row is configured or reminder_date is NULL — a missing config
    means "never remind", mirroring the old `_reminder_date_reached` posture.
    `deadline_date` may itself be NULL (window then has no stop date).

    ⚠ Column-name trap (verified against the LIVE table 2026-07-31): the real
    closing DATE lives in `deadline_date` — the column literally named
    `closing_date` is an INT day-of-month input (31) alongside closing_month/
    closing_year, NOT a date. Querying `closing_date` here made the window
    compare a date against 31 and killed the whole job (caught in
    cross-review, reverted once by accident, now guarded by
    `test_deadline_window_queries_the_real_schema_columns`)."""
    cursor = conn.cursor()
    try:
        cursor.execute(
            "SELECT reminder_date, deadline_date FROM dbo.submission_deadline WHERE fiscal_year = ?",
            fiscal_year,
        )
        row = cursor.fetchone()
    finally:
        cursor.close()
    if row is None or row[0] is None:
        return None
    return row[0], row[1]


def _find_still_not_submitted_departments(conn, fiscal_year: int) -> list[str]:
    """Scope lock (plan §1): departments with NO approval_status row (DRAFT)
    or a REJECTED row only — anything already in the chain (PENDING_*) or
    APPROVED is excluded here; PENDING_* belongs to Phase A turn reminders
    so a department is never double-reminded."""
    cursor = conn.cursor()
    try:
        cursor.execute(
            """
            SELECT DISTINCT department FROM dbo.cc_filler_map
            WHERE department IS NOT NULL AND department NOT IN (
                SELECT department FROM budget.approval_status
                WHERE fiscal_year = ? AND status <> ?
            )
            ORDER BY department
            """,
            fiscal_year, REJECTED,
        )
        rows = cursor.fetchall()
    finally:
        cursor.close()
    return [row[0] for row in rows]


def _find_fillers(conn, department: str) -> list[str]:
    """Every Filler email mapped to this department in `dbo.cc_filler_map`
    (ADR-0019 Filler-set source of truth)."""
    cursor = conn.cursor()
    try:
        cursor.execute(
            "SELECT DISTINCT filler_email FROM dbo.cc_filler_map "
            "WHERE department = ? AND filler_email IS NOT NULL AND LTRIM(RTRIM(filler_email)) <> ''",
            department,
        )
        rows = cursor.fetchall()
    finally:
        cursor.close()
    return [row[0] for row in rows]


def _resolve_approver1_cc_email(conn, filler_email: str) -> str | None:
    """Derived approver1 for a not-yet-submitted department (plan §1 locked
    decision): the SAME rule `app.approval.resolve_chain` freezes at submit
    time — the filler's `manager_employee_code` from
    `dbo.v_employee_budget_01`, fallback Nipaporn — resolved to an email.
    None when the email lookup finds nothing (caller sends without cc)."""
    _, manager_empcode = resolve_submitter(conn, filler_email)
    try:
        return lookup_email_by_empcode(conn, manager_empcode or NIPAPORN_EMPCODE)
    except Exception:
        logger.warning("approver1 cc lookup failed for filler=%r — sending without cc", filler_email)
        return None


def _run_deadline_reminders(
    conn, fiscal_year: int, dry_run: bool, notifications_dry_run: bool, today: date,
    *, sleep: Callable[[float], None] = time.sleep, send_delay_seconds: float = 2.0, max_sends: int = 150,
    now: datetime | None = None,
) -> int:
    # `now` stamps reminder_log rows (injectable for deterministic tests, same
    # clock Phase A uses); `today` drives the reminder/closing window.
    now = now or datetime.now(timezone.utc)
    window = _deadline_window(conn, fiscal_year)
    if window is None:
        logger.info(
            "fiscal_year=%s: no submission_deadline row (or no reminder_date) configured "
            "— no deadline reminders", fiscal_year,
        )
        return 0
    reminder_date, deadline_date = window
    if today < reminder_date:
        logger.info("fiscal_year=%s: reminder_date %s not yet reached — no deadline reminders", fiscal_year, reminder_date)
        return 0
    if deadline_date is not None and today > deadline_date:
        logger.info("fiscal_year=%s: deadline_date %s has passed — deadline reminders stopped", fiscal_year, deadline_date)
        return 0

    departments = _find_still_not_submitted_departments(conn, fiscal_year)
    if not departments:
        logger.info("fiscal_year=%s: 0 still-not-submitted department(s) — nothing to remind", fiscal_year)
        return 0

    # Group by filler: ONE mail per person listing ALL their pending
    # departments (§7.1 — the per-ฝ่าย mail of the first revamp is gone).
    by_filler: dict[str, list[str]] = {}
    for department in departments:
        for filler_email in _find_fillers(conn, department):
            by_filler.setdefault(filler_email, []).append(department)

    # Per-person due gate: inside the reminder window (checked above) AND
    # the person's own 7-day cadence is clear. Content is always ALL their
    # pending departments.
    due: list[tuple[str, list[str]]] = []
    for filler_email, depts in by_filler.items():
        last_sent = _last_sent_at(conn, DEADLINE_REMINDER_TYPE, PERSON_SENTINEL, fiscal_year, filler_email)
        if _deadline_due(last_sent, today):
            due.append((filler_email, sorted(depts)))

    if not due:
        logger.info("fiscal_year=%s: 0 deadline reminder(s) due", fiscal_year)
        return 0

    to_send, capped = _apply_cap(due, max_sends, DEADLINE_REMINDER_TYPE, fiscal_year)

    if dry_run:
        for filler_email, depts in to_send:
            logger.info("[DRY-RUN] would send deadline reminder filler=%s departments=%s", filler_email, depts)
        return len(to_send)

    attempted = sent = failed = retried = 0
    for i, (filler_email, depts) in enumerate(to_send):
        if i:
            sleep(send_delay_seconds)  # §7.3.2 pacing: N sends -> N-1 sleeps
        attempted += 1
        try:
            cc_email = _resolve_approver1_cc_email(conn, filler_email)
            # Never cc the filler themselves (same rule as notify_reject /
            # notify_approved's cc == To skip, plan §3.1).
            cc_emails = [cc_email] if cc_email and cc_email.lower() != filler_email.lower() else []
            result = notifications.notify_deadline_reminder(
                # The email's `closing_date` display arg is fed from the
                # schema's `deadline_date` (the real closing DATE) — NOT from
                # the int day-of-month column named `closing_date`.
                filler_email, depts, fiscal_year, deadline_date,
                cc_emails=cc_emails, dry_run=notifications_dry_run,
            )
            if result is None or not result.sent:
                # Unresolvable — or suppressed by NOTIFICATIONS_DRY_RUN under
                # a manual --execute BEFORE the go-live flip: nothing REALLY
                # sent, so nothing logged (else a stale cadence row swallows
                # the first real reminder after the flip — gate 2026-07-31).
                failed += 1
                continue
            _log_reminder(
                conn, DEADLINE_REMINDER_TYPE, PERSON_SENTINEL, fiscal_year, filler_email,
                now,
            )
            sent += 1
            if result.retries:
                retried += 1  # mails that needed >=1 retry attempt (§7.3.5)
        except Exception:
            conn.rollback()
            failed += 1
            logger.exception(
                "deadline reminder failed for filler=%r — continuing with next person", filler_email,
            )

    logger.info(
        "fiscal_year=%s phase=deadline summary: attempted=%d sent=%d failed=%d retried=%d capped=%d",
        fiscal_year, attempted, sent, failed, retried, capped,
    )
    return sent


# ---------------------------------------------------------------------------
# entry points
# ---------------------------------------------------------------------------

def run(
    fiscal_year: int, dry_run: bool, notifications_dry_run: bool, now: datetime | None = None,
    *, sleep: Callable[[float], None] = time.sleep,
) -> int:
    """Runs both phases on ONE connection. Returns the total number of
    reminders sent (dry-run: the number that WOULD be). Pacing delay and the
    per-phase cap come from Settings (§7.3); `sleep` is injectable so tests
    never really wait."""
    now = now or datetime.now(timezone.utc)
    settings = get_settings()
    with get_fabric_conn() as conn:
        turn_sent = _run_turn_reminders(
            conn, fiscal_year, dry_run, notifications_dry_run, now,
            sleep=sleep,
            send_delay_seconds=settings.reminder_send_delay_seconds,
            max_sends=settings.reminder_max_sends_per_run,
        )
        deadline_sent = _run_deadline_reminders(
            conn, fiscal_year, dry_run, notifications_dry_run, bangkok_today(),
            sleep=sleep,
            send_delay_seconds=settings.reminder_send_delay_seconds,
            max_sends=settings.reminder_max_sends_per_run,
            now=now,
        )
        return turn_sent + deadline_sent


def main() -> int:
    configure_logging()
    import argparse

    parser = argparse.ArgumentParser(
        description="A12 automation D: grouped 7-day turn reminders (1 mail/approver) + grouped deadline reminders (1 mail/filler)"
    )
    add_common_args(parser)
    args = parser.parse_args()
    dry_run = is_dry_run(args)
    settings = get_settings()

    logger.info(
        "starting send_reminders fiscal_year=%s dry_run=%s notifications_dry_run=%s",
        args.fiscal_year, dry_run, settings.notifications_dry_run,
    )
    run(args.fiscal_year, dry_run=dry_run, notifications_dry_run=settings.notifications_dry_run)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
