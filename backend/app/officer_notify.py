"""Officer-review notifier — Module 3 of PRD #34 (issue #34).

`notifications.py` is on the hard-constraint zero-edit list, so the Thai
HTML body for this mail is built HERE, not as a new `notify_officer_review`
inside `notifications.py`. This module imports `notifications`' private
layout helpers (`_wrap` / `_lead_p` / `_lead_link_p` / `_label_value_table`)
READ-ONLY — same visual house style as every other notification — and calls
`app.notifications.send_mail`, the ONE transport seam, exactly like every
existing `notify_*` function does. `html.escape` is applied to every
interpolated value (the webUrl included — `notifications.py`'s own bodies
are not escaped, so this module cannot assume the seam does it)."""
import html
import logging
from datetime import date, datetime
from decimal import Decimal

import httpx

from app import notifications
from app.config import Settings, get_settings
from app.notifications import NotificationResult, send_mail

logger = logging.getLogger(__name__)


def _fmt_money(value: float) -> str:
    return f"{Decimal(str(round(float(value), 2))):,.2f}"


def build_subject(planning_year: int, as_of: datetime) -> str:
    return f"[Budget] ไฟล์ตรวจงบประมาณ FY{planning_year} สำหรับฝ่ายงบประมาณ — ข้อมูล ณ {as_of:%d/%m/%Y %H:%M}"


def build_body_html(
    *,
    web_url: str,
    as_of: datetime,
    planning_year: int,
    n_departments: int,
    fy_total: float,
    board_total: float,
    sap_total: float,
    sap_watermark: date | None,
    lines_per_topic: dict[str, int],
) -> str:
    board_year = planning_year - 1
    safe_url = html.escape(web_url, quote=True)
    wm_text = sap_watermark.strftime("%d/%m/%Y") if sap_watermark else "ไม่ทราบ"

    rows: list[tuple[str, str, str | None]] = [
        ("ปีงบประมาณ", html.escape(f"FY{planning_year}"), None),
        ("ข้อมูล ณ", html.escape(f"{as_of:%d/%m/%Y %H:%M}"), None),
        ("จำนวนฝ่ายในขอบเขต", html.escape(str(n_departments)), None),
        (f"รวมปี {planning_year}", html.escape(_fmt_money(fy_total)), None),
        (f"งบอนุมัติ {board_year}", html.escape(_fmt_money(board_total)), None),
        (f"ใช้จริง SAP {board_year} (YTD ณ {html.escape(wm_text)})", html.escape(_fmt_money(sap_total)), None),
    ]
    for group, n in lines_per_topic.items():
        rows.append((html.escape(group), f"{n} รายการ", None))

    content = (
        notifications._lead_p("ไฟล์ตรวจงบประมาณประจำสัปดาห์พร้อมแล้วครับ")
        + notifications._lead_link_p(safe_url, "เปิดไฟล์ใน SharePoint")
        + notifications._label_value_table(rows)
    )
    return notifications._wrap(content)


def notify_officer_review(
    recipients: list[str],
    *,
    web_url: str,
    as_of: datetime,
    planning_year: int,
    n_departments: int,
    fy_total: float,
    board_total: float,
    sap_total: float,
    sap_watermark: date | None,
    lines_per_topic: dict[str, int],
    dry_run: bool,
    settings: Settings | None = None,
) -> list[NotificationResult]:
    """ONE `send_mail` call for the whole recipient list (2026-09-25: was one
    call per recipient) — To = `recipients[0]`, cc = the rest, deduplicated
    case-insensitively and with the To address itself excluded from cc.
    `recipients` is already validated/deduplicated by the caller
    (`jobs.officer_review.parse_recipients`); this function dedupes again
    defensively so a future caller change can never put the same address in
    both To and cc. Returns a single-element list so the caller's existing
    `[r for r in results if not r.sent]` shape keeps working unchanged.

    `send_mail`'s `cc` argument is dropped entirely (not just filtered) when
    `Settings.notifications_redirect_all_to` is set (`app.notifications`,
    zero-edit) — non-prod environments running with that redirect only ever
    see the To address, never the cc list. That is the existing redirect
    behaviour for every notifier in this codebase, not something new here.

    A `NotificationError` (from `send_mail` itself), a raw `httpx.HTTPError`
    (a transport failure `send_mail` can let escape), a bare `ValueError`
    (e.g. a non-finite `Retry-After` header) or an `OverflowError` (an
    absurdly large `Retry-After` reaching `time.sleep`) all make this ONE
    call fail — with a single combined mail there is no "other recipients"
    to keep trying, so the caller (`jobs.officer_review.run_build`) treats
    any `sent=False` on a REAL run as a job FAIL: the file is already
    published at that point, but a re-run is idempotent (the same file is
    simply overwritten again next time). Recipient addresses are never
    logged here — only the count, by the caller."""
    settings = settings or get_settings()
    subject = build_subject(planning_year, as_of)
    body = build_body_html(
        web_url=web_url, as_of=as_of, planning_year=planning_year, n_departments=n_departments,
        fy_total=fy_total, board_total=board_total, sap_total=sap_total, sap_watermark=sap_watermark,
        lines_per_topic=lines_per_topic,
    )
    if not recipients:
        return []
    to_email = recipients[0]
    seen = {to_email.lower()}
    cc: list[str] = []
    for addr in recipients[1:]:
        key = addr.lower()
        if key in seen:
            continue
        seen.add(key)
        cc.append(addr)
    try:
        result = send_mail(to_email, subject, body, cc=cc or None, dry_run=dry_run, settings=settings)
    except (notifications.NotificationError, httpx.HTTPError, ValueError, OverflowError) as exc:
        logger.warning("officer_notify: send failed (%s)", type(exc).__name__)
        result = NotificationResult(sent=False, to_email=to_email, subject=subject, dry_run=dry_run, detail=type(exc).__name__)
    return [result]
