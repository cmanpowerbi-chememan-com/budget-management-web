"""A12 scheduled job (automation D) — reminder emails, 2026-07-31 revamp
(plan/email-notify-revamp.md). TWO phases in ONE job (no new job created):

Phase A — TURN reminders: every `budget.approval_status` row sitting in
PENDING_APPROVER1/2/3 whose current turn started >= 7 days ago gets a
`notify_turn(reminder=True)` nudge to the CURRENT approver, repeated every
7 days until they act. The turn-start anchor is `app.approval.current_turn_info`
— the SAME anchor the 30-day auto-escalate (`is_step_stale`) uses, so the
two clocks can never drift (plan invariant §5).

Phase B — DEADLINE reminders (rework of the old behavior): Fillers of
still-not-submitted departments (NO approval_status row = DRAFT, or status
REJECTED — departments already in the chain are Phase A's job, never both).
ONE email per (department, filler) — replaces the old grouped per-filler
mail — To the filler, cc the derived approver1 (the filler's
`manager_employee_code` from `dbo.v_employee_budget_01`, fallback Nipaporn
— the same rule `app.approval.resolve_chain` freezes at submit time).

Cadence bookkeeping lives in `budget.reminder_log` (db/ddl/budget_reminder_log.sql):
one row per (reminder_type, department, fiscal_year, recipient), updated
after each SUCCESSFUL send. A mail that fails is never logged, so it is
retried on the next run. Dry-run never sends and never writes the log.

Run (from `backend/`):
    python -m jobs.send_reminders --fiscal-year 2027            # dry-run preview (default)
    python -m jobs.send_reminders --fiscal-year 2027 --execute  # actually send

The old gate is unchanged: `--execute` + `DRY_RUN=false` (jobs/common.py,
untouched) + `Settings.notifications_dry_run` for the actual Graph send.
"""
import logging
from datetime import date, datetime, timezone

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


# ---------------------------------------------------------------------------
# reminder_log bookkeeping (budget.reminder_log, plan §3.3)
# ---------------------------------------------------------------------------

def _last_sent_at(conn, reminder_type: str, department: str, fiscal_year: int, recipient: str) -> datetime | None:
    """MAX(sent_at) ever logged for this exact (type, department, year,
    recipient) — None when never reminded. For turn reminders `recipient`
    is the current approver's empcode, so an approver CHANGE (re-freeze on
    resubmit) naturally starts a fresh cadence."""
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
    reach here on failure or dry-run — a failed mail must be retried next
    run). UPDATE-first keeps the PK (reminder_type, department, fiscal_year,
    recipient) stable across repeats."""
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
    """Naive-UTC comparison, same posture as `app.approval.is_step_stale`
    (SQL Server DATETIME2 carries no offset; never crash on a tz mismatch)."""
    return dt.replace(tzinfo=None) if dt.tzinfo is not None else dt


def _turn_due(turn_start: datetime, last_sent: datetime | None, now: datetime) -> bool:
    """7-day turn cadence (plan §3.3): due when the turn has sat >= 7 days
    and either no reminder was ever sent THIS turn, or the last one went out
    >= 7 days ago. A `last_sent` BEFORE `turn_start` belongs to a previous
    chain cycle (reject -> resubmit re-froze the row) and counts as never
    sent."""
    if last_sent is not None and _naive(last_sent) < _naive(turn_start):
        last_sent = None
    anchor = last_sent if last_sent is not None else turn_start
    return (_naive(now) - _naive(anchor)).days >= REMINDER_INTERVAL_DAYS


def _deadline_due(last_sent: datetime | None, today: date) -> bool:
    """7-day deadline cadence (plan §3.3): due when never sent, or the last
    send was >= 7 days ago. (The window check — reminder_date..closing_date
    — happens once per run in `_run_deadline_reminders`, not here.)"""
    if last_sent is None:
        return True
    return (today - _naive(last_sent).date()).days >= REMINDER_INTERVAL_DAYS


# ---------------------------------------------------------------------------
# Phase A — turn reminders (PENDING_APPROVER1/2/3)
# ---------------------------------------------------------------------------

def _run_turn_reminders(conn, fiscal_year: int, dry_run: bool, notifications_dry_run: bool, now: datetime) -> int:
    rows = fetch_pending_rows(conn, fiscal_year)
    due: list[tuple[dict, datetime, str]] = []
    for row in rows:
        turn_start, approver_empcode = current_turn_info(row)
        if not approver_empcode:
            logger.warning(
                "department=%r status=%s has no current approver to remind — skipped",
                row["department"], row["status"],
            )
            continue
        last_sent = _last_sent_at(conn, TURN_REMINDER_TYPE, row["department"], fiscal_year, approver_empcode)
        if _turn_due(turn_start, last_sent, now):
            due.append((row, turn_start, approver_empcode))

    if not due:
        logger.info("fiscal_year=%s: 0 turn reminder(s) due", fiscal_year)
        return 0

    if dry_run:
        for row, turn_start, empcode in due:
            logger.info(
                "[DRY-RUN] would send turn reminder department=%r approver=%s turn_start=%s",
                row["department"], empcode, turn_start,
            )
        return len(due)

    sent = 0
    for row, turn_start, approver_empcode in due:
        department = row["department"]
        try:
            result = notifications.notify_turn(
                conn, department=department, fiscal_year=fiscal_year,
                approver_empcode=approver_empcode, submitter_email=row["submitter_email"],
                reminder=True, days_pending=(_naive(now) - _naive(turn_start)).days,
                dry_run=notifications_dry_run,
            )
            if result is None or not result.sent:
                # Email unresolvable — or suppressed by NOTIFICATIONS_DRY_RUN
                # under a manual --execute BEFORE the go-live flip: nothing was
                # REALLY sent, so nothing is logged. The row stays due, and the
                # first real send after the flip is never swallowed by a stale
                # cadence row (gate finding 2026-07-31).
                continue
            _log_reminder(conn, TURN_REMINDER_TYPE, department, fiscal_year, approver_empcode, now)
            sent += 1
        except Exception:
            conn.rollback()
            logger.exception("turn reminder failed for department=%r — continuing with next row", department)

    logger.info("fiscal_year=%s: sent %d/%d turn reminder(s)", fiscal_year, sent, len(due))
    return sent


# ---------------------------------------------------------------------------
# Phase B — deadline reminders (DRAFT / REJECTED departments)
# ---------------------------------------------------------------------------

def _deadline_window(conn, fiscal_year: int) -> tuple[date, date | None] | None:
    """`(reminder_date, closing_date)` from `dbo.submission_deadline` — the
    existing, Nipaporn-maintained config row (plan §1: no new config). None
    when no row is configured or reminder_date is NULL — a missing config
    means "never remind", mirroring the old `_reminder_date_reached` posture.
    `closing_date` may itself be NULL (window then has no stop date)."""
    cursor = conn.cursor()
    try:
        cursor.execute(
            "SELECT reminder_date, closing_date FROM dbo.submission_deadline WHERE fiscal_year = ?",
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
    now: datetime | None = None,
) -> int:
    # `now` stamps the reminder_log rows (injectable for deterministic tests,
    # same clock Phase A uses); `today` drives the reminder/closing window.
    now = now or datetime.now(timezone.utc)
    window = _deadline_window(conn, fiscal_year)
    if window is None:
        logger.info(
            "fiscal_year=%s: no submission_deadline row (or no reminder_date) configured "
            "— no deadline reminders", fiscal_year,
        )
        return 0
    reminder_date, closing_date = window
    if today < reminder_date:
        logger.info("fiscal_year=%s: reminder_date %s not yet reached — no deadline reminders", fiscal_year, reminder_date)
        return 0
    if closing_date is not None and today > closing_date:
        logger.info("fiscal_year=%s: closing_date %s has passed — deadline reminders stopped", fiscal_year, closing_date)
        return 0

    departments = _find_still_not_submitted_departments(conn, fiscal_year)
    if not departments:
        logger.info("fiscal_year=%s: 0 still-not-submitted department(s) — nothing to remind", fiscal_year)
        return 0

    due: list[tuple[str, str]] = []  # (department, filler_email)
    for department in departments:
        for filler_email in _find_fillers(conn, department):
            last_sent = _last_sent_at(conn, DEADLINE_REMINDER_TYPE, department, fiscal_year, filler_email)
            if _deadline_due(last_sent, today):
                due.append((department, filler_email))

    if not due:
        logger.info("fiscal_year=%s: 0 deadline reminder(s) due", fiscal_year)
        return 0

    if dry_run:
        for department, filler_email in due:
            logger.info("[DRY-RUN] would send deadline reminder department=%r filler=%s", department, filler_email)
        return len(due)

    sent = 0
    for department, filler_email in due:
        try:
            cc_email = _resolve_approver1_cc_email(conn, filler_email)
            # Never cc the filler themselves (same rule as notify_reject /
            # notify_approved's cc == To skip, plan §3.1).
            cc_emails = [cc_email] if cc_email and cc_email.lower() != filler_email.lower() else []
            result = notifications.notify_deadline_reminder(
                filler_email, department, fiscal_year, closing_date,
                cc_emails=cc_emails, dry_run=notifications_dry_run,
            )
            if result is None or not result.sent:
                continue  # nothing really sent -> nothing logged (retry next run; see Phase A note)
            _log_reminder(
                conn, DEADLINE_REMINDER_TYPE, department, fiscal_year, filler_email,
                now,
            )
            sent += 1
        except Exception:
            conn.rollback()
            logger.exception(
                "deadline reminder failed for department=%r filler=%r — continuing with next pair",
                department, filler_email,
            )

    logger.info("fiscal_year=%s: sent %d/%d deadline reminder(s)", fiscal_year, sent, len(due))
    return sent


# ---------------------------------------------------------------------------
# entry points
# ---------------------------------------------------------------------------

def run(fiscal_year: int, dry_run: bool, notifications_dry_run: bool, now: datetime | None = None) -> int:
    """Runs both phases on ONE connection. Returns the total number of
    reminders sent (dry-run: the number that WOULD be)."""
    now = now or datetime.now(timezone.utc)
    with get_fabric_conn() as conn:
        turn_sent = _run_turn_reminders(conn, fiscal_year, dry_run, notifications_dry_run, now)
        deadline_sent = _run_deadline_reminders(conn, fiscal_year, dry_run, notifications_dry_run, bangkok_today(), now)
        return turn_sent + deadline_sent


def main() -> int:
    configure_logging()
    import argparse

    parser = argparse.ArgumentParser(
        description="A12 automation D: 7-day turn reminders (approvers) + per-department deadline reminders (fillers)"
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
