"""A11 scheduled job — auto-escalate stale PENDING_* approval steps (30-day
SLA, ADR-0006, BUILD_PLAN A11).

Run (from `backend/`):
    python -m jobs.auto_escalate --fiscal-year 2027            # dry-run preview (default)
    python -m jobs.auto_escalate --fiscal-year 2027 --execute  # actually escalate

Unlike `auto_submit`, this job is NOT deadline-gated — a step can go stale
at any point during the open cycle, so it runs on the same daily cadence
regardless of where the fiscal_year's cycle currently stands.

Idempotent per 30-day window by construction: escalating a step stamps
that position's `_actioned_at` to "now", so `is_step_stale` computed on the
VERY NEXT run reads that fresh timestamp and correctly reports "not yet
stale" — no separate "already escalated" bookkeeping needed.

A stuck FINAL active position is never escalated (ADR-0006: "never a jump
straight to APPROVED just because someone was slow") —
`auto_escalate_step` raises `InvalidApprovalStateError` for that case,
which this job treats as a normal skip (logged, not a failure).
"""
import logging
from datetime import datetime, timezone

from app import notifications
from app.approval import InvalidApprovalStateError, auto_escalate_step, fetch_pending_rows, is_step_stale
from app.config import get_settings
from app.db import get_fabric_conn
from jobs.common import add_common_args, configure_logging, is_dry_run

logger = logging.getLogger("jobs.auto_escalate")


def run(fiscal_year: int, dry_run: bool, notifications_dry_run: bool) -> int:
    """Returns the number of rows escalated (dry-run: the number that WOULD
    be). Uses ONE connection for the whole run — each row's
    `auto_escalate_step` call commits/rolls back on its own."""
    with get_fabric_conn() as conn:
        rows = fetch_pending_rows(conn, fiscal_year)
        now = datetime.now(timezone.utc)
        stale_rows = [row for row in rows if is_step_stale(row, now)]

        if not stale_rows:
            logger.info("fiscal_year=%s: 0 stale (>=30d) PENDING_* row(s) found — nothing to escalate", fiscal_year)
            return 0

        logger.info(
            "fiscal_year=%s: %d stale row(s) found: %s",
            fiscal_year, len(stale_rows), [row["department"] for row in stale_rows],
        )

        if dry_run:
            for row in stale_rows:
                logger.info("[DRY-RUN] would auto-escalate department=%r status=%s", row["department"], row["status"])
            return len(stale_rows)

        escalated = 0
        for row in stale_rows:
            department = row["department"]
            try:
                state = auto_escalate_step(conn, department, fiscal_year, row, now=now)
            except InvalidApprovalStateError:
                logger.info(
                    "department=%r current step is already the final active position — "
                    "not escalating (ADR-0006)", department,
                )
                continue
            except Exception:
                conn.rollback()
                logger.exception("auto-escalate failed for department=%r — continuing with next row", department)
                continue

            logger.info(
                "auto-escalated department=%r -> status=%s current_approver=%s",
                department, state.status, state.current_approver_empcode,
            )
            escalated += 1

            if state.current_approver_empcode:
                try:
                    notifications.notify_turn(
                        conn, department=department, fiscal_year=fiscal_year,
                        approver_empcode=state.current_approver_empcode, submitter_email=state.submitter_email,
                        dry_run=notifications_dry_run,
                    )
                except Exception:
                    logger.exception("notify_turn failed for department=%r — continuing (non-fatal)", department)

        logger.info("fiscal_year=%s: auto-escalated %d/%d stale row(s)", fiscal_year, escalated, len(stale_rows))
        return escalated


def main() -> int:
    configure_logging()
    import argparse

    parser = argparse.ArgumentParser(
        description="A11: auto-escalate stale (>=30d) PENDING_* approval steps (ADR-0006)"
    )
    add_common_args(parser)
    args = parser.parse_args()
    dry_run = is_dry_run(args)
    settings = get_settings()

    logger.info(
        "starting auto_escalate fiscal_year=%s dry_run=%s notifications_dry_run=%s",
        args.fiscal_year, dry_run, settings.notifications_dry_run,
    )
    run(args.fiscal_year, dry_run=dry_run, notifications_dry_run=settings.notifications_dry_run)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
