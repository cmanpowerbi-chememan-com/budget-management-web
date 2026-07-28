"""Live probe for the 4 notification types (A12) — sends REAL email through
the exact production path (`backend/app/notifications.py` -> Microsoft Graph
sendMail) to jakkaritw ONLY, so the `notifications_dry_run=false` code path
is verified against the real tenant before go-live.

Safety (same pattern as setup/send_signoff_email.py):
- Default run = PROBE (dry_run=True): builds + logs every payload, ZERO HTTP
  calls. `--send` is required to actually deliver.
- Recipient is hardcoded to jakkaritw@chememan.com for ALL 4 types — never a
  real approver/filler.
- Uses department "TEST-PROBE" + sentinel fiscal_year 2099 so every mail is
  unmistakably a test; the deep-link still renders exactly as production
  would build it.
- Does NOT touch `notifications_dry_run` in .env — dry_run is passed
  explicitly per call, in this process only.

Run from repo root:
    python setup/probe_notifications_live.py           # probe, no sends
    python setup/probe_notifications_live.py --send    # real sends (4 mails)
"""
import argparse
import sys
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
PROBE_YEAR = 2099
PROBE_REASON = "นี่คืออีเมลทดสอบระบบ (probe) — ไม่ต้องดำเนินการใดๆ"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--send", action="store_true", help="actually send the 4 emails (default: probe only)")
    args = parser.parse_args()
    dry_run = not args.send

    settings = get_settings()
    mode = "PROBE (no sends)" if dry_run else "REAL SEND"
    print(f"mode={mode} recipient={RECIPIENT} dept={PROBE_DEPT!r} year={PROBE_YEAR}")
    print("NOTE: deep-links use app_base_url =", settings.app_base_url)

    # notify_turn resolves the recipient via empcode -> dbo.v_employee_budget_01,
    # but jakkaritw is not in that view (he is admin, not an employee row), and
    # using a real employee's empcode would email THAT person. So ONLY the
    # recipient resolution is stubbed to RECIPIENT here; subject/body building
    # and the Graph transport stay 100% real (the lookup itself is covered by
    # test_notifications.py).
    notifications._lookup_email_by_empcode = lambda _conn, _empcode: RECIPIENT
    print("notify_turn: recipient lookup stubbed to jakkaritw (he is not in v_employee_budget_01)")

    with get_fabric_conn(settings) as conn:
        results = [
            ("notify_turn (ถึงตา approver)", notifications.notify_turn(
                conn, department=PROBE_DEPT, fiscal_year=PROBE_YEAR,
                approver_empcode="TESTPROBE", submitter_email=RECIPIENT,
                dry_run=dry_run, settings=settings)),
            ("notify_reject (ตีกลับ)", notifications.notify_reject(
                department=PROBE_DEPT, fiscal_year=PROBE_YEAR,
                submitter_email=RECIPIENT, reason=PROBE_REASON,
                dry_run=dry_run, settings=settings)),
            ("notify_approved (อนุมัติครบ)", notifications.notify_approved(
                department=PROBE_DEPT, fiscal_year=PROBE_YEAR,
                submitter_email=RECIPIENT,
                dry_run=dry_run, settings=settings)),
            ("notify_reminder (เตือนยังไม่ส่ง)", notifications.notify_reminder(
                RECIPIENT, [(PROBE_DEPT, PROBE_YEAR), ("TEST-PROBE-2 (ทดสอบระบบ)", PROBE_YEAR)],
                dry_run=dry_run, settings=settings)),
        ]

    ok = True
    for label, r in results:
        if r is None:
            print(f"FAIL {label}: returned None (recipient not resolved)")
            ok = False
            continue
        status = "sent" if r.sent else ("dry-run OK" if r.dry_run else "NOT SENT")
        print(f"{label}: {status} | to={r.to_email} | subject={r.subject!r} | detail={r.detail}")
        if not dry_run and not r.sent:
            ok = False

    if dry_run:
        print("\nprobe complete — re-run with --send to deliver the 4 emails")
    elif ok:
        print("\nall 4 sent — check jakkaritw@chememan.com inbox (and Sent Items)")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
