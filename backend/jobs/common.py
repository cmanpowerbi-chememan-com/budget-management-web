"""Shared scaffolding for the A11 scheduled job (`auto_submit`) and the A12
`send_reminders` job — logging setup + the never-cut dry-run safety gate.

Safety (never-cut #1, BUILD_PLAN A11/A12): every job defaults to a preview.
`--execute` is the ONLY CLI way to actually write/send; nothing in this
build ever passes it. The `DRY_RUN` env var is a belt-and-braces layer on
top — even `--execute` stays a no-op preview unless `DRY_RUN` is
EXPLICITLY set to `false` (its default is `true`), so a CI/cron misconfig
that forgets to unset `DRY_RUN` can never cause a real write.

No auto-detected "current planning year": every job REQUIRES an explicit
`--fiscal-year`. There is no existing helper anywhere in this codebase that
derives "the current planning year" from `dbo.submission_deadline` (each
row is just one configured year), and inventing one felt like guessing a
business rule rather than following a decision — flagged in the final
report. The GitHub Actions workflow supplies it via a `workflow_dispatch`
input.
"""
import argparse
import logging
import os
import sys


def configure_logging() -> None:
    """Loud, structured, file-friendly output (BUILD_PLAN A11: "Loud
    structured output") — every job calls this once at the top of `main()`."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        stream=sys.stdout,
    )


def add_common_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--fiscal-year", type=int, required=True,
        help="the planning year to act on (no auto-detect — always supplied explicitly)",
    )
    parser.add_argument(
        "--execute", action="store_true",
        help="actually write/send (default: dry-run preview only, never-cut safety rule)",
    )


def is_dry_run(args: argparse.Namespace) -> bool:
    """True (preview only) unless BOTH `--execute` was passed AND the
    `DRY_RUN` env var is explicitly `'false'` (default `'true'`)."""
    env_forces_dry_run = os.getenv("DRY_RUN", "true").strip().lower() != "false"
    return env_forces_dry_run or not args.execute
