"""Weekly officer-review workbook robot — Module 4 of PRD #34 (issue #34).

    python -m jobs.officer_review --fiscal-year 2027 [--execute] [--probe] [--out PATH]

Flow (normal mode): build -> reconcile (retry once on FAIL, D5) -> DRY-RUN
stops here (optionally writes `--out`) -> REAL: validate recipients ->
publish -> mail. Any control/publish/mail FAIL exits non-zero and skips the
remaining steps — a broken run never publishes and never mails (PRD story
20: "a wrong file is never published").

`--probe` runs the read-only permission check only (no build, no write):
Fabric SELECT 1, gold SELECT TOP 1, Graph token roles (Sites.ReadWrite.All +
Mail.Send), and a read-only GET of the site/drive/`officer review/` folder.

Dry-run is the default (jobs.common.is_dry_run: needs BOTH `--execute` AND
`DRY_RUN=false`). The schedule (`.github/workflows/officer-review.yml`)
additionally gates on the repo variable `OFFICER_REVIEW_LIVE` — its own gate,
deliberately NOT the shared `NOTIFICATIONS_DRY_RUN`/reminders variables (PRD
story 29: keep this robot separate from the armed reminder automation).

Never logs department names, personal names, or recipient email addresses —
only counts and control numbers (PRD: PII stays out of CI logs)."""
import argparse
import logging
import os
import re
import time
from collections.abc import Callable
from datetime import datetime
from urllib.parse import quote
from zoneinfo import ZoneInfo

import httpx

from app import notifications
from app.attachments import GRAPH_BASE, _resolve_site_and_drive
from app.config import Settings, get_settings
from app.db import get_fabric_conn, get_gold_conn
from app.officer_notify import notify_officer_review
from app.officer_publisher import OFFICER_FOLDER_NAME, OfficerPublishError, publish_officer_workbook
from app.officer_reconcile import ReconcileResult, reconcile
from app.officer_workbook import BuildResult, build_officer_workbook
from app.sap import clear_sap_caches
from jobs.common import add_common_args, configure_logging, is_dry_run
from jobs.probe_graph_permissions import decode_jwt_payload

logger = logging.getLogger("jobs.officer_review")

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_RECIPIENT_DOMAIN_SUFFIX = "@chememan.com"
_DEFAULT_RETRY_DELAY_SECONDS = 300.0
BANGKOK_TZ = ZoneInfo("Asia/Bangkok")

# OPS-2/SEC-F2/SPEC-6/SEC-F1/OPS-8 fix round 2026-09-24: every log record
# this job process emits goes through this filter, installed on the ROOT
# handlers right after `configure_logging()` — catches `app.notifications`'s
# own `sent to=%s cc=%s` INFO/WARNING lines too (zero-edit there) without
# needing to know every logger name that might ever print an address.
_EMAIL_REDACT_RE = re.compile(r"[\w.+-]+@[\w-]+(\.[\w-]+)+")


class _EmailRedactingLogFilter(logging.Filter):
    """Redacts every email-like substring in a formatted log message to
    `<email>`. Rewrites `record.msg` with the ALREADY-FORMATTED (`%`-args
    applied) text and clears `record.args`, so the redaction survives
    whatever the handler's formatter does next — a record is never dropped,
    only its text is cleaned."""

    def filter(self, record: logging.LogRecord) -> bool:
        message = record.getMessage()
        redacted = _EMAIL_REDACT_RE.sub("<email>", message)
        if redacted != message:
            record.msg = redacted
            record.args = ()
        return True


def install_email_redaction() -> None:
    """Attach `_EmailRedactingLogFilter` to every handler currently on the
    root logger. Call ONCE, right after `configure_logging()` — that is the
    call that creates the root `StreamHandler` this filter attaches to."""
    filt = _EmailRedactingLogFilter()
    for handler in logging.getLogger().handlers:
        handler.addFilter(filt)


class OfficerConfigError(RuntimeError):
    """A required piece of configuration (gold DB connection info) is
    missing — a clear, loud error BEFORE any connection attempt (D10),
    instead of an obscure pyodbc failure with `SERVER=None`."""


def parse_recipients(raw: str) -> tuple[list[str], int]:
    """Comma/semicolon-separated, trimmed, de-duplicated (case-insensitive),
    basic email-shape checked, AND restricted to the company domain (SEC-F5,
    owner decision: company domain only) — `@chememan.com`, case-insensitive.
    An entry failing either check is DROPPED with a WARNING (never crashes
    the parse — one bad entry must not take the whole run down); a
    duplicate is silently deduplicated, not counted as dropped.

    Returns `(valid_recipients, dropped_count)` — OPS-7: the caller MUST
    treat `dropped_count > 0` as a FAIL on a REAL run (before publishing,
    never a silent partial recipient list) and report both counts even on a
    PREVIEW run."""
    if not raw:
        return [], 0
    seen: set[str] = set()
    out: list[str] = []
    dropped = 0
    for part in re.split(r"[,;]", raw):
        addr = part.strip()
        if not addr:
            continue
        key = addr.lower()
        if key in seen:
            continue
        if not _EMAIL_RE.match(addr) or not key.endswith(_RECIPIENT_DOMAIN_SUFFIX):
            logger.warning("officer_review: OFFICER_REVIEW_RECIPIENTS entry dropped — not a valid %s address", _RECIPIENT_DOMAIN_SUFFIX)
            dropped += 1
            continue
        seen.add(key)
        out.append(addr)
    return out, dropped


def _ensure_gold_configured(settings: Settings) -> None:
    if not settings.gold_sql_server or not settings.gold_sql_database:
        raise OfficerConfigError(
            "GOLD_SQL_SERVER / GOLD_SQL_DATABASE are not configured — cannot read gold.fact_gl_trans"
        )


def check_fy_sanity(planning_year: int, *, now: datetime | None = None) -> str | None:
    """OPS-10: a mistyped or bumped `AUTOMATION_FISCAL_YEAR` (shared with the
    ARMED reminders workflow) must FAIL loud BEFORE any read — combined with
    D6 (an empty scope still publishes+mails), a wrong year would otherwise
    produce a green REAL run that quietly stops updating the real year's
    file and starts publishing an empty one for the wrong year. A "planning
    fiscal year" can only legitimately mean the current Bangkok year or the
    next one. Returns an error message, or `None` when the year is sane."""
    today = (now or datetime.now(BANGKOK_TZ)).astimezone(BANGKOK_TZ)
    if planning_year not in (today.year, today.year + 1):
        return (
            f"fiscal_year={planning_year} is neither the current Bangkok year ({today.year}) "
            f"nor next year ({today.year + 1}) — refusing to read, in case AUTOMATION_FISCAL_YEAR is wrong"
        )
    return None


def _build_and_reconcile(fabric_conn, gold_conn, planning_year: int, settings: Settings) -> tuple[BuildResult, ReconcileResult]:
    # C-F1/SPEC-5/OPS-5: ONE SAP snapshot per ATTEMPT, fresh across attempts
    # — without this, the D5 retry (300s later) reused the SAME cached SAP
    # figures the WEB side saw on attempt 1 while the FABRIC side always
    # read gold fresh, so a SAP load landing mid-run failed BOTH attempts
    # instead of the one honest transient mismatch D5 exists to absorb.
    clear_sap_caches()
    build = build_officer_workbook(fabric_conn, gold_conn, planning_year=planning_year, settings=settings)
    if build.xlsx_bytes is None:
        return build, ReconcileResult(ok=False, failures=["build produced no bytes"])
    recon = reconcile(build.xlsx_bytes, build, fabric_conn, gold_conn, planning_year=planning_year)
    return build, recon


def _build_with_retry(
    fabric_conn, gold_conn, planning_year: int, settings: Settings, *,
    sleep: Callable[[float], None], retry_delay_seconds: float,
) -> tuple[BuildResult, ReconcileResult, bool, int]:
    """D5: on ANY FAIL (build-time control OR the three-way reconcile),
    sleep once then rebuild + re-reconcile from scratch — a live save during
    the submission window, or a SAP load landing mid-run, can cause one
    honest transient mismatch. A second FAIL is real: no publish, no mail."""
    build, recon = _build_and_reconcile(fabric_conn, gold_conn, planning_year, settings)
    ok = build.ok and recon.ok
    if ok:
        return build, recon, True, 1

    logger.warning(
        "officer_review: attempt 1 FAILED reconcile (%d build + %d reconcile failures) — retrying once after %.0fs",
        len(build.failures), len(recon.failures), retry_delay_seconds,
    )
    sleep(retry_delay_seconds)
    build, recon = _build_and_reconcile(fabric_conn, gold_conn, planning_year, settings)
    ok = build.ok and recon.ok
    return build, recon, ok, 2


def run_probe(settings: Settings) -> int:
    """Read-only permission check. No build, no write, no mail. Exit 0 only
    when every check PASSes."""
    ok = True

    try:
        with get_fabric_conn(settings) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT 1")
            cursor.fetchall()
            cursor.close()
        print("PASS: Fabric SQL DB read (SELECT 1)")
    except Exception as exc:  # noqa: BLE001 — probe reports every failure, never crashes mid-checklist
        print(f"FAIL: Fabric SQL DB read — {exc}")
        ok = False

    try:
        _ensure_gold_configured(settings)
        with get_gold_conn(settings) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT TOP 1 1 FROM gold.fact_gl_trans")
            cursor.fetchall()
            cursor.close()
        print("PASS: gold warehouse read (SELECT TOP 1 FROM gold.fact_gl_trans)")
    except Exception as exc:  # noqa: BLE001
        print(f"FAIL: gold warehouse read — {exc}")
        ok = False

    token = None
    try:
        token = notifications._get_graph_token(settings)
        payload = decode_jwt_payload(token)
        roles = set(payload.get("roles") or [])
        for role in ("Sites.ReadWrite.All", "Mail.Send"):
            if role in roles:
                print(f"PASS: Graph token carries role {role}")
            else:
                print(f"FAIL: Graph token missing role {role}")
                ok = False
    except Exception as exc:  # noqa: BLE001 — OPS-9: any exception (httpx transport error, malformed token
        # response, ...) FAILs this ONE check and the probe still runs every remaining check
        print(f"FAIL: Graph token/role check — {type(exc).__name__}: {exc}")
        ok = False

    if token is not None:
        try:
            _site_id, drive_id = _resolve_site_and_drive(token, settings)
            print("PASS: resolved SharePoint site + drive")
            resp = httpx.get(
                f"{GRAPH_BASE}/drives/{drive_id}/root:/{quote(OFFICER_FOLDER_NAME, safe='')}",
                headers={"Authorization": f"Bearer {token}"}, timeout=30,
            )
            if resp.status_code == 200:
                print(f"PASS: '{OFFICER_FOLDER_NAME}' folder already exists")
            elif resp.status_code == 404:
                print(f"PASS: '{OFFICER_FOLDER_NAME}' folder does not exist yet — will be created on first real publish")
            else:
                print(f"FAIL: unexpected status resolving '{OFFICER_FOLDER_NAME}' folder: {resp.status_code}")
                ok = False
        except Exception as exc:  # noqa: BLE001
            print(f"FAIL: site/drive/folder resolution — {exc}")
            ok = False

    return 0 if ok else 1


def run_build(
    *, planning_year: int, dry_run: bool, settings: Settings, out_path: str | None,
    recipients: list[str], recipients_dropped: int = 0, sleep: Callable[[float], None] = time.sleep,
    retry_delay_seconds: float = _DEFAULT_RETRY_DELAY_SECONDS,
) -> int:
    # OPS-10: fail loud on a wrong planning year BEFORE any read — a
    # mistyped/bumped AUTOMATION_FISCAL_YEAR must never quietly publish an
    # empty (or wrong-year) file every week.
    fy_error = check_fy_sanity(planning_year)
    if fy_error:
        print(f"MODE: FAIL — {fy_error}")
        return 1

    _ensure_gold_configured(settings)

    with get_fabric_conn(settings) as fabric_conn, get_gold_conn(settings) as gold_conn:
        build, recon, ok, attempts = _build_with_retry(
            fabric_conn, gold_conn, planning_year, settings, sleep=sleep, retry_delay_seconds=retry_delay_seconds,
        )

    all_failures = build.failures + recon.failures
    print(f"CONTROL: attempts={attempts} ok={ok} failures={len(all_failures)} warnings={len(build.warnings)}")
    print(
        f"SUMMARY: fy={planning_year} n_departments={build.n_departments} "
        f"fy_total={build.grand_total_year:.2f} board_total={build.grand_board_total:.2f} "
        f"sap_total={build.grand_sap_total:.2f} lines_per_topic={build.lines_per_topic}"
    )
    # SPEC-8: PDPA/illegal-char WARN entries are only ever coordinates
    # (sheet!cell), never values (by construction — see officer_workbook.py)
    # — surface them so someone can actually find and fix the cell, capped
    # at 20 lines + the total count.
    if build.warnings:
        for w in build.warnings[:20]:
            logger.warning("officer_review CONTROL WARN: %s", w)
        print(f"WARNINGS: {len(build.warnings)} total (showing up to 20 in the log)")
    if not ok:
        for f in all_failures[:20]:
            logger.error("officer_review CONTROL FAIL: %s", f)
        print("MODE: FAIL — reconcile did not pass after retry; no publish, no mail")
        return 1

    if out_path:
        with open(out_path, "wb") as fh:
            fh.write(build.xlsx_bytes)
        print(f"OUT: wrote {len(build.xlsx_bytes)} bytes to {out_path}")

    if dry_run:
        print("MODE: PREVIEW — would publish + mail (no Graph write, no mail sent)")
        return 0

    if not recipients:
        print("MAIL FAIL: no valid OFFICER_REVIEW_RECIPIENTS — refusing to publish on a REAL run")
        return 1
    if recipients_dropped:
        # SEC-F5/OPS-7 (owner decision: company domain only, strict on a
        # REAL run): a misconfigured or external entry must never silently
        # mail fewer people than configured, or leak budget totals outside
        # chememan.com.
        print(f"MAIL FAIL: {recipients_dropped} configured OFFICER_REVIEW_RECIPIENTS entr(ies) were dropped (invalid or non-@chememan.com) — refusing to publish on a REAL run")
        return 1

    try:
        web_url = publish_officer_workbook(build.xlsx_bytes, planning_year=planning_year, settings=settings, sleep=sleep)
    except OfficerPublishError as exc:
        print(f"PUBLISH FAIL: {exc}")
        return 1
    print("PUBLISHED: file overwritten in SharePoint (officer review/)")
    logger.info("officer_review: published webUrl=%s", web_url)

    try:
        results = notify_officer_review(
            recipients, web_url=web_url, as_of=build.as_of, planning_year=planning_year,
            n_departments=build.n_departments, fy_total=build.grand_total_year,
            board_total=build.grand_board_total, sap_total=build.grand_sap_total,
            sap_watermark=build.sap_watermark, lines_per_topic=build.lines_per_topic,
            dry_run=False, settings=settings,
        )
    except notifications.NotificationError as exc:
        print(f"MAIL FAIL: send raised — {exc} — file already published, re-run is idempotent")
        return 1
    failed = [r for r in results if not r.sent]
    print(f"MAIL: sent={len(results) - len(failed)}/{len(results)} recipients")
    if failed:
        print("MAIL FAIL: at least one send did not succeed — file already published, re-run is idempotent")
        return 1

    print("MODE: REAL — published and mailed")
    return 0


def main() -> int:
    configure_logging()
    install_email_redaction()  # OPS-2/SEC-F2/SPEC-6: right after configure_logging(), per its own contract
    parser = argparse.ArgumentParser(description="Weekly officer-review workbook robot (PRD #34)")
    add_common_args(parser)
    parser.add_argument("--probe", action="store_true", help="read-only permission check only; no build, no write")
    parser.add_argument("--out", type=str, default=None, help="local path to also write the built xlsx bytes to (never passed in CI)")
    args = parser.parse_args()

    settings = get_settings()
    dry_run = is_dry_run(args)
    logger.info("starting officer_review fiscal_year=%s dry_run=%s probe=%s", args.fiscal_year, dry_run, args.probe)

    # OPS-9: `run_probe` is now inside the SAME try/except as build mode —
    # an unexpected exception (httpx transport error, KeyError, ...) that
    # escapes an individual probe check's own try/except (or `get_settings`
    # itself) exits loud (2) instead of an unhandled traceback.
    try:
        if args.probe:
            return run_probe(settings)

        recipients, dropped = parse_recipients(os.getenv("OFFICER_REVIEW_RECIPIENTS", ""))
        print(f"RECIPIENTS: valid={len(recipients)} dropped={dropped}")
        return run_build(
            planning_year=args.fiscal_year, dry_run=dry_run, settings=settings,
            out_path=args.out, recipients=recipients, recipients_dropped=dropped,
        )
    except Exception:  # noqa: BLE001 — unexpected exception -> loud, exit 2, never a silent partial run
        logger.exception("officer_review: unexpected exception")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
