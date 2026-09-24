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
from urllib.parse import quote

import httpx

from app import notifications
from app.attachments import GRAPH_BASE, _resolve_site_and_drive
from app.config import Settings, get_settings
from app.db import get_fabric_conn, get_gold_conn
from app.officer_notify import notify_officer_review
from app.officer_publisher import OFFICER_FOLDER_NAME, OfficerPublishError, publish_officer_workbook
from app.officer_reconcile import ReconcileResult, reconcile
from app.officer_workbook import BuildResult, build_officer_workbook
from jobs.common import add_common_args, configure_logging, is_dry_run
from jobs.probe_graph_permissions import TokenDecodeError, decode_jwt_payload

logger = logging.getLogger("jobs.officer_review")

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_DEFAULT_RETRY_DELAY_SECONDS = 300.0


class OfficerConfigError(RuntimeError):
    """A required piece of configuration (gold DB connection info) is
    missing — a clear, loud error BEFORE any connection attempt (D10),
    instead of an obscure pyodbc failure with `SERVER=None`."""


def parse_recipients(raw: str) -> list[str]:
    """Comma/semicolon-separated, trimmed, de-duplicated (case-insensitive),
    basic email-shape checked. An entry that fails the shape check is
    dropped with a WARNING (never crashes the parse — one bad entry must not
    take the whole run down)."""
    if not raw:
        return []
    seen: set[str] = set()
    out: list[str] = []
    for part in re.split(r"[,;]", raw):
        addr = part.strip()
        if not addr:
            continue
        key = addr.lower()
        if key in seen:
            continue
        if not _EMAIL_RE.match(addr):
            logger.warning("officer_review: OFFICER_REVIEW_RECIPIENTS entry does not look like an email — dropped")
            continue
        seen.add(key)
        out.append(addr)
    return out


def _ensure_gold_configured(settings: Settings) -> None:
    if not settings.gold_sql_server or not settings.gold_sql_database:
        raise OfficerConfigError(
            "GOLD_SQL_SERVER / GOLD_SQL_DATABASE are not configured — cannot read gold.fact_gl_trans"
        )


def _build_and_reconcile(fabric_conn, gold_conn, planning_year: int, settings: Settings) -> tuple[BuildResult, ReconcileResult]:
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
    except (notifications.NotificationError, TokenDecodeError) as exc:
        print(f"FAIL: Graph token/role check — {exc}")
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
    recipients: list[str], sleep: Callable[[float], None] = time.sleep,
    retry_delay_seconds: float = _DEFAULT_RETRY_DELAY_SECONDS,
) -> int:
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

    try:
        web_url = publish_officer_workbook(build.xlsx_bytes, planning_year=planning_year, settings=settings, sleep=sleep)
    except OfficerPublishError as exc:
        print(f"PUBLISH FAIL: {exc}")
        return 1
    print("PUBLISHED: file overwritten in SharePoint (officer review/)")
    logger.info("officer_review: published webUrl=%s", web_url)

    results = notify_officer_review(
        recipients, web_url=web_url, as_of=build.as_of, planning_year=planning_year,
        n_departments=build.n_departments, fy_total=build.grand_total_year,
        board_total=build.grand_board_total, sap_total=build.grand_sap_total,
        sap_watermark=build.sap_watermark, lines_per_topic=build.lines_per_topic,
        dry_run=False, settings=settings,
    )
    failed = [r for r in results if not r.sent]
    print(f"MAIL: sent={len(results) - len(failed)}/{len(results)} recipients")
    if failed:
        print("MAIL FAIL: at least one send did not succeed — file already published, re-run is idempotent")
        return 1

    print("MODE: REAL — published and mailed")
    return 0


def main() -> int:
    configure_logging()
    parser = argparse.ArgumentParser(description="Weekly officer-review workbook robot (PRD #34)")
    add_common_args(parser)
    parser.add_argument("--probe", action="store_true", help="read-only permission check only; no build, no write")
    parser.add_argument("--out", type=str, default=None, help="local path to also write the built xlsx bytes to (never passed in CI)")
    args = parser.parse_args()

    settings = get_settings()
    dry_run = is_dry_run(args)
    logger.info("starting officer_review fiscal_year=%s dry_run=%s probe=%s", args.fiscal_year, dry_run, args.probe)

    if args.probe:
        return run_probe(settings)

    recipients = parse_recipients(os.getenv("OFFICER_REVIEW_RECIPIENTS", ""))
    try:
        return run_build(
            planning_year=args.fiscal_year, dry_run=dry_run, settings=settings,
            out_path=args.out, recipients=recipients,
        )
    except Exception:  # noqa: BLE001 — unexpected exception -> loud, exit 2, never a silent partial run
        logger.exception("officer_review: unexpected exception")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
