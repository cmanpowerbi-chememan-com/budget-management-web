"""Live probe for all 6 notification types (A12) — exercises the exact
production path (`backend/app/notifications.py` -> Microsoft Graph sendMail)
to jakkaritw ONLY, so the `notifications_dry_run=false` code path is
verified against the real tenant before go-live.

Safety (same pattern as setup/send_signoff_email.py):
- Default run = PROBE (dry_run=True): builds + logs every payload, ZERO HTTP
  calls (`send_mail` makes no token fetch / no POST when dry_run=True).
  `--send` is required to actually deliver.
- Recipient AND every cc are hardcoded to jakkaritw@chememan.com for ALL 6
  types — never a real approver/filler/admin. Every notify_* function in
  notifications.py resolves its DB-backed recipient/cc through the SAME
  module-level function, `lookup_email_by_empcode` (`notify_turn`,
  `notify_turn_reminder`'s To; `_resolve_approver1_cc`'s cc used by
  `notify_reject`/`notify_approved`/`notify_step_overridden`;
  `notify_step_overridden`'s "next approver" display line) — stubbing that
  ONE function here is the single choke point that pins every resolved
  address to RECIPIENT (verified by reading notifications.py, 2026-08-01).
  `notify_deadline_reminder` takes no `conn` and does no DB lookup at all —
  its `filler_email`/`cc_emails` are supplied directly by the caller, so
  this script hardcodes both to RECIPIENT itself.
- Uses department "TEST-PROBE" + sentinel fiscal_year 2099 + a sentinel
  empcode (does not exist in dbo.v_employee_budget_01 — belt-and-braces
  even without the stub above) so every mail is unmistakably a test; the
  deep-link still renders exactly as production would build it.
- Does NOT touch `notifications_dry_run` in .env — dry_run is passed
  explicitly per call, in this process only.
- A post-call assertion aborts (non-zero exit, no further calls skipped
  since dry-run already made zero HTTP calls) if any resolved recipient
  ever drifts away from RECIPIENT — a safety net for catching a bug in
  THIS script during the probe run, before jakkaritw ever runs --send.

Run from repo root:
    python setup/probe_notifications_live.py           # probe, no sends
    python setup/probe_notifications_live.py --send    # real sends (6 mails, jakkaritw only)
"""
import argparse
import sys
from datetime import date
from pathlib import Path

# Windows console defaults to cp1252 which cannot encode Thai subjects/bodies.
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# Import the backend app package (backend/app/*) the same way pytest does.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from app import notifications  # noqa: E402
from app.config import get_settings  # noqa: E402
from app.db import get_fabric_conn  # noqa: E402

RECIPIENT = "jakkaritw@chememan.com"
PROBE_DEPT = "TEST-PROBE (ทดสอบระบบ)"
PROBE_DEPT_2 = "TEST-PROBE-2 (ทดสอบระบบ)"
PROBE_YEAR = 2099
PROBE_REASON = "นี่คืออีเมลทดสอบระบบ (probe) — ไม่ต้องดำเนินการใดๆ"
PROBE_EMPCODE = "TESTPROBE"  # sentinel — never resolves to a real employee


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--send", action="store_true", help="actually send the 6 emails (default: probe only)")
    args = parser.parse_args()
    dry_run = not args.send

    settings = get_settings()
    mode = "PROBE (no sends)" if dry_run else "REAL SEND"
    print(f"mode={mode} recipient={RECIPIENT} dept={PROBE_DEPT!r} year={PROBE_YEAR}")
    print("NOTE: deep-links use app_base_url =", settings.app_base_url)

    # Single choke point (see module docstring): every notify_* recipient/cc
    # lookup goes through this one function.
    notifications.lookup_email_by_empcode = lambda _conn, _empcode: RECIPIENT
    print("recipient/cc lookup (lookup_email_by_empcode) stubbed to jakkaritw for every call site")

    # Spy on the transport seam so we can report the actual `cc` each type
    # sent, without needing NotificationResult to carry one (it doesn't) —
    # still calls through to the real send_mail, so dry-run/--send behavior
    # is untouched.
    original_send_mail = notifications.send_mail
    captured: list[dict] = []

    def _spy_send_mail(to_email, subject, html_body, cc=None, **kwargs):
        captured.append({"to": to_email, "cc": cc})
        return original_send_mail(to_email, subject, html_body, cc, **kwargs)

    notifications.send_mail = _spy_send_mail

    with get_fabric_conn(settings) as conn:
        calls = [
            ("notify_turn (ถึงตา approver)", lambda: notifications.notify_turn(
                conn, department=PROBE_DEPT, fiscal_year=PROBE_YEAR,
                approver_empcode=PROBE_EMPCODE, submitter_email=RECIPIENT,
                dry_run=dry_run, settings=settings)),
            ("notify_reject (ตีกลับ)", lambda: notifications.notify_reject(
                conn, department=PROBE_DEPT, fiscal_year=PROBE_YEAR,
                submitter_email=RECIPIENT, reason=PROBE_REASON,
                approver1_empcode=PROBE_EMPCODE,
                dry_run=dry_run, settings=settings)),
            ("notify_approved (อนุมัติครบ)", lambda: notifications.notify_approved(
                conn, department=PROBE_DEPT, fiscal_year=PROBE_YEAR,
                submitter_email=RECIPIENT, approver1_empcode=PROBE_EMPCODE,
                dry_run=dry_run, settings=settings)),
            ("notify_step_overridden (ข้ามขั้นแทน)", lambda: notifications.notify_step_overridden(
                conn, department=PROBE_DEPT, fiscal_year=PROBE_YEAR,
                submitter_email=RECIPIENT, skipped_approver_empcode=PROBE_EMPCODE,
                admin_email=RECIPIENT, dry_run=dry_run, settings=settings,
                new_current_approver_empcode=PROBE_EMPCODE)),
            ("notify_deadline_reminder (เตือนยังไม่ส่ง)", lambda: notifications.notify_deadline_reminder(
                RECIPIENT, [PROBE_DEPT, PROBE_DEPT_2], PROBE_YEAR, date(PROBE_YEAR, 12, 31),
                cc_emails=[RECIPIENT], dry_run=dry_run, settings=settings)),
            ("notify_turn_reminder (เตือน approver)", lambda: notifications.notify_turn_reminder(
                conn, approver_empcode=PROBE_EMPCODE,
                items=[(PROBE_DEPT, PROBE_YEAR, 3), (PROBE_DEPT_2, PROBE_YEAR, 10)],
                dry_run=dry_run, settings=settings)),
        ]

        results = []
        for label, thunk in calls:
            captured.clear()
            r = thunk()
            cc_used = captured[0]["cc"] if captured else None
            results.append((label, r, cc_used))

    ok = True
    for label, r, cc_used in results:
        if r is None:
            print(f"FAIL {label}: returned None (recipient not resolved)")
            ok = False
            continue
        if r.to_email.lower() != RECIPIENT.lower():
            print(f"SAFETY ABORT {label}: resolved recipient {r.to_email!r} is NOT {RECIPIENT!r}")
            ok = False
            continue
        status = "sent" if r.sent else ("dry-run OK" if r.dry_run else "NOT SENT")
        print(f"{label}: {status} | to={r.to_email} | cc={cc_used} | subject={r.subject!r} | detail={r.detail}")
        if not dry_run and not r.sent:
            ok = False

    if dry_run:
        print("\nprobe complete — re-run with --send to deliver the 6 emails (jakkaritw only)")
    elif ok:
        print("\nall 6 sent — check jakkaritw@chememan.com inbox (and Sent Items)")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
