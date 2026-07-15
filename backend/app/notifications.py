"""Email notifications (A12) — Microsoft Graph `sendMail`, Thai subject/body,
convenience-only deep-links (ADR-0016). This module owns the ONE transport
seam (`send_mail`) every notify_* helper and job (`jobs/*.py`) calls through
— tests monkeypatch `httpx.post` here, never real network.

Safety (never-cut #1): `dry_run` is a REQUIRED keyword on every public
function — there is no silent default that could accidentally send mail.
Callers (the approval router, the scheduled jobs) read the actual default
from `Settings.notifications_dry_run` (True until jakkaritw flips it at
go-live, config.py). `dry_run=True` makes ZERO HTTP calls (no token fetch,
no sendMail POST) — only the payload is built and logged, so a notify
attempt can never leak a secret or hit the network by accident.

Sender / auth pattern proven in `setup/send_signoff_email.py` (CLAUDE.md
"Send Outlook Email from Scripts"): service principal `cman-fabric-write`
(client-credentials, `ENTRA_*`), `POST /users/{sender}/sendMail`,
202 = accepted. Uses `httpx` (already a backend dependency) instead of
`requests` (the script's library, not in `backend/requirements.txt`) so no
new dependency is introduced for this module.
"""
import logging
from dataclasses import dataclass
from urllib.parse import quote

import httpx
import pyodbc

from app.config import Settings, get_settings

logger = logging.getLogger(__name__)

GRAPH_BASE = "https://graph.microsoft.com/v1.0"
# Proven sender (CLAUDE.md "Send Outlook Email from Scripts") — the SP has
# Mail.Send tenant-wide via this mailbox, verified 2026-06-05.
SENDER_EMAIL = "jakkaritw@chememan.com"


class NotificationError(RuntimeError):
    """A real (non-dry-run) send failed at the token or sendMail step.
    Callers MUST catch this — a notification failure must never fail the
    underlying business action (approval transition, scheduled job)."""


@dataclass
class NotificationResult:
    sent: bool
    to_email: str
    subject: str
    dry_run: bool
    detail: str | None = None


def build_deep_link(department: str, fiscal_year: int, settings: Settings | None = None) -> str:
    """`?dept=<url-encoded ฝ่าย>&year=<fiscal_year>` (ADR-0016) — convenience
    only, access is still enforced server-side on click. `quote(..., safe="")`
    encodes Thai, spaces, AND a literal `/` in a department name (e.g.
    `บัญชี/การเงิน` -> `%2F`), matching the ADR's explicit example."""
    settings = settings or get_settings()
    base = settings.app_base_url.rstrip("/")
    return f"{base}/?dept={quote(department, safe='')}&year={fiscal_year}"


def _get_graph_token(settings: Settings) -> str:
    url = f"https://login.microsoftonline.com/{settings.entra_tenant_id}/oauth2/v2.0/token"
    data = {
        "client_id": settings.entra_client_id,
        "client_secret": settings.entra_client_secret,
        "scope": "https://graph.microsoft.com/.default",
        "grant_type": "client_credentials",
    }
    resp = httpx.post(url, data=data, timeout=30)
    if resp.status_code != 200:
        raise NotificationError(f"Graph token request failed: {resp.status_code} {resp.text}")
    return resp.json()["access_token"]


def _post_send_mail(token: str, to_email: str, subject: str, html_body: str) -> None:
    message = {
        "message": {
            "subject": subject,
            "body": {"contentType": "HTML", "content": html_body},
            "toRecipients": [{"emailAddress": {"address": to_email}}],
        },
        "saveToSentItems": True,
    }
    resp = httpx.post(
        f"{GRAPH_BASE}/users/{SENDER_EMAIL}/sendMail",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        json=message,
        timeout=30,
    )
    if resp.status_code != 202:
        raise NotificationError(f"Graph sendMail failed: {resp.status_code} {resp.text}")


def send_mail(
    to_email: str, subject: str, html_body: str, *, dry_run: bool, settings: Settings | None = None
) -> NotificationResult:
    """The ONE transport seam. `dry_run=True`: construct + log the payload,
    ZERO HTTP calls. `dry_run=False`: fetch a Graph token then POST
    sendMail — both calls go through `httpx.post` (the seam every test in
    this module monkeypatches)."""
    if not to_email:
        logger.warning("notifications: no recipient email resolved, subject=%r — skipping", subject)
        return NotificationResult(sent=False, to_email="", subject=subject, dry_run=dry_run, detail="no recipient")

    if dry_run:
        logger.info("notifications[DRY-RUN]: to=%s subject=%r body_len=%d", to_email, subject, len(html_body))
        return NotificationResult(sent=False, to_email=to_email, subject=subject, dry_run=True, detail="dry_run")

    settings = settings or get_settings()
    token = _get_graph_token(settings)
    _post_send_mail(token, to_email, subject, html_body)
    logger.info("notifications: sent to=%s subject=%r", to_email, subject)
    return NotificationResult(sent=True, to_email=to_email, subject=subject, dry_run=False)


def _lookup_email_by_empcode(conn: pyodbc.Connection, empcode: str | None) -> str | None:
    """Reverse of `app.approval.resolve_submitter` (email -> empcode) — here
    empcode -> email, against the same confirmed source
    `dbo.v_employee_budget_01` (spec §1b)."""
    if not empcode:
        return None
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT email FROM dbo.v_employee_budget_01 WHERE employee_code = ?", empcode)
        row = cursor.fetchone()
    finally:
        cursor.close()
    return row[0] if row else None


def notify_turn(
    conn: pyodbc.Connection, *, department: str, fiscal_year: int, approver_empcode: str | None,
    submitter_email: str | None, dry_run: bool, settings: Settings | None = None,
) -> NotificationResult | None:
    """Turn-notify: a department just landed on an approver's step (initial
    submit -> approver1's turn; each approve -> the next approver's turn;
    also used by the A11 auto_submit/auto_escalate jobs for the same
    "landed on a step" event). Returns None (no send attempted) when the
    approver's email cannot be resolved — logged, never raised, so a
    missing employee-master row never blocks the caller."""
    to_email = _lookup_email_by_empcode(conn, approver_empcode)
    if not to_email:
        logger.warning(
            "notify_turn: no email resolved for empcode=%r, department=%r/%s — skipped",
            approver_empcode, department, fiscal_year,
        )
        return None
    link = build_deep_link(department, fiscal_year, settings)
    subject = f"[Budget] รออนุมัติงบประมาณ ฝ่าย {department} ปี {fiscal_year}"
    body = (
        "<p>เรียน ผู้อนุมัติ</p>"
        f"<p>ฝ่าย <b>{department}</b> ปีงบประมาณ {fiscal_year} รอการอนุมัติจากท่าน "
        f"(ผู้ส่ง: {submitter_email or '-'})</p>"
        f'<p><a href="{link}">คลิกที่นี่เพื่อตรวจสอบและอนุมัติ</a></p>'
    )
    return send_mail(to_email, subject, body, dry_run=dry_run, settings=settings)


def notify_reject(
    *, department: str, fiscal_year: int, submitter_email: str | None, reason: str,
    dry_run: bool, settings: Settings | None = None,
) -> NotificationResult | None:
    """Reject-notify: the LAST SUBMITTER only (ADR-0008) — `submitter_email`
    is the value already frozen on the `approval_status` row at submit time,
    so this needs NO extra DB lookup and can never point at a stale/renamed
    employee-master row."""
    if not submitter_email:
        logger.warning("notify_reject: no submitter_email for department=%r/%s — skipped", department, fiscal_year)
        return None
    link = build_deep_link(department, fiscal_year, settings)
    subject = f"[Budget] งบประมาณ ฝ่าย {department} ปี {fiscal_year} ถูกตีกลับ"
    body = (
        "<p>เรียน ผู้ส่งงบประมาณ</p>"
        f"<p>ฝ่าย <b>{department}</b> ปีงบประมาณ {fiscal_year} ถูกตีกลับ พร้อมเหตุผล:</p>"
        f"<p>{reason}</p>"
        f'<p><a href="{link}">คลิกที่นี่เพื่อแก้ไขและส่งใหม่</a></p>'
    )
    return send_mail(submitter_email, subject, body, dry_run=dry_run, settings=settings)


def notify_approved(
    *, department: str, fiscal_year: int, submitter_email: str | None,
    dry_run: bool, settings: Settings | None = None,
) -> NotificationResult | None:
    """Approved-notify: fires once, when the LAST step of the normal
    approval chain lands the department on APPROVED (there is no next
    approver left to `notify_turn`). Recipient is `submitter_email`, the
    same frozen value `notify_reject` uses — no DB lookup needed. Never
    fired for the admin-direct-approve branches (ADMIN_SUBMIT/
    ADMIN_OVERRIDE_*) — those go through `submit_department`, not the
    `approve` action this is gated on (router decision)."""
    if not submitter_email:
        logger.warning("notify_approved: no submitter_email for department=%r/%s — skipped", department, fiscal_year)
        return None
    link = build_deep_link(department, fiscal_year, settings)
    subject = f"[Budget] งบประมาณของฝ่าย {department} ปี {fiscal_year} ได้รับการอนุมัติครบทุกขั้นแล้ว"
    body = (
        "<p>เรียน ผู้ส่งงบประมาณ</p>"
        f"<p>งบประมาณของฝ่าย <b>{department}</b> ปีงบประมาณ {fiscal_year} "
        "ได้รับการอนุมัติครบทุกขั้นแล้ว</p>"
        f'<p><a href="{link}">คลิกที่นี่เพื่อดูรายละเอียด</a></p>'
    )
    return send_mail(submitter_email, subject, body, dry_run=dry_run, settings=settings)


def notify_reminder(
    to_email: str, pending_departments: list[tuple[str, int]], *, dry_run: bool, settings: Settings | None = None,
) -> NotificationResult | None:
    """Automation D: ONE grouped email per Filler listing every still-not-
    submitted `(department, fiscal_year)` they Fill — the caller's discovery
    query already excludes anything submitted (spec: "submitted ones
    excluded"). Each department gets its own deep-link (the URL scheme
    carries exactly one department, ADR-0016 — a single combined link
    covering many departments is not representable)."""
    if not to_email or not pending_departments:
        return None
    settings = settings or get_settings()
    items = "".join(
        f'<li><b>{dept}</b> (ปี {year}) — '
        f'<a href="{build_deep_link(dept, year, settings)}">ไปกรอกงบประมาณ</a></li>'
        for dept, year in pending_departments
    )
    subject = "[Budget] แจ้งเตือน: ยังไม่ได้ส่งงบประมาณ"
    body = (
        "<p>เรียน ผู้กรอกงบประมาณ</p>"
        "<p>ฝ่ายที่ท่านรับผิดชอบยังไม่ได้ส่งงบประมาณ ดังนี้:</p>"
        f"<ul>{items}</ul>"
        "<p>กรุณาดำเนินการก่อนถึงกำหนดปิดรับ</p>"
    )
    return send_mail(to_email, subject, body, dry_run=dry_run, settings=settings)
