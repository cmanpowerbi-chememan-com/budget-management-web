# 27. Manual admin step-override replaces the 30-day auto-escalation

Date: 2026-08-01
Status: Accepted
Supersedes: the **"approver valid but silent > 30 days → auto-escalate"** clause of
ADR-0006 (everything else in ADR-0006 — chain resolution, snapshot-at-submit, invalid-approver
fallback, self-skip/dedup, reject semantics, the state machine — stands unchanged)
Relates to: ADR-0008 (approval unit = ฝ่าย), ADR-0012 (admin overlay), ADR-0013 (only
submit/approve/reject move status), plan/email-notify-revamp.md (the 7-day reminder engine)
Amended 2026-09-30: Turn reminders skip the ฝ่าย of a **Muted สายงาน** — see "Amendment —
muted สายงาน get no reminders" at the end. "Turn reminders never stop" still holds for every
other ฝ่าย.

## Context

ADR-0006 gave a stuck approval an automatic remedy: once the current PENDING_* step had sat
unactioned for 30 days, a scheduled job (`jobs/auto_escalate.py`) marked that one step
approved on the system's behalf, advanced to the next approver, and logged `AUTO_ESCALATE`.
It never jumped to `APPROVED` — budget dept still reviewed.

Two things changed since that decision:

1. **A 7-day reminder engine now exists** (2026-07-31 email revamp). The current approver is
   nudged every 7 days for as long as the step sits unactioned. In June 2026 the only signal
   a stuck approval produced was silence, so an automatic remedy carried its weight; now the
   normal case is handled by visibility instead.
2. **jakkaritw's objection (grilling 2026-08-01)**: a *system* deciding that one person's
   review can be waived is the wrong default for a financial control, even though the step is
   only skipped and never finally approved. A person should make that call, on the record.

The blocker discovered while grilling: `approve_department` / `reject_department` authorize
strictly against the frozen occupant of the current step (`_authorize_current_step`), with
**no admin bypass anywhere**. So deleting auto-escalation without adding something would leave
a silent approver as a permanently stuck ฝ่าย — no product path out, only a manual DB edit,
against a hard 31 Oct cycle close.

## Decision

- **Delete the 30-day auto-escalation entirely** — the job, the `AUTO_ESCALATE` action, the
  `is_step_stale` threshold, and its step in the automations workflow. Not flag-gated, not
  dormant code: removed. `budget.approval_log` holds zero `AUTO_ESCALATE` rows (verified live
  2026-08-01, the whole log is empty), so there is no history to preserve.
- **Add a manual admin step-override.** An `ADMIN_EMAILS` admin may advance a stuck step
  without being its frozen approver.
  - **Advances exactly one step**, following the same active-position walk a real approve
    uses. It may **never** land `APPROVED` — the invariant ADR-0006 protected is unchanged,
    only its trigger moves from clock to human.
  - **Position 1 only.** Positions 2 and 3 are the budget-dept review itself
    (Nipaporn/Waraporn); allowing an admin to skip those would let a non-budget admin push a
    budget past the very review this rule exists to guarantee. Attempting it is an error, not
    a silent no-op.
  - **No waiting period and no mandatory reason.** Available the moment a ฝ่าย is
    `PENDING_APPROVER1`. Rationale: the audit trail (who, when, from→to) plus the mandatory
    notification below already answer "why did this happen", and a stale-time gate would block
    the genuinely urgent case (approver resigns today, cycle closes tomorrow).
  - **Logged as its own action** with the acting admin's real email — never a `system:` actor,
    which was correct for a job and would be a lie for a human click.
- **Notify immediately on override**: to the ฝ่าย's submitter, **cc the approver who was
  skipped**, at the moment of the click. Consistent with every other event mail in the system;
  no monthly digest exists anywhere and none is introduced.
- **Turn reminders never stop.** Every 7 days, for as long as the step is unactioned — no end
  date, no cc escalation, no cap. Explicitly chosen by jakkaritw over a "cc budget dept after
  28 days" variant.

## Consequences

- A stuck approval no longer resolves itself. The remedy is a human clicking a button, which
  means an unnoticed stuck ฝ่าย stays stuck: the reminder mail is the only automatic signal,
  and it targets the person who is already not responding. Accepted knowingly — the residual
  risk is "nobody looks", and the mitigation offered (cc budget dept after 4 rounds) was
  declined; the deferred "admin overdue/stuck approvals view" from ADR-0006 is the natural
  future fix if that risk materialises.
- The override is unbounded in time and unexplained by default. Auditors get *who / when /
  which step / notified whom*, not *why*.
- `_current_step_started_at` stays (the 7-day reminder cadence anchors on it); only
  `is_step_stale` and the 30-day threshold go. The reminder clock is now the only consumer of
  that anchor, so the "two clocks can never drift" concern from the email revamp disappears.
- Positions 2 and 3 have no override at all. If Nipaporn and Waraporn are both unavailable, a
  budget waits — deliberate: that is the review the whole control exists for.

## Amendment — muted สายงาน get no reminders (2026-09-30)

Turn reminders never stop — **except for a ฝ่าย whose สายงาน is muted**. On 2026-09-30, the
morning the first wave of Deadline reminders went out, the budget team asked to stop reminder
mail for สายงาน `Chief Commercial Officer` and `Commercial`. jakkaritw decided to mute BOTH
weekly mails for those สายงาน: the Deadline reminder to their Fillers and the Turn reminder to
their approvers, at every step — the budget-dept steps 2 and 3 included. The muted list is a
repo-level setting that holds until someone removes it; it is not tied to a fiscal year.

What does not change for a muted ฝ่าย: filling, saving, submitting, approving, rejecting and
the admin step-override all work as before, under the same deadline; every one-time event mail
still goes out (the "your turn" mail at submit and at each step, approved, rejected,
override); the approver's in-app pending badge still shows.

Consequence: the residual risk accepted above — "an unnoticed stuck ฝ่าย stays stuck" — is
larger for a muted ฝ่าย, because after the one-time "your turn" mail there is no automatic
signal at all. Accepted knowingly: the budget team chases muted สายงาน by hand, and the muted
list should be reviewed before each cycle's reminder window.
