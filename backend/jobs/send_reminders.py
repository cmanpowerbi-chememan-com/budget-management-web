"""A12 scheduled job (automation D) — pre-deadline reminder emails to
Fillers of still-not-submitted departments (BUILD_PLAN A12 item 3).

Run (from `backend/`):
    python -m jobs.send_reminders --fiscal-year 2027            # dry-run preview (default)
    python -m jobs.send_reminders --fiscal-year 2027 --execute  # actually send

Gated on `dbo.submission_deadline.reminder_date` for `fiscal_year` (the same
row `app.deadline` reads for `deadline_date`) — a no-op before that date, and
a no-op forever if no row is configured for this year (never silently act
on an unconfigured year, mirroring `app.deadline.is_post_deadline`'s
missing-row posture, inverted: missing config here means "never remind").

"Still not submitted" = any department with NO `approval_status` row for
`fiscal_year`, OR a row whose status is `REJECTED` — DELIBERATELY BROADER
than `auto_submit`'s true-DRAFT-only scope: unlike auto_submit (which runs
AFTER the deadline and must leave REJECTED departments to the admin,
ADR-0012), reminders run BEFORE the deadline, and a REJECTED department is
exactly who needs reminding to fix and resubmit before the cutoff.

Grouped: ONE email per Filler listing every department they Fill that is
still not submitted (spec: "submitted ones excluded") — `dbo.cc_filler_map`
is the Filler-set source of truth (ADR-0019).
"""
import logging

from app import notifications
from app.approval import REJECTED
from app.config import get_settings
from app.db import get_fabric_conn
from app.deadline import bangkok_today
from jobs.common import add_common_args, configure_logging, is_dry_run

logger = logging.getLogger("jobs.send_reminders")


def _reminder_date_reached(conn, fiscal_year: int) -> bool:
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT reminder_date FROM dbo.submission_deadline WHERE fiscal_year = ?", fiscal_year)
        row = cursor.fetchone()
    finally:
        cursor.close()
    if row is None or row[0] is None:
        return False
    return bangkok_today() >= row[0]


def _find_still_not_submitted_departments(conn, fiscal_year: int) -> list[str]:
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


def _group_by_filler(conn, departments: list[str]) -> dict[str, list[str]]:
    """Returns `{filler_email: [department, ...]}`, one entry per Filler,
    each listing every still-not-submitted department they Fill (a Filler
    spanning >1 department is common, `project_ccdept_fillscope_distribution`
    memory: 45% of real Fillers span more than one ฝ่าย)."""
    filler_to_depts: dict[str, list[str]] = {}
    for department in departments:
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
        for (filler_email,) in rows:
            filler_to_depts.setdefault(filler_email, []).append(department)
    return filler_to_depts


def run(fiscal_year: int, dry_run: bool, notifications_dry_run: bool) -> int:
    """Returns the number of Fillers reminded (dry-run: the number that
    WOULD be)."""
    with get_fabric_conn() as conn:
        if not _reminder_date_reached(conn, fiscal_year):
            logger.info(
                "fiscal_year=%s: reminder_date not yet reached (or no submission_deadline row configured) "
                "— nothing to do", fiscal_year,
            )
            return 0

        departments = _find_still_not_submitted_departments(conn, fiscal_year)
        if not departments:
            logger.info("fiscal_year=%s: 0 still-not-submitted department(s) — nothing to remind", fiscal_year)
            return 0

        filler_to_depts = _group_by_filler(conn, departments)
        logger.info(
            "fiscal_year=%s: %d still-not-submitted department(s), %d Filler(s) to remind",
            fiscal_year, len(departments), len(filler_to_depts),
        )

        if dry_run:
            for filler_email, depts in filler_to_depts.items():
                logger.info("[DRY-RUN] would remind filler=%s departments=%s", filler_email, depts)
            return len(filler_to_depts)

        sent = 0
        for filler_email, depts in filler_to_depts.items():
            try:
                notifications.notify_reminder(
                    filler_email, [(dept, fiscal_year) for dept in depts], dry_run=notifications_dry_run,
                )
                sent += 1
            except Exception:
                logger.exception("notify_reminder failed for filler=%r — continuing with next filler", filler_email)

        logger.info("fiscal_year=%s: reminded %d/%d Filler(s)", fiscal_year, sent, len(filler_to_depts))
        return sent


def main() -> int:
    configure_logging()
    import argparse

    parser = argparse.ArgumentParser(
        description="A12 automation D: pre-deadline reminder emails to Fillers of still-not-submitted departments"
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
