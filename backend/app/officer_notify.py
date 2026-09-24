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
    """One `send_mail` call PER recipient — the seam supports exactly one To
    address (D12). The caller (`jobs.officer_review`) must treat ANY
    `sent=False` result on a REAL run as a job FAIL: the file is already
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
    return [send_mail(to, subject, body, dry_run=dry_run, settings=settings) for to in recipients]
