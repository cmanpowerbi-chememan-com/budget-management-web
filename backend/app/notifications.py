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
import time
from dataclasses import dataclass
from datetime import date, datetime
from typing import Callable
from urllib.parse import quote
from zoneinfo import ZoneInfo

import httpx
import pyodbc

from app.config import Settings, get_settings

logger = logging.getLogger(__name__)

GRAPH_BASE = "https://graph.microsoft.com/v1.0"
# Fallback sender only — the real value is `Settings.notifications_sender_email`
# (default `cmanpowerbi@chememan.com`, the shared Power-BI/reporting mailbox
# jakkaritw picked 2026-08-02 so app mail is not "from Jakkaritw" and replies
# do not land in a personal inbox). Mail.Send is an APPLICATION role, so the
# SP can send as any mailbox; sending as cmanpowerbi verified 202 on
# 2026-08-02. Kept as a module constant for the no-settings call path.
SENDER_EMAIL = "cmanpowerbi@chememan.com"


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
    # §7.3: how many RETRY attempts this send needed (0 = first try). The
    # reminder job aggregates this into its per-phase `retried=N` summary.
    retries: int = 0


def build_deep_link(department: str, fiscal_year: int, settings: Settings | None = None) -> str:
    """`?dept=<url-encoded ฝ่าย>&year=<label_year>` (ADR-0016) — convenience
    only, access is still enforced server-side on click. `fiscal_year` here
    stays the PLANNING year (unchanged contract, same as every other
    argument named `fiscal_year` in this module) — callers do NOT change.
    The emitted URL's `year` carries the LABEL year (`fiscal_year - 1`)
    instead, matching what the YearPicker actually DISPLAYS
    (`frontend/src/grid/YearPicker.tsx`: label = value - 1) so a
    hand-typed/clicked `?year=` lands on the same grid view as the
    dropdown option with that label. Inverse of
    `frontend/src/filters/deepLink.ts` `parseYear` (label + 1 = planning) —
    round-trip: planning P -> this emits `year=P-1` -> `parseDeepLink`
    returns `{ year: P }` again. `quote(..., safe="")` encodes Thai,
    spaces, AND a literal `/` in a department name (e.g.
    `บัญชี/การเงิน` -> `%2F`), matching the ADR's explicit example."""
    settings = settings or get_settings()
    base = settings.app_base_url.rstrip("/")
    label_year = fiscal_year - 1
    return f"{base}/?dept={quote(department, safe='')}&year={label_year}"


def _year_phrase(fiscal_year: int) -> str:
    """Human-readable year mention for subject/body text (gate residual,
    2026-07-23): always shows the planning year AND the on-screen label
    year (`fiscal_year - 1`, `frontend/src/grid/YearPicker.tsx`) side by
    side so a recipient reading the email never sees a different year than
    the YearPicker they land on. Used by the BODY of every notify_* builder
    (subjects carry the planning year only, 2026-07-28 user-requested
    format) so the wording can't drift between mail types. Does NOT touch
    `build_deep_link` / the URL — text only."""
    return f"ปีงบประมาณ {fiscal_year} (หน้าจอ: Year {fiscal_year - 1})"


# --- HTML template (2026-07-28, styled after the Contract Management sample) ---
# Inline styles only — email clients strip <style>/<head>. Font stack favors
# Segoe UI / Leelawadee UI (both ship with Windows + render Thai cleanly).
_FONT_WRAP = "font-family:'Segoe UI','Leelawadee UI',Tahoma,sans-serif;font-size:14px;color:#333333;line-height:1.6;"
_HL_BLUE = "color:#2E74B5;font-weight:bold;"
_HL_RED = "color:#C55A11;font-weight:bold;"


def _hl(text: str) -> str:
    """Blue bold highlight — department names, key values (sample's blue)."""
    return f'<span style="{_HL_BLUE}">{text}</span>'


def _hl_red(text: str) -> str:
    """Red-orange bold highlight — deadlines / things needing action (sample's red date)."""
    return f'<span style="{_HL_RED}">{text}</span>'


def _wrap(content_html: str) -> str:
    """One shared envelope: font wrapper + signature, so every mail type
    looks identical in structure (sample: 'Best Regards,' + bold team name)."""
    return (
        f'<div style="{_FONT_WRAP}">'
        f"{content_html}"
        '<p style="margin-top:24px;">Best Regards,<br><b>Budget Management Team</b></p>'
        "</div>"
    )


# --- Shared table styles (Contract Management sample's label/value table) ---
_TD = "padding:8px 12px;border-bottom:1px solid #E5E7EB;"
_LABEL_TD = f"{_TD}color:#6B7280;font-weight:bold;"
# Highlight-row variants: 'red' = needs action (sample's Expired Date row),
# 'green' = good news (fully approved).
_HIGHLIGHT_ROW = {
    "red": ("background:#FDECEA;", _HL_RED),
    "green": ("background:#E8F5E9;", "color:#2E7D32;font-weight:bold;"),
}


def _label_value_table(rows: list[tuple[str, str, str | None]]) -> str:
    """Label/value detail table like the sample: gray bold label column,
    zebra rows, one optional highlight row ('red'/'green'). Each row is
    (label, value_html, variant)."""
    trs = []
    for i, (label, value_html, variant) in enumerate(rows):
        if variant:
            bg, value_style = _HIGHLIGHT_ROW[variant]
            trs.append(
                f'<tr style="{bg}">'
                f'<td style="{_LABEL_TD}">{label}</td>'
                f'<td style="{_TD}{value_style}">{value_html}</td>'
                "</tr>"
            )
        else:
            trs.append(
                f'<tr style="background:{"#FFFFFF" if i % 2 == 0 else "#F5F7FA"};">'
                f'<td style="{_LABEL_TD}">{label}</td>'
                f'<td style="{_TD}">{value_html}</td>'
                "</tr>"
            )
    return (
        '<table style="border-collapse:collapse;width:100%;max-width:640px;'
        'border:1px solid #E5E7EB;">'
        f"{''.join(trs)}</table>"
    )


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


# §7.3.1 bulk-send hardening: client-credentials tokens live ~1h, but a
# reminder round used to fetch one PER MAIL (99–367 token requests/round).
# Cache the token module-level with its expiry, refreshing when <60s remain.
_GRAPH_TOKEN_TTL_SECONDS = 3600
_TOKEN_EXPIRY_MARGIN_SECONDS = 60
_token_cache: dict = {"token": None, "expires_at": 0.0}


def _reset_graph_token_cache() -> None:
    """Test hook — module state must never leak between tests (a cached
    token from one test would silently skip the token POST another counts)."""
    _token_cache["token"] = None
    _token_cache["expires_at"] = 0.0


def _get_graph_token_cached(settings: Settings) -> str:
    now = time.time()
    cached = _token_cache["token"]
    if cached is not None and now < _token_cache["expires_at"] - _TOKEN_EXPIRY_MARGIN_SECONDS:
        return cached
    token = _get_graph_token(settings)
    _token_cache["token"] = token
    _token_cache["expires_at"] = now + _GRAPH_TOKEN_TTL_SECONDS
    return token


# §7.3.3 retry policy: ONLY transient throttling statuses are retried;
# anything else fails immediately (a 400 won't heal by waiting).
_RETRYABLE_STATUSES = {429, 503, 504}
_RETRY_BACKOFF_SECONDS = (2, 8, 30)  # per retry attempt; 3 attempts total = initial + 2 retries
_MAX_SEND_ATTEMPTS = 3


def _post_send_mail(
    token: str, to_email: str, subject: str, html_body: str, cc: list[str] | None = None,
    *, sleep: Callable[[float], None] = time.sleep, sender: str = SENDER_EMAIL,
) -> int:
    """POST sendMail, retrying transient throttling (429/503/504) up to
    `_MAX_SEND_ATTEMPTS` total attempts — honoring the `Retry-After` header
    when present, else the 2s/8s backoff ladder. Returns the number of
    retries used (0 = first try). All-attempts-failed raises the same
    NotificationError as any other failure, so the caller's per-recipient
    isolation treats it as failed and never writes reminder_log (§7.3.3).
    `sleep` is injectable so tests never really wait."""
    message = {
        "message": {
            "subject": subject,
            "body": {"contentType": "HTML", "content": html_body},
            "toRecipients": [{"emailAddress": {"address": to_email}}],
        },
        "saveToSentItems": True,
    }
    if cc:
        # Key ABSENT (not an empty array) when there is no cc — 2026-07-31
        # revamp: reject/final-approve cc the frozen approver1, deadline
        # reminders cc the derived approver1; everything else stays To-only.
        message["message"]["ccRecipients"] = [{"emailAddress": {"address": addr}} for addr in cc]
    for attempt in range(_MAX_SEND_ATTEMPTS):
        resp = httpx.post(
            f"{GRAPH_BASE}/users/{sender}/sendMail",
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            json=message,
            timeout=30,
        )
        if resp.status_code == 202:
            return attempt
        if resp.status_code in _RETRYABLE_STATUSES and attempt < _MAX_SEND_ATTEMPTS - 1:
            retry_after = resp.headers.get("Retry-After")
            try:
                delay = float(retry_after) if retry_after is not None else _RETRY_BACKOFF_SECONDS[attempt]
            except (TypeError, ValueError):
                delay = _RETRY_BACKOFF_SECONDS[attempt]
            logger.warning(
                "notifications: sendMail throttled status=%s to=%s (attempt %d/%d) — retrying in %ss",
                resp.status_code, to_email, attempt + 1, _MAX_SEND_ATTEMPTS, delay,
            )
            sleep(delay)
            continue
        raise NotificationError(f"Graph sendMail failed: {resp.status_code} {resp.text}")
    raise NotificationError("Graph sendMail failed: exhausted attempts")  # unreachable, defensive


def send_mail(
    to_email: str, subject: str, html_body: str, cc: list[str] | None = None,
    *, dry_run: bool, settings: Settings | None = None, sleep: Callable[[float], None] = time.sleep,
) -> NotificationResult:
    """The ONE transport seam. `dry_run=True`: construct + log the payload,
    ZERO HTTP calls. `dry_run=False`: fetch a Graph token (module-level
    cached, §7.3.1) then POST sendMail (with 429/503/504 retry, §7.3.3) —
    both calls go through `httpx.post` (the seam every test in this module
    monkeypatches). `cc` is an optional list of cc addresses (2026-07-31
    revamp) — falsy/empty means the payload carries no ccRecipients key at
    all. `sleep` is injectable so retry tests never really wait."""
    if not to_email:
        logger.warning("notifications: no recipient email resolved, subject=%r — skipping", subject)
        return NotificationResult(sent=False, to_email="", subject=subject, dry_run=dry_run, detail="no recipient")

    if dry_run:
        logger.info(
            "notifications[DRY-RUN]: to=%s cc=%s subject=%r body_len=%d", to_email, cc or [], subject, len(html_body)
        )
        return NotificationResult(sent=False, to_email=to_email, subject=subject, dry_run=True, detail="dry_run")

    settings = settings or get_settings()
    token = _get_graph_token_cached(settings)
    retries = _post_send_mail(
        token, to_email, subject, html_body, cc, sleep=sleep,
        sender=settings.notifications_sender_email,
    )
    logger.info("notifications: sent to=%s cc=%s subject=%r retries=%d", to_email, cc or [], subject, retries)
    return NotificationResult(sent=True, to_email=to_email, subject=subject, dry_run=False, retries=retries)


def lookup_email_by_empcode(conn: pyodbc.Connection, empcode: str | None) -> str | None:
    """Reverse of `app.approval.resolve_submitter` (email -> empcode) — here
    empcode -> email, against the same confirmed source
    `dbo.v_employee_budget_01` (spec §1b). Public since the 2026-07-31
    revamp: `jobs/send_reminders.py` also resolves empcode -> email for the
    deadline-reminder cc (derived approver1)."""
    if not empcode:
        return None
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT email FROM dbo.v_employee_budget_01 WHERE employee_code = ?", empcode)
        row = cursor.fetchone()
    finally:
        cursor.close()
    return row[0] if row else None


def _resolve_approver1_cc(conn: pyodbc.Connection, to_email: str, approver1_empcode: str | None) -> list[str] | None:
    """2026-07-31 revamp cc rule (plan §3.1): reject + final-approve mails
    cc the FROZEN approver1. Returns None (no cc) when the empcode is blank,
    the lookup finds no email, or the resolved cc IS the To address (a
    duplicate mail to the same person). A lookup FAILURE is swallowed —
    loudly logged — so a broken cc lookup can never block the main To send."""
    if not approver1_empcode:
        return None
    try:
        cc_email = lookup_email_by_empcode(conn, approver1_empcode)
    except Exception:
        logger.warning(
            "notifications: cc lookup failed for approver1 empcode=%r — sending To=%s without cc",
            approver1_empcode, to_email,
        )
        return None
    if not cc_email or cc_email.lower() == to_email.lower():
        return None
    return [cc_email]


def notify_turn(
    conn: pyodbc.Connection, *, department: str, fiscal_year: int, approver_empcode: str | None,
    submitter_email: str | None, dry_run: bool, settings: Settings | None = None,
    reminder: bool = False, days_pending: int | None = None,
) -> NotificationResult | None:
    """Turn-notify: a department just landed on an approver's step (initial
    submit -> approver1's turn; each approve -> the next approver's turn;
    also used by the A11 auto_submit job for the same "landed on a step"
    event). Returns None (no send attempted) when the approver's email
    cannot be resolved — logged, never raised, so a missing employee-master
    row never blocks the caller.

    `reminder=True` (2026-07-31 revamp, jobs/send_reminders Phase A): the
    7-day repeat nudge for a turn that has sat unactioned — same mail with
    a "[เตือน]" subject prefix and an extra body line stating the turn has
    been pending `days_pending` days, so the repeat is visibly a reminder,
    not a confusing duplicate of the original turn mail."""
    to_email = lookup_email_by_empcode(conn, approver_empcode)
    if not to_email:
        logger.warning(
            "notify_turn: no email resolved for empcode=%r, department=%r/%s — skipped",
            approver_empcode, department, fiscal_year,
        )
        return None
    link = build_deep_link(department, fiscal_year, settings)
    subject = f"รอการอนุมัติ งบประมาณของฝ่าย {department} ปีงบประมาณ {fiscal_year}"
    pending_line = ""
    if reminder:
        subject = f"[เตือน] {subject}"
        if days_pending is not None:
            pending_line = f"<p>งบประมาณนี้{_hl_red(f'ค้างการอนุมัติมาแล้ว {days_pending} วัน')} กรุณาดำเนินการ</p>"
    body = _wrap(
        "<p>เรียน ผู้อนุมัติ</p>"
        "<p>มีงบประมาณรอการอนุมัติจากท่าน รายละเอียดดังนี้:</p>"
        + _label_value_table([
            ("ฝ่าย", _hl(department), None),
            ("ปีงบประมาณ", _year_phrase(fiscal_year), None),
            ("ผู้ส่ง", submitter_email or "-", None),
            ("สถานะ", "รอการอนุมัติจากท่าน", "red"),
        ])
        + pending_line
        + f'<p><a href="{link}">คลิกที่นี่เพื่อตรวจสอบและอนุมัติ</a></p>'
    )
    return send_mail(to_email, subject, body, dry_run=dry_run, settings=settings)


def notify_reject(
    conn: pyodbc.Connection, *, department: str, fiscal_year: int, submitter_email: str | None, reason: str,
    approver1_empcode: str | None, dry_run: bool, settings: Settings | None = None,
) -> NotificationResult | None:
    """Reject-notify: To the LAST SUBMITTER (ADR-0008) — `submitter_email`
    is the value already frozen on the `approval_status` row at submit time,
    so the main recipient needs NO extra DB lookup and can never point at a
    stale/renamed employee-master row. 2026-07-31 revamp: cc the frozen
    `approver1_empcode` (every layer uses this one function) — resolution
    failure only ever drops the cc, never the To send."""
    if not submitter_email:
        logger.warning("notify_reject: no submitter_email for department=%r/%s — skipped", department, fiscal_year)
        return None
    cc = _resolve_approver1_cc(conn, submitter_email, approver1_empcode)
    link = build_deep_link(department, fiscal_year, settings)
    subject = f"ถูกตีกลับ งบประมาณของฝ่าย {department} ปีงบประมาณ {fiscal_year}"
    body = _wrap(
        "<p>เรียน ผู้ส่งงบประมาณ</p>"
        "<p>งบประมาณของท่านถูกตีกลับ รายละเอียดดังนี้:</p>"
        + _label_value_table([
            ("ฝ่าย", _hl(department), None),
            ("ปีงบประมาณ", _year_phrase(fiscal_year), None),
            ("สถานะ", "ถูกตีกลับ", "red"),
            ("เหตุผล", reason, None),
        ])
        + f'<p><a href="{link}">คลิกที่นี่เพื่อแก้ไขและส่งใหม่</a></p>'
    )
    return send_mail(submitter_email, subject, body, cc=cc, dry_run=dry_run, settings=settings)


def notify_approved(
    conn: pyodbc.Connection, *, department: str, fiscal_year: int, submitter_email: str | None,
    approver1_empcode: str | None, dry_run: bool, settings: Settings | None = None,
) -> NotificationResult | None:
    """Approved-notify: fires once, when the LAST step of the normal
    approval chain lands the department on APPROVED (there is no next
    approver left to `notify_turn`). Recipient is `submitter_email`, the
    same frozen value `notify_reject` uses — no DB lookup needed. 2026-07-31
    revamp: cc the frozen `approver1_empcode` so the first approver sees the
    chain completed. Never fired for the admin-direct-approve branches
    (ADMIN_SUBMIT/ADMIN_OVERRIDE_*) — those go through `submit_department`,
    not the `approve` action this is gated on (router decision)."""
    if not submitter_email:
        logger.warning("notify_approved: no submitter_email for department=%r/%s — skipped", department, fiscal_year)
        return None
    cc = _resolve_approver1_cc(conn, submitter_email, approver1_empcode)
    link = build_deep_link(department, fiscal_year, settings)
    subject = f"ได้รับการอนุมัติ งบประมาณของฝ่าย {department} ปีงบประมาณ {fiscal_year}"
    body = _wrap(
        "<p>เรียน ผู้ส่งงบประมาณ</p>"
        "<p>งบประมาณของท่านได้รับการอนุมัติครบทุกขั้นแล้ว รายละเอียดดังนี้:</p>"
        + _label_value_table([
            ("ฝ่าย", _hl(department), None),
            ("ปีงบประมาณ", _year_phrase(fiscal_year), None),
            ("สถานะ", "อนุมัติครบทุกขั้นแล้ว", "green"),
        ])
        + f'<p><a href="{link}">คลิกที่นี่เพื่อดูรายละเอียด</a></p>'
    )
    return send_mail(submitter_email, subject, body, cc=cc, dry_run=dry_run, settings=settings)


def notify_step_overridden(
    conn: pyodbc.Connection, *, department: str, fiscal_year: int, submitter_email: str | None,
    skipped_approver_empcode: str | None, admin_email: str, dry_run: bool,
    settings: Settings | None = None, new_current_approver_empcode: str | None = None,
) -> NotificationResult | None:
    """6th notification (ADR-0027): fires the moment an admin step-override
    advances a stuck position-1 step — To the ฝ่าย's frozen `submitter_email`
    (same source `notify_approved` uses, no extra lookup), cc the SKIPPED
    approver, resolved from `skipped_approver_empcode` via
    `lookup_email_by_empcode` with `_resolve_approver1_cc`'s skip rules (no
    cc when the empcode is blank, the lookup finds nothing, or cc == To; a
    cc lookup failure is swallowed and only ever drops the cc, never the To
    send). `new_current_approver_empcode` (the approver the step just landed
    on, from the router's post-transition state) only feeds the body's
    สถานะปัจจุบัน row. No monthly digest — this immediate mail is the one
    and only override notification; the next approver ALSO still gets their
    normal `notify_turn` mail (router wiring), so an override sends exactly
    two mails."""
    if not submitter_email:
        logger.warning(
            "notify_step_overridden: no submitter_email for department=%r/%s — skipped", department, fiscal_year
        )
        return None
    cc = _resolve_approver1_cc(conn, submitter_email, skipped_approver_empcode)
    skipped_display = cc[0] if cc else (skipped_approver_empcode or "-")
    waiting_display = "-"
    if new_current_approver_empcode:
        # Review fix: this lookup feeds ONLY the cosmetic สถานะปัจจุบัน row —
        # same posture as `_resolve_approver1_cc` just above, a display-only
        # query must never abort the functional To send. Guarded the same
        # way: log a warning and fall back to the raw empcode.
        try:
            next_email = lookup_email_by_empcode(conn, new_current_approver_empcode)
        except Exception:
            logger.warning(
                "notify_step_overridden: next-approver email lookup failed for empcode=%r — "
                "falling back to the empcode in the body", new_current_approver_empcode,
            )
            next_email = None
        waiting_display = f"รอการอนุมัติจาก {next_email or new_current_approver_empcode}"
    now_str = datetime.now(ZoneInfo("Asia/Bangkok")).strftime("%d/%m/%Y %H:%M")
    link = build_deep_link(department, fiscal_year, settings)
    subject = f"ดำเนินการแทนผู้อนุมัติ งบประมาณของฝ่าย {department} ปีงบประมาณ {fiscal_year}"
    body = _wrap(
        "<p>เรียน ผู้ส่งงบประมาณ</p>"
        "<p>ผู้ดูแลระบบได้ดำเนินการอนุมัติแทนผู้อนุมัติขั้นที่ 1 ให้งบประมาณของท่านแล้ว รายละเอียดดังนี้:</p>"
        + _label_value_table([
            ("ฝ่าย", _hl(department), None),
            ("ปีงบประมาณ", _year_phrase(fiscal_year), None),
            ("ผู้อนุมัติที่ถูกข้าม", skipped_display, None),
            ("ผู้ดำเนินการแทน", admin_email, None),
            ("วันเวลา", now_str, None),
            ("สถานะปัจจุบัน", waiting_display, None),
        ])
        + f'<p><a href="{link}">คลิกที่นี่เพื่อดูรายละเอียด</a></p>'
    )
    return send_mail(submitter_email, subject, body, cc=cc, dry_run=dry_run, settings=settings)


def notify_deadline_reminder(
    filler_email: str, departments: list[str], fiscal_year: int, closing_date: date | None,
    cc_emails: list[str] | None = None, *, dry_run: bool, settings: Settings | None = None,
) -> NotificationResult | None:
    """Automation D, §7 rework (2026-07-31): ONE GROUPED email per FILLER
    listing every still-not-submitted department they owe — a 46-department
    filler gets 1 mail, not 46. Each row keeps its own per-department deep
    link (ADR-0016, the one thing worth keeping from the per-ฝ่าย design).
    A single-department filler gets the SAME template — no special branch.
    `cc_emails` arrives already resolved by the caller (the filler's
    manager-derived approver1, ONE address) — this function only renders
    and sends."""
    if not filler_email or not departments:
        return None
    settings = settings or get_settings()
    # Table layout (styled after the Contract Management sample's detail
    # table): gray bold label header, zebra rows, one department per row.
    header = (
        '<tr style="background:#F5F7FA;">'
        f'<td style="{_LABEL_TD}">ฝ่าย</td>'
        f'<td style="{_LABEL_TD}">ปีงบประมาณ</td>'
        f'<td style="{_TD}"></td>'
        "</tr>"
    )
    rows = "".join(
        f'<tr style="background:{"#FFFFFF" if i % 2 == 0 else "#F5F7FA"};">'
        f'<td style="{_TD}">{_hl(dept)}</td>'
        f'<td style="{_TD}">{_year_phrase(fiscal_year)}</td>'
        f'<td style="{_TD}"><a href="{build_deep_link(dept, fiscal_year, settings)}">กรอกงบประมาณ</a></td>'
        "</tr>"
        for i, dept in enumerate(departments)
    )
    table = (
        '<table style="border-collapse:collapse;width:100%;max-width:640px;'
        'border:1px solid #E5E7EB;">'
        f"{header}{rows}</table>"
    )
    closing_line = ""
    if closing_date is not None:
        closing_line = f"<p>กรุณาดำเนินการก่อนถึงกำหนดปิดรับ {_hl_red(closing_date.strftime('%d/%m/%Y'))}</p>"
    else:
        closing_line = "<p>กรุณาดำเนินการก่อนถึงกำหนดปิดรับ</p>"
    subject = f"แจ้งเตือน: ยังไม่ได้ส่งงบประมาณ {len(departments)} ฝ่าย ปีงบประมาณ {fiscal_year}"
    body = _wrap(
        "<p>เรียน ผู้กรอกงบประมาณ</p>"
        "<p>ฝ่ายที่ท่านรับผิดชอบยังไม่ได้ส่งงบประมาณ ดังนี้:</p>"
        f"{table}{closing_line}"
    )
    return send_mail(filler_email, subject, body, cc=cc_emails or None, dry_run=dry_run, settings=settings)


def notify_turn_reminder(
    conn: pyodbc.Connection, *, approver_empcode: str | None,
    items: list[tuple[str, int, int]], dry_run: bool, settings: Settings | None = None,
) -> NotificationResult | None:
    """§7 rework: the 7-day turn reminder, GROUPED — ONE email per approver
    listing every department currently waiting on them. `items` is
    `(department, fiscal_year, days_pending)` per row, each row carrying its
    own days-pending so a long-stuck department stands out from one that
    just landed. Returns None (no send attempted, no reminder_log row by
    the caller) when the approver's email cannot be resolved — same posture
    as `notify_turn`. No cc (turn mails stay To-only, §7.1)."""
    if not items:
        return None
    to_email = lookup_email_by_empcode(conn, approver_empcode)
    if not to_email:
        logger.warning(
            "notify_turn_reminder: no email resolved for empcode=%r (%d departments waiting) — skipped",
            approver_empcode, len(items),
        )
        return None
    settings = settings or get_settings()
    header = (
        '<tr style="background:#F5F7FA;">'
        f'<td style="{_LABEL_TD}">ฝ่าย</td>'
        f'<td style="{_LABEL_TD}">ปีงบประมาณ</td>'
        f'<td style="{_LABEL_TD}">ค้างมา</td>'
        f'<td style="{_TD}"></td>'
        "</tr>"
    )
    rows = "".join(
        f'<tr style="background:{"#FFFFFF" if i % 2 == 0 else "#F5F7FA"};">'
        f'<td style="{_TD}">{_hl(dept)}</td>'
        f'<td style="{_TD}">{_year_phrase(year)}</td>'
        f'<td style="{_TD}">{_hl_red(f"{days} วัน") if days >= 7 else f"{days} วัน"}</td>'
        f'<td style="{_TD}"><a href="{build_deep_link(dept, year, settings)}">ตรวจสอบและอนุมัติ</a></td>'
        "</tr>"
        for i, (dept, year, days) in enumerate(items)
    )
    table = (
        '<table style="border-collapse:collapse;width:100%;max-width:640px;'
        'border:1px solid #E5E7EB;">'
        f"{header}{rows}</table>"
    )
    subject = f"[เตือน] มีงบประมาณ {len(items)} ฝ่ายรอการอนุมัติจากท่าน"
    body = _wrap(
        "<p>เรียน ผู้อนุมัติ</p>"
        "<p>มีงบประมาณค้างรอการอนุมัติจากท่าน รายละเอียดดังนี้:</p>"
        f"{table}"
        "<p>กรุณาดำเนินการอนุมัติหรือตีกลับ เพื่อให้การจัดทำงบประมาณเป็นไปตามกำหนด</p>"
    )
    return send_mail(to_email, subject, body, dry_run=dry_run, settings=settings)
