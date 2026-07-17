"""A11 scheduled job — auto-submit true-DRAFT departments at the planning
year's deadline (ADR-0006, BUILD_PLAN A11).

Run (from `backend/`):
    python -m jobs.auto_submit --fiscal-year 2027            # dry-run preview (default)
    python -m jobs.auto_submit --fiscal-year 2027 --execute  # actually submit

"True DRAFT" = a department with >=1 `budget.pending_budget` row for
`fiscal_year` (something was entered) but NO `budget.approval_status` row
at all. REJECTED departments are deliberately NOT touched here — ADR-0012
gives the admin sole post-deadline ownership of every straggler, REJECTED
included, via `submit_department`'s override branch; this job only ever
targets a true DRAFT (see `app.approval.auto_submit_department`'s
docstring for the full reasoning).

Idempotent by construction: a department vanishes from the discovery query
the moment it has an `approval_status` row (any status), so a 2nd run
never re-submits it.

Safety: this job never sends real email either — `notifications.notify_turn`
is always called with `dry_run=notifications_dry_run`, a SEPARATE flag from
this job's own `--execute` (default True, `Settings.notifications_dry_run`,
a distinct go-live toggle jakkaritw flips independently).
"""
import logging

from app import notifications
from app.approval import auto_submit_department
from app.config import Settings, get_settings
from app.db import get_fabric_conn
from app.deadline import is_post_deadline
from app.gl_access import fetch_admin_gl_codes
from jobs.common import add_common_args, configure_logging, is_dry_run

logger = logging.getLogger("jobs.auto_submit")


def _gl_exclusion_clause(alias: str, exclude_gl_codes: frozenset[str]) -> tuple[str, list[str]]:
    """Build the optional `AND <alias>.gl_account NOT IN (?, ?, ...)`
    restriction, fully parameterized (never string-interpolated) — same
    idiom as `read_model._cc_filter_clause`. Empty set = no restriction."""
    if not exclude_gl_codes:
        return "", []
    placeholders = ", ".join(["?"] * len(exclude_gl_codes))
    return f" AND {alias}.gl_account NOT IN ({placeholders})", list(exclude_gl_codes)


def _find_true_draft_departments(
    conn, fiscal_year: int, exclude_gl_codes: frozenset[str] = frozenset(),
) -> list[tuple[str, str]]:
    """Returns `[(department, last_editor_email), ...]` — `last_editor_email`
    is the `_user` value on that department's MOST RECENTLY updated
    `pending_budget` row (write_model.py stores the saving user's email
    there, never an empcode) for `fiscal_year`, deterministically de-duped
    if more than one row ties on `_updated_at`.

    `exclude_gl_codes` (GL `edit_by` admin-only lock, ADR-0024, flag-gated —
    see `run`): admin-GL rows are approved-on-save the instant the admin
    saves them, independent of this job's normal-chain auto-submit, so the
    "last editor" used to resolve approver1 must never be derived from
    someone who only touched a secret admin-GL row. Excluded from BOTH the
    candidate row `p` and the correlated MAX(_updated_at) subquery `p2`, so
    an admin-GL edit can never win the "most recent" comparison either.
    Empty (the default, flag OFF) adds no filter at all — the query text is
    byte-identical to before this exclusion existed."""
    p_gl_clause, p_gl_params = _gl_exclusion_clause("p", exclude_gl_codes)
    p2_gl_clause, p2_gl_params = _gl_exclusion_clause("p2", exclude_gl_codes)

    cursor = conn.cursor()
    try:
        cursor.execute(
            f"""
            SELECT p.department, p._user
            FROM budget.pending_budget p
            WHERE p.fiscal_year = ?
              AND p.department IS NOT NULL
              {p_gl_clause}
              AND NOT EXISTS (
                  SELECT 1 FROM budget.approval_status a
                  WHERE a.department = p.department AND a.fiscal_year = p.fiscal_year
              )
              AND p._updated_at = (
                  SELECT MAX(p2._updated_at) FROM budget.pending_budget p2
                  WHERE p2.department = p.department AND p2.fiscal_year = p.fiscal_year
                    {p2_gl_clause}
              )
            """,
            fiscal_year, *p_gl_params, *p2_gl_params,
        )
        rows = cursor.fetchall()
    finally:
        cursor.close()

    deduped: dict[str, str] = {}
    for department, last_editor_email in sorted(rows, key=lambda r: (r[0], r[1] or "")):
        deduped.setdefault(department, last_editor_email)
    return sorted(deduped.items())


def run(fiscal_year: int, dry_run: bool, notifications_dry_run: bool, settings: Settings | None = None) -> int:
    """Returns the number of departments auto-submitted (dry-run: the number
    that WOULD be). Uses ONE connection for the whole run — each
    department's `auto_submit_department` call commits/rolls back on its
    own, matching `write_model._run_per_item`'s per-item isolation pattern.

    GL `edit_by` admin-only lock (design v2, ADR-0024, flag-gated): only
    fetches the admin-GL set (one extra query) when
    `Settings.gl_edit_by_enabled` is True — the flag-OFF default never runs
    this query at all (zero behavior change), same idiom as
    `read_model.get_budget_grid`."""
    settings = settings or get_settings()
    with get_fabric_conn() as conn:
        if not is_post_deadline(conn, fiscal_year):
            logger.info(
                "fiscal_year=%s is not yet past its submission deadline (or no deadline row configured) "
                "— nothing to do", fiscal_year,
            )
            return 0

        exclude_gl_codes = fetch_admin_gl_codes(conn) if settings.gl_edit_by_enabled else frozenset()
        candidates = _find_true_draft_departments(conn, fiscal_year, exclude_gl_codes=exclude_gl_codes)
        if not candidates:
            logger.info("fiscal_year=%s: 0 true-DRAFT department(s) found — nothing to auto-submit", fiscal_year)
            return 0

        logger.info(
            "fiscal_year=%s: %d true-DRAFT department(s) found: %s",
            fiscal_year, len(candidates), [d for d, _ in candidates],
        )

        if dry_run:
            for department, last_editor_email in candidates:
                logger.info("[DRY-RUN] would auto-submit department=%r last_editor=%r", department, last_editor_email)
            return len(candidates)

        submitted = 0
        for department, last_editor_email in candidates:
            try:
                state = auto_submit_department(conn, department, fiscal_year, last_editor_email)
                logger.info(
                    "auto-submitted department=%r -> status=%s current_approver=%s",
                    department, state.status, state.current_approver_empcode,
                )
                submitted += 1
            except Exception:
                conn.rollback()
                logger.exception("auto-submit failed for department=%r — continuing with next department", department)
                continue

            if state.current_approver_empcode:
                try:
                    notifications.notify_turn(
                        conn, department=department, fiscal_year=fiscal_year,
                        approver_empcode=state.current_approver_empcode, submitter_email=last_editor_email,
                        dry_run=notifications_dry_run,
                    )
                except Exception:
                    logger.exception("notify_turn failed for department=%r — continuing (non-fatal)", department)

        logger.info("fiscal_year=%s: auto-submitted %d/%d department(s)", fiscal_year, submitted, len(candidates))
        return submitted


def main() -> int:
    configure_logging()
    import argparse

    parser = argparse.ArgumentParser(
        description="A11: auto-submit true-DRAFT departments at the planning year's deadline (ADR-0006)"
    )
    add_common_args(parser)
    args = parser.parse_args()
    dry_run = is_dry_run(args)
    settings = get_settings()

    logger.info(
        "starting auto_submit fiscal_year=%s dry_run=%s notifications_dry_run=%s",
        args.fiscal_year, dry_run, settings.notifications_dry_run,
    )
    run(args.fiscal_year, dry_run=dry_run, notifications_dry_run=settings.notifications_dry_run)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
